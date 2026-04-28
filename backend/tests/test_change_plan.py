"""Tests pro endpoint POST /billing/change-plan e seu service.

Cobre os cenarios chave:
- Tenant sem assinatura → 400 NOT_A_SUBSCRIBER
- Plano alvo nao no catalogo → 400 INVALID_PRICE_ID
- Mesmo plano → 400 SAME_PLAN
- count_certs > max_cnpjs do alvo → 422 PLAN_CNPJ_LIMIT_EXCEEDED
- Subscription cancelada → 409 SUBSCRIPTION_INACTIVE
- Caso feliz → chama Stripe.Subscription.modify e retorna 200
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from routers.billing import change_plan, ChangePlanRequest  # noqa: E402
from services.billing.plans import load_plans  # noqa: E402


def _starter_id() -> str:
    for p in load_plans():
        if p.key == "starter":
            return p.price_id_monthly
    raise RuntimeError("starter not in catalog")


def _business_id() -> str:
    for p in load_plans():
        if p.key == "business":
            return p.price_id_monthly
    raise RuntimeError("business not in catalog")


def _enterprise_id() -> str:
    for p in load_plans():
        if p.key == "enterprise":
            return p.price_id_monthly
    raise RuntimeError("enterprise not in catalog")


def _mock_sb(
    subscription_id: str | None = "sub_test_123",
    subscription_status: str = "active",
    cert_count: int = 0,
) -> MagicMock:
    """Mock supabase: tenants.select + certificates.select."""
    sb = MagicMock()

    tenants_resp = MagicMock()
    tenants_resp.data = {
        "stripe_subscription_id": subscription_id,
        "subscription_status": subscription_status,
    }

    certs_resp = MagicMock()
    certs_resp.count = cert_count

    def table_factory(name):
        tbl = MagicMock()
        if name == "tenants":
            tbl.select.return_value.eq.return_value.single.return_value.execute.return_value = tenants_resp
        elif name == "certificates":
            tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = certs_resp
        return tbl

    sb.table.side_effect = table_factory
    return sb


def _mock_stripe(current_price_id: str, subscription_id: str = "sub_test_123") -> MagicMock:
    stripe = MagicMock()
    stripe.Subscription.retrieve.return_value = {
        "id": subscription_id,
        "metadata": {},
        "items": {"data": [{"id": "si_test_1", "price": {"id": current_price_id}}]},
    }
    stripe.Subscription.modify.return_value = {
        "id": subscription_id,
        "status": "active",
    }
    return stripe


def _call(price_id: str, **mocks):
    auth = {"tenant_id": "t-1", "user_id": "u-1"}
    body = ChangePlanRequest(price_id=price_id)

    sb = mocks.pop("sb", _mock_sb())
    stripe = mocks.pop("stripe", _mock_stripe(current_price_id=_starter_id()))

    async def _run():
        return await change_plan(body=body, auth=auth)

    with patch("services.billing.change_plan.get_supabase_client", return_value=sb), \
            patch("services.billing.change_plan.get_stripe", return_value=stripe):
        try:
            return asyncio.run(_run())
        except HTTPException as e:
            return e


def test_not_a_subscriber_400():
    sb = _mock_sb(subscription_id=None)
    res = _call(_business_id(), sb=sb)
    assert isinstance(res, HTTPException)
    assert res.status_code == 400
    assert res.detail["error_code"] == "NOT_A_SUBSCRIBER"


def test_invalid_price_id_400():
    res = _call("price_que_nao_existe")
    assert isinstance(res, HTTPException)
    assert res.status_code == 400
    assert res.detail["error_code"] == "INVALID_PRICE_ID"


def test_subscription_cancelled_409():
    sb = _mock_sb(subscription_status="cancelled")
    res = _call(_business_id(), sb=sb)
    assert isinstance(res, HTTPException)
    assert res.status_code == 409
    assert res.detail["error_code"] == "SUBSCRIPTION_INACTIVE"


def test_cnpj_limit_excedido_422():
    """Tenant com 2 certs no Business querendo downgrade pra Starter (max=1) → 422."""
    sb = _mock_sb(cert_count=2)
    stripe = _mock_stripe(current_price_id=_business_id())
    res = _call(_starter_id(), sb=sb, stripe=stripe)
    assert isinstance(res, HTTPException)
    assert res.status_code == 422
    assert res.detail["error_code"] == "PLAN_CNPJ_LIMIT_EXCEEDED"
    assert res.detail["plan_max_cnpjs"] == 1
    assert res.detail["cnpj_count"] == 2


def test_same_plan_400():
    """Tenant ja no Business pedindo Business → 400 SAME_PLAN."""
    sb = _mock_sb(cert_count=0)
    stripe = _mock_stripe(current_price_id=_business_id())
    res = _call(_business_id(), sb=sb, stripe=stripe)
    assert isinstance(res, HTTPException)
    assert res.status_code == 400
    assert res.detail["error_code"] == "SAME_PLAN"


def test_upgrade_starter_to_business_ok():
    """Tenant Starter com 1 cert vai pra Business (max=5) → chama modify e retorna 200."""
    sb = _mock_sb(cert_count=1)
    stripe = _mock_stripe(current_price_id=_starter_id())
    res = _call(_business_id(), sb=sb, stripe=stripe)

    assert not isinstance(res, HTTPException), f"esperava 200, got {res}"
    assert res.subscription_id == "sub_test_123"
    assert res.new_price_id == _business_id()
    assert res.previous_price_id == _starter_id()
    assert res.plan_key == "business"
    # confirma que Stripe.Subscription.modify foi chamado com items+proration
    stripe.Subscription.modify.assert_called_once()
    call_args = stripe.Subscription.modify.call_args
    assert call_args.kwargs["proration_behavior"] == "create_prorations"
    assert call_args.kwargs["items"][0]["id"] == "si_test_1"
    assert call_args.kwargs["items"][0]["price"] == _business_id()


def test_downgrade_enterprise_to_business_com_3_certs_ok():
    """Tenant Enterprise com 3 certs faz downgrade pra Business (max=5) → libera (3<=5)."""
    sb = _mock_sb(cert_count=3)
    stripe = _mock_stripe(current_price_id=_enterprise_id())
    res = _call(_business_id(), sb=sb, stripe=stripe)
    assert not isinstance(res, HTTPException)
    assert res.plan_key == "business"
