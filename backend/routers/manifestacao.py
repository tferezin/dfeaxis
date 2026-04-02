"""Endpoints de Manifestação do Destinatário (NF-e)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase import get_supabase_client
from middleware.lgpd import mask_cnpj
from middleware.security import verify_api_key, verify_jwt_token, verify_jwt_with_trial
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
        raise HTTPException(status_code=404, detail=f"Certificado nao encontrado para CNPJ {mask_cnpj(cnpj)}")

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
    auth: dict = Depends(verify_jwt_with_trial),
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


@router.post("/manifestacao", response_model=ManifestacaoResponse)
async def enviar_manifestacao(
    body: ManifestacaoRequest,
    auth: dict = Depends(verify_api_key),
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
        new_status = status_map[body.tipo_evento]
        sb.table("documents").update({
            "manifestacao_status": new_status,
            "manifestacao_at": "now()",
        }).eq("id", doc_id).execute()

    # Registra evento de auditoria
    sb.table("manifestacao_events").insert({
        "tenant_id": tenant_id,
        "document_id": doc_id,
        "chave_acesso": body.chave_acesso,
        "tipo_evento": body.tipo_evento,
        "cstat": result.cstat,
        "xmotivo": result.xmotivo,
        "protocolo": result.protocolo,
        "latency_ms": result.latency_ms,
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
    auth: dict = Depends(verify_api_key),
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
