"""Endpoints NFS-e — consulta ao Ambiente Nacional de NFS-e (ADN).

DISCLAIMER: O ADN foi instituido pela Reforma Tributaria (vigente desde 01/2026).
Nem todos os municipios aderiram ao sistema nacional. Consultas para municipios
nao integrados podem retornar lista vazia.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase import get_supabase_client
from middleware.lgpd import mask_cnpj
from middleware.security import verify_api_key
from models.schemas import NfseOut, NfseListResponse, NfsePollingResponse
from services.cert_manager import decrypt_password
from services.nfse_client import nfse_client
from services.nsu_controller import nsu_controller

logger = logging.getLogger(__name__)

router = APIRouter()

# Aviso sobre cobertura parcial do ADN
ADN_DISCLAIMER = (
    "O Ambiente Nacional de NFS-e (ADN) não cobre todos os municípios. "
    "Resultados podem estar incompletos para municípios não integrados."
)


def _get_cert_and_password(tenant_id: str, cnpj: str) -> tuple[dict, str]:
    """Busca certificado ativo e decifra a senha do .pfx.

    Raises HTTPException 404 se certificado nao encontrado.
    """
    sb = get_supabase_client()

    cert_result = sb.table("certificates").select(
        "id, tenant_id, cnpj, pfx_encrypted, pfx_iv, "
        "pfx_password_encrypted, last_nsu_nfse"
    ).eq("tenant_id", tenant_id).eq("cnpj", cnpj).eq("is_active", True).execute()

    if not cert_result.data:
        raise HTTPException(
            status_code=404,
            detail=f"Certificado ativo não encontrado para CNPJ {mask_cnpj(cnpj)}",
        )

    cert = cert_result.data[0]
    pfx_password = None
    if cert.get("pfx_password_encrypted"):
        pfx_password = decrypt_password(cert["pfx_password_encrypted"], tenant_id)

    if not pfx_password:
        raise HTTPException(
            status_code=500,
            detail="Erro ao decifrar senha do certificado",
        )

    return cert, pfx_password


@router.get("/nfse", response_model=NfseListResponse)
async def listar_nfse(
    cnpj: str = Query(..., min_length=14, max_length=14),
    data_inicio: str = Query(..., description="Data inicio YYYY-MM-DD"),
    data_fim: str = Query(..., description="Data fim YYYY-MM-DD"),
    pagina: int = Query(1, ge=1, description="Pagina de resultados"),
    auth: dict = Depends(verify_api_key),
):
    """Lista NFS-e recebidas por um CNPJ em um periodo.

    Consulta o Ambiente Nacional de NFS-e (ADN).
    Nem todos os municipios estao integrados ao ADN.
    """
    tenant_id = auth["tenant_id"]
    cert, pfx_password = _get_cert_and_password(tenant_id, cnpj)

    # Converte hex do Supabase
    pfx_encrypted = cert["pfx_encrypted"]
    pfx_iv = cert["pfx_iv"]
    if isinstance(pfx_encrypted, str) and not pfx_encrypted.startswith("v2:"):
        pfx_encrypted = bytes.fromhex(pfx_encrypted.replace("\\x", ""))
    if isinstance(pfx_iv, str) and pfx_iv:
        pfx_iv = bytes.fromhex(pfx_iv.replace("\\x", ""))

    response = nfse_client.consultar_nfse_por_cnpj(
        cnpj=cnpj,
        data_inicio=data_inicio,
        data_fim=data_fim,
        pfx_encrypted=pfx_encrypted,
        pfx_iv=pfx_iv,
        tenant_id=tenant_id,
        pfx_password=pfx_password,
        pagina=pagina,
    )

    if not response.success:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.message,
        )

    documentos = [
        NfseOut(
            chave=doc.chave,
            nsu=doc.nsu,
            xml_content=doc.xml_content,
            codigo_municipio=doc.codigo_municipio,
            codigo_servico=doc.codigo_servico,
            data_emissao=doc.data_emissao,
            valor_servico=doc.valor_servico,
        )
        for doc in response.documents
    ]

    return NfseListResponse(
        cnpj=cnpj,
        documentos=documentos,
        total=len(documentos),
        disclaimer=ADN_DISCLAIMER,
    )


@router.get("/nfse/{chave}")
async def consultar_nfse_por_chave(
    chave: str,
    auth: dict = Depends(verify_api_key),
):
    """Consulta uma NFS-e especifica por chave de acesso."""
    tenant_id = auth["tenant_id"]
    sb = get_supabase_client()

    # Primeiro tenta buscar no banco local
    local = sb.table("documents").select("*").eq(
        "tenant_id", tenant_id
    ).eq("chave_acesso", chave).eq("tipo", "NFSE").execute()

    if local.data:
        doc = local.data[0]
        return NfseOut(
            chave=doc["chave_acesso"],
            nsu=doc.get("nsu", ""),
            xml_content=doc.get("xml_content", ""),
            codigo_municipio=doc.get("codigo_municipio"),
            codigo_servico=doc.get("codigo_servico"),
            data_emissao=None,
            valor_servico=None,
        )

    # Se nao encontrou localmente, busca um certificado ativo do tenant
    cert_result = sb.table("certificates").select(
        "id, tenant_id, cnpj, pfx_encrypted, pfx_iv, pfx_password_encrypted"
    ).eq("tenant_id", tenant_id).eq("is_active", True).limit(1).execute()

    if not cert_result.data:
        raise HTTPException(
            status_code=404,
            detail="Nenhum certificado ativo encontrado para consulta no ADN",
        )

    cert = cert_result.data[0]
    pfx_password = None
    if cert.get("pfx_password_encrypted"):
        pfx_password = decrypt_password(cert["pfx_password_encrypted"], tenant_id)

    if not pfx_password:
        raise HTTPException(status_code=500, detail="Erro ao decifrar senha do certificado")

    pfx_encrypted = cert["pfx_encrypted"]
    pfx_iv = cert["pfx_iv"]
    if isinstance(pfx_encrypted, str) and not pfx_encrypted.startswith("v2:"):
        pfx_encrypted = bytes.fromhex(pfx_encrypted.replace("\\x", ""))
    if isinstance(pfx_iv, str) and pfx_iv:
        pfx_iv = bytes.fromhex(pfx_iv.replace("\\x", ""))

    response = nfse_client.consultar_nfse_por_chave(
        chave_acesso=chave,
        pfx_encrypted=pfx_encrypted,
        pfx_iv=pfx_iv,
        tenant_id=tenant_id,
        pfx_password=pfx_password,
    )

    if not response.success:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.message,
        )

    if not response.documents:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada")

    doc = response.documents[0]
    return NfseOut(
        chave=doc.chave,
        nsu=doc.nsu,
        xml_content=doc.xml_content,
        codigo_municipio=doc.codigo_municipio,
        codigo_servico=doc.codigo_servico,
        data_emissao=doc.data_emissao,
        valor_servico=doc.valor_servico,
    )


@router.post("/nfse/polling", response_model=NfsePollingResponse)
async def trigger_nfse_polling(
    cnpj: str = Query(..., min_length=14, max_length=14),
    auth: dict = Depends(verify_api_key),
):
    """Dispara consulta de distribuicao NFS-e no ADN (similar ao polling SEFAZ).

    Busca novas NFS-e a partir do ultimo NSU processado.
    """
    tenant_id = auth["tenant_id"]
    cert, pfx_password = _get_cert_and_password(tenant_id, cnpj)
    sb = get_supabase_client()

    ult_nsu = cert.get("last_nsu_nfse", "000000000000000")

    pfx_encrypted = cert["pfx_encrypted"]
    pfx_iv = cert["pfx_iv"]
    if isinstance(pfx_encrypted, str) and not pfx_encrypted.startswith("v2:"):
        pfx_encrypted = bytes.fromhex(pfx_encrypted.replace("\\x", ""))
    if isinstance(pfx_iv, str) and pfx_iv:
        pfx_iv = bytes.fromhex(pfx_iv.replace("\\x", ""))

    response = nfse_client.consultar_dps_distribuicao(
        cnpj=cnpj,
        ult_nsu=ult_nsu,
        pfx_encrypted=pfx_encrypted,
        pfx_iv=pfx_iv,
        tenant_id=tenant_id,
        pfx_password=pfx_password,
    )

    docs_found = 0
    if response.success and response.documents:
        docs_found = len(response.documents)

        # Salva documentos no banco
        for doc in response.documents:
            sb.table("documents").upsert({
                "tenant_id": tenant_id,
                "cnpj": cnpj,
                "tipo": "NFSE",
                "chave_acesso": doc.chave,
                "nsu": doc.nsu,
                "xml_content": doc.xml_content,
                "status": "available",
                "is_resumo": False,
                "manifestacao_status": "nao_aplicavel",
                "codigo_municipio": doc.codigo_municipio,
                "codigo_servico": doc.codigo_servico,
            }, on_conflict="tenant_id,chave_acesso").execute()

        # Atualiza ultimo NSU
        sb.table("certificates").update({
            "last_nsu_nfse": response.ult_nsu,
        }).eq("id", cert["id"]).execute()

    # Log do polling
    sb.table("polling_log").insert({
        "tenant_id": tenant_id,
        "cnpj": cnpj,
        "tipo": "nfse",
        "triggered_by": "manual",
        "status": "success" if response.success else "error",
        "docs_found": docs_found,
        "ult_nsu": response.ult_nsu,
        "latency_ms": response.latency_ms,
        "error_message": response.message if not response.success else None,
    }).execute()

    return NfsePollingResponse(
        status="success" if response.success else "error",
        cnpj=cnpj,
        docs_found=docs_found,
        ult_nsu=response.ult_nsu,
        message=response.message,
        disclaimer=ADN_DISCLAIMER,
    )
