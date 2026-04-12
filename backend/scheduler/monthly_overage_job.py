"""Scheduled job: cálculo mensal de excedente + criação de InvoiceItem no Stripe.

Roda 1x por mês no dia 01, 02:00 UTC.

Para cada tenant com subscription ativa:
1. Calcula excedente do mês anterior (docs_consumidos_mes - docs_included_mes)
2. Se houver excedente > 0:
   - Cria InvoiceItem no Stripe (fica pendurado no customer até a próxima fatura)
   - Registra em monthly_overage_charges (idempotência + auditoria)
3. Zera docs_consumidos_mes via reset_monthly_counter()

Idempotência: UNIQUE (tenant_id, ciclo_mes) garante que rodar 2x no mesmo mês
não duplica a cobrança.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from db.supabase import get_supabase_client
from services.billing.plans import get_plan_by_price_id
from services.billing.stripe_client import get_stripe

logger = logging.getLogger(__name__)


def _previous_month_first_day() -> date:
    """Retorna o primeiro dia do mês anterior ao atual."""
    today = date.today()
    if today.month == 1:
        return date(today.year - 1, 12, 1)
    return date(today.year, today.month - 1, 1)


def _already_charged(tenant_id: str, ciclo_mes: date) -> bool:
    """Verifica idempotência — se já cobrou esse ciclo para esse tenant."""
    sb = get_supabase_client()
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
        logger.warning("idempotency lookup failed for tenant %s: %s", tenant_id, exc)
        return False


def _get_tenant_overage_rate(tenant: dict) -> Optional[int]:
    """Retorna overage_cents_per_doc baseado no plano (via stripe_price_id)."""
    price_id = tenant.get("stripe_price_id")
    if not price_id:
        return None
    lookup = get_plan_by_price_id(price_id)
    if not lookup:
        logger.warning("price_id %s não encontrado no catálogo", price_id)
        return None
    return lookup.plan.overage_cents_per_doc


def process_monthly_overage() -> None:
    """Job principal — roda no dia 1 de cada mês."""
    sb = get_supabase_client()
    stripe = get_stripe()
    ciclo_mes = _previous_month_first_day()

    logger.info("process_monthly_overage: iniciando ciclo %s", ciclo_mes)

    # Busca tenants ativos com contador > 0
    try:
        result = (
            sb.table("tenants")
            .select(
                "id, company_name, email, stripe_customer_id, stripe_price_id, "
                "docs_consumidos_mes, docs_included_mes"
            )
            .eq("subscription_status", "active")
            .gt("docs_consumidos_mes", 0)
            .execute()
        )
    except Exception as exc:
        logger.error("process_monthly_overage: query tenants failed: %s", exc)
        return

    tenants = result.data or []
    logger.info("process_monthly_overage: %d tenants com uso no ciclo", len(tenants))

    processed = 0
    skipped = 0
    errors = 0

    for tenant in tenants:
        tenant_id = tenant["id"]
        consumed = tenant.get("docs_consumidos_mes") or 0
        included = tenant.get("docs_included_mes") or 0
        excedente_docs = max(0, consumed - included)

        # Idempotência
        if _already_charged(tenant_id, ciclo_mes):
            logger.info("tenant %s já cobrado no ciclo %s, pulando", tenant_id, ciclo_mes)
            skipped += 1
            continue

        # Se não houve excedente, apenas registra (para manter histórico) e reseta
        if excedente_docs == 0:
            try:
                sb.table("monthly_overage_charges").insert({
                    "tenant_id": tenant_id,
                    "ciclo_mes": ciclo_mes.isoformat(),
                    "docs_consumidos": consumed,
                    "docs_included": included,
                    "excedente_docs": 0,
                    "excedente_cents": 0,
                    "stripe_invoice_item_id": None,
                }).execute()
                sb.rpc("reset_monthly_counter", {"p_tenant_id": tenant_id}).execute()
                processed += 1
                continue
            except Exception as exc:
                logger.error("insert zero-overage failed for %s: %s", tenant_id, exc)
                errors += 1
                continue

        # Calcula valor do excedente
        rate_cents = _get_tenant_overage_rate(tenant)
        if rate_cents is None:
            logger.error("tenant %s sem rate definido — pulando", tenant_id)
            errors += 1
            continue

        excedente_cents = excedente_docs * rate_cents
        customer_id = tenant.get("stripe_customer_id")

        if not customer_id:
            logger.error("tenant %s sem stripe_customer_id — pulando", tenant_id)
            errors += 1
            continue

        # Cria InvoiceItem no Stripe (fica pendurado até a próxima fatura do ciclo)
        try:
            invoice_item = stripe.InvoiceItem.create(
                customer=customer_id,
                amount=excedente_cents,
                currency="brl",
                description=(
                    f"Excedente de documentos — {ciclo_mes.strftime('%m/%Y')} "
                    f"({excedente_docs} docs × R$ {rate_cents / 100:.2f})"
                ),
                metadata={
                    "tenant_id": tenant_id,
                    "ciclo_mes": ciclo_mes.isoformat(),
                    "excedente_docs": str(excedente_docs),
                },
            )
            logger.info(
                "InvoiceItem criado: tenant=%s ciclo=%s docs=%d valor=R$%.2f id=%s",
                tenant_id, ciclo_mes, excedente_docs, excedente_cents / 100,
                invoice_item.id,
            )
        except Exception as exc:
            logger.error("stripe InvoiceItem.create failed for %s: %s", tenant_id, exc)
            errors += 1
            continue

        # Registra na tabela de histórico (idempotência futura)
        try:
            sb.table("monthly_overage_charges").insert({
                "tenant_id": tenant_id,
                "ciclo_mes": ciclo_mes.isoformat(),
                "docs_consumidos": consumed,
                "docs_included": included,
                "excedente_docs": excedente_docs,
                "excedente_cents": excedente_cents,
                "stripe_invoice_item_id": invoice_item.id,
            }).execute()
        except Exception as exc:
            logger.error("insert overage row failed for %s: %s", tenant_id, exc)
            # Stripe já criou o item — não deletamos. Registra erro mas continua.

        # Reseta contador do mês novo
        try:
            sb.rpc("reset_monthly_counter", {"p_tenant_id": tenant_id}).execute()
        except Exception as exc:
            logger.error("reset_monthly_counter failed for %s: %s", tenant_id, exc)

        processed += 1

    logger.info(
        "process_monthly_overage: concluído — processados=%d, pulados=%d, erros=%d",
        processed, skipped, errors,
    )
