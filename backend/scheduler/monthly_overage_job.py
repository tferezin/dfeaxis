"""Job dia 5: apuracao + faturamento do excedente do mes anterior.

Roda as 02:00 do dia 5 de cada mes em **horario de Sao Paulo** (05:00 UTC).
Por convencao atual, billing_day = 5 pra todos os tenants (configuracao
padronizada). Se no futuro os tenants puderem escolher billing_day
diferente (10/15), este job filtrara por billing_day=today.day em SP tz.

Depende do snapshot feito no dia 1 (monthly_snapshot_reset_job). Aqui a
gente apenas le esse snapshot e processa:

1. Busca rows em monthly_overage_charges do mes anterior cujo
   stripe_invoice_item_id ainda e NULL (nao foram cobradas)
2. Pra cada row, calcula excedente_cents com overage_cents_per_doc atual
3. Pra tenants com excedente > 0:
   - Cria InvoiceItem pendurado no Stripe
   - Atualiza row com stripe_invoice_item_id + excedente_cents
4. Pros tenants ANUAIS:
   - Cria Invoice avulsa (charge_automatically + auto_advance=True)
   - Finalize_invoice → Stripe cobra na hora via cartao salvo
   - Atualiza row com stripe_invoice_id
5. Pros tenants MENSAIS:
   - Nao faz mais nada aqui. Stripe cobra automaticamente na subscription
     renewal (anchor configurado no checkout pra ser dia 5). InvoiceItem
     pendurado entra nessa fatura.

Idempotencia: filtro `stripe_invoice_item_id IS NULL` garante que rodar
2x no mesmo dia nao duplica cobranca.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from db.supabase import get_supabase_client
from services.billing.plans import get_plan_by_price_id
from services.billing.stripe_client import get_stripe

logger = logging.getLogger(__name__)

# Vide monthly_snapshot_reset_job — billing usa calendario SP, nao UTC.
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


def _get_plan_info(
    stripe_price_id: str | None,
) -> tuple[Optional[int], bool]:
    """Retorna (overage_cents_per_doc, is_yearly) pro price_id do tenant."""
    if not stripe_price_id:
        return (None, False)
    lookup = get_plan_by_price_id(stripe_price_id)
    if not lookup:
        logger.warning(
            "price_id %s nao encontrado no catalogo", stripe_price_id
        )
        return (None, False)
    return (lookup.plan.overage_cents_per_doc, lookup.period == "yearly")


def _create_invoice_item(
    stripe,
    customer_id: str,
    tenant_id: str,
    excedente_docs: int,
    excedente_cents: int,
    rate_cents: int,
    ciclo_mes: date,
) -> Optional[str]:
    """Cria InvoiceItem pendurado no Stripe."""
    description = (
        f"Excedente de documentos — {ciclo_mes.strftime('%m/%Y')} "
        f"({excedente_docs} docs x R$ {rate_cents / 100:.2f})"
    )
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
                "type": "monthly_overage",
            },
        )
        return invoice_item.id
    except Exception as exc:
        logger.error(
            "stripe InvoiceItem.create failed for %s: %s", tenant_id, exc
        )
        return None


def _create_and_finalize_invoice(
    stripe,
    customer_id: str,
    tenant_id: str,
    ciclo_mes: date,
) -> Optional[str]:
    """Cria Invoice avulsa (pra plano anual) e finaliza — cobra na hora.

    pending_invoice_items_behavior='include' garante que o InvoiceItem
    de excedente criado logo acima entra nessa Invoice avulsa, e nao no
    proximo ciclo de renewal do subscription anual (que so cobra em 12
    meses). Sem esse flag, Stripe pode decidir pendurar o item ate la.

    Idempotency: usa ciclo_mes+tenant_id como chave — 2 execucoes do mesmo
    job no mesmo dia retornam a mesma Invoice em vez de duplicar.
    """
    idempotency_key = f"yearly-overage-{tenant_id}-{ciclo_mes.isoformat()}"
    try:
        invoice = stripe.Invoice.create(
            customer=customer_id,
            collection_method="charge_automatically",
            auto_advance=True,
            pending_invoice_items_behavior="include",
            description=(
                f"Excedente — competencia {ciclo_mes.strftime('%m/%Y')}"
            ),
            metadata={
                "tenant_id": tenant_id,
                "type": "yearly_overage_standalone",
                "ciclo_mes": ciclo_mes.isoformat(),
            },
            idempotency_key=idempotency_key,
        )
        stripe.Invoice.finalize_invoice(invoice.id)
        return invoice.id
    except Exception as exc:
        logger.error(
            "stripe Invoice.create/finalize failed for %s: %s",
            tenant_id, exc,
        )
        return None


def process_monthly_overage() -> None:
    """Job principal — roda dia 5 as 02:00 UTC.

    Le snapshots do dia 1 (monthly_overage_charges com stripe_invoice_item_id
    IS NULL) e processa o faturamento.
    """
    sb = get_supabase_client()
    stripe = get_stripe()
    ciclo_mes = _previous_month_first_day()

    logger.info(
        "process_monthly_overage: iniciando faturamento do ciclo %s",
        ciclo_mes,
    )

    # Busca snapshots pendentes de cobranca
    try:
        snapshots_result = (
            sb.table("monthly_overage_charges")
            .select(
                "id, tenant_id, docs_consumidos, docs_included, "
                "excedente_docs"
            )
            .eq("ciclo_mes", ciclo_mes.isoformat())
            .is_("stripe_invoice_item_id", "null")
            .execute()
        )
    except Exception as exc:
        logger.error("query snapshots failed: %s", exc)
        return

    snapshots = snapshots_result.data or []
    logger.info(
        "process_monthly_overage: %d snapshots pendentes no ciclo %s",
        len(snapshots), ciclo_mes,
    )

    charged_monthly = 0
    charged_yearly = 0
    no_overage = 0
    errors = 0

    # Busca tenants relacionados em lote (evita N+1)
    tenant_ids = [s["tenant_id"] for s in snapshots]
    if not tenant_ids:
        logger.info("process_monthly_overage: nada a cobrar")
        return

    try:
        tenants_result = (
            sb.table("tenants")
            .select(
                "id, stripe_customer_id, stripe_price_id, billing_day, "
                "subscription_status"
            )
            .in_("id", tenant_ids)
            # Cobra tenants ativos E past_due (consumiu antes de cancelar).
            # Cancelados/expirados nao sao cobrados — ja resolveram o fim
            # via portal/suporte e ja pagaram ou nao pagaram.
            .in_("subscription_status", ["active", "past_due"])
            .execute()
        )
    except Exception as exc:
        logger.error("query tenants failed: %s", exc)
        return

    tenants_by_id = {t["id"]: t for t in (tenants_result.data or [])}

    for snapshot in snapshots:
        snapshot_id = snapshot["id"]
        tenant_id = snapshot["tenant_id"]
        excedente_docs = snapshot["excedente_docs"] or 0

        tenant = tenants_by_id.get(tenant_id)
        if not tenant:
            logger.warning(
                "snapshot %s aponta pra tenant %s que nao existe ou nao "
                "esta ativo — pulando",
                snapshot_id, tenant_id,
            )
            errors += 1
            continue

        # Filtro de billing_day — so processa tenants cujo billing_day e
        # hoje (em SP tz). Hoje por padrao e 5 pra todos os tenants;
        # mantemos a validacao pra preparar o futuro onde tenants poderao
        # escolher entre 5/10/15 e isso vai rodar em dias diferentes.
        today = _today_br()
        if tenant.get("billing_day") != today.day:
            continue

        # Sem excedente — marca snapshot como processado (stripe_invoice_item_id
        # com valor sentinela NO_OVERAGE) pra nao reprocessar na proxima
        # execucao do mesmo dia (ex: retry apos crash).
        if excedente_docs == 0:
            try:
                sb.table("monthly_overage_charges").update(
                    {"stripe_invoice_item_id": "NO_OVERAGE"}
                ).eq("id", snapshot_id).execute()
            except Exception as exc:
                logger.warning(
                    "nao consegui marcar snapshot %s como NO_OVERAGE: %s",
                    snapshot_id, exc,
                )
            no_overage += 1
            continue

        # Calcula excedente_cents com rate atual do catalogo
        rate_cents, is_yearly = _get_plan_info(tenant.get("stripe_price_id"))
        if rate_cents is None:
            logger.error(
                "tenant %s sem rate definido — pulando", tenant_id
            )
            errors += 1
            continue

        excedente_cents = excedente_docs * rate_cents
        customer_id = tenant.get("stripe_customer_id")
        if not customer_id:
            logger.error(
                "tenant %s sem stripe_customer_id — pulando", tenant_id
            )
            errors += 1
            continue

        # Passo 1: cria InvoiceItem pendurado (ambos planos)
        invoice_item_id = _create_invoice_item(
            stripe, customer_id, tenant_id, excedente_docs,
            excedente_cents, rate_cents, ciclo_mes,
        )
        if not invoice_item_id:
            errors += 1
            continue

        update_row: dict = {
            "excedente_cents": excedente_cents,
            "stripe_invoice_item_id": invoice_item_id,
        }

        # Passo 2: pra anual, cria Invoice avulsa e finaliza (cobra na hora)
        if is_yearly:
            invoice_id = _create_and_finalize_invoice(
                stripe, customer_id, tenant_id, ciclo_mes,
            )
            if invoice_id:
                update_row["stripe_invoice_id"] = invoice_id
                charged_yearly += 1
                logger.info(
                    "Plano anual — invoice avulsa finalizada: tenant=%s "
                    "invoice=%s valor=R$%.2f",
                    tenant_id, invoice_id, excedente_cents / 100,
                )
            else:
                # InvoiceItem criado mas Invoice falhou — deixa pendurado
                # e alerta. Proxima rodada pode tentar de novo (mas ai o
                # InvoiceItem ja existe; pode duplicar).
                errors += 1
                logger.error(
                    "tenant %s (anual): InvoiceItem criado mas Invoice "
                    "falhou. Intervencao manual pode ser necessaria.",
                    tenant_id,
                )
        else:
            # Plano mensal — Stripe cobra na subscription renewal
            charged_monthly += 1
            logger.info(
                "Plano mensal — InvoiceItem pendurado: tenant=%s "
                "invoice_item=%s valor=R$%.2f",
                tenant_id, invoice_item_id, excedente_cents / 100,
            )

        # Atualiza snapshot
        try:
            sb.table("monthly_overage_charges").update(update_row).eq(
                "id", snapshot_id
            ).execute()
        except Exception as exc:
            logger.error(
                "update snapshot %s failed: %s", snapshot_id, exc
            )

    logger.info(
        "process_monthly_overage: concluido — mensal=%d anual=%d "
        "sem_excedente=%d erros=%d",
        charged_monthly, charged_yearly, no_overage, errors,
    )
