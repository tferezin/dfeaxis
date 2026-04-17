"""Admin dashboard API — cross-tenant visibility for operators.

All endpoints require JWT auth + email in ADMIN_EMAILS env var.
Uses service_role Supabase client for cross-tenant queries.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from db.supabase import get_supabase_client
from middleware.lgpd import mask_cnpj
from services.billing.plans import DEFAULT_PLAN_CATALOG

logger = logging.getLogger("dfeaxis.admin")

router = APIRouter(tags=["Admin"])

# ---------------------------------------------------------------------------
# Admin auth dependency
# ---------------------------------------------------------------------------

_ADMIN_EMAILS_RAW = os.getenv(
    "ADMIN_EMAILS", "ferezinth@hotmail.com,ferezaeai@gmail.com"
)
ADMIN_EMAILS: set[str] = {
    e.strip().lower() for e in _ADMIN_EMAILS_RAW.split(",") if e.strip()
}

# Plan price lookup (monthly_amount_cents by plan key)
_PLAN_PRICES: dict[str, int] = {
    p["key"]: p["monthly_amount_cents"] for p in DEFAULT_PLAN_CATALOG
}


async def _verify_admin(request: Request) -> dict:
    """Verify JWT then check the user email is in the admin list.

    Returns dict with tenant_id, user_id, and email.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"message": "Bearer token required", "error_code": "TOKEN_MISSING"},
        )

    token = auth_header.split(" ", 1)[1]
    sb = get_supabase_client()

    try:
        user_response = sb.auth.get_user(token)
        user = user_response.user
        if not user:
            raise HTTPException(
                status_code=401,
                detail={"message": "Invalid token", "error_code": "TOKEN_INVALID"},
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"message": "Invalid or expired token", "error_code": "TOKEN_INVALID"},
        )

    email = (user.email or "").lower()
    if email not in ADMIN_EMAILS:
        logger.warning(
            "Admin access denied for %s",
            email,
            extra={"path": request.url.path},
        )
        raise HTTPException(
            status_code=403,
            detail={"message": "Admin access denied", "error_code": "ADMIN_DENIED"},
        )

    return {"user_id": user.id, "email": email}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _days_ago(n: int) -> str:
    return _iso(_utc_now() - timedelta(days=n))


def _start_of_today() -> str:
    return _iso(_utc_now().replace(hour=0, minute=0, second=0, microsecond=0))


def _start_of_month() -> str:
    now = _utc_now()
    return _iso(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))


