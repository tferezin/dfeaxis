"""Job dia 1: snapshot do mes anterior + reset do contador mensal.

Roda as 02:00 do dia 1 de cada mes em **horario de Sao Paulo** (05:00 UTC).
Importante usar SP tz: o usuario ve o "mes" no fuso local. Se o job
rodasse antes da meia-noite SP (ex: 02:00 UTC = 23:00 SP do dia 30),
docs capturados entre 23:00-23:59 SP do dia 30 nao entrariam no snapshot
do mes que acabou — bug fiscal/financeiro.

Fluxo:
1. Snapshot — pra cada tenant com subscription ativa:
   - Le docs_consumidos_mes (valor final do mes que acabou)
   - Calcula excedente = max(0, consumidos - incluidos)
   - Insere row em monthly_overage_charges (idempotente via UNIQUE ciclo_mes)
   - Campos stripe_invoice_item_id e stripe_invoice_id ficam NULL — serao
     preenchidos pelo monthly_overage_job do dia 5 (faturamento).
2. Reset — zera docs_consumidos_mes=0 pra todos os tenants ativos.

Separamos snapshot (dia 1) de faturamento (dia 5) porque:
- Dashboard do cliente fica honesto a partir do dia 1 (mes novo = contador
  zero, uso acumulado real do mes corrente)
- Cobrança acontece no billing_day do tenant (dia 5), respeitando a regra
  do produto "cobranca no dia 5 do mes seguinte"
- Snapshot no dia 1 congela o valor final do mes anterior antes do reset,
  garantindo que ninguem perde historico
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

# Modelo de billing e baseado no calendario brasileiro (mes do tenant =
# mes em horario de Sao Paulo). Calculos de "hoje" e "mes anterior"
# DEVEM usar SP tz, nao UTC, mesmo se o servidor estiver em UTC.
_BR_TZ = ZoneInfo("America/Sao_Paulo")


def _today_br() -> date:
    """Data corrente no fuso de Sao Paulo (UTC-3)."""
    return datetime.now(_BR_TZ).date()


def _previous_month_first_day() -> date:
    """Retorna o primeiro dia do mes anterior ao atual (em SP tz)."""
    today = _today_br()
    if today.month == 1:
        return date(today.year - 1, 12, 1)
    return date(today.year, today.month - 1, 1)


def _already_snapshotted(
    sb, tenant_id: str, ciclo_mes: date
) -> bool:
    """Idempotencia — se ja tirou snapshot desse ciclo pra esse tenant."""
    try:
        result = (
            sb.table("monthly_overage_charges")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("ciclo_mes", ciclo_mes.isoformat())
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception as exc:
        logger.warning(
            "idempotency lookup failed for tenant %s: %s", tenant_id, exc
        )
        return False


def _reset_tenant_counter(sb, tenant_id: str) -> bool:
    """Reseta docs_consumidos_mes=0 pra um unico tenant. Retorna True se ok."""
    try:
        sb.rpc("reset_monthly_counter", {"p_tenant_id": tenant_id}).execute()
        return True
    except Exception:
        try:
            sb.table("tenants").update(
                {"docs_consumidos_mes": 0}
            ).eq("id", tenant_id).execute()
            return True
        except Exception as exc:
            logger.error(
                "reset docs_consumidos_mes failed for %s: %s", tenant_id, exc
            )
            return False


def _snapshot_and_reset_tenant(
    sb, tenant: dict, ciclo_mes: date
) -> tuple[bool, bool]:
    """Snapshot + reset atomicos por tenant.

    Retorna (snapshot_ok, reset_ok). Se snapshot_ok=True mas reset_ok=False,
    tem risco do tenant ficar com counter nao zerado mesmo apos snapshot —
    logs vao sinalizar pra intervencao manual. Ordem importa: snapshot
    PRIMEIRO pra garantir historico antes de perder o valor.
    """
    tenant_id = tenant["id"]

    if _already_snapshotted(sb, tenant_id, ciclo_mes):
        logger.debug(
            "snapshot ja existe pra tenant=%s ciclo=%s — so reset",
            tenant_id, ciclo_mes,
        )
        # Ja snapshot-ou numa execucao anterior mas pode ter crashado antes
        # de resetar. Garante o reset agora (idempotente).
        return (True, _reset_tenant_counter(sb, tenant_id))

    consumed = tenant.get("docs_consumidos_mes") or 0
    included = tenant.get("docs_included_mes") or 0
    excedente_docs = max(0, consumed - included)

    try:
        sb.table("monthly_overage_charges").insert({
            "tenant_id": tenant_id,
            "ciclo_mes": ciclo_mes.isoformat(),
            "docs_consumidos": consumed,
            "docs_included": included,
            "excedente_docs": excedente_docs,
            "excedente_cents": 0,  # recalculado no dia 5 (monthly_overage_job)
            "stripe_invoice_item_id": None,
            "stripe_invoice_id": None,
        }).execute()
    except Exception as exc:
        logger.error(
            "snapshot insert failed for tenant=%s: %s", tenant_id, exc
        )
        return (False, False)

    # Reset imediatamente apos snapshot — se crashar depois, proxima execucao
    # pula o snapshot (_already_snapshotted) mas tenta o reset de novo.
    reset_ok = _reset_tenant_counter(sb, tenant_id)
    if not reset_ok:
        logger.error(
            "tenant %s snapshotted mas reset falhou — dashboard pode "
            "mostrar docs_consumidos_mes incorreto ate proxima execucao",
            tenant_id,
        )
    return (True, reset_ok)


def process_monthly_snapshot_reset() -> None:
    """Job principal — roda dia 1 as 02:00 UTC.

    Snapshot + reset sao feitos por tenant, atomicamente. Se crashar no
    meio, os tenants ja processados ficam consistentes (snapshot + reset
    ambos feitos). Tenants nao processados serao pegos na proxima execucao.
    """
    sb = get_supabase_client()
    ciclo_mes = _previous_month_first_day()

    logger.info(
        "process_monthly_snapshot_reset: iniciando ciclo %s", ciclo_mes
    )

    try:
        result = (
            sb.table("tenants")
            .select(
                "id, docs_consumidos_mes, docs_included_mes, "
                "subscription_status"
            )
            # Inclui past_due pra manter historico do mes anterior mesmo
            # se o pagamento falhou — cobranca e decidida no dia 5.
            .in_("subscription_status", ["active", "past_due"])
            .execute()
        )
    except Exception as exc:
        logger.error("query tenants failed: %s", exc)
        return

    tenants = result.data or []
    logger.info(
        "process_monthly_snapshot_reset: %d tenants ativos/past_due", len(tenants)
    )

    snapshots_ok = 0
    resets_ok = 0
    errors = 0

    for tenant in tenants:
        snap_ok, reset_ok = _snapshot_and_reset_tenant(sb, tenant, ciclo_mes)
        if snap_ok:
            snapshots_ok += 1
        else:
            errors += 1
        if reset_ok:
            resets_ok += 1

    logger.info(
        "process_monthly_snapshot_reset: concluido — snapshots=%d "
        "resets=%d erros=%d",
        snapshots_ok, resets_ok, errors,
    )
