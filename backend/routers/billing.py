"""Billing endpoints — checkout, customer portal, webhook.

These are the user-facing routes. All real billing logic lives in
`services/billing/` so this file stays thin and the module remains
copy-paste-able to other projects.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from config import settings
from db.supabase import get_supabase_client
from middleware.security import verify_jwt_token
from services.billing import (
    create_checkout_session,
    create_portal_session,
    handle_webhook_event,
    load_plans,
)
from services.billing.plans import get_plan_by_price_id

logger = logging.getLogger("dfeaxis.routers.billing")

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    price_id: str = Field(..., description="Stripe Price ID (price_...)")
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
    billing_day: Optional[int] = Field(
        default=5,
        description="Dia do mês para cobrança recorrente (5, 10 ou 15)",
    )


class CheckoutResponse(BaseModel):
    session_id: str
    url: str


class PortalResponse(BaseModel):
    session_id: str
    url: str


class PlanOut(BaseModel):
    key: str
    name: str
    description: str
    price_id_monthly: str
    price_id_yearly: str
    monthly_amount_cents: int
    yearly_amount_cents: int
    docs_included: int
    overage_cents_per_doc: int
    max_cnpjs: int
    features: list[str]


# ---------------------------------------------------------------------------
# Public: list available plans (no auth — landing/pricing UI)
# ---------------------------------------------------------------------------

@router.get("/billing/plans", response_model=list[PlanOut])
async def list_plans():
    """Returns the configured plans (loaded from data/stripe_plans.json)."""
    return [PlanOut(**vars(p)) for p in load_plans()]


# ---------------------------------------------------------------------------
# Authenticated: checkout session
# ---------------------------------------------------------------------------

@router.post(
    "/billing/checkout",
    response_model=CheckoutResponse,
    status_code=201,
)
async def checkout(
    body: CheckoutRequest,
    auth: dict = Depends(verify_jwt_token),
):
    """Creates a Stripe Checkout Session for the current tenant.

    Frontend redirects the user to the returned URL. After payment,
    Stripe redirects back to `success_url` and fires the
    `checkout.session.completed` webhook which unblocks the trial.
    """
    tenant_id = auth["tenant_id"]
    # Valida billing_day
    billing_day = body.billing_day or 5
    if billing_day not in (5, 10, 15):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "billing_day deve ser 5, 10 ou 15",
                "error_code": "INVALID_BILLING_DAY",
            },
        )

    # Gate proativo: bloqueia escolha de plano com max_cnpjs menor que CNPJs
    # ja cadastrados. Espelha o gate de certificates.py:146 mas no momento da
    # escolha, evitando cliente pagar plano errado e ficar sem conseguir
    # adicionar/operar os CNPJs que ja tem. Downgrade via Customer Portal eh
    # tratado em config separada (Stripe Dashboard).
    target = get_plan_by_price_id(body.price_id)
    if target is not None:
        sb = get_supabase_client()
        cert_count = sb.table("certificates").select(
            "id", count="exact"
        ).eq("tenant_id", tenant_id).eq("is_active", True).execute().count or 0
        if cert_count > target.plan.max_cnpjs:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        f"Voce tem {cert_count} CNPJs cadastrados, mas o plano "
                        f"{target.plan.name} permite ate {target.plan.max_cnpjs}. "
                        "Escolha um plano compativel ou remova certificados antes."
                    ),
                    "error_code": "PLAN_CNPJ_LIMIT_EXCEEDED",
                    "cnpj_count": cert_count,
                    "plan_max_cnpjs": target.plan.max_cnpjs,
                    "plan_key": target.plan.key,
                },
            )

    try:
        session = create_checkout_session(
            tenant_id=tenant_id,
            price_id=body.price_id,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            billing_day=billing_day,
        )
    except ValueError as e:
        # R3: price_id desconhecido (fora do catalogo) — 400 com msg clara
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(e),
                "error_code": "INVALID_PRICE_ID",
            },
        )
    except RuntimeError:
        # Stripe not configured
        logger.exception("checkout: Stripe nao configurado pra tenant %s", tenant_id)
        raise HTTPException(status_code=503, detail="Servico de pagamento indisponivel")
    except Exception:
        logger.exception("checkout failed for tenant %s", tenant_id)
        raise HTTPException(status_code=500, detail="Erro ao criar sessao de checkout")

    return CheckoutResponse(session_id=session["id"], url=session["url"])


# ---------------------------------------------------------------------------
# Authenticated: customer portal
# ---------------------------------------------------------------------------

@router.post("/billing/portal", response_model=PortalResponse)
async def portal(auth: dict = Depends(verify_jwt_token)):
    """Creates a Stripe Customer Portal session.

    The user is redirected to a Stripe-hosted page where they can
    manage cards, view invoices, cancel, or change plans.
    """
    tenant_id = auth["tenant_id"]
    try:
        session = create_portal_session(tenant_id=tenant_id)
    except ValueError:
        # Cliente sem stripe_customer_id (nunca pagou) — mensagem amigavel
        logger.info("portal: tenant %s sem stripe_customer_id", tenant_id)
        raise HTTPException(
            status_code=400,
            detail="Voce ainda nao tem assinatura ativa. Assine um plano primeiro.",
        )
    except RuntimeError:
        logger.exception("portal: Stripe nao configurado pra tenant %s", tenant_id)
        raise HTTPException(status_code=503, detail="Servico de pagamento indisponivel")
    except Exception:
        logger.exception("portal failed for tenant %s", tenant_id)
        raise HTTPException(status_code=500, detail="Erro ao acessar portal de cobranca")

    return PortalResponse(session_id=session["id"], url=session["url"])


# ---------------------------------------------------------------------------
# Public: Stripe webhook (no JWT — verified via signature)
# ---------------------------------------------------------------------------

@router.post("/billing/webhook", status_code=200)
async def webhook(request: Request):
    """Receives Stripe webhook events.

    Verifies the signature against STRIPE_WEBHOOK_SECRET, dispatches the
    event to the appropriate handler, and is idempotent (duplicate
    deliveries are no-ops).
    """
    if not settings.stripe_webhook_secret:
        logger.warning("Webhook received but STRIPE_WEBHOOK_SECRET is not set")
        raise HTTPException(
            status_code=503,
            detail="Webhook secret not configured",
        )

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")

    try:
        result = handle_webhook_event(
            payload=payload,
            signature=signature,
            webhook_secret=settings.stripe_webhook_secret,
        )
    except Exception as e:
        # Stripe will retry on non-2xx — return 400 for invalid sig,
        # 500 for handler errors. Detail generico — nao vaza msg interna
        # pra Stripe Dashboard / tracebacks.
        msg = str(e)
        if "signature" in msg.lower() or "Invalid" in msg:
            logger.warning("Invalid webhook signature: %s", msg)
            raise HTTPException(status_code=400, detail="Invalid signature")
        logger.exception("Webhook processing failed")
        raise HTTPException(status_code=500, detail="Webhook processing failed")

    return result
