"""Endpoints de tenant/onboarding."""

import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from admin_guards import should_block_prod
from db.supabase import get_supabase_client
from middleware.lgpd import audit_log
from middleware.security import verify_jwt_token
from models.schemas import TenantRegisterRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def _is_prod_access_allowed_globally() -> bool:
    """Flag global — se PROD_ACCESS_ALLOWED='true' no env, qualquer tenant
    pode virar sefaz_ambiente='1' sem precisar de approval individual.

    Durante soft launch (primeiros clientes), fica 'false' → só tenants
    com prod_access_approved=true conseguem. Quando amadurecer, seta
    'true' no Railway pra liberar geral sem deploy.
    """
    return os.getenv("PROD_ACCESS_ALLOWED", "false").strip().lower() == "true"


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

    # Trial: 500 docs OU 10 dias (o que vier primeiro). Campos-chave:
    # - trial_cap=500 vem do DEFAULT da migration 007
    # - docs_consumidos_trial começa em 0 (default da coluna)
    # - trial_blocked_at começa null (seta via polling quando bate cap, via
    #   email_job quando expira tempo, ou é limpo via webhook Stripe no upgrade)
    #
    # NÃO setamos `credits` nem `docs_included_mes` aqui porque durante o trial
    # o único gate é o trial_cap. `docs_included_mes` só existe quando o tenant
    # vira `active` via webhook Stripe — `subscriptions.sync_subscription_to_db`
    # popula `plan`, `max_cnpjs` e `docs_included_mes` a partir do catálogo.
    insert_data = {
        "user_id": user_id,
        "company_name": body.company_name,
        "email": body.email,
        "plan": "starter",  # placeholder até Stripe confirmar upgrade
        "max_cnpjs": 1,
        # Ciência automática é o comportamento padrão do DFeAxis — o evento
        # 210210 é disparado na própria captura. Antes o onboarding criava
        # como "manual" (override do default auto_ciencia da migration 002),
        # o que gerava confusão no getting-started. Alinhado 2026-04-23.
        "manifestacao_mode": "auto_ciencia",
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
    request: Request,
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

    # A5: snapshot dos valores ANTES de mudar — vai pro audit_log pra
    # forensics (especialmente sefaz_ambiente que é o campo mais sensível).
    old_values: dict = {}
    try:
        old_res = sb.table("tenants").select(
            "polling_mode, manifestacao_mode, sefaz_ambiente"
        ).eq("id", auth["tenant_id"]).single().execute()
        if old_res.data:
            old_values = {k: old_res.data.get(k) for k in updates.keys()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load previous settings for audit: %s", exc)

    # Guard 1 (commit 047dfb0): conta admin (LINKTI/BEIERSDORF) NUNCA
    # pode ir pra prod — identidade hardcoded no admin_guards.py.
    # Guard 2 (commit atual): outros tenants só podem ir pra prod se
    # (flag global PROD_ACCESS_ALLOWED=true) OU (prod_access_approved=true
    # no row do tenant). Durante soft launch, default é TRAVADO pra evitar
    # cliente novo virar prod sem aprovação manual nossa.
    if updates.get("sefaz_ambiente") == "1":
        # Guard 1: identidade admin
        blocked, reason = should_block_prod(
            user_id=auth.get("user_id"),
            tenant_id=auth.get("tenant_id"),
            user_email=auth.get("email"),
        )
        if blocked:
            raise HTTPException(status_code=403, detail=reason)

        # Guard 2: flag global OU allowlist individual
        if not _is_prod_access_allowed_globally():
            tenant_row = sb.table("tenants").select(
                "prod_access_approved"
            ).eq("id", auth["tenant_id"]).single().execute()
            approved = bool(
                tenant_row.data and tenant_row.data.get("prod_access_approved")
            )
            if not approved:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Sua conta ainda não foi liberada para captura em "
                        "Produção. Envie um e-mail para contato@dfeaxis.com.br "
                        "solicitando a liberação — nossa equipe revisa o setup "
                        "do seu CNPJ e certificado e habilita o ambiente."
                    ),
                )

        # Guard 3: tenant precisa ter pelo menos 1 certificado A1 cadastrado.
        # Sem cert nao tem como autenticar SOAP na SEFAZ — a "ativacao" nao
        # serviria pra nada e ainda permitiria virar prod por engano antes
        # de configurar o ambiente.
        cert_res = sb.table("certificates").select(
            "id", count="exact"
        ).eq("tenant_id", auth["tenant_id"]).limit(1).execute()
        cert_count = cert_res.count if cert_res.count is not None else len(cert_res.data or [])
        if cert_count < 1:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Cadastre pelo menos um certificado A1 antes de ativar "
                    "Produção. (Menu Cadastros → Certificados A1)"
                ),
            )

        # Guard 4: tenant precisa ter realizado pelo menos 1 captura em
        # Homologacao antes de virar prod. Garante que o setup foi testado
        # end-to-end (cert valido, CNPJ certo, SOAP respondendo) sem o risco
        # de uma primeira tentativa quebrar em prod e gerar consumo indevido.
        docs_res = sb.table("documents").select(
            "id", count="exact"
        ).eq("tenant_id", auth["tenant_id"]).limit(1).execute()
        docs_count = docs_res.count if docs_res.count is not None else len(docs_res.data or [])
        if docs_count < 1:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Realize pelo menos uma captura em Homologação antes de "
                    "ativar Produção. (Menu Execução → Captura Manual)"
                ),
            )

    result = sb.table("tenants").update(updates).eq(
        "id", auth["tenant_id"]
    ).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    # A5: registra auditoria — especialmente importante pra sefaz_ambiente
    # (LGPD/forensics: quem virou prod e quando). Falha em audit nunca derruba
    # o request (`audit_log` ja captura excecoes internamente).
    client_ip = request.client.host if request.client else None
    audit_log(
        tenant_id=auth["tenant_id"],
        user_id=auth.get("user_id"),
        action="tenant.settings_updated",
        resource_type="tenant",
        resource_id=auth["tenant_id"],
        details={
            "changes": updates,
            "old_values": old_values,
            "is_prod_switch": updates.get("sefaz_ambiente") == "1",
        },
        ip_address=client_ip,
    )

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
