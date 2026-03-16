"""Endpoints de tenant/onboarding."""

from fastapi import APIRouter, Body, Depends, HTTPException

from db.supabase import get_supabase_client
from middleware.security import verify_jwt_token

router = APIRouter()


@router.post("/tenants/register", status_code=201)
async def register_tenant(
    company_name: str,
    email: str,
    auth: dict = Depends(verify_jwt_token),
):
    """Registra tenant na primeira vez que faz login (onboarding)."""
    sb = get_supabase_client()
    user_id = auth["user_id"]

    # Verifica se já existe
    existing = sb.table("tenants").select("id").eq(
        "user_id", user_id
    ).execute()

    if existing.data:
        return {"tenant_id": existing.data[0]["id"], "status": "already_exists"}

    result = sb.table("tenants").insert({
        "user_id": user_id,
        "company_name": company_name,
        "email": email,
        "plan": "starter",
        "credits": 100,  # créditos iniciais de teste
        "manifestacao_mode": "manual",
    }).execute()

    return {"tenant_id": result.data[0]["id"], "status": "created"}


@router.get("/tenants/me")
async def get_tenant(auth: dict = Depends(verify_jwt_token)):
    """Retorna dados do tenant logado."""
    sb = get_supabase_client()
    result = sb.table("tenants").select("*").eq(
        "id", auth["tenant_id"]
    ).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    return result.data


@router.patch("/tenants/settings")
async def update_settings(
    polling_mode: str = Body(None, pattern=r"^(manual|auto)$"),
    manifestacao_mode: str = Body(None, pattern=r"^(auto_ciencia|manual)$"),
    auth: dict = Depends(verify_jwt_token),
):
    """Atualiza configurações do tenant.

    - polling_mode: 'manual' ou 'auto' (polling automático a cada 15 min)
    - manifestacao_mode: 'auto_ciencia' (Ciência automática) ou 'manual'
    """
    updates = {}
    if polling_mode is not None:
        updates["polling_mode"] = polling_mode
    if manifestacao_mode is not None:
        updates["manifestacao_mode"] = manifestacao_mode

    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    sb = get_supabase_client()
    result = sb.table("tenants").update(updates).eq(
        "id", auth["tenant_id"]
    ).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    return result.data[0]
