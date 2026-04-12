"""Scheduled job: alerta de NF-e pendentes de manifestação definitiva.

Roda 1x/dia. Varre documentos com manifestacao_status='ciencia' cujo
manifestacao_deadline está a 10 ou 5 dias de vencer. Envia e-mail
agrupado por tenant (um e-mail por tenant com total de docs pendentes).

Proteção contra duplicatas via audit_log, mesmo padrão de email_jobs.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from db.supabase import get_supabase_client
from services.email_service import email_service

logger = logging.getLogger(__name__)

ALERT_DAYS = {10, 5}


def _already_sent(tenant_id: str, email_type: str, window_hours: int = 20) -> bool:
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
    except Exception:
        return False

    if not result.data:
        return False

    last_str = result.data[0].get("created_at", "")
    try:
        last = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False

    return (datetime.now(timezone.utc) - last).total_seconds() < window_hours * 3600


def _record_sent(tenant_id: str, email_type: str, details: dict) -> None:
    sb = get_supabase_client()
    try:
        sb.table("audit_log").insert({
            "tenant_id": tenant_id,
            "action": "email_sent",
            "resource_type": "email",
            "resource_id": email_type,
            "details": details,
        }).execute()
    except Exception as exc:
        logger.warning("Failed to record manifestacao alert audit: %s", exc)


def check_manifestacao_expiring() -> None:
    """Envia alertas para tenants com NF-e pendentes de manifestação definitiva."""
    sb = get_supabase_client()
    now = datetime.now(timezone.utc)

    # Busca docs com ciência cujo deadline está dentro dos próximos 10 dias
    cutoff = (now + timedelta(days=max(ALERT_DAYS) + 1)).isoformat()

    try:
        result = (
            sb.table("documents")
            .select("tenant_id, chave_acesso, manifestacao_deadline")
            .eq("manifestacao_status", "ciencia")
            .not_.is_("manifestacao_deadline", "null")
            .lt("manifestacao_deadline", cutoff)
            .execute()
        )
    except Exception as exc:
        logger.error("check_manifestacao_expiring: query failed: %s", exc)
        return

    docs = result.data or []
    if not docs:
        logger.debug("check_manifestacao_expiring: nenhum doc próximo do vencimento")
        return

    # Agrupa por tenant
    by_tenant: dict[str, list[dict]] = {}
    for doc in docs:
        tid = doc["tenant_id"]
        by_tenant.setdefault(tid, []).append(doc)

    logger.info(
        "check_manifestacao_expiring: %d docs em %d tenants",
        len(docs), len(by_tenant),
    )

    for tenant_id, tenant_docs in by_tenant.items():
        # Calcula dias restantes do doc mais urgente
        min_days = 999
        for d in tenant_docs:
            try:
                deadline = datetime.fromisoformat(
                    d["manifestacao_deadline"].replace("Z", "+00:00")
                )
                days_left = max(0, int((deadline - now).total_seconds() // 86400))
                min_days = min(min_days, days_left)
            except (TypeError, ValueError):
                continue

        if min_days > max(ALERT_DAYS):
            continue

        # Encontra o bucket de alerta (10 ou 5 dias)
        alert_bucket = None
        for threshold in sorted(ALERT_DAYS, reverse=True):
            if min_days <= threshold:
                alert_bucket = threshold

        if not alert_bucket:
            continue

        email_type = f"manifestacao_expiring_d{alert_bucket}"

        if _already_sent(tenant_id, email_type, window_hours=20):
            continue

        # Busca dados do tenant
        try:
            tenant_row = (
                sb.table("tenants")
                .select("email, company_name")
                .eq("id", tenant_id)
                .single()
                .execute()
            )
        except Exception:
            continue

        tenant = tenant_row.data
        if not tenant or not tenant.get("email"):
            continue

        name = tenant.get("company_name") or tenant["email"].split("@")[0]
        total = len(tenant_docs)

        ok = email_service.send_manifestacao_expiring(
            to_email=tenant["email"],
            name=name,
            total_docs=total,
            min_days_remaining=min_days,
        )

        if ok:
            _record_sent(tenant_id, email_type, {
                "total_docs": total,
                "min_days_remaining": min_days,
                "alert_bucket": alert_bucket,
            })
