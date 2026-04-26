"""Stripe Checkout Session creation.

Modelo de cobranca: mes calendario + billing_day separados (decisao D8 do
planejamento, refinada em 23/Abril):

- Ciclo de uso: mes calendario (dia 1 a 30/31). Reset de contador no dia 1.
- Billing_day: data de cobranca (5/10/15), SEMPRE no mes seguinte ao
  consumo. Ex: uso de Abril e cobrado dia 5 de Maio.
- Primeira cobranca (adesao): ProRata baseado em dias restantes do mes
  calendario corrente. Se ProRata >= R$ 50, cobra imediato via Invoice
  avulsa. Se < R$ 50, da de cortesia. Subscription Stripe sempre comeca
  a cobrar mesmo na proxima competencia (billing_day do mes seguinte).

Formula da ProRata:
    proration = (dias_restantes_do_mes / dias_do_mes) * valor_mensal

    Onde dias_restantes_do_mes = last_day_of_month - today.day
    (cliente que assina dia 4 num mes de 30 dias: 30 - 4 = 26 dias)

Stripe subscription na adesao:
- billing_cycle_anchor = timestamp do proximo billing_day do mes seguinte
- proration_behavior = 'none' (desabilita ProRata nativo — fazemos manualmente)
- trial_end = billing_cycle_anchor (subscription nao cobra nada ate o anchor)

Ex: cliente Starter assina dia 4/Abril, billing_day=5:
- Anchor = 5/Maio (proximo mes)
- ProRata = 26/30 * R$290 = R$251,33 -> Invoice avulsa cobra hoje
- Dia 5/Maio: subscription cobra R$ 290 (mensalidade de Maio)

Ex: cliente Starter assina dia 30/Abril, billing_day=5:
- Anchor = 5/Maio
- ProRata = 0/30 * R$290 = R$ 0 (ou 1/30 dependendo se incluir o dia 30)
  -> abaixo de R$ 50: nao cria Invoice avulsa (cortesia)
- Dia 5/Maio: subscription cobra R$ 290 (mensalidade de Maio)
"""

from __future__ import annotations

import calendar
import logging
import os
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

from config import settings

from .customers import ensure_customer
from .plans import get_plan_by_price_id
from .stripe_client import get_stripe

logger = logging.getLogger("dfeaxis.billing.checkout")

# Limite minimo em centavos — abaixo disso, ProRata vira cortesia
PRORATION_MIN_CENTS = 5000  # R$ 50,00

# Por convencao atual, todos os tenants cobram no dia 5 do mes seguinte.
# No futuro podemos aceitar 10/15 — o schema ja tem a coluna billing_day.
# Por enquanto qualquer outro valor e ignorado e sobreescrito pra 5.
DEFAULT_BILLING_DAY = 5
_ALLOWED_BILLING_DAYS = (5, 10, 15)


# ---------------------------------------------------------------------------
# Redirect URL allowlist (R4 — defesa contra open redirect via Stripe checkout)
# ---------------------------------------------------------------------------

_DEFAULT_ALLOWED_HOSTS = (
    "dfeaxis.com.br",
    "www.dfeaxis.com.br",
    "localhost:3000",
)
_DEFAULT_FALLBACK_URL = "https://dfeaxis.com.br/dashboard?checkout=success"


def _allowed_redirect_hosts() -> tuple[str, ...]:
    """Le ALLOWED_REDIRECT_HOSTS do env (csv), fallback pros hosts default."""
    raw = os.getenv("ALLOWED_REDIRECT_HOSTS", "").strip()
    if not raw:
        return _DEFAULT_ALLOWED_HOSTS
    parsed = tuple(h.strip().lower() for h in raw.split(",") if h.strip())
    return parsed or _DEFAULT_ALLOWED_HOSTS


