"""Unit tests pro gate de acesso à SEFAZ produção.

Valida o helper `_is_prod_access_allowed_globally` (env var parsing).
Os testes do guard no endpoint (3 caminhos: admin blacklist / flag
global / allowlist por tenant) precisariam de Supabase real — são
cobertos em testes de integração separados. Aqui cobrimos só a
lógica pura que dá pra isolar.
"""

from __future__ import annotations

import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from routers.tenants import _is_prod_access_allowed_globally  # noqa: E402


class TestFlagGlobalParsing:
    """Env var PROD_ACCESS_ALLOWED — default false, case insensitive."""

    def setup_method(self):
        # Salva valor original pra restaurar
        self._original = os.environ.get("PROD_ACCESS_ALLOWED")

    def teardown_method(self):
        if self._original is None:
            os.environ.pop("PROD_ACCESS_ALLOWED", None)
        else:
            os.environ["PROD_ACCESS_ALLOWED"] = self._original

    def test_default_eh_false_sem_env(self):
        os.environ.pop("PROD_ACCESS_ALLOWED", None)
        assert _is_prod_access_allowed_globally() is False

    def test_true_lowercase_habilita(self):
        os.environ["PROD_ACCESS_ALLOWED"] = "true"
        assert _is_prod_access_allowed_globally() is True

    def test_true_uppercase_habilita(self):
        os.environ["PROD_ACCESS_ALLOWED"] = "TRUE"
        assert _is_prod_access_allowed_globally() is True

    def test_true_mixed_case_habilita(self):
        os.environ["PROD_ACCESS_ALLOWED"] = "True"
        assert _is_prod_access_allowed_globally() is True

    def test_true_com_espacos_habilita(self):
        os.environ["PROD_ACCESS_ALLOWED"] = "  true  "
        assert _is_prod_access_allowed_globally() is True

    def test_false_explicito_nao_habilita(self):
        os.environ["PROD_ACCESS_ALLOWED"] = "false"
        assert _is_prod_access_allowed_globally() is False

    def test_string_vazia_nao_habilita(self):
        os.environ["PROD_ACCESS_ALLOWED"] = ""
        assert _is_prod_access_allowed_globally() is False

    def test_valor_invalido_nao_habilita(self):
        # Defensive: "yes", "1", "on" NÃO devem ligar — evita habilitar
        # por engano com valor não-booleano. Apenas "true" (case-insens).
        for val in ("yes", "1", "on", "sim", "enabled"):
            os.environ["PROD_ACCESS_ALLOWED"] = val
            assert (
                _is_prod_access_allowed_globally() is False
            ), f"valor '{val}' não deveria habilitar"

    def test_valor_0_nao_habilita(self):
        os.environ["PROD_ACCESS_ALLOWED"] = "0"
        assert _is_prod_access_allowed_globally() is False


class TestSemantica:
    """Docs-em-código: o comportamento correto da flag."""

    def test_comportamento_soft_launch(self):
        """Durante soft launch (env var não setada OU 'false'), só
        tenants com prod_access_approved=true podem virar produção.
        """
        # Simulação: env não setado → gate fechado globalmente
        os.environ.pop("PROD_ACCESS_ALLOWED", None)
        assert _is_prod_access_allowed_globally() is False
        # → endpoint vai consultar prod_access_approved do tenant

    def test_comportamento_full_launch(self):
        """Após soft launch, setando PROD_ACCESS_ALLOWED=true no
        Railway sem deploy, qualquer tenant (exceto blacklist admin)
        pode virar produção sem approval individual.
        """
        os.environ["PROD_ACCESS_ALLOWED"] = "true"
        assert _is_prod_access_allowed_globally() is True
        # → endpoint nem precisa consultar prod_access_approved

        # Limpa pra não afetar outros testes
        os.environ.pop("PROD_ACCESS_ALLOWED", None)
