"""Endpoints de documentos — integração SAP DRC."""

import base64
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase import get_supabase_client
from middleware.lgpd import mask_cnpj
from middleware.security import verify_api_key
from models.schemas import (
    ConfirmarResponse,
    DocumentoOut,
    DocumentosResponse,
    RetroativoRequest,
    RetroativoResponse,
    RetroativoStatusResponse,
    SefazEndpointStatus,
    SefazStatusResponse,
)
from scheduler.polling_job import run_retroactive_job
from services.sefaz_client import sefaz_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/documentos", response_model=DocumentosResponse)
async def listar_documentos(
    cnpj: str = Query(..., min_length=14, max_length=14),
    tipo: str = Query("nfe", pattern=r"^(nfe|cte|mdfe)$"),
    desde: Optional[str] = Query(None, description="NSU a partir de"),
    incluir_pendentes: bool = Query(
        True,
        description="Incluir resumos pendentes de manifestação (modo manual)",
    ),
    auth: dict = Depends(verify_api_key),
):
    """Lista documentos para um CNPJ/tipo.

    Endpoint principal consumido pelo SAP DRC via RFC Destination HTTP.

    Retorna:
    - Documentos com XML completo (status=available)
    - Resumos pendentes de manifestação (is_resumo=true, sem XML)
      para que o SAP decida quais aceitar

    O SAP pode filtrar por `is_resumo` e chamar POST /manifestacao
    para aceitar os que desejar.
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Verifica se o CNPJ pertence ao tenant
    cert = sb.table("certificates").select("id").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", cnpj).eq("is_active", True).execute()

    if not cert.data:
        raise HTTPException(
            status_code=403,
            detail=f"CNPJ {mask_cnpj(cnpj)} nao cadastrado para este tenant",
        )

    # Busca documentos disponíveis + pendentes de manifestação
    statuses = ["available"]
    if incluir_pendentes:
        statuses.append("pending_manifestacao")

    query = sb.table("documents").select("*").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", cnpj).eq(
        "tipo", tipo.upper()
    ).in_("status", statuses)

    if desde:
        query = query.gt("nsu", desde)

    query = query.order("nsu")
    result = query.execute()

    documentos = []
    for doc in result.data:
        xml_b64 = ""
        if doc.get("xml_content"):
            xml_b64 = base64.b64encode(
                doc["xml_content"].encode("utf-8")
            ).decode("ascii")

        documentos.append(DocumentoOut(
            chave=doc["chave_acesso"],
            tipo=doc["tipo"],
            nsu=doc["nsu"],
            xml_b64=xml_b64,
            fetched_at=doc["fetched_at"],
            manifestacao_status=doc.get("manifestacao_status"),
            is_resumo=doc.get("is_resumo", False),
        ))

    ult_nsu = documentos[-1].nsu if documentos else desde or "000000000000000"

    return DocumentosResponse(
        cnpj=cnpj,
        documentos=documentos,
        ult_nsu=ult_nsu,
        total=len(documentos),
    )


@router.post("/documentos/{chave}/confirmar", response_model=ConfirmarResponse)
async def confirmar_documento(
    chave: str,
    auth: dict = Depends(verify_api_key),
):
    """Confirma entrega do documento e descarta o XML do banco.

    O SAP DRC chama este endpoint após processar cada documento.

    Este é o ponto onde o contador do trial avança. A captura em si não
    conta — apenas quando o SAP confirma que recebeu e processou, marcamos
    como consumido contra o trial_cap. Mesmo racional pro contador mensal
    de planos pagos (docs_consumidos_mes).
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Transição atômica available → delivered.
    # O filtro `status=available` garante idempotência: se o SAP chamar 2x
    # pra mesma chave, a segunda chamada retorna 404 (não duplica contagem).
    result = sb.table("documents").update({
        "status": "delivered",
        "xml_content": None,
        "delivered_at": datetime.now(timezone.utc).isoformat(),
    }).eq(
        "chave_acesso", chave
    ).eq(
        "tenant_id", tenant_id
    ).eq(
        "status", "available"
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail=f"Documento {chave} não encontrado ou já confirmado",
        )

    # Lê status do tenant pra decidir qual contador incrementar.
    # Preferimos incrementar DEPOIS do update pra evitar contar docs que
    # nunca foram entregues (caso o update falhe por algum motivo).
    try:
        tenant_row = sb.table("tenants").select(
            "subscription_status, trial_cap, docs_consumidos_trial"
        ).eq("id", tenant_id).single().execute()
        tenant_data = tenant_row.data or {}
        sub_status = tenant_data.get("subscription_status")

        if sub_status == "trial":
            # Trial: incrementa docs_consumidos_trial. A RPC é atômica e
            # retorna o novo valor. Se bateu cap, seta trial_blocked_at.
            rpc_res = sb.rpc("increment_trial_docs", {
                "p_tenant_id": tenant_id,
                "p_count": 1,
            }).execute()

            new_count = 0
            if rpc_res.data is not None:
                if isinstance(rpc_res.data, int):
                    new_count = rpc_res.data
                elif isinstance(rpc_res.data, list) and rpc_res.data:
                    first = rpc_res.data[0]
                    if isinstance(first, dict):
                        new_count = int(next(iter(first.values()), 0) or 0)
                    else:
                        new_count = int(first or 0)

            trial_cap = int(tenant_data.get("trial_cap") or 500)
            if new_count >= trial_cap:
                # Cap batido — bloqueia tenant. Próximas chamadas de qualquer
                # rota protegida por verify_trial_active vão retornar 403.
                sb.table("tenants").update({
                    "trial_blocked_at": datetime.now(timezone.utc).isoformat(),
                    "trial_blocked_reason": "cap",
                }).eq("id", tenant_id).execute()
                logger.info(
                    "tenant %s atingiu trial_cap=%d (confirmados=%d), bloqueando",
                    tenant_id, trial_cap, new_count,
                )

        elif sub_status == "active":
            # Plano pago: incrementa docs_consumidos_mes. Cobrança de excedente
            # roda no scheduler monthly_overage_job no dia 1 de cada mês.
            sb.rpc("increment_monthly_docs", {
                "p_tenant_id": tenant_id,
                "p_count": 1,
            }).execute()
    except Exception as exc:  # noqa: BLE001 — contador nunca quebra confirmação
        logger.warning(
            "falha ao incrementar contador de consumo para tenant %s chave %s: %s",
            tenant_id, chave, exc,
        )

    return ConfirmarResponse(status="discarded")


