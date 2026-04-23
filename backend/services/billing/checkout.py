"""Stripe Checkout Session creation.

ProRata na primeira cobranca (Fase 4.5 — decisao D8):
- Cliente assina no meio do mes → primeira fatura proporcional aos dias
  que faltam ate o proximo billing_day.
- Segunda fatura em diante → valor cheio no billing_day (5/10/15).
- Regra do minimo: se o valor proporcional for menor que R$ 50 (5000
  centavos), a gente da os dias restantes de cortesia e so comeca a cobrar
  no primeiro billing_day completo. Evita cobranca esquisita tipo R$ 19.
- Aplica pra plano mensal E anual — pro anual o calculo usa o valor anual
  distribuido por 365 dias, o que da valores muito acima do minimo em
  praticamente qualquer cenario razoavel.
"""

from __future__ import annotations

import calendar
import logging
from datetime import datetime, timezone
from typing import Literal

from config import settings

from .customers import ensure_customer
from .plans import get_plan_by_price_id
from .stripe_client import get_stripe

logger = logging.getLogger("dfeaxis.billing.checkout")

# Limite minimo em centavos — abaixo disso, dias restantes viram cortesia
PRORATION_MIN_CENTS = 5000  # R$ 50,00


def _compute_next_billing_anchor(
    billing_day: int, now: datetime
) -> datetime:
    """Retorna o timestamp do proximo billing_day a partir de `now` (UTC).

    Regras:
    - Se hoje < billing_day no mes atual → anchor e billing_day deste mes
    - Caso contrario → anchor e billing_day do proximo mes
    - Quando billing_day nao existe no mes (ex: 31 em Fev), usa o ultimo dia
      do mes — mas como permitimos so 5/10/15, isso nunca acontece na pratica

    Anchor sempre a meia-noite UTC do dia escolhido.
    """
    if now.day < billing_day:
        year, month = now.year, now.month
    else:
        # Proximo mes
        if now.month == 12:
            year, month = now.year + 1, 1
        else:
            year, month = now.year, now.month + 1

    # Safety: clamp ao ultimo dia do mes se billing_day > days_in_month
    last_day = calendar.monthrange(year, month)[1]
    day = min(billing_day, last_day)

    return datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)


def _estimate_proration_cents(
    price_id: str, now: datetime, anchor: datetime
) -> int | None:
    """Estima o valor da proracao em centavos.

    Retorna None se nao conseguir mapear o price_id pro catalogo
    (ex: price de teste manual nao cadastrado em stripe_plans.json).

    Heuristica:
    - Mensal: monthly_amount_cents / 30 * dias_restantes
    - Anual: yearly_amount_cents / 365 * dias_restantes

    Stripe vai recalcular exato no checkout (pode dar alguns centavos de
    diferenca por contagem de dias). A gente so usa pra decidir se
    aplica o minimo de R$ 50 ou nao.
    """
    lookup = get_plan_by_price_id(price_id)
    if not lookup:
        return None

    days_remaining = max(0, (anchor - now).days)
    if days_remaining == 0:
        return 0

    plan = lookup.plan
    if lookup.period == "yearly":
        daily_cents = plan.yearly_amount_cents / 365
    else:
        daily_cents = plan.monthly_amount_cents / 30

    return int(daily_cents * days_remaining)


def create_checkout_session(
    tenant_id: str,
    price_id: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
    mode: Literal["subscription", "payment"] = "subscription",
    billing_day: int = 5,
) -> dict:
    """Creates a Stripe Checkout Session for the tenant + price.

    Pra subscriptions, aplica ProRata na primeira cobranca:
    - Subscription comeca agora mas anchora no proximo billing_day do tenant
    - Stripe cobra proporcional automaticamente no checkout
    - Se ProRata estimada < R$ 50, usa `trial_end` pro Stripe dar esses dias
      de cortesia — cliente paga R$ 0 no checkout e a primeira fatura cheia
      sai no billing_day
    """
    customer_id = ensure_customer(tenant_id)
    stripe = get_stripe()

    session_metadata = {"tenant_id": tenant_id, "billing_day": str(billing_day)}

    subscription_data: dict = {"metadata": session_metadata}

    if mode == "subscription":
        now = datetime.now(timezone.utc)
        anchor = _compute_next_billing_anchor(billing_day, now)
        anchor_ts = int(anchor.timestamp())
        proration_cents = _estimate_proration_cents(price_id, now, anchor)

        if proration_cents is None:
            # Price fora do catalogo (teste manual). Sem ProRata — Stripe
            # cobra ciclo cheio no checkout e inicia ciclo normal.
            logger.warning(
                "price_id %s nao esta no catalogo — checkout sem ProRata",
                price_id,
            )
        elif proration_cents < PRORATION_MIN_CENTS:
            # Cortesia: dias restantes de graca. Trial_end == anchor faz o
            # Stripe nao cobrar nada hoje e iniciar cobranca cheia no
            # primeiro billing_day.
            subscription_data["trial_end"] = anchor_ts
            logger.info(
                "Checkout c/ cortesia: tenant=%s proration=%d cents < %d → "
                "trial_end=%s",
                tenant_id, proration_cents, PRORATION_MIN_CENTS,
                anchor.isoformat(),
            )
        else:
            # ProRata padrao: anchor no proximo billing_day, Stripe cobra
            # proporcional no checkout.
            subscription_data["billing_cycle_anchor"] = anchor_ts
            subscription_data["proration_behavior"] = "create_prorations"
            logger.info(
                "Checkout c/ ProRata: tenant=%s proration≈%d cents anchor=%s",
                tenant_id, proration_cents, anchor.isoformat(),
            )

    session = stripe.checkout.Session.create(
        mode=mode,
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url or settings.stripe_checkout_success_url,
        cancel_url=cancel_url or settings.stripe_checkout_cancel_url,
        client_reference_id=tenant_id,
        metadata=session_metadata,
        allow_promotion_codes=True,
        subscription_data=subscription_data if mode == "subscription" else None,
    )

    logger.info(
        "Created checkout session %s for tenant %s price %s",
        session.id,
        tenant_id,
        price_id,
    )
    return {"id": session.id, "url": session.url}
