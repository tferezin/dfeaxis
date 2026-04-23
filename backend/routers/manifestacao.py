"""Endpoints de Manifestação do Destinatário (NF-e)."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase import get_supabase_client
from middleware.lgpd import mask_cnpj
from middleware.security import verify_api_key, verify_jwt_or_api_key, verify_jwt_token, verify_jwt_with_trial
from models.schemas import (
    DocumentoPendenteOut,
    ManifestacaoBatchRequest,
    ManifestacaoBatchResponse,
    ManifestacaoRequest,
    ManifestacaoResponse,
)
from services.cert_manager import decrypt_password
from services.manifestacao import EVENTO_DESCRICAO, manifestacao_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_cert_and_password(tenant_id: str, cnpj: str) -> tuple:
    """Busca certificado e decifra senha. Retorna (cert_row, pfx_encrypted, pfx_iv, password)."""
    sb = get_supabase_client()
    cert = sb.table("certificates").select(
        "id, cnpj, pfx_encrypted, pfx_iv, pfx_password_encrypted, tenant_id"
    ).eq("tenant_id", tenant_id).eq("cnpj", cnpj).eq("is_active", True).execute()

    if not cert.data:
        raise HTTPException(status_code=404, detail=f"Certificado não encontrado para CNPJ {mask_cnpj(cnpj)}")

    row = cert.data[0]

    password = None
    if row.get("pfx_password_encrypted"):
        password = decrypt_password(row["pfx_password_encrypted"], tenant_id)

    if not password:
        raise HTTPException(status_code=400, detail="Senha do certificado não configurada")

    # Converte BYTEA
    pfx_encrypted = row["pfx_encrypted"]
    pfx_iv = row["pfx_iv"]
    if isinstance(pfx_encrypted, str):
        pfx_encrypted = bytes.fromhex(pfx_encrypted.replace("\\x", ""))
    if isinstance(pfx_iv, str):
        pfx_iv = bytes.fromhex(pfx_iv.replace("\\x", ""))

    return row, pfx_encrypted, pfx_iv, password


@router.get("/manifestacao/pendentes", response_model=list[DocumentoPendenteOut])
async def listar_pendentes(
    cnpj: str = Query(..., min_length=14, max_length=14),
    auth: dict = Depends(verify_jwt_or_api_key),
):
    """Lista documentos NF-e pendentes de manifestação.

    Retorna resumos (resNFe) que ainda não receberam Ciência.
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    result = sb.table("documents").select("*").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", cnpj).eq(
        "manifestacao_status", "pendente"
    ).order("fetched_at", desc=True).execute()

    pendentes = []
    for doc in result.data:
        pendentes.append(DocumentoPendenteOut(
            chave=doc["chave_acesso"],
            nsu=doc["nsu"],
            manifestacao_status=doc.get("manifestacao_status", "pendente"),
            fetched_at=doc["fetched_at"],
        ))

    return pendentes


