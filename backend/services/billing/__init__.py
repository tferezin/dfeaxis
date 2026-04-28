"""Stripe billing module — plug-and-play across SaaS projects.

This package is intentionally **decoupled** from DFeAxis-specific logic so it
can be lifted into another SaaS by:

  1. Copying this folder
  2. Setting STRIPE_* env vars
  3. Adapting `plans.py` (price IDs, plan features)
  4. Calling `apply_subscription_state(tenant_id, ...)` from your own
     subscription state handler (typically a thin wrapper that updates
     your project's "tenants" or "users" table)

Public API:
    from services.billing import (
        get_stripe,
        ensure_customer,
        create_checkout_session,
        create_portal_session,
        handle_webhook_event,
        sync_subscription_to_db,
        load_plans,
    )
"""

from .stripe_client import get_stripe
from .customers import ensure_customer
from .checkout import create_checkout_session
from .portal import create_portal_session
from .subscriptions import sync_subscription_to_db
from .webhooks import handle_webhook_event
from .plans import load_plans, get_plan_by_price_id
from .change_plan import change_subscription_plan, ChangePlanError

__all__ = [
    "get_stripe",
    "ensure_customer",
    "create_checkout_session",
    "create_portal_session",
    "sync_subscription_to_db",
    "handle_webhook_event",
    "load_plans",
    "get_plan_by_price_id",
    "change_subscription_plan",
    "ChangePlanError",
]
