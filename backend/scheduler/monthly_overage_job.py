"""Scheduled job: cálculo mensal de excedente + cobrança no Stripe.

Roda 1x por mês no dia 01, 02:00 UTC.

Para cada tenant com subscription ativa:
1. Calcula excedente do mês anterior (docs_consumidos_mes - docs_included_mes)
2. Se houver excedente > 0:
   a. Plano MENSAL: cria InvoiceItem pendurado → vai na próxima fatura da
      subscription (que é no mês que vem — perfeito).
   b. Plano ANUAL: cria Invoice AVULSA imediata (InvoiceItem + Invoice.create
      + finalize). Senão o excedente ficaria pendurado esperando 1 ano até
      a próxima renovação anual — user seria cobrado só em Abril/2027 pelo
      excedente de Abril/2026.
3. Registra em monthly_overage_charges (idempotência + auditoria)
4. Zera docs_consumidos_mes via reset_monthly_counter()

Idempotência: UNIQUE (tenant_id, ciclo_mes) garante que rodar 2x no mesmo mês
não duplica a cobrança.

Decisão D9 do planejamento: excedente é um "produto separado" do ciclo — cobra
mensalmente independente do plano ser mensal ou anual.
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


def _is_yearly_plan(tenant: dict) -> bool:
    """Detecta se tenant esta em plano anual (pra decidir cobranca avulsa)."""
    price_id = tenant.get("stripe_price_id")
    if not price_id:
        return False
    lookup = get_plan_by_price_id(price_id)
    if not lookup:
        return False
    return lookup.period == "yearly"


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

        # Decide o fluxo de cobranca:
        # - Plano MENSAL: InvoiceItem pendurado — entra na proxima fatura do
        #   subscription, que e mes que vem. OK.
        # - Plano ANUAL: InvoiceItem + Invoice avulsa imediata. Senao ficaria
        #   pendurado esperando 1 ano pra proxima renovacao anual.
        is_yearly = _is_yearly_plan(tenant)
        description = (
            f"Excedente de documentos — {ciclo_mes.strftime('%m/%Y')} "
            f"({excedente_docs} docs × R$ {rate_cents / 100:.2f})"
        )
        invoice_item_id: Optional[str] = None
        invoice_id: Optional[str] = None

        try:
            invoice_item = stripe.InvoiceItem.create(
                customer=customer_id,
                amount=excedente_cents,
                currency="brl",
                description=description,
                metadata={
                    "tenant_id": tenant_id,
                    "ciclo_mes": ciclo_mes.isoformat(),
                    "excedente_docs": str(excedente_docs),
                    "plan_period": "yearly" if is_yearly else "monthly",
                },
            )
            invoice_item_id = invoice_item.id

            if is_yearly:
                # Fatura avulsa imediata — nao espera o ciclo anual
                invoice = stripe.Invoice.create(
                    customer=customer_id,
                    collection_method="charge_automatically",
                    auto_advance=True,
                    description=(
                        f"Excedente mensal — {ciclo_mes.strftime('%m/%Y')}"
                    ),
                    metadata={
                        "tenant_id": tenant_id,
                        "ciclo_mes": ciclo_mes.isoformat(),
                        "type": "yearly_overage_standalone",
                    },
                )
                # Finaliza pra cobrar automatic via cartao do customer
                stripe.Invoice.finalize_invoice(invoice.id)
                invoice_id = invoice.id

                logger.info(
                    "Invoice anual avulsa criada: tenant=%s ciclo=%s docs=%d "
                    "valor=R$%.2f invoice=%s",
                    tenant_id, ciclo_mes, excedente_docs,
                    excedente_cents / 100, invoice_id,
                )
            else:
                logger.info(
                    "InvoiceItem mensal pendurado: tenant=%s ciclo=%s docs=%d "
                    "valor=R$%.2f id=%s",
                    tenant_id, ciclo_mes, excedente_docs,
                    excedente_cents / 100, invoice_item_id,
                )
        except Exception as exc:
            logger.error(
                "stripe cobranca excedente falhou for %s (yearly=%s): %s",
                tenant_id, is_yearly, exc,
            )
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
                "stripe_invoice_item_id": invoice_item_id,
                "stripe_invoice_id": invoice_id,  # null pra mensal; set pra anual
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
