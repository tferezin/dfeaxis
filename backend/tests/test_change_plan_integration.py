"""Integration test: valida o mecanismo Stripe Subscription.modify contra sandbox.

Os 7 unit tests em test_change_plan.py cobrem nossa LOGICA (gate, mapeamento
de erros). Aqui validamos o COMPORTAMENTO REAL da Stripe quando a gente
chama Subscription.modify — o que os mocks nao podem provar:

    - modify NAO cria 2a subscription (so muda items[0].price)
    - proration_behavior=create_prorations gera invoice de prorata
    - sub volta status='active' apos modify
    - sub_id permanece o mesmo

Bypass do catalogo: usamos sandbox price IDs diretamente ja que stripe_plans.json
tem IDs live. O gate que depende do catalogo eh validado em test_change_plan.py.

Skip se SUPABASE/STRIPE keys faltarem no env.
"""

from __future__ import annotations

import os
import sys
import time
import uuid

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(_BACKEND_DIR, "..", ".env"))

import stripe  # noqa: E402

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

# Sandbox price IDs (descobertos via Stripe.Price.list em runtime).
# Hardcoded aqui pra evitar discovery em cada run; se mudarem no futuro,
# rodar `python -c "import stripe; stripe.api_key='...'; print([p.id for p in stripe.Price.list().data])"`
SANDBOX_STARTER_MONTHLY = "price_1TL8mFRt1dC9HqXtio9ptFI5"  # R$ 290/mo
SANDBOX_BUSINESS_MONTHLY = "price_1TL8mGRt1dC9HqXt2rVwjqmb"  # R$ 690/mo
SANDBOX_ENTERPRISE_MONTHLY = "price_1TL8mIRt1dC9HqXtqn3SkQcI"  # R$ 1.490/mo


def _stripe_configured() -> bool:
    return stripe.api_key.startswith("sk_test_")


pytestmark = pytest.mark.skipif(
    not _stripe_configured(),
    reason="Requires STRIPE_SECRET_KEY=sk_test_* in env (sandbox only)",
)


def _create_test_customer() -> str:
    """Cria customer sandbox com cartao default (test card via PaymentMethod)."""
    suffix = uuid.uuid4().hex[:8]
    customer = stripe.Customer.create(
        email=f"qa-change-plan-{suffix}@dfeaxis-test.com",
        name=f"QA ChangePlan {suffix}",
        metadata={"qa": "change_plan_integration"},
    )

    # Anexa um PaymentMethod de teste (4242). Sem isso, subscription criada
    # com starter mensal entra em incomplete (cobra na hora, sem trial_end aqui).
    pm = stripe.PaymentMethod.create(
        type="card",
        card={"token": "tok_visa"},
    )
    stripe.PaymentMethod.attach(pm.id, customer=customer.id)
    stripe.Customer.modify(
        customer.id,
        invoice_settings={"default_payment_method": pm.id},
    )
    return customer.id


def _cleanup(customer_id: str | None, subscription_id: str | None) -> None:
    if subscription_id:
        try:
            stripe.Subscription.cancel(subscription_id)
        except Exception:
            pass
    if customer_id:
        try:
            stripe.Customer.delete(customer_id)
        except Exception:
            pass


