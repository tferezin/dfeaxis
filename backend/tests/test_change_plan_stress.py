"""Stress test concurrente: N requests paralelas de change-plan.

Cobre cenarios reais de usuario:
- Duplo-clique no botao "Mudar para X" → 2 chamadas paralelas
- Network retry no frontend → mesma request 2-3x
- Cliente em tab dupla disparando trocas diferentes simultaneamente

Validacoes:
1. Stripe.Subscription.modify NAO acumula items (fica sempre com 1)
2. Final state e DETERMINISTICO ou pelo menos consistente (ultimo write vence)
3. Customer continua com EXATAMENTE 1 subscription
4. Sem subscriptions zumbis ou erros silenciosos
"""

from __future__ import annotations

import concurrent.futures
import os
import sys
import time
import uuid
from typing import Any

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(_BACKEND_DIR, "..", ".env"))

import stripe  # noqa: E402

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

SANDBOX_STARTER = "price_1TL8mFRt1dC9HqXtio9ptFI5"
SANDBOX_BUSINESS = "price_1TL8mGRt1dC9HqXt2rVwjqmb"
SANDBOX_ENTERPRISE = "price_1TL8mIRt1dC9HqXtqn3SkQcI"

ALL_PRICES = [SANDBOX_STARTER, SANDBOX_BUSINESS, SANDBOX_ENTERPRISE]


pytestmark = pytest.mark.skipif(
    not stripe.api_key.startswith("sk_test_"),
    reason="Requires sandbox STRIPE_SECRET_KEY",
)


def _create_customer_with_sub(start_price: str = SANDBOX_STARTER) -> tuple[str, str, str]:
    """Cria customer + subscription trialing. Retorna (customer_id, sub_id, item_id)."""
    suffix = uuid.uuid4().hex[:8]
    customer = stripe.Customer.create(
        email=f"qa-stress-{suffix}@dfeaxis-test.com",
        metadata={"qa": "stress_change_plan"},
    )
    sub = stripe.Subscription.create(
        customer=customer.id,
        items=[{"price": start_price}],
        trial_period_days=7,
    )
    return customer.id, sub.id, sub["items"]["data"][0]["id"]


def _cleanup(customer_id: str | None, sub_id: str | None) -> None:
    if sub_id:
        try:
            stripe.Subscription.cancel(sub_id)
        except Exception:
            pass
    if customer_id:
        try:
            stripe.Customer.delete(customer_id)
        except Exception:
            pass


def _modify_to(sub_id: str, item_id: str, new_price: str) -> dict[str, Any]:
    """Wrapper pra rodar em thread; captura resultado ou exception."""
    try:
        result = stripe.Subscription.modify(
            sub_id,
            items=[{"id": item_id, "price": new_price}],
            proration_behavior="create_prorations",
        )
        return {"ok": True, "sub_id": result.id, "price": new_price}
    except Exception as e:
        return {"ok": False, "error": str(e), "price": new_price}


def test_5_chamadas_paralelas_mesmo_price_sem_acumular_items():
    """5 chamadas paralelas pra mesmo price → sub final tem 1 item (nao 5)."""
    customer_id: str | None = None
    sub_id: str | None = None
    try:
        customer_id, sub_id, item_id = _create_customer_with_sub(SANDBOX_STARTER)

        # 5 threads chamando modify pra Business simultaneamente
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exec:
            futures = [
                exec.submit(_modify_to, sub_id, item_id, SANDBOX_BUSINESS)
                for _ in range(5)
            ]
            results = [f.result(timeout=20) for f in futures]

        # Pelo menos a 1a deve ter sucesso. Stripe pode retornar erro nas
        # subsequentes se item_id ficou stale (raro, mas possivel).
        sucessos = [r for r in results if r["ok"]]
        assert len(sucessos) >= 1, f"esperava >= 1 sucesso, got: {results}"

        # Estado final do Stripe deve ter exatamente 1 subscription com 1 item
        final = stripe.Subscription.retrieve(sub_id)
        assert len(final["items"]["data"]) == 1, (
            f"items acumularam: {len(final['items']['data'])}"
        )
        assert final["items"]["data"][0]["price"]["id"] == SANDBOX_BUSINESS

        # Customer continua com 1 sub
        subs = stripe.Subscription.list(customer=customer_id, limit=10).data
        active = [s for s in subs if s.status not in ("canceled",)]
        assert len(active) == 1, f"esperava 1 sub, got {len(active)}"

    finally:
        _cleanup(customer_id, sub_id)


