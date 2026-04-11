"""Scheduled jobs for transactional trial emails.

Two jobs:
  * ``check_trial_nudges``   — run every 6h. Sends countdown nudges on days
    5/2/1 remaining and an "almost at cap" email at >=80% of trial_cap.
  * ``check_trial_expirations`` — run every 1h. Sends the "trial expired"
    email once a tenant passes trial_expires_at or is blocked.

Duplicate-send protection uses the existing ``audit_log`` table: we insert
an entry with ``action='email_sent'`` and ``details.email_type`` per send,
and each job queries the log to skip already-sent emails. No schema
migration required.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from db.supabase import get_supabase_client
from services.email_service import email_service

logger = logging.getLogger(__name__)

# Trial defaults — kept in sync with backend/routers/tenants.py
DEFAULT_TRIAL_CAP = 500
NUDGE_DAYS = {5, 2, 1}
CAP_WARNING_PCT = 0.80


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Supabase returns ISO-8601 with TZ
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _already_sent(tenant_id: str, email_type: str, window_hours: int = 20) -> bool:
    """Return True if an email of this type was sent in the recent window.

    We deliberately use a short window for nudges (20h) so that a daily
    nudge for a given day won't fire twice, but a new day can fire again.
    Expired emails use a longer window via a dedicated ``email_type``
    marker — they are effectively once-per-tenant by design.
    """
    sb = get_supabase_client()
    try:
        result = (
            sb.table("audit_log")
            .select("id, created_at")
            .eq("tenant_id", tenant_id)
            .eq("action", "email_sent")
            .eq("resource_type", "email")
            .eq("resource_id", email_type)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit_log lookup failed: %s", exc)
        return False

    if not result.data:
        return False

    if email_type == "trial_expired":
        # Never resend the final "expired" email.
        return True

    last = _parse_iso(result.data[0].get("created_at"))
    if not last:
        return False
    delta = datetime.now(timezone.utc) - last
    return delta.total_seconds() < window_hours * 3600


def _record_sent(tenant_id: str, email_type: str, details: dict) -> None:
    sb = get_supabase_client()
    try:
        sb.table("audit_log").insert(
            {
                "tenant_id": tenant_id,
                "action": "email_sent",
                "resource_type": "email",
                "resource_id": email_type,
                "details": details,
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to record email audit: %s", exc)


def _display_name(tenant: dict) -> str:
    return (
        tenant.get("company_name")
        or tenant.get("email", "").split("@")[0]
        or "cliente"
    )


# ---------------------------------------------------------------------- #
# Job 1 — nudges during active trial
# ---------------------------------------------------------------------- #


def check_trial_nudges() -> None:
    """Send countdown + cap-warning emails to active trial tenants."""
    sb = get_supabase_client()
    now = datetime.now(timezone.utc)

    try:
        result = (
            sb.table("tenants")
            .select(
                "id, email, company_name, subscription_status, trial_active, "
                "trial_expires_at, trial_cap, docs_consumidos_trial, "
                "trial_blocked_at"
            )
            .eq("subscription_status", "trial")
            .eq("trial_active", True)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("check_trial_nudges: failed to load tenants: %s", exc)
        return

    tenants = result.data or []
    logger.info("check_trial_nudges: %d active trial tenants", len(tenants))

    for tenant in tenants:
        tenant_id = tenant["id"]
        email = tenant.get("email")
        if not email:
            continue
        # Already blocked tenants are handled by the expirations job.
        if tenant.get("trial_blocked_at"):
            continue

        expires_at = _parse_iso(tenant.get("trial_expires_at"))
        days_remaining: Optional[int] = None
        if expires_at:
            seconds = (expires_at - now).total_seconds()
            days_remaining = max(0, int(seconds // 86400))

        docs_cap = tenant.get("trial_cap") or DEFAULT_TRIAL_CAP
        docs_consumed = tenant.get("docs_consumidos_trial") or 0
        pct = (docs_consumed / docs_cap) if docs_cap else 0.0
        name = _display_name(tenant)

        # Cap warning takes priority over countdown if both apply on the
        # same tick — the user needs to know they are about to be blocked.
        if pct >= CAP_WARNING_PCT and pct < 1.0:
            if not _already_sent(tenant_id, "trial_cap_warning", window_hours=48):
                ok = email_service.send_trial_cap_warning(
                    to_email=email,
                    name=name,
                    docs_consumed=docs_consumed,
                    docs_cap=docs_cap,
                )
                if ok:
                    _record_sent(
                        tenant_id,
                        "trial_cap_warning",
                        {
                            "docs_consumed": docs_consumed,
                            "docs_cap": docs_cap,
                            "pct": round(pct, 2),
                        },
                    )

        if days_remaining is not None and days_remaining in NUDGE_DAYS:
            nudge_type = f"trial_nudge_d{days_remaining}"
            if not _already_sent(tenant_id, nudge_type, window_hours=20):
                ok = email_service.send_trial_nudge(
                    to_email=email,
                    name=name,
                    days_remaining=days_remaining,
                    docs_consumed=docs_consumed,
                    docs_cap=docs_cap,
                )
                if ok:
                    _record_sent(
                        tenant_id,
                        nudge_type,
                        {
                            "days_remaining": days_remaining,
                            "docs_consumed": docs_consumed,
                            "docs_cap": docs_cap,
                        },
                    )


# ---------------------------------------------------------------------- #
# Job 2 — expired trial
# ---------------------------------------------------------------------- #


def check_trial_expirations() -> None:
    """Send the final 'trial expired' email once per tenant."""
    sb = get_supabase_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Two conditions to cover: time expiry OR blocked (cap / manual).
    # Supabase python client doesn't chain OR ergonomically, so run two
    # queries and deduplicate.
    tenants: dict[str, dict] = {}

    try:
        time_expired = (
            sb.table("tenants")
            .select(
                "id, email, company_name, subscription_status, trial_active, "
                "trial_expires_at, trial_blocked_reason"
            )
            .eq("subscription_status", "trial")
            .lt("trial_expires_at", now_iso)
            .execute()
        )
        for row in time_expired.data or []:
            tenants[row["id"]] = row
    except Exception as exc:  # noqa: BLE001
        logger.error("check_trial_expirations: time query failed: %s", exc)

    try:
        blocked = (
            sb.table("tenants")
            .select(
                "id, email, company_name, subscription_status, trial_active, "
                "trial_expires_at, trial_blocked_reason"
            )
            .eq("subscription_status", "trial")
            .not_.is_("trial_blocked_reason", "null")
            .execute()
        )
        for row in blocked.data or []:
            tenants.setdefault(row["id"], row)
    except Exception as exc:  # noqa: BLE001
        logger.error("check_trial_expirations: blocked query failed: %s", exc)

    logger.info("check_trial_expirations: %d expired/blocked trials", len(tenants))

    for tenant in tenants.values():
        tenant_id = tenant["id"]
        email = tenant.get("email")
        if not email:
            continue
        if _already_sent(tenant_id, "trial_expired"):
            continue

        reason_code = (tenant.get("trial_blocked_reason") or "").lower()
        reason = "cap" if "cap" in reason_code or "limit" in reason_code else "time"
        name = _display_name(tenant)

        ok = email_service.send_trial_expired(
            to_email=email,
            name=name,
            reason=reason,
        )
        if ok:
            _record_sent(
                tenant_id,
                "trial_expired",
                {
                    "reason": reason,
                    "trial_blocked_reason": tenant.get("trial_blocked_reason"),
                    "trial_expires_at": tenant.get("trial_expires_at"),
                },
            )
