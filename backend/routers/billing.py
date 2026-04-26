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
from middleware.security import verify_jwt_token
from services.billing import (
    create_checkout_session,
    create_portal_session,
    handle_webhook_event,
    load_plans,
)

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
    except RuntimeError as e:
        # Stripe not configured
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("checkout failed for tenant %s", tenant_id)
        raise HTTPException(status_code=500, detail=f"checkout failed: {e}")

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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("portal failed for tenant %s", tenant_id)
        raise HTTPException(status_code=500, detail=f"portal failed: {e}")

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
        # 500 for handler errors
        msg = str(e)
        if "signature" in msg.lower() or "Invalid" in msg:
            logger.warning("Invalid webhook signature: %s", msg)
            raise HTTPException(status_code=400, detail="Invalid signature")
        logger.exception("Webhook processing failed")
        raise HTTPException(status_code=500, detail=f"webhook failed: {msg}")

    return result
