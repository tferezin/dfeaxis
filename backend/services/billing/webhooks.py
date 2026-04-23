"""Stripe webhook event dispatcher with idempotency.

The handler is intentionally minimal: each event type maps to a small
function. Idempotency is enforced via the billing_events table — duplicate
deliveries are no-ops.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from db.supabase import get_supabase_client
from services.billing.plans import get_plan_by_price_id
from services.tracking import send_purchase_event

from .stripe_client import get_stripe
from .subscriptions import sync_subscription_to_db

logger = logging.getLogger("dfeaxis.billing.webhooks")


# Event types we care about
HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
}


def handle_webhook_event(
    payload: bytes,
    signature: str,
    webhook_secret: str,
) -> dict:
    """Verifies signature, dispatches the event, returns a status dict.

    Raises stripe.error.SignatureVerificationError if signature is invalid.
    """
    stripe = get_stripe()

    event = stripe.Webhook.construct_event(
        payload=payload,
        sig_header=signature,
        secret=webhook_secret,
    )

    event_id: str = event["id"]
    event_type: str = event["type"]

    # Idempotency check — if we've seen this event_id, skip
    if _is_duplicate(event_id):
        logger.info("Webhook %s already processed (idempotent skip)", event_id)
        return {"status": "duplicate", "event_id": event_id}

    if event_type not in HANDLED_EVENTS:
        logger.debug("Webhook %s ignored (type=%s)", event_id, event_type)
        _record_event(event_id, event_type, event["data"]["object"], tenant_id=None)
        return {"status": "ignored", "event_id": event_id, "event_type": event_type}

    try:
        tenant_id = _dispatch(event_type, event["data"]["object"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Webhook %s failed during dispatch: %s", event_id, exc)
        # Don't record on failure so retry can re-process
        raise

    _record_event(event_id, event_type, event["data"]["object"], tenant_id=tenant_id)
    return {
        "status": "processed",
        "event_id": event_id,
        "event_type": event_type,
        "tenant_id": tenant_id,
    }


def _dispatch(event_type: str, obj: dict[str, Any]) -> str | None:
    """Routes a Stripe event to its handler. Returns the affected tenant_id."""
    if event_type == "checkout.session.completed":
        return _on_checkout_completed(obj)

    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        return _on_subscription_change(obj)

    if event_type == "invoice.paid":
        return _on_invoice_paid(obj)

    if event_type == "invoice.payment_failed":
        return _on_invoice_failed(obj)

    return None


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def _on_checkout_completed(session: dict) -> str | None:
    """User completed checkout. Pull the subscription, sync, fire GA4 purchase.

    Este é o ponto de conversão real do negócio: trial → cliente pagante.
    Disparamos o evento `purchase` no GA4 via Measurement Protocol para que
    a campanha do Google Ads otimize por receita real, não só por cadastros.

    Tambem e aqui que criamos a Invoice avulsa de ProRata (se houver). No
    checkout.py agendamos via metadata (prorata_cents) — aqui lemos e
    cobramos. Isso e separado da subscription porque a sub tem trial_end
    ate o billing_cycle_anchor — sem cobranca recorrente ate la.
    """
    tenant_id = (session.get("metadata") or {}).get("tenant_id") or session.get(
        "client_reference_id"
    )
    subscription_id = session.get("subscription")
    if not subscription_id:
        logger.warning(
            "checkout.session.completed without subscription id (mode=%s)",
            session.get("mode"),
        )
        return tenant_id

    stripe = get_stripe()
    sub = stripe.Subscription.retrieve(subscription_id)
    sync_subscription_to_db(sub)

    # CRITICO: copia o default_payment_method da subscription pro customer
    # root. Sem isso, Invoice avulsa com charge_automatically nao cobra
    # (fatura fica em status=open esperando pagamento manual). Precisa ser
    # feito ANTES de criar a Invoice de ProRata.
    try:
        _sync_default_payment_method(stripe, sub)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "sync default_payment_method failed for session=%s: %s",
            session.get("id"), exc,
        )

    # Cria Invoice avulsa de ProRata se agendada no checkout. Nao falha o
    # webhook se nao der — logamos e seguimos, subscription ja foi criada.
    try:
        _create_prorata_invoice_from_metadata(session=session, subscription=sub)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "prorata invoice failed for tenant=%s session=%s: %s",
            tenant_id, session.get("id"), exc,
        )

    # Dispara purchase no GA4 via Measurement Protocol.
    # Tracking NUNCA pode quebrar o webhook — qualquer erro vira warning log.
    try:
        _fire_ga4_purchase(session=session, subscription=sub, tenant_id=tenant_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ga4 purchase fire failed for tenant=%s session=%s: %s",
            tenant_id, session.get("id"), exc,
        )

    return tenant_id


def _sync_default_payment_method(stripe, subscription: dict) -> None:
    """Copia subscription.default_payment_method pro customer.invoice_settings.

    Stripe Checkout atrela o cartao ao payment_method da subscription, mas
    NAO ao customer root. Invoice avulsa com charge_automatically busca o
    metodo no customer.invoice_settings.default_payment_method — se nao
    tiver, fatura fica em 'open' sem cobrar. Essa funcao garante que o
    customer tenha o mesmo payment_method da sub pra Invoices avulsas
    futuras (ProRata, overage anual) cobrem automaticamente.
    """
    customer_id = subscription.get("customer")
    pm_id = subscription.get("default_payment_method")
    if not customer_id or not pm_id:
        return
    try:
        stripe.Customer.modify(
            customer_id,
            invoice_settings={"default_payment_method": pm_id},
        )
        logger.info(
            "default_payment_method sincronizado pro customer=%s pm=%s",
            customer_id, pm_id,
        )
    except Exception as exc:
        logger.error(
            "Customer.modify default_payment_method falhou: customer=%s pm=%s %s",
            customer_id, pm_id, exc,
        )


def _create_prorata_invoice_from_metadata(
    *, session: dict, subscription: dict
) -> None:
    """Le prorata_cents/prorata_days do metadata e cria a Invoice avulsa.

    Agendado no checkout.py via subscription_data.metadata. A gente chama
    aqui apos a subscription estar criada e o cartao capturado — momento
    correto pra debitar o ProRata imediatamente.
    """
    # Metadata pode estar na session ou na sub (ambos apontam pro mesmo dict
    # no create_checkout_session). Usamos o que tiver.
    metadata = subscription.get("metadata") or session.get("metadata") or {}
    prorata_cents_str = metadata.get("prorata_cents")
    if not prorata_cents_str:
        return  # sem ProRata — cortesia ou erro de catalogo

    try:
        prorata_cents = int(prorata_cents_str)
        prorata_days = int(metadata.get("prorata_days") or 0)
    except (TypeError, ValueError):
        logger.warning(
            "ProRata metadata invalida na session=%s: cents=%r days=%r",
            session.get("id"),
            prorata_cents_str,
            metadata.get("prorata_days"),
        )
        return

    tenant_id = metadata.get("tenant_id") or session.get("client_reference_id")
    customer_id = subscription.get("customer") or session.get("customer")
    if not customer_id or not tenant_id:
        logger.warning(
            "ProRata sem customer/tenant — session=%s customer=%s tenant=%s",
            session.get("id"), customer_id, tenant_id,
        )
        return

    # Label amigavel do mes (pt-BR)
    now = datetime.now(timezone.utc)
    month_label = now.strftime("%m/%Y")

    # Import tardio pra evitar ciclo (checkout.py importa nada deste modulo,
    # mas webhook.py ja importa de varios lugares)
    from services.billing.checkout import create_prorata_invoice

    create_prorata_invoice(
        customer_id=customer_id,
        proration_cents=prorata_cents,
        days_remaining=prorata_days,
        month_label=month_label,
        tenant_id=tenant_id,
        # Idempotency: se webhook for reentregue, Stripe retorna mesmo InvoiceItem
        # em vez de duplicar a cobranca.
        idempotency_session_id=session.get("id"),
    )


def _fire_ga4_purchase(
    *,
    session: dict,
    subscription: dict,
    tenant_id: str | None,
) -> None:
    """Dispara evento `purchase` server-side para GA4 via Measurement Protocol.

    Separado do handler principal para facilitar teste unitário e isolamento
    de erros (o caller já faz try/except).

    Idempotência: retries do Stripe são sequenciais, mas a janela entre a
    verificação de duplicata em `handle_webhook_event` e o insert em
    `_record_event` permite race condition teórica. Contra isso, confiamos
    em 2 camadas:
      1. `billing_events.stripe_event_id` tem UNIQUE constraint (insert race
         resolvido pelo banco)
      2. O GA4 deduplica eventos `purchase` pelo `transaction_id` — vamos
         usar `subscription.id` como transaction_id justamente pra ativar
         esse mecanismo de segurança adicional.
    """
    # Busca ga_client_id do tenant (capturado no cookie _ga durante signup).
    ga_client_id: str | None = None
    if tenant_id:
        sb = get_supabase_client()
        res = (
            sb.table("tenants")
            .select("ga_client_id")
            .eq("id", tenant_id)
            .limit(1)
            .execute()
        )
        if res.data:
            ga_client_id = res.data[0].get("ga_client_id")

    # Descobre o valor pago. Preferimos o amount da session (é o que o Stripe
    # efetivamente cobrou); fallback pro plano via price_id da subscription.
    amount_total_cents = session.get("amount_total")
    currency = (session.get("currency") or "brl").upper()

    items = (subscription.get("items") or {}).get("data") or []
    first_item = items[0] if items else {}
    # first_item vazio → .get() devolve None, sem necessidade de else extra.
    price_id = (first_item.get("price") or {}).get("id")

    item_id: str | None = None
    item_name: str | None = None
    if price_id:
        lookup = get_plan_by_price_id(price_id)
        if lookup:
            item_id = lookup.plan.key
            item_name = f"DFeAxis {lookup.plan.name}"
            if amount_total_cents is None:
                amount_total_cents = (
                    lookup.plan.yearly_amount_cents
                    if lookup.period == "yearly"
                    else lookup.plan.monthly_amount_cents
                )

    if amount_total_cents is None:
        amount_total_cents = 0

    value_reais = round(amount_total_cents / 100.0, 2)

    transaction_id = subscription.get("id") or session.get("id") or "unknown"

    send_purchase_event(
        client_id=ga_client_id,
        transaction_id=transaction_id,
        value_brl=value_reais,
        currency=currency,
        item_id=item_id,
        item_name=item_name,
    )


def _on_subscription_change(subscription: dict) -> str | None:
    """customer.subscription.{created,updated,deleted} — re-sync."""
    sync_subscription_to_db(subscription)
    return (subscription.get("metadata") or {}).get("tenant_id")


def _on_invoice_paid(invoice: dict) -> str | None:
    """Renewal payment succeeded — keep tenant active + limpa past_due_since.

    NOTA: o reset de docs_consumidos_mes NAO acontece mais aqui. Reset esta
    no monthly_overage_job (scheduler) que roda no dia 1 de cada mes
    calendario. Assim o ciclo de apuracao e sempre o mes calendario (dia 1
    a 30/31), independente do billing_day do tenant ser 5, 10 ou 15.

    Stripe manda invoice.paid tanto na compra inicial quanto em cada renewal.
    Aqui sincroniza sub + limpa past_due_since (se estava em dunning, pagou
    agora, reset).
    """
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return None
    stripe = get_stripe()
    sub = stripe.Subscription.retrieve(subscription_id)
    sync_subscription_to_db(sub)

    tenant_id = (sub.get("metadata") or {}).get("tenant_id")
    if tenant_id:
        # Limpa past_due_since — pagou, sai do dunning
        try:
            sb = get_supabase_client()
            sb.table("tenants").update({"past_due_since": None}).eq(
                "id", tenant_id
            ).execute()
        except Exception as exc:
            logger.warning(
                "nao consegui limpar past_due_since pra tenant=%s: %s",
                tenant_id, exc,
            )

    return tenant_id


def _on_invoice_failed(invoice: dict) -> str | None:
    """Payment failed — marca past_due + stampa past_due_since pra dunning.

    Stripe vai fazer retry automatico nos proximos dias (configurado na conta).
    A gente usa past_due_since pra calcular quantos dias restam ate o
    bloqueio (regra 5+5: 5 dias de tolerancia a partir da primeira falha).

    Se o retry passar mais tarde, webhook invoice.paid limpa past_due_since.
    """
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return None
    stripe = get_stripe()
    sub = stripe.Subscription.retrieve(subscription_id)
    sync_subscription_to_db(sub)

    tenant_id = (sub.get("metadata") or {}).get("tenant_id")
    if tenant_id:
        sb = get_supabase_client()
        # So marca past_due_since se ainda nao tem (preserva data da PRIMEIRA
        # falha pra dunning. Se cliente falhar dia 5 e dia 8, o D-dia pra
        # bloqueio e contado a partir do dia 5, nao do dia 8).
        try:
            current = sb.table("tenants").select("past_due_since").eq(
                "id", tenant_id
            ).single().execute()
            if not current.data or not current.data.get("past_due_since"):
                sb.table("tenants").update({
                    "past_due_since": datetime.now(timezone.utc).isoformat(),
                }).eq("id", tenant_id).execute()
                logger.info(
                    "past_due_since marcado pra tenant=%s (primeira falha)",
                    tenant_id,
                )
        except Exception as exc:
            logger.warning(
                "nao consegui atualizar past_due_since pra tenant=%s: %s",
                tenant_id, exc,
            )

    return tenant_id


# ---------------------------------------------------------------------------
# Idempotency log (billing_events table)
# ---------------------------------------------------------------------------

def _is_duplicate(event_id: str) -> bool:
    sb = get_supabase_client()
    res = (
        sb.table("billing_events")
        .select("id")
        .eq("stripe_event_id", event_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def _record_event(
    event_id: str,
    event_type: str,
    payload: dict,
    tenant_id: str | None,
) -> None:
    sb = get_supabase_client()
    try:
        sb.table("billing_events").insert(
            {
                "tenant_id": tenant_id,
                "stripe_event_id": event_id,
                "event_type": event_type,
                "payload": json.loads(json.dumps(payload, default=str)),
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001
        # If the row already exists (race condition between two webhook
        # deliveries), the UNIQUE constraint will reject — that's fine.
        if "duplicate" not in str(exc).lower() and "23505" not in str(exc):
            logger.error("Failed to record billing_event %s: %s", event_id, exc)
