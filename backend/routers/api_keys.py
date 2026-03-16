"""Endpoints de gestao de API keys."""

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request

from db.supabase import get_supabase_client
from middleware.lgpd import audit_log
from middleware.security import verify_jwt_token

router = APIRouter()


@router.post("/api-keys", status_code=201)
async def create_api_key(
    request: Request,
    description: str = "",
    auth: dict = Depends(verify_jwt_token),
):
    """Gera uma nova API key para integracao SAP DRC.

    Retorna a key apenas uma vez -- armazena apenas o hash no banco.
    """
    tenant_id = auth["tenant_id"]
    user_id = auth.get("user_id")
    client_ip = request.client.host if request.client else None

    raw_key = f"dfa_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:8]

    sb = get_supabase_client()

    # Limita a 5 keys por tenant
    existing = sb.table("api_keys").select("id").eq(
        "tenant_id", tenant_id
    ).eq("is_active", True).execute()

    if len(existing.data) >= 5:
        raise HTTPException(status_code=400, detail="Limite de 5 API keys atingido")

    sb.table("api_keys").insert({
        "tenant_id": tenant_id,
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "description": description or "API Key",
    }).execute()

    # Audit log
    audit_log(
        tenant_id=tenant_id,
        user_id=user_id,
        action="api_key.create",
        resource_type="api_key",
        resource_id=None,
        details={
            "key_prefix": key_prefix,
            "description": description or "API Key",
        },
        ip_address=client_ip,
    )

    return {"api_key": raw_key, "prefix": key_prefix}


@router.get("/api-keys")
async def list_api_keys(auth: dict = Depends(verify_jwt_token)):
    """Lista API keys do tenant (sem expor a key completa)."""
    sb = get_supabase_client()
    result = sb.table("api_keys").select(
        "id, key_prefix, description, last_used_at, is_active, created_at"
    ).eq("tenant_id", auth["tenant_id"]).execute()

    return result.data


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    request: Request,
    auth: dict = Depends(verify_jwt_token),
):
    """Revoga uma API key."""
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]
    user_id = auth.get("user_id")
    client_ip = request.client.host if request.client else None

    result = sb.table("api_keys").update(
        {"is_active": False}
    ).eq("id", key_id).eq("tenant_id", tenant_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="API key nao encontrada")

    # Audit log
    revoked_prefix = result.data[0].get("key_prefix", "") if result.data else ""
    audit_log(
        tenant_id=tenant_id,
        user_id=user_id,
        action="api_key.revoke",
        resource_type="api_key",
        resource_id=key_id,
        details={"key_prefix": revoked_prefix},
        ip_address=client_ip,
    )
