"""Stripe Checkout Session creation."""

from __future__ import annotations

import logging
from typing import Literal

from config import settings

from .customers import ensure_customer
from .stripe_client import get_stripe

logger = logging.getLogger("dfeaxis.billing.checkout")


def create_checkout_session(
    tenant_id: str,
    price_id: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
    mode: Literal["subscription", "payment"] = "subscription",
    billing_day: int = 5,
) -> dict:
    """Creates a Stripe Checkout Session for the tenant + price.

    Returns the session object with `id` and `url`. Frontend redirects
    the user to `url` to complete payment.

    The session is linked to the tenant via:
      - customer (ensured / lazily created)
      - metadata.tenant_id (for webhook lookup)
      - client_reference_id (also for webhook lookup, redundant for safety)

    billing_day (5/10/15) é propagado via metadata para o webhook salvar
    no tenant quando a subscription for criada.
    """
    customer_id = ensure_customer(tenant_id)
    stripe = get_stripe()

    session_metadata = {"tenant_id": tenant_id, "billing_day": str(billing_day)}

    session = stripe.checkout.Session.create(
        mode=mode,
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url or settings.stripe_checkout_success_url,
        cancel_url=cancel_url or settings.stripe_checkout_cancel_url,
        client_reference_id=tenant_id,
        metadata=session_metadata,
        # Allow the user to apply promotion codes if you create any in the dashboard
        allow_promotion_codes=True,
        # Pass tenant_id + billing_day through to the subscription so webhooks have it
        subscription_data={
            "metadata": session_metadata,
        } if mode == "subscription" else None,
    )

    logger.info(
        "Created checkout session %s for tenant %s price %s",
        session.id,
        tenant_id,
        price_id,
    )
    return {"id": session.id, "url": session.url}
