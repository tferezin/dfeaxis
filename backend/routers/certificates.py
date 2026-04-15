"""Endpoints de gestao de certificados A1 (.pfx)."""

import hashlib
import secrets

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from db.supabase import get_supabase_client
from middleware.lgpd import audit_log, mask_cnpj
from middleware.security import verify_jwt_token, verify_jwt_with_trial
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
    auth: dict = Depends(verify_jwt_with_trial),
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

    # Content type check (relaxed — browsers may send various types for .pfx)
    # Validation of the actual file content happens in extract_cert_info below

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

    # Anti-fraude: o CNPJ informado no form deve bater com o do certificado.
    # Antes: `if cert_cnpj and cert_cnpj != cnpj` deixava passar silenciosamente
    # quando `cert_cnpj is None` (cert PF / sem OID 2.16.76.1.3.3). Usuário
    # podia declarar qualquer CNPJ e queimar múltiplos trials. Agora rejeitamos
    # qualquer certificado sem CNPJ extraível.
    cert_cnpj = cert_info.get("cnpj")
    if not cert_cnpj:
        audit_log(
            tenant_id=tenant_id,
            user_id=user_id,
            action="certificate.upload.rejected",
            resource_type="certificate",
            details={
                "reason": "missing_cnpj_in_san",
                "declared_cnpj": mask_cnpj(cnpj),
            },
            ip_address=client_ip,
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "Certificado sem CNPJ no campo Subject Alternative Name "
                "(OID 2.16.76.1.3.3). Use um certificado A1 ICP-Brasil "
                "para Pessoa Jurídica (e-CNPJ)."
            ),
        )
    if cert_cnpj != cnpj:
        raise HTTPException(
            status_code=422,
            detail=(
                f"CNPJ informado ({mask_cnpj(cnpj)}) não confere com o do "
                f"certificado ({mask_cnpj(cert_cnpj)}). Use o certificado "
                "correspondente ao CNPJ cadastrado."
            ),
        )

    # Cifra o .pfx com AES-256-GCM (v2) and the password
    encrypted, meta = encrypt_pfx(pfx_bytes, tenant_id)
    senha_encrypted = encrypt_password(senha, tenant_id)

    # v2 format: blob contains salt+nonce+ciphertext+tag, no separate IV needed.
    # Store version prefix with hex so decrypt can auto-detect.
    pfx_hex = f"{meta['version']}:{encrypted.hex()}"

    sb = get_supabase_client()

    # --- Plan enforcement: limite de CNPJs do plano ---
    tenant_plan_row = sb.table("tenants").select(
        "plan, max_cnpjs"
    ).eq("id", tenant_id).single().execute()
    tenant_plan_data = tenant_plan_row.data or {}
    max_cnpjs = tenant_plan_data.get("max_cnpjs") or 1

    # Verifica se já existe certificado para este mesmo CNPJ (update, não novo)
    replacing_existing = sb.table("certificates").select("id").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", cnpj).execute()

    if not replacing_existing.data:
        # Só aplica o limite se for um insert novo (não substituição)
        active_certs = sb.table("certificates").select(
            "id", count="exact"
        ).eq("tenant_id", tenant_id).eq("is_active", True).execute()
        active_count = active_certs.count or 0

        if active_count >= max_cnpjs:
            raise HTTPException(
                status_code=402,
                detail={
                    "message": (
                        f"Limite de CNPJs do plano atingido ({max_cnpjs}). "
                        "Faça upgrade."
                    ),
                    "error_code": "CNPJ_LIMIT_REACHED",
                },
            )

    # --- Anti-abuse: 1 CNPJ = 1 trial na vida ---
    # Verifica se algum OUTRO tenant já usou este CNPJ
    cnpj_taken = sb.table("tenants").select("id").eq(
        "cnpj", cnpj
    ).neq("id", tenant_id).execute()

    if cnpj_taken.data:
        raise HTTPException(
            status_code=403,
            detail=(
                "Este CNPJ já passou pelo período de teste. "
                "Entre em contato com o suporte."
            ),
        )

    # Busca CNPJ atual do tenant para saber se precisa gravar
    tenant_row = sb.table("tenants").select("cnpj").eq(
        "id", tenant_id
    ).single().execute()
    current_tenant_cnpj = (tenant_row.data or {}).get("cnpj")

    # Verifica se CNPJ ja existe para este tenant (reusa query anterior)
    existing = replacing_existing

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

    # Atualiza tenant: polling_mode + CNPJ (se ainda não tiver)
    tenant_updates: dict = {}
    if polling_mode in ("manual", "auto"):
        tenant_updates["polling_mode"] = polling_mode
    if not current_tenant_cnpj:
        tenant_updates["cnpj"] = cnpj
    if tenant_updates:
        sb.table("tenants").update(tenant_updates).eq("id", tenant_id).execute()

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

    # --- Auto-geração de API key (apenas se tenant não tem nenhuma ativa) ---
    generated_api_key: str | None = None
    generated_api_key_id: str | None = None
    try:
        existing_keys = sb.table("api_keys").select("id").eq(
            "tenant_id", tenant_id
        ).eq("is_active", True).execute()

        if not existing_keys.data:
            raw_key = f"dfa_{secrets.token_urlsafe(32)}"
            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            key_prefix = raw_key[:8]

            key_result = sb.table("api_keys").insert({
                "tenant_id": tenant_id,
                "key_hash": key_hash,
                "key_prefix": key_prefix,
                "description": (
                    "Chave gerada automaticamente após upload do certificado"
                ),
            }).execute()

            generated_api_key = raw_key
            generated_api_key_id = (
                key_result.data[0]["id"] if key_result.data else None
            )

            audit_log(
                tenant_id=tenant_id,
                user_id=user_id,
                action="api_key.create",
                resource_type="api_key",
                resource_id=generated_api_key_id,
                details={
                    "key_prefix": key_prefix,
                    "description": "auto-generated on cert upload",
                },
                ip_address=client_ip,
            )
    except Exception:
        # Falha ao gerar API key não deve bloquear o upload do certificado
        generated_api_key = None
        generated_api_key_id = None

    return CertificateUploadResponse(
        certificate_id=cert_id,
        cnpj=cnpj,
        valid_until=cert_info["valid_until"],
        api_key=generated_api_key,
        api_key_id=generated_api_key_id,
    )


@router.get("/certificates", response_model=list[CertificateOut])
async def list_certificates(auth: dict = Depends(verify_jwt_with_trial)):
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
    auth: dict = Depends(verify_jwt_with_trial),
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