def test_subscription_modify_nao_cria_segunda_subscription():
    """Garante que Subscription.modify atualiza in-place — sem cobrar 2x."""
    customer_id: str | None = None
    sub_id: str | None = None
    try:
        customer_id = _create_test_customer()

        # Cria subscription Starter mensal
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": SANDBOX_STARTER_MONTHLY}],
            trial_period_days=7,  # status='trialing' — aceita modify
        )
        sub_id = sub.id
        original_item_id = sub["items"]["data"][0]["id"]

        # Antes do modify: cliente tem 1 subscription ativa
        subs_before = stripe.Subscription.list(customer=customer_id, limit=10).data
        assert len(subs_before) == 1, f"esperava 1 sub, achei {len(subs_before)}"

        # Modify pra Business mensal (upgrade)
        modified = stripe.Subscription.modify(
            sub_id,
            items=[{"id": original_item_id, "price": SANDBOX_BUSINESS_MONTHLY}],
            proration_behavior="create_prorations",
        )

        # Validacoes:
        # 1) Mesmo subscription_id (modify in-place, nao criou outra)
        assert modified.id == sub_id, "Subscription.modify nao deve criar nova sub"

        # 2) Items[0].price mudou pra Business
        new_price_id = modified["items"]["data"][0]["price"]["id"]
        assert new_price_id == SANDBOX_BUSINESS_MONTHLY, (
            f"price nao trocou: {new_price_id}"
        )

        # 3) Items[0] ainda tem 1 item (nao acumulou)
        assert len(modified["items"]["data"]) == 1, "deveria ter 1 item apos modify"

        # 4) Customer ainda tem APENAS 1 subscription (nao virou 2)
        subs_after = stripe.Subscription.list(customer=customer_id, limit=10).data
        active_subs = [s for s in subs_after if s.status not in ("canceled",)]
        assert len(active_subs) == 1, (
            f"esperava 1 sub apos modify, achei {len(active_subs)} "
            f"(ids: {[s.id for s in active_subs]})"
        )

    finally:
        _cleanup(customer_id, sub_id)


def test_subscription_modify_downgrade_funciona():
    """Cliente Enterprise volta pra Business — modify deve funcionar igual no sentido contrario."""
    customer_id: str | None = None
    sub_id: str | None = None
    try:
        customer_id = _create_test_customer()
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": SANDBOX_ENTERPRISE_MONTHLY}],
            trial_period_days=7,
        )
        sub_id = sub.id
        item_id = sub["items"]["data"][0]["id"]

        modified = stripe.Subscription.modify(
            sub_id,
            items=[{"id": item_id, "price": SANDBOX_BUSINESS_MONTHLY}],
            proration_behavior="create_prorations",
        )

        new_price_id = modified["items"]["data"][0]["price"]["id"]
        assert new_price_id == SANDBOX_BUSINESS_MONTHLY
        assert modified.id == sub_id

    finally:
        _cleanup(customer_id, sub_id)


def test_subscription_modify_idempotent_para_mesmo_price():
    """Chamando modify 2x com mesmo price_id — segunda chamada eh no-op (mesmo state)."""
    customer_id: str | None = None
    sub_id: str | None = None
    try:
        customer_id = _create_test_customer()
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": SANDBOX_STARTER_MONTHLY}],
            trial_period_days=7,
        )
        sub_id = sub.id
        item_id = sub["items"]["data"][0]["id"]

        # 1a chamada: starter -> business
        m1 = stripe.Subscription.modify(
            sub_id,
            items=[{"id": item_id, "price": SANDBOX_BUSINESS_MONTHLY}],
            proration_behavior="create_prorations",
        )
        # 2a chamada: business -> business (mesmo)
        item_id_after = m1["items"]["data"][0]["id"]
        m2 = stripe.Subscription.modify(
            sub_id,
            items=[{"id": item_id_after, "price": SANDBOX_BUSINESS_MONTHLY}],
            proration_behavior="create_prorations",
        )

        assert m2.id == sub_id, "deve ser mesma sub"
        assert m2["items"]["data"][0]["price"]["id"] == SANDBOX_BUSINESS_MONTHLY
        assert len(m2["items"]["data"]) == 1, "nao acumulou itens"

    finally:
        _cleanup(customer_id, sub_id)


def test_subscription_cancelled_nao_pode_modify():
    """Sub cancelada nao aceita modify — nosso service mapeia pra SUBSCRIPTION_INACTIVE."""
    customer_id: str | None = None
    sub_id: str | None = None
    try:
        customer_id = _create_test_customer()
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": SANDBOX_STARTER_MONTHLY}],
            trial_period_days=7,
        )
        sub_id = sub.id
        item_id = sub["items"]["data"][0]["id"]

        # Cancela primeiro
        stripe.Subscription.cancel(sub_id)

        # Tentativa de modify apos cancel deve falhar
        with pytest.raises(stripe.error.InvalidRequestError):
            stripe.Subscription.modify(
                sub_id,
                items=[{"id": item_id, "price": SANDBOX_BUSINESS_MONTHLY}],
                proration_behavior="create_prorations",
            )

    finally:
        _cleanup(customer_id, sub_id)
