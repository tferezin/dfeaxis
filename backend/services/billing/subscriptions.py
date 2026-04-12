"""Subscription state synchronization between Stripe and our DB.

Stripe is the source of truth — these helpers pull the current state
from a Stripe Subscription object and mirror it onto the tenants row.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from db.supabase import get_supabase_client
from services.billing.plans import get_plan_by_price_id

logger = logging.getLogger("dfeaxis.billing.subscriptions")


# Stripe statuses that mean "user has access"
ACTIVE_STATUSES = {"active", "trialing"}
# Stripe statuses that mean "blocked, but recoverable"
PAST_DUE_STATUSES = {"past_due", "unpaid"}
# Stripe statuses that mean "fully ended"
ENDED_STATUSES = {"canceled", "incomplete_expired"}


def sync_subscription_to_db(stripe_subscription: dict) -> None:
    """Mirrors a Stripe Subscription onto the linked tenants row.

    Looks up the tenant via metadata.tenant_id (or by stripe_customer_id
    as a fallback). Updates:
      - subscription_status: 'active' | 'past_due' | 'cancelled' | 'expired'
      - stripe_subscription_id, stripe_price_id
      - current_period_end, cancel_at_period_end
      - trial_active = false (subscription always overrides trial)
      - trial_blocked_at = null, trial_blocked_reason = null (unblock)
    """
    sub = stripe_subscription
    tenant_id = _resolve_tenant_id(sub)
    if not tenant_id:
        logger.warning(
            "Cannot resolve tenant for Stripe subscription %s", sub.get("id")
        )
        return

    status = sub.get("status")
    db_status = _map_status(status)

    items = (sub.get("items") or {}).get("data") or []
    first_item = items[0] if items else {}
    price_id = (first_item.get("price") or {}).get("id") if first_item else None

    # In newer Stripe API versions, current_period_end is on the subscription
    # ITEM, not on the subscription root. Read from item first, fall back to root.
    period_end = first_item.get("current_period_end") or sub.get("current_period_end")
    period_end_iso = (
        datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()
        if period_end
        else None
    )

    update = {
        "subscription_status": db_status,
        "stripe_subscription_id": sub.get("id"),
        "stripe_price_id": price_id,
        "current_period_end": period_end_iso,
        "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
    }

    # If subscription is active, lift any trial blocks
    if db_status == "active":
        update["trial_active"] = False
        update["trial_blocked_at"] = None
        update["trial_blocked_reason"] = None
        update["pfx_inactive_since"] = None  # cancel pfx countdown

        # Apply plan limits from the subscribed price
        if price_id:
            lookup = get_plan_by_price_id(price_id)
            if lookup:
                plan = lookup.plan
                update["plan"] = plan.key
                update["max_cnpjs"] = plan.max_cnpjs
                update["docs_included_mes"] = plan.docs_included
            else:
                logger.warning(
                    "No plan matched price_id=%s for subscription %s",
                    price_id,
                    sub.get("id"),
                )

    sb = get_supabase_client()
    sb.table("tenants").update(update).eq("id", tenant_id).execute()

    logger.info(
        "Synced subscription %s for tenant %s: status=%s price=%s period_end=%s",
        sub.get("id"),
        tenant_id,
        db_status,
        price_id,
        period_end_iso,
    )


def _map_status(stripe_status: str | None) -> str:
    """Maps Stripe subscription.status → our subscription_status enum."""
    if not stripe_status:
        return "expired"
    if stripe_status in ACTIVE_STATUSES:
        return "active"
    if stripe_status in PAST_DUE_STATUSES:
        return "expired"  # treat as no-access; user fixes via portal
    if stripe_status in ENDED_STATUSES:
        return "cancelled"
    return "expired"  # incomplete, paused, etc — no access


def _resolve_tenant_id(stripe_obj: dict) -> Optional[str]:
    """Tries metadata.tenant_id first, falls back to looking up by customer."""
    metadata = stripe_obj.get("metadata") or {}
    tenant_id = metadata.get("tenant_id")
    if tenant_id:
        return tenant_id

    customer_id = stripe_obj.get("customer")
    if not customer_id:
        return None

    sb = get_supabase_client()
    res = (
        sb.table("tenants")
        .select("id")
        .eq("stripe_customer_id", customer_id)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["id"]
    return None