def _validate_redirect_url(url: str | None, fallback: str) -> str:
    """Valida URL de redirect contra allowlist. Rejeita open redirect.

    Cliente passa success_url/cancel_url no body do checkout request, e Stripe
    redireciona o usuario pra esse URL apos checkout. Se nao validamos, atacante
    pode passar `https://evil.com` e usar checkout legitimo da DFeAxis pra
    fazer phishing (URL na barra do browser comeca com checkout.stripe.com).

    Regras:
    - URL ausente -> usa fallback
    - URL sem scheme http(s) -> usa fallback
    - hostname (com port se houver) nao na allowlist -> usa fallback + warning
    - URL valido -> retorna como veio
    """
    if not url:
        return fallback

    try:
        parsed = urlparse(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("URL de redirect invalida (%s): %s — usando fallback", url, exc)
        return fallback

    if parsed.scheme not in ("http", "https"):
        logger.warning(
            "URL de redirect com scheme nao-http (%s) — usando fallback",
            parsed.scheme,
        )
        return fallback

    if not parsed.netloc:
        logger.warning("URL de redirect sem host (%s) — usando fallback", url)
        return fallback

    # netloc inclui port se houver. Comparacao case-insensitive.
    netloc = parsed.netloc.lower()
    allowed = _allowed_redirect_hosts()
    if netloc not in allowed:
        logger.warning(
            "URL de redirect para host nao permitido (%s) — usando fallback. "
            "Allowlist: %s",
            netloc, ",".join(allowed),
        )
        return fallback

    return url


def _compute_next_billing_anchor(
    billing_day: int, now: datetime
) -> datetime:
    """Retorna o timestamp do billing_day do MES SEGUINTE a partir de `now` (UTC).

    Modelo mes calendario: subscription Stripe sempre ancora no mes que vem,
    pra que a primeira cobranca cheia cubra a competencia completa do mes
    seguinte. O ProRata dos dias restantes do mes corrente e cobrado a
    parte (Invoice avulsa imediata).

    Quando billing_day nao existe no mes seguinte (ex: 31 em Fev), usaria
    o ultimo dia. Mas defensivamente: validamos billing_day in (5, 10, 15)
    pra prevenir bypass futuro (ex: novo endpoint que nao valida, ou
    write direto no banco). Assim nao precisamos confiar no caller.
    """
    if billing_day not in _ALLOWED_BILLING_DAYS:
        raise ValueError(
            f"billing_day deve ser um de {_ALLOWED_BILLING_DAYS}, "
            f"recebido {billing_day}"
        )

    # Sempre pula pro mes seguinte
    if now.month == 12:
        year, month = now.year + 1, 1
    else:
        year, month = now.year, now.month + 1

    last_day = calendar.monthrange(year, month)[1]
    day = min(billing_day, last_day)

    return datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)


def _compute_prorata_cents(
    price_id: str, now: datetime
) -> tuple[int | None, int]:
    """Calcula ProRata em centavos — so pra plano MENSAL.

    Formula: (dias_restantes / dias_do_mes) * valor_mensal.
    dias_restantes = last_day_of_month - now.day + 1 (inclui o dia de
    adesao como dia consumido — cliente que assina dia 30 tem 1 dia).

    - Plano mensal: cobra ProRata proporcional
    - Plano anual: retorna (0, 0) — plano anual cobra valor cheio na
      adesao, sem ProRata (decisao do usuario 23/Abril)

    Retorna (proration_cents, dias_restantes) ou (None, 0) se o price_id
    nao estiver no catalogo.
    """
    lookup = get_plan_by_price_id(price_id)
    if not lookup:
        return (None, 0)

    # Plano anual nao usa ProRata — cobra cheio na adesao
    if lookup.period == "yearly":
        return (0, 0)

    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_remaining = days_in_month - now.day + 1

    if days_remaining <= 0:
        return (0, 0)

    plan = lookup.plan
    proration_cents = int(
        plan.monthly_amount_cents * days_remaining / days_in_month
    )
    return (proration_cents, days_remaining)