def _safe_int(val, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 1. GET /admin/dashboard — main metrics summary
# ---------------------------------------------------------------------------

@router.get("/admin/dashboard")
async def admin_dashboard(_admin: dict = Depends(_verify_admin)):
    """Aggregated metrics for the admin dashboard."""
    sb = get_supabase_client()

    # --- Tenants ---
    tenants_res = sb.table("tenants").select(
        "id, subscription_status, plan, created_at"
    ).execute()
    tenants_data = tenants_res.data or []

    status_counts = {
        "total": len(tenants_data),
        "trial_active": 0,
        "trial_expired": 0,
        "active_paid": 0,
        "past_due": 0,
        "cancelled": 0,
    }
    plan_counts: dict[str, int] = {"starter": 0, "business": 0, "enterprise": 0}

    for t in tenants_data:
        s = t.get("subscription_status", "")
        if s == "trial":
            status_counts["trial_active"] += 1
        elif s == "expired":
            status_counts["trial_expired"] += 1
        elif s == "active":
            status_counts["active_paid"] += 1
            plan_key = (t.get("plan") or "").lower()
            if plan_key in plan_counts:
                plan_counts[plan_key] += 1
        elif s == "past_due":
            status_counts["past_due"] += 1
        elif s == "cancelled":
            status_counts["cancelled"] += 1

    # MRR = sum of active plan monthly prices
    mrr_cents = sum(
        _PLAN_PRICES.get(plan, 0) * count for plan, count in plan_counts.items()
    )

    # --- Documents ---
    docs_total_res = sb.table("documents").select(
        "id", count="exact"
    ).execute()
    total_captured = docs_total_res.count or 0

    docs_delivered_res = sb.table("documents").select(
        "id", count="exact"
    ).eq("status", "delivered").execute()
    total_delivered = docs_delivered_res.count or 0

    today_start = _start_of_today()
    docs_today_res = sb.table("documents").select(
        "id", count="exact"
    ).gte("fetched_at", today_start).execute()
    captured_today = docs_today_res.count or 0

    month_start = _start_of_month()
    docs_month_res = sb.table("documents").select(
        "id", count="exact"
    ).gte("fetched_at", month_start).execute()
    captured_this_month = docs_month_res.count or 0

    # --- SEFAZ polling ---
    polls_today_res = sb.table("polling_log").select(
        "id", count="exact"
    ).gte("created_at", today_start).execute()
    polls_today = polls_today_res.count or 0

    errors_today_res = sb.table("polling_log").select(
        "id", count="exact"
    ).gte("created_at", today_start).eq("status", "error").execute()
    errors_today = errors_today_res.count or 0

    # Average latency from today's polls
    latency_res = sb.table("polling_log").select(
        "latency_ms"
    ).gte("created_at", today_start).not_.is_("latency_ms", "null").limit(500).execute()
    latency_values = [r["latency_ms"] for r in (latency_res.data or []) if r.get("latency_ms")]
    avg_latency_ms = int(sum(latency_values) / len(latency_values)) if latency_values else 0

    # --- Trial funnel ---
    d7 = _days_ago(7)
    d30 = _days_ago(30)

    signups_7d = len([t for t in tenants_data if (t.get("created_at") or "") >= d7])
    signups_30d = len([t for t in tenants_data if (t.get("created_at") or "") >= d30])

    # Conversions: tenants created in period that are now 'active'
    conversions_7d = len([
        t for t in tenants_data
        if (t.get("created_at") or "") >= d7
        and t.get("subscription_status") == "active"
    ])
    conversions_30d = len([
        t for t in tenants_data
        if (t.get("created_at") or "") >= d30
        and t.get("subscription_status") == "active"
    ])
    conversion_rate_30d = round(
        conversions_30d / signups_30d if signups_30d > 0 else 0.0, 4
    )

    # --- Campaign attribution ---
    utm_map: dict[str, int] = {}
    campaign_map: dict[str, int] = {}
    for t in tenants_data:
        src = t.get("utm_source")
        if src:
            utm_map[src] = utm_map.get(src, 0) + 1
        camp = t.get("utm_campaign")
        if camp:
            campaign_map[camp] = campaign_map.get(camp, 0) + 1

    # Need utm columns — re-fetch with those columns for campaign data
    campaign_res = sb.table("tenants").select(
        "utm_source, utm_campaign"
    ).execute()
    utm_map = {}
    campaign_map = {}
    for t in (campaign_res.data or []):
        src = t.get("utm_source")
        if src:
            utm_map[src] = utm_map.get(src, 0) + 1
        camp = t.get("utm_campaign")
        if camp:
            campaign_map[camp] = campaign_map.get(camp, 0) + 1

    utm_sources = sorted(
        [{"source": k, "count": v} for k, v in utm_map.items()],
        key=lambda x: x["count"], reverse=True,
    )[:10]
    top_campaigns = sorted(
        [{"campaign": k, "count": v} for k, v in campaign_map.items()],
        key=lambda x: x["count"], reverse=True,
    )[:10]

    return {
        "tenants": status_counts,
        "revenue": {
            "mrr_cents": mrr_cents,
            "arr_cents": mrr_cents * 12,
            "plans": plan_counts,
        },
        "documents": {
            "total_captured": total_captured,
            "total_delivered": total_delivered,
            "captured_today": captured_today,
            "captured_this_month": captured_this_month,
        },
        "sefaz": {
            "polls_today": polls_today,
            "errors_today": errors_today,
            "avg_latency_ms": avg_latency_ms,
        },
        "trial_funnel": {
            "signups_7d": signups_7d,
            "signups_30d": signups_30d,
            "conversions_7d": conversions_7d,
            "conversions_30d": conversions_30d,
            "conversion_rate_30d": conversion_rate_30d,
        },
        "campaign": {
            "utm_sources": utm_sources,
            "top_campaigns": top_campaigns,
        },
    }


# ---------------------------------------------------------------------------
# 2. GET /admin/tenants — list all tenants
# ---------------------------------------------------------------------------

@router.get("/admin/tenants")
async def admin_list_tenants(
    status: Optional[str] = Query(None, description="Filter by subscription_status"),
    search: Optional[str] = Query(None, description="Search by company name or email"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: dict = Depends(_verify_admin),
):
    """List all tenants with key details."""
    sb = get_supabase_client()

    query = sb.table("tenants").select(
        "id, company_name, email, plan, subscription_status, "
        "created_at, trial_expires_at, trial_blocked_at, "
        "docs_consumidos_trial, docs_consumidos_mes, "
        "max_cnpjs, cnpj, utm_source, utm_campaign"
    )

    if status:
        query = query.eq("subscription_status", status)

    if search:
        # Supabase ilike for partial text search
        query = query.or_(
            f"company_name.ilike.%{search}%,email.ilike.%{search}%"
        )

    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()

    tenants = []
    for t in (result.data or []):
        # Mask CNPJ for LGPD
        cnpj_raw = t.get("cnpj") or ""
        tenants.append({
            **t,
            "cnpj": mask_cnpj(cnpj_raw) if cnpj_raw else None,
        })

    return {"tenants": tenants, "count": len(tenants), "offset": offset}


# ---------------------------------------------------------------------------
# 3. GET /admin/tenants/{tenant_id} — single tenant detail
# ---------------------------------------------------------------------------

@router.get("/admin/tenants/{tenant_id}")
async def admin_tenant_detail(
    tenant_id: str,
    _admin: dict = Depends(_verify_admin),
):
    """Full detail for a single tenant."""
    sb = get_supabase_client()

    # Tenant base data
    tenant_res = sb.table("tenants").select("*").eq("id", tenant_id).execute()
    if not tenant_res.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant = tenant_res.data[0]

    # Mask sensitive fields
    if tenant.get("cnpj"):
        tenant["cnpj"] = mask_cnpj(tenant["cnpj"])

    # Certificates (without PFX data)
    certs_res = sb.table("certificates").select(
        "id, cnpj, company_name, valid_from, valid_until, is_active, created_at"
    ).eq("tenant_id", tenant_id).order("created_at", desc=True).execute()

    certs = []
    for c in (certs_res.data or []):
        if c.get("cnpj"):
            c["cnpj"] = mask_cnpj(c["cnpj"])
        certs.append(c)

    # API keys (without key_hash)
    keys_res = sb.table("api_keys").select(
        "id, name, is_active, created_at, last_used_at"
    ).eq("tenant_id", tenant_id).order("created_at", desc=True).execute()

    # Recent polling logs (last 20)
    logs_res = sb.table("polling_log").select(
        "id, cnpj, tipo, triggered_by, status, docs_found, "
        "latency_ms, error_message, created_at"
    ).eq("tenant_id", tenant_id).order(
        "created_at", desc=True
    ).limit(20).execute()

    polling_logs = []
    for log in (logs_res.data or []):
        if log.get("cnpj"):
            log["cnpj"] = mask_cnpj(log["cnpj"])
        polling_logs.append(log)

    # Billing events (last 20)
    billing_res = sb.table("billing_events").select(
        "id, event_type, stripe_event_id, processed_at"
    ).eq("tenant_id", tenant_id).order(
        "processed_at", desc=True
    ).limit(20).execute()

    return {
        "tenant": tenant,
        "certificates": certs,
        "api_keys": keys_res.data or [],
        "polling_logs": polling_logs,
        "billing_events": billing_res.data or [],
    }


# ---------------------------------------------------------------------------
# 4. GET /admin/revenue/history — monthly revenue breakdown (last 12 months)
# ---------------------------------------------------------------------------

@router.get("/admin/revenue/history")
async def admin_revenue_history(_admin: dict = Depends(_verify_admin)):
    """Monthly revenue breakdown from billing_events for the last 12 months."""
    sb = get_supabase_client()

    twelve_months_ago = _iso(_utc_now() - timedelta(days=365))

    # Fetch payment events
    events_res = sb.table("billing_events").select(
        "event_type, processed_at, payload"
    ).gte("processed_at", twelve_months_ago).in_(
        "event_type", ["invoice.paid", "invoice.payment_succeeded"]
    ).order("processed_at").execute()

    # Group by month
    monthly: dict[str, int] = {}
    for ev in (events_res.data or []):
        created = ev.get("processed_at", "")
        if len(created) >= 7:
            month_key = created[:7]  # "2026-04"
        else:
            continue

        # Try to extract amount from payload
        payload = ev.get("payload") or {}
        amount = _safe_int(
            payload.get("amount_paid")
            or payload.get("amount")
            or payload.get("data", {}).get("object", {}).get("amount_paid"),
            0,
        )
        monthly[month_key] = monthly.get(month_key, 0) + amount

    # Fill in missing months with 0
    now = _utc_now()
    result = []
    for i in range(11, -1, -1):
        dt = now - timedelta(days=30 * i)
        key = dt.strftime("%Y-%m")
        result.append({"month": key, "revenue_cents": monthly.get(key, 0)})

    return {"months": result}


# ---------------------------------------------------------------------------
# 5. GET /admin/documents/stats — daily capture stats (last 30 days)
# ---------------------------------------------------------------------------

@router.get("/admin/documents/stats")
async def admin_document_stats(_admin: dict = Depends(_verify_admin)):
    """Daily document capture counts for last 30 days, broken down by tipo."""
    sb = get_supabase_client()

    d30 = _days_ago(30)

    docs_res = sb.table("documents").select(
        "tipo, fetched_at"
    ).gte("fetched_at", d30).order("fetched_at").execute()

    # Group by day + tipo
    daily: dict[str, dict[str, int]] = {}
    for doc in (docs_res.data or []):
        fetched = doc.get("fetched_at", "")
        if len(fetched) >= 10:
            day = fetched[:10]
        else:
            continue
        tipo = (doc.get("tipo") or "UNKNOWN").upper()
        if day not in daily:
            daily[day] = {}
        daily[day][tipo] = daily[day].get(tipo, 0) + 1

    # Build result for last 30 days
    now = _utc_now()
    result = []
    for i in range(29, -1, -1):
        dt = now - timedelta(days=i)
        day_key = dt.strftime("%Y-%m-%d")
        day_data = daily.get(day_key, {})
        result.append({
            "date": day_key,
            "total": sum(day_data.values()),
            "NFE": day_data.get("NFE", 0),
            "CTE": day_data.get("CTE", 0),
            "MDFE": day_data.get("MDFE", 0),
            "NFSE": day_data.get("NFSE", 0),
        })

    return {"days": result}


# ---------------------------------------------------------------------------
# 6. GET /admin/sefaz/health — SEFAZ polling health + recent errors
# ---------------------------------------------------------------------------

@router.get("/admin/sefaz/health")
async def admin_sefaz_health(_admin: dict = Depends(_verify_admin)):
    """Current SEFAZ polling health and recent errors."""
    sb = get_supabase_client()

    today_start = _start_of_today()

    # Today's stats
    total_res = sb.table("polling_log").select(
        "id", count="exact"
    ).gte("created_at", today_start).execute()

    error_res = sb.table("polling_log").select(
        "id", count="exact"
    ).gte("created_at", today_start).eq("status", "error").execute()

    success_res = sb.table("polling_log").select(
        "id", count="exact"
    ).gte("created_at", today_start).eq("status", "success").execute()

    total_today = total_res.count or 0
    errors_today = error_res.count or 0
    success_today = success_res.count or 0

    # Determine overall health status
    if total_today == 0:
        health_status = "idle"
    elif errors_today == 0:
        health_status = "healthy"
    elif errors_today / max(total_today, 1) < 0.1:
        health_status = "degraded"
    else:
        health_status = "unhealthy"

    # Last 50 errors
    errors_res = sb.table("polling_log").select(
        "id, cnpj, tipo, triggered_by, error_message, latency_ms, created_at"
    ).eq("status", "error").order(
        "created_at", desc=True
    ).limit(50).execute()

    recent_errors = []
    for err in (errors_res.data or []):
        if err.get("cnpj"):
            err["cnpj"] = mask_cnpj(err["cnpj"])
        recent_errors.append(err)

    return {
        "status": health_status,
        "today": {
            "total_polls": total_today,
            "success": success_today,
            "errors": errors_today,
        },
        "recent_errors": recent_errors,
    }


# ---------------------------------------------------------------------------
# 7. GET /admin/chat/escalated — escalated chat conversations
# ---------------------------------------------------------------------------

@router.get("/admin/chat/escalated")
async def admin_escalated_chats(
    limit: int = Query(30, ge=1, le=100),
    _admin: dict = Depends(_verify_admin),
):
    """List escalated chat conversations with messages."""
    sb = get_supabase_client()

    convs_res = sb.table("chat_conversations").select(
        "id, context, tenant_id, status, escalated_at, metadata, created_at, last_message_at"
    ).eq("escalated_to_human", True).order(
        "escalated_at", desc=True
    ).limit(limit).execute()

    conversations = []
    for conv in (convs_res.data or []):
        # Enrich with tenant info
        tenant_id = conv.get("tenant_id")
        tenant_info = None
        if tenant_id:
            t_res = sb.table("tenants").select(
                "company_name, email"
            ).eq("id", tenant_id).execute()
            if t_res.data:
                tenant_info = t_res.data[0]

        # Fetch messages from chat_messages table
        conv_id = conv.get("id")
        msgs = []
        if conv_id:
            msgs_res = sb.table("chat_messages").select(
                "role, content, created_at"
            ).eq("conversation_id", conv_id).order("created_at").limit(50).execute()
            msgs = msgs_res.data or []

        conversations.append({
            "id": conv_id,
            "context": conv.get("context"),
            "tenant_id": tenant_id,
            "tenant": tenant_info,
            "status": conv.get("status"),
            "escalated_at": conv.get("escalated_at"),
            "message_count": len(msgs),
            "messages": msgs,
            "metadata": conv.get("metadata"),
            "created_at": conv.get("created_at"),
        })

    return {"conversations": conversations, "count": len(conversations)}


# ---------------------------------------------------------------------------
# 8. GET /admin/certificates/expiring — certificates expiring within 30 days
# ---------------------------------------------------------------------------

@router.get("/admin/certificates/expiring")
async def admin_expiring_certificates(
    days: int = Query(30, ge=1, le=90, description="Window in days"),
    _admin: dict = Depends(_verify_admin),
):
    """Certificates expiring within the given window."""
    sb = get_supabase_client()

    threshold = _iso(_utc_now() + timedelta(days=days))
    now_iso = _iso(_utc_now())

    certs_res = sb.table("certificates").select(
        "id, tenant_id, cnpj, company_name, valid_from, valid_until, is_active, created_at"
    ).eq("is_active", True).lte(
        "valid_until", threshold
    ).gte(
        "valid_until", now_iso  # not already expired
    ).order("valid_until").execute()

    certs = []
    for c in (certs_res.data or []):
        # Enrich with tenant info
        tenant_id = c.get("tenant_id")
        tenant_info = None
        if tenant_id:
            t_res = sb.table("tenants").select(
                "company_name, email"
            ).eq("id", tenant_id).execute()
            if t_res.data:
                tenant_info = t_res.data[0]

        # Days remaining
        valid_until = c.get("valid_until", "")
        days_remaining = None
        if valid_until:
            try:
                exp_dt = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
                days_remaining = max(0, (exp_dt - _utc_now()).days)
            except (ValueError, TypeError):
                pass

        if c.get("cnpj"):
            c["cnpj"] = mask_cnpj(c["cnpj"])

        certs.append({
            **c,
            "tenant": tenant_info,
            "days_remaining": days_remaining,
        })

    return {"certificates": certs, "count": len(certs)}
