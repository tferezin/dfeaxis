"""LGPD/minimização: cleanup de .pfx cifrado após 30 dias de inatividade.

Comportamento (executa 1x/dia):

1. **Marca inativos** — para tenants em estado bloqueado/expirado/cancelado
   sem `pfx_inactive_since`, marca agora como o início do countdown.
2. **Reseta voltantes** — para tenants que voltaram a `subscription_status='active'`,
   limpa `pfx_inactive_since` (countdown não conta mais).
3. **Apaga material criptográfico** — para tenants cujo `pfx_inactive_since`
   é mais antigo que 30 dias, zera `pfx_encrypted` e
   `pfx_password_encrypted` em todos os certificados, marca `is_active=false`,
   e registra a ação no audit_log.

O usuário pode reativar a conta a qualquer momento; ao pagar, terá que
fazer re-upload do .pfx (dados não-criptográficos como nome/email/CNPJ
permanecem preservados indefinidamente).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from db.supabase import get_supabase_client
from middleware.lgpd import audit_log

logger = logging.getLogger("dfeaxis.scheduler.pfx_cleanup")

# Tempo de retenção do .pfx após inatividade declarada
PFX_RETENTION_DAYS = 30

# Estados que disparam o countdown de inatividade
INACTIVE_STATUSES = ("expired", "cancelled")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mark_inactive_tenants(sb) -> int:
    """Marca pfx_inactive_since=NOW() para tenants bloqueados que ainda
    não têm o countdown iniciado.
    """
    now_iso = _now().isoformat()

    # Tenants em estado terminal que ainda não foram marcados
    result = (
        sb.table("tenants")
        .select("id, subscription_status, trial_blocked_at")
        .in_("subscription_status", list(INACTIVE_STATUSES))
        .is_("pfx_inactive_since", "null")
        .execute()
    )
    matched = result.data or []

    # Tenants em trial bloqueado (cap ou time) também contam como inativos
    blocked_trial = (
        sb.table("tenants")
        .select("id")
        .eq("subscription_status", "trial")
        .not_.is_("trial_blocked_at", "null")
        .is_("pfx_inactive_since", "null")
        .execute()
    )
    matched.extend(blocked_trial.data or [])

    if not matched:
        return 0

    ids = list({t["id"] for t in matched})
    sb.table("tenants").update({"pfx_inactive_since": now_iso}).in_(
        "id", ids
    ).execute()

    for tenant_id in ids:
        audit_log(
            tenant_id=tenant_id,
            user_id=None,
            action="pfx.inactivity_started",
            resource_type="tenant",
            resource_id=tenant_id,
            details={"retention_days": PFX_RETENTION_DAYS, "marked_at": now_iso},
            ip_address=None,
        )

    logger.info(
        "pfx_cleanup: marcados %d tenant(s) como inativos (countdown %d dias iniciado)",
        len(ids),
        PFX_RETENTION_DAYS,
    )
    return len(ids)


def _reset_returning_tenants(sb) -> int:
    """Limpa pfx_inactive_since para tenants que voltaram a active."""
    result = (
        sb.table("tenants")
        .select("id")
        .eq("subscription_status", "active")
        .not_.is_("pfx_inactive_since", "null")
        .execute()
    )
    rows = result.data or []
    if not rows:
        return 0

    ids = [t["id"] for t in rows]
    sb.table("tenants").update({"pfx_inactive_since": None}).in_(
        "id", ids
    ).execute()

    for tenant_id in ids:
        audit_log(
            tenant_id=tenant_id,
            user_id=None,
            action="pfx.inactivity_reset",
            resource_type="tenant",
            resource_id=tenant_id,
            details={"reason": "subscription_active"},
            ip_address=None,
        )

    logger.info("pfx_cleanup: %d tenant(s) reativados — countdown resetado", len(ids))
    return len(ids)


def _purge_expired_pfx(sb) -> int:
    """Apaga pfx cifrado para tenants cujo countdown expirou."""
    cutoff = (_now() - timedelta(days=PFX_RETENTION_DAYS)).isoformat()

    expired = (
        sb.table("tenants")
        .select("id, email, pfx_inactive_since")
        .lt("pfx_inactive_since", cutoff)
        .not_.is_("pfx_inactive_since", "null")
        .execute()
    )
    rows = expired.data or []
    if not rows:
        return 0

    purged = 0
    for tenant in rows:
        tenant_id = tenant["id"]

        # Lista certificados do tenant que ainda têm material criptográfico.
        # Como pfx_encrypted é NOT NULL no schema, usamos string vazia como
        # marcador de "purgado" (em vez de NULL).
        certs = (
            sb.table("certificates")
            .select("id, cnpj, pfx_encrypted")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        cert_rows = [c for c in (certs.data or []) if c.get("pfx_encrypted")]
        if not cert_rows:
            continue

        cert_ids = [c["id"] for c in cert_rows]
        sb.table("certificates").update(
            {
                "pfx_encrypted": "",
                "pfx_password_encrypted": "",
                "is_active": False,
            }
        ).in_("id", cert_ids).execute()

        for cert in cert_rows:
            audit_log(
                tenant_id=tenant_id,
                user_id=None,
                action="pfx.purged",
                resource_type="certificate",
                resource_id=cert["id"],
                details={
                    "reason": "lgpd_inactivity_30_days",
                    "inactive_since": tenant["pfx_inactive_since"],
                },
                ip_address=None,
            )
        purged += len(cert_ids)
        logger.info(
            "pfx_cleanup: tenant %s — %d certificado(s) purgados (LGPD)",
            tenant_id,
            len(cert_ids),
        )

    if purged:
        logger.info("pfx_cleanup: total purgado neste run = %d certificados", purged)
    return purged


def cleanup_inactive_pfx() -> dict:
    """Job principal — chamado pelo scheduler 1x/dia.

    Returns:
        dict com contagens das operações realizadas.
    """
    try:
        sb = get_supabase_client()
        marked = _mark_inactive_tenants(sb)
        reset = _reset_returning_tenants(sb)
        purged = _purge_expired_pfx(sb)
        return {"marked": marked, "reset": reset, "purged": purged}
    except Exception as exc:  # noqa: BLE001
        logger.error("pfx_cleanup: erro inesperado: %s", exc, exc_info=True)
        return {"marked": 0, "reset": 0, "purged": 0, "error": str(exc)}
