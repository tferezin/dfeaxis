"""Endpoints de tenant/onboarding."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from db.supabase import get_supabase_client
from middleware.security import verify_jwt_token
from models.schemas import TenantRegisterRequest

router = APIRouter()


@router.post("/tenants/register", status_code=201)
async def register_tenant(
    body: TenantRegisterRequest,
    auth: dict = Depends(verify_jwt_token),
):
    """Registra tenant na primeira vez que faz login (onboarding).

    CNPJ NÃO é pedido aqui — será extraído do .pfx no upload de certificado
    e validado globalmente (1 CNPJ = 1 trial na vida).
    """
    sb = get_supabase_client()
    user_id = auth["user_id"]

    # Verifica se já existe
    existing = sb.table("tenants").select("id").eq(
        "user_id", user_id
    ).execute()

    if existing.data:
        return {"tenant_id": existing.data[0]["id"], "status": "already_exists"}

    trial_expires = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()

    insert_data = {
        "user_id": user_id,
        "company_name": body.company_name,
        "email": body.email,
        "plan": "starter",
        "credits": 100,  # créditos iniciais de teste
        "max_cnpjs": 1,
        "docs_included_mes": 3000,
        "manifestacao_mode": "manual",
        "trial_expires_at": trial_expires,
        "trial_active": True,
        "subscription_status": "trial",
    }
    if body.phone:
        insert_data["phone"] = body.phone
    if body.ga_client_id:
        insert_data["ga_client_id"] = body.ga_client_id

    # Campaign attribution — inclui apenas campos não-nulos pra manter
    # o insert mínimo e deixar colunas com default NULL intactas.
    for attr_field in (
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "referrer",
        "landing_path",
    ):
        value = getattr(body, attr_field, None)
        if value:
            insert_data[attr_field] = value

    result = sb.table("tenants").insert(insert_data).execute()

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
    sefaz_ambiente: str = Body(None, pattern=r"^(1|2)$"),
    auth: dict = Depends(verify_jwt_token),
):
    """Atualiza configurações do tenant.

    - polling_mode: 'manual' ou 'auto' (polling automático a cada 15 min)
    - manifestacao_mode: 'auto_ciencia' (Ciência automática) ou 'manual'
    - sefaz_ambiente: '1' (Produção) ou '2' (Homologação)
    """
    updates = {}
    if polling_mode is not None:
        updates["polling_mode"] = polling_mode
    if manifestacao_mode is not None:
        updates["manifestacao_mode"] = manifestacao_mode
    if sefaz_ambiente is not None:
        updates["sefaz_ambiente"] = sefaz_ambiente

    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    sb = get_supabase_client()
    result = sb.table("tenants").update(updates).eq(
        "id", auth["tenant_id"]
    ).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    return result.data[0]


@router.get("/tenants/trial-status")
async def get_trial_status(auth: dict = Depends(verify_jwt_token)):
    """Retorna status do período de teste do tenant."""
    sb = get_supabase_client()
    result = sb.table("tenants").select(
        "trial_active, trial_expires_at, subscription_status"
    ).eq("id", auth["tenant_id"]).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    data = result.data
    now = datetime.now(timezone.utc)
    expires_at = data.get("trial_expires_at")

    days_remaining = 0
    if expires_at:
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        delta = expires_dt - now
        days_remaining = max(0, delta.days)

    return {
        "trial_active": data.get("trial_active", False),
        "trial_expires_at": expires_at,
        "days_remaining": days_remaining,
        "subscription_status": data.get("subscription_status", "trial"),
    }
