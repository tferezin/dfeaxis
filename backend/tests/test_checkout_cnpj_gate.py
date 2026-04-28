"""Tests pro gate proativo de CNPJ count em POST /billing/checkout.

Implementado em routers/billing.py. Bloqueia 422 se cliente escolhe plano
com max_cnpjs menor que CNPJs ativos cadastrados.
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

from routers.billing import checkout, CheckoutRequest  # noqa: E402
from services.billing.plans import load_plans  # noqa: E402


def _mock_sb_with_cert_count(count: int) -> MagicMock:
    """Mock supabase client returning N active certs pro tenant."""
    sb = MagicMock()
    res = MagicMock()
    res.count = count
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = res
    return sb


def _call_checkout(price_id: str, cert_count: int) -> HTTPException | dict:
    """Chama checkout() com auth mock e supabase mock; retorna exceção ou response."""
    auth = {"tenant_id": "11111111-2222-3333-4444-555555555555", "user_id": "u1"}
    body = CheckoutRequest(
        price_id=price_id,
        success_url="https://x/y",
        cancel_url="https://x/z",
        billing_day=5,
    )

    sb = _mock_sb_with_cert_count(cert_count)

    async def _run():
        return await checkout(body=body, auth=auth)

    with patch("routers.billing.get_supabase_client", return_value=sb), \
            patch("routers.billing.create_checkout_session",
                  return_value={"id": "cs_test_x", "url": "https://stripe.test/x"}):
        try:
            return asyncio.run(_run())
        except HTTPException as e:
            return e


def _starter_price_id() -> str:
    """Pega o price_id_monthly do plano starter (max_cnpjs=1)."""
    for p in load_plans():
        if p.key == "starter":
            return p.price_id_monthly
    raise RuntimeError("starter plan not in catalog")


def _business_price_id() -> str:
    for p in load_plans():
        if p.key == "business":
            return p.price_id_monthly
    raise RuntimeError("business plan not in catalog")


def _enterprise_price_id() -> str:
    for p in load_plans():
        if p.key == "enterprise":
            return p.price_id_monthly
    raise RuntimeError("enterprise plan not in catalog")


def test_gate_bloqueia_starter_quando_tem_2_cnpjs():
    """Tenant com 2 certs ativos NAO pode escolher Starter (max=1)."""
    result = _call_checkout(_starter_price_id(), cert_count=2)

    assert isinstance(result, HTTPException), f"esperava HTTPException, got {result}"
    assert result.status_code == 422
    detail = result.detail
    assert detail["error_code"] == "PLAN_CNPJ_LIMIT_EXCEEDED"
    assert detail["cnpj_count"] == 2
    assert detail["plan_max_cnpjs"] == 1
    assert detail["plan_key"] == "starter"


def test_gate_bloqueia_business_quando_tem_6_cnpjs():
    """Tenant com 6 certs NAO pode escolher Business (max=5) — caso da pergunta."""
    result = _call_checkout(_business_price_id(), cert_count=6)

    assert isinstance(result, HTTPException)
    assert result.status_code == 422
    assert result.detail["error_code"] == "PLAN_CNPJ_LIMIT_EXCEEDED"
    assert result.detail["plan_max_cnpjs"] == 5


def test_gate_libera_business_no_limite():
    """5 certs + Business (max=5) → passa (count == max, nao excede)."""
    result = _call_checkout(_business_price_id(), cert_count=5)

    assert not isinstance(result, HTTPException), f"era pra liberar, got {result}"
    assert result.url == "https://stripe.test/x"


def test_gate_libera_enterprise_com_muitos_cnpjs():
    """10 certs + Enterprise (max=50) → passa."""
    result = _call_checkout(_enterprise_price_id(), cert_count=10)

    assert not isinstance(result, HTTPException)
    assert result.session_id == "cs_test_x"


def test_gate_libera_starter_zero_cnpjs():
    """0 certs (cliente novo) → starter passa (caso comum no trial)."""
    result = _call_checkout(_starter_price_id(), cert_count=0)

    assert not isinstance(result, HTTPException)


def test_gate_silencioso_com_price_id_invalido():
    """Price_id desconhecido nao bate no gate (cai no INVALID_PRICE_ID em create_checkout_session)."""
    # Quando price_id nao existe no catalogo, get_plan_by_price_id retorna None
    # e o gate eh skipped — deixa o create_checkout_session lidar (que vai
    # levantar ValueError → 400 INVALID_PRICE_ID via except no proprio endpoint).
    # Aqui mockamos create_checkout_session pra retornar OK, entao o gate
    # silencioso significa que NAO levanta 422.
    result = _call_checkout("price_inexistente", cert_count=99)

    assert not isinstance(result, HTTPException), \
        f"price_id invalido nao deve bater no gate (esperava passar), got {result}"
