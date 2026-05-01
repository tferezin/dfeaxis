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
    # Item M1 — incidentes operacionais que precisam de tratamento explicito.
    # Reembolso e chargeback indicam que o pagamento foi revertido pelo
    # banco/cliente; tratamos como past_due pra suspender acesso ate o
    # cliente regularizar via /billing/portal.
    "charge.refunded",
    "charge.dispute.created",
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
    obj = event["data"]["object"]

    # Claim atômico ANTES do dispatch — evita race condition em entregas
    # paralelas do Stripe. UNIQUE constraint em billing_events.stripe_event_id
    # serializa: apenas um worker insere, os outros recebem dup error e
    # fazem skip. Sem isso, 2 webhooks idênticos chegando junto poderiam
    # ambos passar pelo _is_duplicate antes do _record_event e cobrar 2x.
    if not _record_event(event_id, event_type, obj, tenant_id=None):
        logger.info("Webhook %s already claimed (idempotent skip)", event_id)
        return {"status": "duplicate", "event_id": event_id}

    if event_type not in HANDLED_EVENTS:
        logger.debug("Webhook %s ignored (type=%s)", event_id, event_type)
        return {"status": "ignored", "event_id": event_id, "event_type": event_type}

    try:
        tenant_id = _dispatch(event_type, obj)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Webhook %s failed during dispatch: %s", event_id, exc)
        # Solta o claim pra Stripe poder retentar e reprocessar.
        _release_claim(event_id)
        raise

    # Sucesso — atualiza tenant_id no row já inserido (audit)
    if tenant_id:
        _set_event_tenant(event_id, tenant_id)
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

    # Item M1: refund e dispute — incidentes operacionais.
    if event_type == "charge.refunded":
        return _on_charge_refunded(obj)

    if event_type == "charge.dispute.created":
        return _on_charge_dispute(obj)

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

    # Cria Invoice avulsa de ProRata se agendada no checkout.
    # IMPORTANTE (A1, segurança): se falhar, propaga a exception. O Stripe
    # vai retentar o webhook ate 3 dias com backoff exponencial — assim a
    # ProRata nao se perde silenciosamente. Trade-off: subscription ja foi
    # sincronizada no DB (tenant ve "active"), mas isso ja era o caso antes;
    # a diferenca e que agora a cobranca acontece no retry em vez de virar
    # zero. _release_claim no _dispatch ira liberar o claim pra retry.
    try:
        _create_prorata_invoice_from_metadata(session=session, subscription=sub)
    except Exception as exc:
        logger.error(
            "prorata invoice failed for tenant=%s session=%s — propagando "
            "pra Stripe retentar webhook: %s",
            tenant_id, session.get("id"), exc,
        )
        raise

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

    Idempotência: o claim atômico em billing_events (insert ANTES do dispatch)
    já previne entregas paralelas chegarem aqui em duplicado. Como segunda
    camada, GA4 deduplica `purchase` por `transaction_id` — usamos
    `subscription.id` justamente pra ativar essa proteção adicional.
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

    transaction_id = subscription.get("id") or session.get("id") or "unknown"

    # Guard 4 — não disparar GA4 sem valor concreto. Conversão sem `value`
    # cai no fallback hardcoded da conversion action no painel do Ads
    # (ex: "Se não houver um valor, use R$ 1") e polui o Smart Bidding com
    # ticket inventado. Melhor descartar e investigar o caller pelo log.
    if amount_total_cents is None or amount_total_cents <= 0:
        logger.warning(
            "ga4_purchase_skipped_no_amount transaction_id=%s session_id=%s "
            "subscription_id=%s tenant_id=%s mode=%s livemode=%s price_id=%s",
            transaction_id,
            session.get("id"),
            subscription.get("id"),
            tenant_id,
            session.get("mode"),
            session.get("livemode"),
            price_id,
        )
        return

    value_reais = round(amount_total_cents / 100.0, 2)

    # Instrumentação: log do payload completo de cada disparo. Permite
    # auditar quem chamou _fire_ga4_purchase e cruzar com transaction_id
    # do GA4/Ads quando aparecer divergência.
    logger.info(
        "ga4_purchase_dispatch transaction_id=%s value=%.2f currency=%s "
        "session_id=%s mode=%s livemode=%s tenant_id=%s ga_client_id=%s "
        "item_id=%s",
        transaction_id,
        value_reais,
        currency,
        session.get("id"),
        session.get("mode"),
        session.get("livemode"),
        tenant_id,
        "present" if ga_client_id else "missing",
        item_id,
    )

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
    Aqui sincroniza sub + limpa past_due_since SE a subscription voltou
    pra status='active' (defesa contra: Invoice avulsa de overage paga
    enquanto a renewal principal ainda ta em dunning, ou eventual
    consistency entre invoice.paid e customer.subscription.updated).
    """
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        # Invoice avulsa (ProRata, overage anual) — sem subscription
        # vinculada. Nao mexe em past_due_since; quem decide isso e o
        # invoice.paid da subscription principal.
        return None
    stripe = get_stripe()
    sub = stripe.Subscription.retrieve(subscription_id)
    sync_subscription_to_db(sub)

    tenant_id = (sub.get("metadata") or {}).get("tenant_id")
    sub_status = sub.get("status")

    # Defensive: so limpa past_due_since se a sub estiver active.
    # Se sub.status ainda e 'past_due' (Stripe ainda nao reconciliou ou
    # esta invoice paga e antiga, nao a renewal corrente), preserva o
    # past_due_since pra continuar bloqueando ate a renewal real ser paga.
    if tenant_id and sub_status == "active":
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
    elif tenant_id and sub_status != "active":
        logger.info(
            "invoice.paid recebida mas sub=%s ainda esta status=%s — "
            "preservando past_due_since pra tenant=%s",
            subscription_id, sub_status, tenant_id,
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
# Item M1: handlers de incidentes operacionais (refund / chargeback)
# ---------------------------------------------------------------------------

def _lookup_tenant_by_customer(customer_id: str | None) -> str | None:
    """Resolve tenant_id a partir do Stripe customer_id."""
    if not customer_id:
        return None
    sb = get_supabase_client()
    try:
        res = (
            sb.table("tenants")
            .select("id")
            .eq("stripe_customer_id", customer_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("lookup tenant by customer falhou: %s", exc)
        return None
    if res.data:
        return res.data[0]["id"]
    return None


def _mark_past_due(tenant_id: str, reason: str) -> None:
    """Marca tenant como past_due + stampa past_due_since (idempotente).

    Usado por refund e dispute. Preserva past_due_since se ja setado pra
    nao resetar a contagem do dunning (regra 5+5).
    """
    sb = get_supabase_client()
    try:
        current = sb.table("tenants").select(
            "past_due_since, subscription_status"
        ).eq("id", tenant_id).single().execute()
        existing = current.data or {}
        updates: dict = {"subscription_status": "past_due"}
        if not existing.get("past_due_since"):
            updates["past_due_since"] = datetime.now(timezone.utc).isoformat()
        sb.table("tenants").update(updates).eq("id", tenant_id).execute()
        logger.warning(
            "tenant=%s marcado past_due (motivo=%s)", tenant_id, reason,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "falha ao marcar tenant=%s past_due (%s): %s",
            tenant_id, reason, exc,
        )


def _on_charge_refunded(charge: dict) -> str | None:
    """charge.refunded — pagamento estornado. Suspende acesso ate regularizar.

    Stripe dispara este evento tanto pra refund total quanto parcial. Pra
    simplificar, qualquer refund coloca o tenant em past_due — se for
    legitimo (refund parcial agendado), suporte regulariza manualmente
    via admin. Se for fraude/dispute, ja esta bloqueado.
    """
    customer_id = charge.get("customer")
    tenant_id = _lookup_tenant_by_customer(customer_id)
    amount_refunded = charge.get("amount_refunded") or 0
    logger.error(
        "REFUND charge=%s customer=%s tenant=%s amount_refunded_cents=%s",
        charge.get("id"), customer_id, tenant_id, amount_refunded,
    )
    if tenant_id:
        _mark_past_due(tenant_id, reason="charge.refunded")
    return tenant_id


def _on_charge_dispute(charge: dict) -> str | None:
    """charge.dispute.created — chargeback. Incidente serio: bloqueia + alerta.

    Chargeback significa que o cliente disputou a cobranca no banco. Stripe
    cobra fee de ~$15 USD por dispute, alem de risco de churn forcado.
    Bloqueamos imediatamente — suporte humano precisa entrar em contato.
    """
    customer_id = charge.get("customer")
    tenant_id = _lookup_tenant_by_customer(customer_id)
    amount = charge.get("amount") or 0
    logger.critical(
        "CHARGEBACK charge=%s customer=%s tenant=%s amount_cents=%s "
        "ATENCAO: contato com suporte necessario",
        charge.get("id"), customer_id, tenant_id, amount,
    )
    if tenant_id:
        _mark_past_due(tenant_id, reason="charge.dispute.created")
    return tenant_id


# ---------------------------------------------------------------------------
# Idempotency log (billing_events table)
# ---------------------------------------------------------------------------

def _is_duplicate(event_id: str) -> bool:
    """Verifica se o event_id já foi gravado. Mantido pra compat com testes —
    fluxo de produção usa o claim atômico via _record_event direto."""
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
) -> bool:
    """INSERT no billing_events. Retorna True se gravou, False se já existia.

    Atua como **claim atômico** — quando chamado antes do dispatch, a
    UNIQUE constraint em stripe_event_id serializa entregas paralelas:
    apenas um worker insere, os outros recebem False e fazem skip.
    """
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
        return True
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "duplicate" in msg or "23505" in str(exc) or "already exists" in msg:
            return False
        logger.error("Failed to record billing_event %s: %s", event_id, exc)
        # Erros não-UNIQUE propagam — não queremos prosseguir achando
        # que claimamos quando na verdade falhou.
        raise


def _release_claim(event_id: str) -> None:
    """DELETE row pra permitir retry do Stripe quando dispatch falhou.
    Best-effort: se DELETE falhar, Stripe vai retentar e o retry vai cair
    no caminho 'duplicate' — não é o ideal, mas não causa cobrança errada."""
    sb = get_supabase_client()
    try:
        sb.table("billing_events").delete().eq(
            "stripe_event_id", event_id
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to release claim for %s (Stripe retry vai ser ignorado): %s",
            event_id, exc,
        )


def _set_event_tenant(event_id: str, tenant_id: str) -> None:
    """UPDATE tenant_id no row já claimado. Best-effort (audit only)."""
    sb = get_supabase_client()
    try:
        sb.table("billing_events").update({"tenant_id": tenant_id}).eq(
            "stripe_event_id", event_id
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to update tenant_id for billing_event %s: %s",
            event_id, exc,
        )