def test_5_chamadas_paralelas_prices_diferentes_estado_final_consistente():
    """5 chamadas paralelas alternando price → estado final tem 1 item, 1 sub.

    Não validamos QUAL price ficou (ultimo write vence, ordem nao
    deterministica), apenas que o estado final e CONSISTENTE.
    """
    customer_id: str | None = None
    sub_id: str | None = None
    try:
        customer_id, sub_id, item_id = _create_customer_with_sub(SANDBOX_STARTER)

        prices_to_try = [
            SANDBOX_BUSINESS,
            SANDBOX_ENTERPRISE,
            SANDBOX_STARTER,
            SANDBOX_BUSINESS,
            SANDBOX_ENTERPRISE,
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as exec:
            futures = [
                exec.submit(_modify_to, sub_id, item_id, p)
                for p in prices_to_try
            ]
            results = [f.result(timeout=30) for f in futures]

        sucessos = [r for r in results if r["ok"]]
        assert len(sucessos) >= 1, f"esperava >= 1 sucesso: {results}"

        # Estado final consistente
        final = stripe.Subscription.retrieve(sub_id)
        assert len(final["items"]["data"]) == 1, (
            f"items acumularam: {len(final['items']['data'])}"
        )
        # Final price deve ser um dos que tentamos
        final_price = final["items"]["data"][0]["price"]["id"]
        assert final_price in ALL_PRICES, f"price final inesperado: {final_price}"

        # Customer 1 sub
        subs = stripe.Subscription.list(customer=customer_id, limit=10).data
        active = [s for s in subs if s.status not in ("canceled",)]
        assert len(active) == 1

        print(f"[stress] 5 paralelas alternando prices — final: {final_price}, "
              f"sucessos: {len(sucessos)}/5")

    finally:
        _cleanup(customer_id, sub_id)


def test_10_customers_paralelos_cada_um_com_modify():
    """10 customers diferentes fazendo modify ao mesmo tempo — sem cross-contamination."""
    customers: list[tuple[str | None, str | None]] = []
    try:
        # Cria 10 customers + subs em sequencia (criar paralelo seria outro stress)
        contexts = []
        for _ in range(10):
            cid, sid, item = _create_customer_with_sub(SANDBOX_STARTER)
            contexts.append((cid, sid, item))
            customers.append((cid, sid))

        # 10 modifies paralelos, cada um pra um sub diferente
        def modify_for(ctx: tuple[str, str, str]) -> dict[str, Any]:
            _, sub_id, item_id = ctx
            return _modify_to(sub_id, item_id, SANDBOX_BUSINESS)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as exec:
            results = list(exec.map(modify_for, contexts, timeout=60))

        # Todos devem ter sucedido (cada sub e independente, sem race)
        sucessos = [r for r in results if r["ok"]]
        assert len(sucessos) == 10, (
            f"esperava 10/10 sucessos (subs independentes), got {len(sucessos)}: "
            f"{[r for r in results if not r['ok']]}"
        )

        # Cada sub deve estar em Business com 1 item
        for cid, sid, _ in contexts:
            final = stripe.Subscription.retrieve(sid)
            assert len(final["items"]["data"]) == 1
            assert final["items"]["data"][0]["price"]["id"] == SANDBOX_BUSINESS

    finally:
        for cid, sid in customers:
            _cleanup(cid, sid)
