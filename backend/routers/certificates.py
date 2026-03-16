"""Endpoints de gestao de certificados A1 (.pfx)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from db.supabase import get_supabase_client
from middleware.lgpd import audit_log, mask_cnpj
from middleware.security import verify_jwt_token
from models.schemas import CertificateOut, CertificateUploadResponse, _validate_cnpj
from services.cert_manager import encrypt_pfx, encrypt_password, extract_cert_info

router = APIRouter()

# Allowed content types for .pfx upload
_ALLOWED_PFX_CONTENT_TYPES = {
    "application/x-pkcs12",
    "application/octet-stream",
}


@router.post(
    "/certificates/upload",
    response_model=CertificateUploadResponse,
    status_code=201,
)
async def upload_certificate(
    request: Request,
    pfx_file: UploadFile = File(...),
    cnpj: str = Form(..., min_length=14, max_length=18),
    senha: str = Form(...),
    polling_mode: str = Form("manual"),
    auth: dict = Depends(verify_jwt_token),
):
    """Upload de certificado A1 (.pfx).

    - Valida o certificado
    - Extrai informacoes (CN, validade)
    - Cifra com AES-256-GCM (v2)
    - Salva no banco
    """
    tenant_id = auth["tenant_id"]
    user_id = auth.get("user_id")
    client_ip = request.client.host if request.client else None

    # Validate CNPJ
    try:
        cnpj = _validate_cnpj(cnpj)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Validate file extension
    filename = pfx_file.filename or ""
    if not filename.lower().endswith(".pfx"):
        raise HTTPException(
            status_code=400,
            detail="Arquivo deve ter extensao .pfx",
        )

    # Validate content type
    content_type = pfx_file.content_type or ""
    if content_type not in _ALLOWED_PFX_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Content-Type invalido: {content_type}. Esperado: application/x-pkcs12 ou application/octet-stream",
        )

    # Le o arquivo
    pfx_bytes = await pfx_file.read()
    if len(pfx_bytes) > 10 * 1024 * 1024:  # 10MB max
        raise HTTPException(status_code=400, detail="Arquivo muito grande (max 10MB)")

    # Valida o certificado
    try:
        cert_info = extract_cert_info(pfx_bytes, senha)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Certificado invalido ou senha incorreta: {e}",
        )

    # Cifra o .pfx com AES-256-GCM (v2) and the password
    encrypted, meta = encrypt_pfx(pfx_bytes, tenant_id)
    senha_encrypted = encrypt_password(senha, tenant_id)

    # v2 format: blob contains salt+nonce+ciphertext+tag, no separate IV needed.
    # Store version prefix with hex so decrypt can auto-detect.
    pfx_hex = f"{meta['version']}:{encrypted.hex()}"

    sb = get_supabase_client()

    # Verifica se CNPJ ja existe para este tenant
    existing = sb.table("certificates").select("id").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", cnpj).execute()

    cert_data = {
        "pfx_encrypted": pfx_hex,
        "pfx_iv": None,  # Not used in v2; kept for schema compat
        "pfx_password_encrypted": senha_encrypted,
        "company_name": cert_info.get("subject_cn"),
        "valid_from": str(cert_info["valid_from"]),
        "valid_until": str(cert_info["valid_until"]),
        "is_active": True,
    }

    if existing.data:
        # Atualiza certificado existente
        result = sb.table("certificates").update(
            cert_data
        ).eq("id", existing.data[0]["id"]).execute()

        cert_id = existing.data[0]["id"]
    else:
        # Insere novo
        cert_data["tenant_id"] = tenant_id
        cert_data["cnpj"] = cnpj
        result = sb.table("certificates").insert(cert_data).execute()

        cert_id = result.data[0]["id"]

    # Atualiza polling_mode no tenant se informado
    if polling_mode in ("manual", "auto"):
        sb.table("tenants").update(
            {"polling_mode": polling_mode}
        ).eq("id", tenant_id).execute()

    # Audit log
    audit_log(
        tenant_id=tenant_id,
        user_id=user_id,
        action="certificate.upload",
        resource_type="certificate",
        resource_id=cert_id,
        details={
            "cnpj": mask_cnpj(cnpj),
            "company_name": cert_info.get("subject_cn"),
            "valid_until": str(cert_info["valid_until"]),
            "is_update": bool(existing.data),
        },
        ip_address=client_ip,
    )

    return CertificateUploadResponse(
        certificate_id=cert_id,
        cnpj=cnpj,
        valid_until=cert_info["valid_until"],
    )


@router.get("/certificates", response_model=list[CertificateOut])
async def list_certificates(auth: dict = Depends(verify_jwt_token)):
    """Lista certificados do tenant."""
    sb = get_supabase_client()

    result = sb.table("certificates").select(
        "id, cnpj, company_name, valid_from, valid_until, "
        "is_active, last_polling_at"
    ).eq("tenant_id", auth["tenant_id"]).execute()

    return [CertificateOut(**cert) for cert in result.data]


@router.delete("/certificates/{cert_id}", status_code=204)
async def delete_certificate(
    cert_id: str,
    request: Request,
    auth: dict = Depends(verify_jwt_token),
):
    """Remove certificado do tenant."""
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]
    user_id = auth.get("user_id")
    client_ip = request.client.host if request.client else None

    result = sb.table("certificates").delete().eq(
        "id", cert_id
    ).eq("tenant_id", tenant_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Certificado nao encontrado")

    # Audit log
    deleted_cnpj = result.data[0].get("cnpj", "") if result.data else ""
    audit_log(
        tenant_id=tenant_id,
        user_id=user_id,
        action="certificate.delete",
        resource_type="certificate",
        resource_id=cert_id,
        details={"cnpj": mask_cnpj(deleted_cnpj)} if deleted_cnpj else None,
        ip_address=client_ip,
    )
