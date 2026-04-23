"""Alertas operacionais expostos via API.

Substitui o antigo sistema de notificacao por email. O ERP do cliente
consulta este endpoint quando quiser (polling curto, daily, on-demand) e
reage conforme a propria logica dele.

Cada alerta tem um `id` deterministico baseado no evento logico — ex:
`cert_expiring:12345678000190:2026-05-11`. O id nao muda enquanto a
condicao continuar verdadeira. Isso permite o ERP deduplicar localmente
sem precisar ackear no servidor.
"""

from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends

from db.supabase import get_supabase_client
from middleware.security import verify_jwt_or_api_key

router = APIRouter()


def _parse_date(value: Any) -> Optional[date]:
    """Aceita date, datetime, ou string ISO — devolve date ou None."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            # Suporta "2026-05-11", "2026-05-11T00:00:00", "2026-05-11T00:00:00+00:00"
            s_norm = s.replace("Z", "+00:00")
            if "T" in s_norm:
                return datetime.fromisoformat(s_norm).date()
            return date.fromisoformat(s_norm[:10])
        except (ValueError, TypeError):
            return None
    return None


def _build_cert_alerts(certs: list[dict]) -> list[dict]:
    """Cert A1 vence em 1 ano. Alerta em 2 faixas:
    - warning: 8-30 dias  -> tempo pra renovar sem stress
    - critical: <= 7 dias OU ja vencido -> bloqueio iminente/atual
    """
    today = date.today()
    alerts = []
    for cert in certs:
        valid_until = _parse_date(cert.get("valid_until"))
        if not valid_until:
            continue
        days = (valid_until - today).days
        cnpj = cert.get("cnpj") or ""
        vu_iso = valid_until.isoformat()

        if days < 0:
            alerts.append({
                "id": f"cert_expired:{cnpj}:{vu_iso}",
                "type": "cert_expired",
                "severity": "critical",
                "message": f"Certificado A1 vencido ha {abs(days)} dia(s)",
                "metadata": {
                    "cnpj": cnpj,
                    "valid_until": vu_iso,
                    "days_overdue": abs(days),
                },
            })
        elif days <= 7:
            alerts.append({
                "id": f"cert_expiring:{cnpj}:{vu_iso}",
                "type": "cert_expiring",
                "severity": "critical",
                "message": f"Certificado A1 expira em {days} dia(s)",
                "metadata": {
                    "cnpj": cnpj,
                    "valid_until": vu_iso,
                    "days_remaining": days,
                },
            })
        elif days <= 30:
            alerts.append({
                "id": f"cert_expiring:{cnpj}:{vu_iso}",
                "type": "cert_expiring",
                "severity": "warning",
                "message": f"Certificado A1 expira em {days} dias",
                "metadata": {
                    "cnpj": cnpj,
                    "valid_until": vu_iso,
                    "days_remaining": days,
                },
            })
    return alerts


def _build_trial_alert(tenant: dict) -> Optional[dict]:
    """Trial termina por tempo OU por cap de documentos — o que vier primeiro."""
    if tenant.get("subscription_status") not in ("trial", "trialing"):
        return None

    trial_expires = _parse_date(tenant.get("trial_expires_at"))
    trial_cap = tenant.get("trial_cap") or 500
    docs_used = tenant.get("docs_consumidos_trial") or 0
    docs_remaining = max(0, trial_cap - docs_used)

    days_remaining: Optional[int] = None
    if trial_expires:
        days_remaining = (trial_expires - date.today()).days

    # Alerta se qualquer uma das condicoes estiver proxima do fim
    near_time = days_remaining is not None and days_remaining <= 3
    near_cap = docs_remaining <= 50

    if not (near_time or near_cap):
        return None

    severity = "critical" if (
        (days_remaining is not None and days_remaining <= 1)
        or docs_remaining <= 10
    ) else "warning"

    # id muda por faixa de tempo/uso pra reativar alerta quando piora:
    # "trial_ending:YYYY-MM-DD:docs_used" — docs_used muda ao consumir
    vu_iso = trial_expires.isoformat() if trial_expires else "no-date"
    bucket = docs_used // 25  # bucket de 25 em 25 docs pra nao mudar toda captura
    alert_id = f"trial_ending:{vu_iso}:b{bucket}"

    parts = []
    if days_remaining is not None:
        parts.append(f"{days_remaining} dia(s)")
    parts.append(f"{docs_remaining} documento(s) restantes")
    message = "Trial termina em " + " ou ".join(parts)

    return {
        "id": alert_id,
        "type": "trial_ending",
        "severity": severity,
        "message": message,
        "metadata": {
            "days_remaining": days_remaining,
            "docs_remaining": docs_remaining,
            "trial_cap": trial_cap,
            "docs_used": docs_used,
        },
    }


def _build_usage_alert(tenant: dict) -> Optional[dict]:
    """Consumo mensal >= 90% do incluido no plano pago."""
    if tenant.get("subscription_status") != "active":
        return None

    docs_used = tenant.get("docs_consumidos_mes") or 0
    docs_included = tenant.get("docs_included_mes") or 0
    if docs_included <= 0:
        return None

    pct = (docs_used / docs_included) * 100
    if pct < 90:
        return None

    # Faixas: 90, 95, 100+ — id muda ao subir faixa
    if pct >= 100:
        faixa = "over"
    elif pct >= 95:
        faixa = "95"
    else:
        faixa = "90"

    month_key = date.today().strftime("%Y-%m")
    docs_remaining = max(0, docs_included - docs_used)
    severity = "critical" if pct >= 100 else "warning"

    return {
        "id": f"high_usage:{month_key}:{faixa}",
        "type": "high_usage" if pct < 100 else "usage_exceeded",
        "severity": severity,
        "message": (
            f"Consumo em {int(pct)}% do plano mensal"
            if pct < 100
            else f"Consumo excedeu o plano em {int(pct - 100)}%"
        ),
        "metadata": {
            "pct_used": int(pct),
            "docs_used": docs_used,
            "docs_included": docs_included,
            "docs_remaining": docs_remaining,
            "month": month_key,
        },
    }


@router.get("/alerts")
async def list_alerts(auth: dict = Depends(verify_jwt_or_api_key)):
    """Lista alertas operacionais ativos do tenant.

    Substitui o disparo de email — o ERP consulta e reage.

    Tipos suportados:
    - `cert_expiring` (warning: 8-30 dias | critical: 0-7 dias)
    - `cert_expired` (certificado ja vencido)
    - `trial_ending` (tempo ou cap proximo do fim)
    - `high_usage` (consumo >= 90% do plano)
    - `usage_exceeded` (consumo > 100% do plano)

    Cada alerta tem `id` deterministico. Se a condicao nao mudou, o id
    tambem nao muda — use isso pra deduplicar no seu ERP.
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    alerts: list[dict] = []

    # Certificados ativos do tenant
    certs_res = sb.table("certificates").select(
        "cnpj, valid_until"
    ).eq("tenant_id", tenant_id).eq("is_active", True).execute()
    alerts.extend(_build_cert_alerts(certs_res.data or []))

    # Tenant (trial + uso mensal)
    tenant_res = sb.table("tenants").select(
        "subscription_status, trial_expires_at, trial_cap, "
        "docs_consumidos_trial, docs_consumidos_mes, docs_included_mes"
    ).eq("id", tenant_id).single().execute()
    tenant = tenant_res.data or {}

    trial_alert = _build_trial_alert(tenant)
    if trial_alert:
        alerts.append(trial_alert)

    usage_alert = _build_usage_alert(tenant)
    if usage_alert:
        alerts.append(usage_alert)

    return {
        "alerts": alerts,
        "total": len(alerts),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
