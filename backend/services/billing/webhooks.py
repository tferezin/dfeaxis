"""Stripe webhook event dispatcher with idempotency.

The handler is intentionally minimal: each event type maps to a small
function. Idempotency is enforced via the billing_events table — duplicate
deliveries are no-ops.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from db.supabase import get_supabase_client

from .stripe_client import get_stripe
from .subscriptions import sync_subscription_to_db

logger = logging.getLogger("dfeaxis.billing.webhooks")


# Event types we care about
HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
}


def handle_webhook_event(
    payload: bytes,
    signature: str,
    webhook_secret: str,
) -> dict:
    """Verifies signature, dispatches the event, returns a status dict.

    Raises stripe.error.SignatureVerificationError if signature is invalid.
    """
    stripe = get_stripe()

    event = stripe.Webhook.construct_event(
        payload=payload,
        sig_header=signature,
        secret=webhook_secret,
    )

    event_id: str = event["id"]
    event_type: str = event["type"]

    # Idempotency check — if we've seen this event_id, skip
    if _is_duplicate(event_id):
        logger.info("Webhook %s already processed (idempotent skip)", event_id)
        return {"status": "duplicate", "event_id": event_id}

    if event_type not in HANDLED_EVENTS:
        logger.debug("Webhook %s ignored (type=%s)", event_id, event_type)
        _record_event(event_id, event_type, event["data"]["object"], tenant_id=None)
        return {"status": "ignored", "event_id": event_id, "event_type": event_type}

    try:
        tenant_id = _dispatch(event_type, event["data"]["object"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Webhook %s failed during dispatch: %s", event_id, exc)
        # Don't record on failure so retry can re-process
        raise

    _record_event(event_id, event_type, event["data"]["object"], tenant_id=tenant_id)
    return {
        "status": "processed",
        "event_id": event_id,
        "event_type": event_type,
        "tenant_id": tenant_id,
    }


def _dispatch(event_type: str, obj: dict[str, Any]) -> str | None:
    """Routes a Stripe event to its handler. Returns the affected tenant_id."""
    if event_type == "checkout.session.completed":
        return _on_checkout_completed(obj)

    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        return _on_subscription_change(obj)

    if event_type == "invoice.paid":
        return _on_invoice_paid(obj)

    if event_type == "invoice.payment_failed":
        return _on_invoice_failed(obj)

    return None


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def _on_checkout_completed(session: dict) -> str | None:
    """User completed checkout. Pull the subscription and sync."""
    tenant_id = (session.get("metadata") or {}).get("tenant_id") or session.get(
        "client_reference_id"
    )
    subscription_id = session.get("subscription")
    if not subscription_id:
        logger.warning(
            "checkout.session.completed without subscription id (mode=%s)",
            session.get("mode"),
        )
        return tenant_id

    stripe = get_stripe()
    sub = stripe.Subscription.retrieve(subscription_id)
    sync_subscription_to_db(sub)
    return tenant_id


def _on_subscription_change(subscription: dict) -> str | None:
    """customer.subscription.{created,updated,deleted} — re-sync."""
    sync_subscription_to_db(subscription)
    return (subscription.get("metadata") or {}).get("tenant_id")


def _on_invoice_paid(invoice: dict) -> str | None:
    """Renewal payment succeeded — keep tenant active."""
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return None
    stripe = get_stripe()
    sub = stripe.Subscription.retrieve(subscription_id)
    sync_subscription_to_db(sub)
    return (sub.get("metadata") or {}).get("tenant_id")


def _on_invoice_failed(invoice: dict) -> str | None:
    """Payment failed — Stripe will retry; we mark past_due via subscription sync."""
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return None
    stripe = get_stripe()
    sub = stripe.Subscription.retrieve(subscription_id)
    sync_subscription_to_db(sub)
    return (sub.get("metadata") or {}).get("tenant_id")


# ---------------------------------------------------------------------------
# Idempotency log (billing_events table)
# ---------------------------------------------------------------------------

def _is_duplicate(event_id: str) -> bool:
    sb = get_supabase_client()
    res = (
        sb.table("billing_events")
        .select("id")
        .eq("stripe_event_id", event_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def _record_event(
    event_id: str,
    event_type: str,
    payload: dict,
    tenant_id: str | None,
) -> None:
    sb = get_supabase_client()
    try:
        sb.table("billing_events").insert(
            {
                "tenant_id": tenant_id,
                "stripe_event_id": event_id,
                "event_type": event_type,
                "payload": json.loads(json.dumps(payload, default=str)),
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001
        # If the row already exists (race condition between two webhook
        # deliveries), the UNIQUE constraint will reject — that's fine.
        if "duplicate" not in str(exc).lower() and "23505" not in str(exc):
            logger.error("Failed to record billing_event %s: %s", event_id, exc)
