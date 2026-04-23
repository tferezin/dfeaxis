"""Testes unitarios das funcoes puras de calculo de ProRata e billing anchor.

Nao dependem de Supabase nem de Stripe — testam apenas as funcoes
matematicas do checkout.py. Rodam standalone:

    cd backend && python3 -m pytest tests/test_billing_prorata_logic.py -v

Usa stubs de sys.modules pra nao carregar supabase/stripe reais durante
o teste. Se as libs estiverem instaladas tambem funciona — o teste so
importa a funcao pura sem tocar em services externos.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Setup pra importar o modulo
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Stubs pra modulos externos nao instalados no ambiente de teste local.
# Em CI/Railway com deps completas eles sao sobrescritos automaticamente.
for modname in ("supabase", "stripe"):
    if modname not in sys.modules:
        sys.modules[modname] = SimpleNamespace(create_client=lambda *a, **kw: None)

# Stub de db.supabase (que importa supabase) — evita inicializacao real
if "db.supabase" not in sys.modules:
    sys.modules["db"] = SimpleNamespace()
    sys.modules["db.supabase"] = SimpleNamespace(
        get_supabase_client=lambda: MagicMock()
    )

# Stub de services.billing.__init__ — o __init__ importa ensure_customer que
# puxa a cadeia toda do Supabase. A gente so quer checkout puro.
if "services" not in sys.modules:
    sys.modules["services"] = SimpleNamespace()
if "services.billing" not in sys.modules:
    sys.modules["services.billing"] = SimpleNamespace()


def _import_checkout_module():
    """Import direto do checkout.py pulando o __init__ do pacote."""
    import importlib.util
    path = os.path.join(_BACKEND_DIR, "services", "billing", "checkout.py")
    spec = importlib.util.spec_from_file_location(
        "services.billing.checkout", path
    )
    module = importlib.util.module_from_spec(spec)

    # Stub os imports relativos internos do checkout
    customers_stub = SimpleNamespace(ensure_customer=lambda _: "cus_stub")
    stripe_client_stub = SimpleNamespace(get_stripe=lambda: MagicMock())
    # plans precisa ser importavel — carrega direto do arquivo
    plans_path = os.path.join(_BACKEND_DIR, "services", "billing", "plans.py")
    plans_spec = importlib.util.spec_from_file_location(
        "services.billing.plans", plans_path
    )
    plans_module = importlib.util.module_from_spec(plans_spec)
    sys.modules["services.billing.plans"] = plans_module
    plans_spec.loader.exec_module(plans_module)

    sys.modules["services.billing.customers"] = customers_stub
    sys.modules["services.billing.stripe_client"] = stripe_client_stub
    sys.modules["services.billing.checkout"] = module
    spec.loader.exec_module(module)
    return module


checkout = _import_checkout_module()


# ---------------------------------------------------------------------------
# _compute_next_billing_anchor — sempre empurra pro MES SEGUINTE
# ---------------------------------------------------------------------------

class TestNextBillingAnchor:
    """billing anchor do Stripe subscription = dia 5 do mes seguinte."""

    def test_meio_do_mes_anchor_proximo_mes(self):
        now = datetime(2026, 4, 15, 14, 30, 0, tzinfo=timezone.utc)
        anchor = checkout._compute_next_billing_anchor(5, now)
        assert anchor == datetime(2026, 5, 5, 0, 0, 0, tzinfo=timezone.utc)

    def test_dia_1_anchor_mes_seguinte(self):
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        anchor = checkout._compute_next_billing_anchor(5, now)
        assert anchor == datetime(2026, 5, 5, 0, 0, 0, tzinfo=timezone.utc)

    def test_dia_billing_anchor_mes_seguinte(self):
        now = datetime(2026, 4, 5, 10, 0, 0, tzinfo=timezone.utc)
        anchor = checkout._compute_next_billing_anchor(5, now)
        assert anchor == datetime(2026, 5, 5, 0, 0, 0, tzinfo=timezone.utc)

    def test_depois_do_billing_day(self):
        now = datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc)
        anchor = checkout._compute_next_billing_anchor(5, now)
        assert anchor == datetime(2026, 5, 5, 0, 0, 0, tzinfo=timezone.utc)

    def test_dezembro_vira_ano(self):
        now = datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc)
        anchor = checkout._compute_next_billing_anchor(5, now)
        assert anchor == datetime(2027, 1, 5, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _compute_prorata_cents — formula baseada em mes calendario
# ---------------------------------------------------------------------------

class TestProrataCents:
    """ProRata = (dias_restantes / dias_do_mes) x valor_mensal."""

    def _mock_lookup(self, monthly_cents=29000, yearly_cents=278400, period="monthly"):
        plan = SimpleNamespace(
            monthly_amount_cents=monthly_cents,
            yearly_amount_cents=yearly_cents,
        )
        return SimpleNamespace(plan=plan, period=period)

    def test_exemplo_usuario_dia_4_abril_starter(self):
        """Cliente Starter 4/Abril (30 dias): 26/30 x 290 = R$ 251,33."""
        with patch.object(checkout, "get_plan_by_price_id") as mock:
            mock.return_value = self._mock_lookup()
            now = datetime(2026, 4, 4, 14, 0, 0, tzinfo=timezone.utc)
            proration, days = checkout._compute_prorata_cents("price_test", now)
        assert days == 26
        assert proration == 25133  # R$ 251,33

    def test_exemplo_usuario_dia_30_abril_starter(self):
        """Cliente 30/Abril: 0 dias restantes → cortesia."""
        with patch.object(checkout, "get_plan_by_price_id") as mock:
            mock.return_value = self._mock_lookup()
            now = datetime(2026, 4, 30, 14, 0, 0, tzinfo=timezone.utc)
            proration, days = checkout._compute_prorata_cents("price_test", now)
        assert days == 0
        assert proration == 0

    def test_dia_29_abril_starter(self):
        """1 dia → R$ 9,66 → abaixo do minimo R$ 50."""
        with patch.object(checkout, "get_plan_by_price_id") as mock:
            mock.return_value = self._mock_lookup()
            now = datetime(2026, 4, 29, 14, 0, 0, tzinfo=timezone.utc)
            proration, days = checkout._compute_prorata_cents("price_test", now)
        assert days == 1
        assert proration == 966

    def test_dia_15_business_mensal(self):
        """Business mensal (R$ 690) dia 15/Abril: 15/30 × 690 = R$ 345."""
        with patch.object(checkout, "get_plan_by_price_id") as mock:
            mock.return_value = self._mock_lookup(monthly_cents=69000)
            now = datetime(2026, 4, 15, 14, 0, 0, tzinfo=timezone.utc)
            proration, days = checkout._compute_prorata_cents("price_test", now)
        assert days == 15
        assert proration == 34500

    def test_fevereiro_28_dias(self):
        """Fevereiro (28 dias): dia 4 = 24 dias restantes."""
        with patch.object(checkout, "get_plan_by_price_id") as mock:
            mock.return_value = self._mock_lookup()
            now = datetime(2026, 2, 4, 14, 0, 0, tzinfo=timezone.utc)
            proration, days = checkout._compute_prorata_cents("price_test", now)
        assert days == 24
        assert proration == int(29000 * 24 / 28)  # R$ 248,57

    def test_plano_anual_usa_mensal_equivalente(self):
        """Anual: yearly/12 = 'mensalidade equivalente' pra ProRata."""
        with patch.object(checkout, "get_plan_by_price_id") as mock:
            mock.return_value = self._mock_lookup(
                yearly_cents=278400, period="yearly"
            )
            now = datetime(2026, 4, 4, 14, 0, 0, tzinfo=timezone.utc)
            proration, days = checkout._compute_prorata_cents("price_test", now)
        assert days == 26
        monthly_eq = 278400 // 12  # 23200
        assert proration == int(monthly_eq * 26 / 30)

    def test_price_id_nao_encontrado(self):
        with patch.object(checkout, "get_plan_by_price_id") as mock:
            mock.return_value = None
            now = datetime(2026, 4, 4, tzinfo=timezone.utc)
            proration, days = checkout._compute_prorata_cents("price_x", now)
        assert proration is None
        assert days == 0


# ---------------------------------------------------------------------------
# Regra do minimo R$ 50 + constantes
# ---------------------------------------------------------------------------

class TestConstantes:
    def test_proration_min_cents_R50(self):
        assert checkout.PRORATION_MIN_CENTS == 5000

    def test_default_billing_day_5(self):
        assert checkout.DEFAULT_BILLING_DAY == 5

    def test_9_reais_abaixo_do_minimo(self):
        assert 966 < checkout.PRORATION_MIN_CENTS  # cortesia

    def test_251_reais_acima_do_minimo(self):
        assert 25133 >= checkout.PRORATION_MIN_CENTS  # cobra