@router.get("/manifestacao/historico")
async def historico_manifestacao(
    cnpj: str | None = Query(None, min_length=14, max_length=14),
    chave_acesso: str | None = Query(None, min_length=44, max_length=44),
    tipo_evento: str | None = Query(None, pattern=r"^(210210|210200|210220|210240)$"),
    limit: int = Query(100, ge=1, le=500),
    auth: dict = Depends(verify_jwt_or_api_key),
):
    """Consulta histórico de manifestações.

    Retorna até 500 eventos de manifestação do tenant autenticado, com filtros
    opcionais por CNPJ, chave de acesso, tipo de evento. Ordenado do mais recente
    para o mais antigo. Cada evento traz: chave, tipo, status SEFAZ, protocolo,
    origem (auto_capture/dashboard/api), data e latência.

    Uso típico: SAP consulta periodicamente para reconciliar status de manifestos.
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    query = sb.table("manifestacao_events").select("*").eq("tenant_id", tenant_id)

    if chave_acesso:
        query = query.eq("chave_acesso", chave_acesso)
    if tipo_evento:
        query = query.eq("tipo_evento", tipo_evento)

    query = query.order("created_at", desc=True).limit(limit)
    result = query.execute()

    events = []
    for row in result.data or []:
        descricao = EVENTO_DESCRICAO.get(row.get("tipo_evento", ""), "")
        events.append({
            "chave_acesso": row.get("chave_acesso"),
            "tipo_evento": row.get("tipo_evento"),
            "descricao": descricao,
            "cstat": row.get("cstat"),
            "xmotivo": row.get("xmotivo"),
            "protocolo": row.get("protocolo"),
            "source": row.get("source"),
            "latency_ms": row.get("latency_ms"),
            "created_at": row.get("created_at"),
        })

    # Se CNPJ foi informado, filtra (via join com documents — a tabela de eventos
    # não tem coluna cnpj diretamente, usamos o document_id)
    if cnpj and events:
        chaves = [e["chave_acesso"] for e in events if e.get("chave_acesso")]
        if chaves:
            docs_res = sb.table("documents").select("chave_acesso").eq(
                "tenant_id", tenant_id
            ).eq("cnpj", cnpj).in_("chave_acesso", chaves).execute()
            chaves_do_cnpj = {d["chave_acesso"] for d in (docs_res.data or [])}
            events = [e for e in events if e.get("chave_acesso") in chaves_do_cnpj]

    return {"total": len(events), "events": events}


@router.post("/manifestacao", response_model=ManifestacaoResponse)
async def enviar_manifestacao(
    body: ManifestacaoRequest,
    auth: dict = Depends(verify_jwt_or_api_key),
):
    """Envia evento de manifestação para uma NF-e.

    Tipos de evento:
    - 210210: Ciência da Operação (reconhece a NF-e)
    - 210200: Confirmação da Operação (confirma recebimento)
    - 210220: Desconhecimento da Operação (não reconhece)
    - 210240: Operação não Realizada (com justificativa obrigatória)
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Busca o documento
    doc = sb.table("documents").select("id, cnpj, tenant_id").eq(
        "tenant_id", tenant_id
    ).eq("chave_acesso", body.chave_acesso).execute()

    if not doc.data:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    cnpj = doc.data[0]["cnpj"]
    doc_id = doc.data[0]["id"]

    cert_row, pfx_encrypted, pfx_iv, password = _get_cert_and_password(tenant_id, cnpj)

    # Envia à SEFAZ
    result = manifestacao_service.enviar_evento(
        chave_acesso=body.chave_acesso,
        cnpj=cnpj,
        tipo_evento=body.tipo_evento,
        pfx_encrypted=pfx_encrypted,
        pfx_iv=pfx_iv,
        tenant_id=tenant_id,
        pfx_password=password,
        justificativa=body.justificativa,
    )

    # Mapeia tipo_evento para status
    status_map = {
        "210210": "ciencia",
        "210200": "confirmada",
        "210220": "desconhecida",
        "210240": "nao_realizada",
    }

    if result.success:
        # Atualiza status do documento
        now = datetime.now(timezone.utc)
        new_status = status_map[body.tipo_evento]
        update_data: dict = {
            "manifestacao_status": new_status,
            "manifestacao_at": now.isoformat(),
        }
        # Se é ciência, seta o deadline de 180 dias para manifesto definitivo
        if body.tipo_evento == "210210":
            update_data["manifestacao_deadline"] = (now + timedelta(days=180)).isoformat()
        # Se é manifesto definitivo, limpa o deadline (já foi cumprido)
        elif body.tipo_evento in ("210200", "210220", "210240"):
            update_data["manifestacao_deadline"] = None
        sb.table("documents").update(update_data).eq("id", doc_id).execute()

    # Determina origem do evento (dashboard via JWT, ou api via API key)
    source = "dashboard" if auth.get("user_id") else "api"

    # Registra evento de auditoria com source + identificador
    sb.table("manifestacao_events").insert({
        "tenant_id": tenant_id,
        "document_id": doc_id,
        "chave_acesso": body.chave_acesso,
        "tipo_evento": body.tipo_evento,
        "cstat": result.cstat,
        "xmotivo": result.xmotivo,
        "protocolo": result.protocolo,
        "latency_ms": result.latency_ms,
        "source": source,
        "user_id": auth.get("user_id"),
        "api_key_id": auth.get("api_key_id"),
    }).execute()

    return ManifestacaoResponse(
        chave_acesso=body.chave_acesso,
        tipo_evento=body.tipo_evento,
        descricao=EVENTO_DESCRICAO[body.tipo_evento],
        cstat=result.cstat,
        xmotivo=result.xmotivo,
        protocolo=result.protocolo,
        success=result.success,
    )


@router.post("/manifestacao/batch", response_model=ManifestacaoBatchResponse)
async def enviar_manifestacao_batch(
    body: ManifestacaoBatchRequest,
    auth: dict = Depends(verify_jwt_or_api_key),
):
    """Envia manifestação em lote para múltiplas NF-e (max 50 por request)."""
    resultados = []
    sucesso = 0
    erro = 0

    for chave in body.chaves:
        req = ManifestacaoRequest(
            chave_acesso=chave,
            tipo_evento=body.tipo_evento,
            justificativa=body.justificativa,
        )
        try:
            result = await enviar_manifestacao(req, auth)
            resultados.append(result)
            if result.success:
                sucesso += 1
            else:
                erro += 1
        except HTTPException as e:
            resultados.append(ManifestacaoResponse(
                chave_acesso=chave,
                tipo_evento=body.tipo_evento,
                descricao=EVENTO_DESCRICAO.get(body.tipo_evento, ""),
                cstat="999",
                xmotivo=e.detail,
                success=False,
            ))
            erro += 1

    return ManifestacaoBatchResponse(
        total=len(body.chaves),
        sucesso=sucesso,
        erro=erro,
        resultados=resultados,
    )