@router.post(
    "/documentos/retroativo",
    response_model=RetroativoResponse,
    status_code=202,
)
async def consulta_retroativa(
    body: RetroativoRequest,
    auth: dict = Depends(verify_api_key),
):
    """Inicia consulta retroativa de documentos em período específico.

    Processa em background — use GET /retroativo/{job_id} para acompanhar.
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Verifica CNPJ do tenant
    cert = sb.table("certificates").select("id").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", body.cnpj).eq("is_active", True).execute()

    if not cert.data:
        raise HTTPException(status_code=403, detail="CNPJ não cadastrado")

    # Verifica se tenant tem plano com retroativa
    tenant = sb.table("tenants").select("plan").eq(
        "id", tenant_id
    ).single().execute()

    if tenant.data.get("plan") == "starter":
        raise HTTPException(
            status_code=403,
            detail="Consulta retroativa não disponível no plano Starter",
        )

    job_id = f"retro_{uuid.uuid4().hex[:12]}"

    sb.table("polling_log").insert({
        "tenant_id": tenant_id,
        "cnpj": body.cnpj,
        "tipo": body.tipo,
        "triggered_by": "retroativo",
        "status": "processing",
        "job_id": job_id,
    }).execute()

    # Executa em background thread
    threading.Thread(
        target=run_retroactive_job,
        args=(tenant_id, body.cnpj, body.tipo, job_id),
        daemon=True,
    ).start()

    return RetroativoResponse(
        job_id=job_id,
        status="processing",
        estimativa_s=45,
    )


@router.get("/documentos/retroativo/{job_id}", response_model=RetroativoStatusResponse)
async def status_retroativo(
    job_id: str,
    auth: dict = Depends(verify_api_key),
):
    """Consulta status de um job de consulta retroativa."""
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    result = sb.table("polling_log").select("*").eq(
        "tenant_id", tenant_id
    ).eq("triggered_by", "retroativo").eq(
        "job_id", job_id
    ).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    log = result.data[0]
    return RetroativoStatusResponse(
        job_id=job_id,
        status=log["status"],
        docs_found=log.get("docs_found", 0),
        progress_pct=100 if log["status"] == "success" else 50,
    )


@router.get("/sefaz/status", response_model=SefazStatusResponse)
async def sefaz_status():
    """Health check dos endpoints SEFAZ por tipo de documento."""
    endpoints = []
    for tipo in ["nfe", "cte", "mdfe"]:
        status = sefaz_client.check_status(tipo)
        endpoints.append(SefazEndpointStatus(
            tipo=status["tipo"],
            ambiente=status["ambiente"],
            status=status["status"],
            latency_ms=status.get("latency_ms"),
        ))

    return SefazStatusResponse(endpoints=endpoints)