def create_prorata_invoice(
    customer_id: str,
    proration_cents: int,
    days_remaining: int,
    month_label: str,
    tenant_id: str,
    idempotency_session_id: str | None = None,
) -> str | None:
    """Cria e finaliza uma Invoice avulsa com ProRata da adesao.

    Fluxo Stripe:
      1. InvoiceItem.create — adiciona valor avulso no customer
      2. Invoice.create — fatura com pending_invoice_items_behavior='include'
         pra GARANTIR que o InvoiceItem pendurado entra nessa fatura e nao
         na proxima renewal da subscription
      3. Invoice.finalize_invoice — cobra automaticamente via cartao salvo

    Idempotencia: quando `idempotency_session_id` e passado (id da Checkout
    Session), usamos como idempotency_key do Stripe. Isso impede cobranca
    dupla caso o webhook checkout.session.completed seja reentregue antes
    do billing_events persistir — Stripe retorna o mesmo InvoiceItem em
    vez de criar outro.

    Retorna invoice.id se criou, None se falhou (logado, nao propaga).
    Customer precisa ter default_payment_method setado em invoice_settings
    (garantido pelo _sync_default_payment_method no webhook).
    """
    stripe = get_stripe()
    item_idempotency_key = (
        f"prorata-item-{idempotency_session_id}"
        if idempotency_session_id
        else None
    )
    invoice_idempotency_key = (
        f"prorata-invoice-{idempotency_session_id}"
        if idempotency_session_id
        else None
    )
    try:
        stripe.InvoiceItem.create(
            customer=customer_id,
            amount=proration_cents,
            currency="brl",
            description=(
                f"ProRata da adesao — {days_remaining} dia(s) restante(s) "
                f"de {month_label}"
            ),
            metadata={
                "tenant_id": tenant_id,
                "type": "prorata_adesao",
                "days_remaining": str(days_remaining),
            },
            idempotency_key=item_idempotency_key,
        )
        invoice = stripe.Invoice.create(
            customer=customer_id,
            collection_method="charge_automatically",
            auto_advance=True,
            # Garante que o InvoiceItem criado acima (pending) entra nesta
            # Invoice avulsa, nao na proxima renewal do subscription anual.
            pending_invoice_items_behavior="include",
            description=f"ProRata da adesao — {month_label}",
            metadata={
                "tenant_id": tenant_id,
                "type": "prorata_adesao",
            },
            idempotency_key=invoice_idempotency_key,
        )
        stripe.Invoice.finalize_invoice(invoice.id)
        logger.info(
            "ProRata Invoice criada: tenant=%s days=%d amount_cents=%d invoice=%s",
            tenant_id, days_remaining, proration_cents, invoice.id,
        )
        return invoice.id
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Falha ao criar Invoice de ProRata pra tenant=%s: %s",
            tenant_id, exc,
        )
        return None


