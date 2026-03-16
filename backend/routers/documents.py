"""Endpoints de documentos — integração SAP DRC."""

import base64
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase import get_supabase_client
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
from services.sefaz_client import sefaz_client

router = APIRouter()


@router.get("/documentos", response_model=DocumentosResponse)
async def listar_documentos(
    cnpj: str = Query(..., min_length=14, max_length=14),
    tipo: str = Query("nfe", pattern=r"^(nfe|cte|mdfe)$"),
    desde: Optional[str] = Query(None, description="NSU a partir de"),
    auth: dict = Depends(verify_api_key),
):
    """Lista documentos disponíveis para um CNPJ/tipo.

    Endpoint principal consumido pelo SAP DRC via RFC Destination HTTP.
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
            detail=f"CNPJ {cnpj} não cadastrado para este tenant",
        )

    # Busca documentos disponíveis
    query = sb.table("documents").select("*").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", cnpj).eq(
        "tipo", tipo.upper()
    ).eq("status", "available")

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
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    result = sb.table("documents").update({
        "status": "delivered",
        "xml_content": None,
        "delivered_at": "now()",
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

    # TODO: Agendar job retroativo via APScheduler
    # Por ora, registra o job e retorna 202
    sb.table("polling_log").insert({
        "tenant_id": tenant_id,
        "cnpj": body.cnpj,
        "tipo": body.tipo,
        "triggered_by": "retroativo",
        "status": "processing",
        "error_message": job_id,  # usa como referência do job
    }).execute()

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
        "error_message", job_id
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
