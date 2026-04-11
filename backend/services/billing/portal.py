"""Stripe Customer Portal session creation."""

from __future__ import annotations

import logging

from config import settings

from .customers import get_customer_id
from .stripe_client import get_stripe

logger = logging.getLogger("dfeaxis.billing.portal")


def create_portal_session(
    tenant_id: str,
    return_url: str | None = None,
) -> dict:
    """Creates a Stripe Customer Portal session.

    The Portal lets the customer manage cards, view invoices, cancel,
    and switch plans — all without us writing UI.

    Raises ValueError if the tenant has no Stripe customer (i.e. never
    completed checkout).
    """
    customer_id = get_customer_id(tenant_id)
    if not customer_id:
        raise ValueError(
            "Tenant has no Stripe customer yet. Complete a checkout first."
        )

    stripe = get_stripe()
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url or settings.stripe_portal_return_url,
    )

    logger.info("Created portal session %s for tenant %s", session.id, tenant_id)
    return {"id": session.id, "url": session.url}
