"""Shared consumption counter logic for trial and monthly billing.

Centralizes the trial/monthly document counter increment that was
previously duplicated in:
  - routers/documents.py  (confirmar_documento)
  - routers/sap_drc.py    (deleteInboundInvoices, deleteOfficialDocument)
"""

import logging
from datetime import datetime, timezone

from db.supabase import get_supabase_client

logger = logging.getLogger("dfeaxis.billing.consumption")


def increment_consumption(tenant_id: str, count: int = 1) -> dict:
    """Increment trial or monthly consumption counter.

    Reads the tenant's subscription_status and routes to the correct
    counter (trial vs monthly). For trial tenants, also checks whether
    the cap was reached and blocks the tenant if so.

    Returns {"blocked": bool, "reason": str|None}
    """
    sb = get_supabase_client()

    tenant_row = sb.table("tenants").select(
        "subscription_status, trial_cap, docs_consumidos_trial"
    ).eq("id", tenant_id).single().execute()
    tenant_data = tenant_row.data or {}
    sub_status = tenant_data.get("subscription_status")

    if sub_status == "trial":
        return _increment_trial(sb, tenant_id, tenant_data, count)
    elif sub_status == "active":
        _increment_monthly(sb, tenant_id, count)
        return {"blocked": False, "reason": None}
    else:
        # past_due, expired, cancelled — no counter to increment
        return {"blocked": False, "reason": None}


def _increment_trial(sb, tenant_id: str, tenant_data: dict, count: int) -> dict:
    """Increment trial counter and block tenant if cap reached."""
    rpc_res = sb.rpc("increment_trial_docs", {
        "p_tenant_id": tenant_id,
        "p_count": count,
    }).execute()

    new_count = 0
    if rpc_res.data is not None:
        if isinstance(rpc_res.data, int):
            new_count = rpc_res.data
        elif isinstance(rpc_res.data, list) and rpc_res.data:
            first = rpc_res.data[0]
            if isinstance(first, dict):
                new_count = int(next(iter(first.values()), 0) or 0)
            else:
                new_count = int(first or 0)

    trial_cap = int(tenant_data.get("trial_cap") or 500)
    if new_count >= trial_cap:
        sb.table("tenants").update({
            "trial_blocked_at": datetime.now(timezone.utc).isoformat(),
            "trial_blocked_reason": "cap",
        }).eq("id", tenant_id).execute()
        logger.info(
            "tenant %s atingiu trial_cap=%d (confirmados=%d), bloqueando",
            tenant_id, trial_cap, new_count,
        )
        return {"blocked": True, "reason": "cap"}

    return {"blocked": False, "reason": None}


def _increment_monthly(sb, tenant_id: str, count: int) -> None:
    """Increment monthly consumption counter for active subscriptions."""
    sb.rpc("increment_monthly_docs", {
        "p_tenant_id": tenant_id,
        "p_count": count,
    }).execute()