def create_checkout_session(
    tenant_id: str,
    price_id: str,
    success_url: str | None = None,
    cancel_url: str | None = None,
    mode: Literal["subscription", "payment"] = "subscription",
    billing_day: int = DEFAULT_BILLING_DAY,
) -> dict:
    """Creates a Stripe Checkout Session for the tenant + price.

    Pra subscriptions, aplica modelo "mes calendario":
    - Subscription Stripe anchora no billing_day do mes seguinte
    - ProRata do mes corrente e tratada manualmente (Invoice avulsa pos-checkout)
    - Se ProRata < R$ 50, da de cortesia (nao cria Invoice avulsa)

    Nota: a Invoice avulsa de ProRata so e criada APOS o checkout (quando
    o cartao ja foi capturado). Aqui no checkout apenas configuramos a
    subscription pra nao cobrar nada ate o anchor. A Invoice avulsa e
    disparada via webhook customer.subscription.created que ja existe.

    Alternativamente, a gente poderia criar a InvoiceItem pendurada aqui
    mesmo e deixar Stripe cobrar na primeira fatura — mas isso nao funciona
    com trial_end (trial bloqueia cobranca via subscription). Entao:
    Invoice avulsa separada via webhook.
    """
    # R3: valida price_id contra catalogo ANTES de criar Customer / chamar
    # Stripe. Cliente nao pode criar checkout pra price_id arbitrario (ex:
    # outro produto, plano descontinuado, price desativado). Stripe ate
    # aceita price_id qualquer e cobra, mas dai a gente fatura/contabilidade
    # interna fica torta. Faz sense reusar a mesma allowlist do catalogo.
    if mode == "subscription":
        if not get_plan_by_price_id(price_id):
            raise ValueError(
                f"price_id {price_id} nao esta no catalogo de planos"
            )

    customer_id = ensure_customer(tenant_id)
    stripe = get_stripe()

    # R4: valida success_url/cancel_url contra allowlist pra evitar open
    # redirect via checkout legitimo (atacante usa nosso checkout pra
    # phishing redirecionando pra dominio dele).
    safe_success_url = _validate_redirect_url(
        success_url or settings.stripe_checkout_success_url,
        fallback=_DEFAULT_FALLBACK_URL,
    )
    safe_cancel_url = _validate_redirect_url(
        cancel_url or settings.stripe_checkout_cancel_url,
        fallback=_DEFAULT_FALLBACK_URL,
    )

    # Por enquanto todos os tenants cobram dia 5 (unica data suportada pelo
    # monthly_overage_job). Se no futuro suportarmos 10/15, a validacao
    # aqui deve aceitar esses valores e o job precisa ser adaptado.
    if billing_day != DEFAULT_BILLING_DAY:
        logger.info(
            "billing_day %d recebido mas forcando pra %d (unica opcao atual)",
            billing_day, DEFAULT_BILLING_DAY,
        )
        billing_day = DEFAULT_BILLING_DAY

    session_metadata = {"tenant_id": tenant_id, "billing_day": str(billing_day)}

    subscription_data: dict = {"metadata": session_metadata}

    if mode == "subscription":
        lookup = get_plan_by_price_id(price_id)
        is_yearly = bool(lookup and lookup.period == "yearly")

        if is_yearly:
            # Plano anual: checkout Stripe padrao — cobra valor cheio na
            # adesao, plano renova no mesmo dia do ano seguinte. Sem
            # ProRata, sem anchor, sem trial_end. Simples.
            session_metadata["plan_period"] = "yearly"
            logger.info(
                "Checkout ANUAL: tenant=%s price=%s — cobra cheio na adesao",
                tenant_id, price_id,
            )
        else:
            # Plano mensal: modelo mes calendario
            # - Subscription ancora no dia 5 do mes seguinte (trial_end ate la)
            # - Proration padrao Stripe desabilitado
            # - ProRata proprio sera cobrada via Invoice avulsa (se >= R$ 50)
            now = datetime.now(timezone.utc)
            anchor = _compute_next_billing_anchor(billing_day, now)
            anchor_ts = int(anchor.timestamp())
            proration_cents, days_remaining = _compute_prorata_cents(
                price_id, now
            )

            subscription_data["billing_cycle_anchor"] = anchor_ts
            subscription_data["proration_behavior"] = "none"
            subscription_data["trial_end"] = anchor_ts
            session_metadata["plan_period"] = "monthly"

            # Stash no metadata pra o webhook saber se deve criar Invoice
            # avulsa de ProRata apos o checkout completar (cartao capturado).
            if (
                proration_cents is not None
                and proration_cents >= PRORATION_MIN_CENTS
            ):
                subscription_data["metadata"]["prorata_cents"] = str(
                    proration_cents
                )
                subscription_data["metadata"]["prorata_days"] = str(
                    days_remaining
                )
                logger.info(
                    "Checkout MENSAL c/ ProRata: tenant=%s dias=%d "
                    "valor_cents=%d anchor=%s",
                    tenant_id, days_remaining, proration_cents,
                    anchor.isoformat(),
                )
            elif proration_cents is not None:
                logger.info(
                    "Checkout MENSAL c/ cortesia (ProRata %d cents < %d): "
                    "tenant=%s anchor=%s",
                    proration_cents, PRORATION_MIN_CENTS, tenant_id,
                    anchor.isoformat(),
                )
            else:
                logger.warning(
                    "price_id %s nao esta no catalogo — sem ProRata",
                    price_id,
                )

    session = stripe.checkout.Session.create(
        mode=mode,
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=safe_success_url,
        cancel_url=safe_cancel_url,
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
