"""Unit tests para admin_guards.py — defesa contra cert admin virar prod.

Não precisa de Supabase ou network. Roda em <1s.
"""

from __future__ import annotations

import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from admin_guards import (  # noqa: E402
    NEVER_PROD_CERT_CNPJS,
    NEVER_PROD_USER_EMAILS,
    safe_ambiente,
    should_block_prod,
)


class TestShouldBlockProd:
    """Detecta cert/usuário que nunca pode ir pra produção."""

    def test_cert_beiersdorf_bloqueado(self):
        blocked, reason = should_block_prod(cert_cnpj="01786983000368")
        assert blocked is True
        assert reason is not None
        assert "01786983000368" in reason

    def test_cert_beiersdorf_com_mascara_bloqueado(self):
        # Normalização aceita CNPJ com pontuação — formato filial 0003-68
        blocked, reason = should_block_prod(cert_cnpj="01.786.983/0003-68")
        assert blocked is True
        assert "01.786.983/0003-68" in reason

    def test_cert_aleatorio_liberado(self):
        blocked, reason = should_block_prod(cert_cnpj="12345678000190")
        assert blocked is False
        assert reason is None

    def test_email_admin_bloqueado(self):
        blocked, reason = should_block_prod(user_email="ferezinth@hotmail.com")
        assert blocked is True
        assert "ferezinth@hotmail.com" in reason

    def test_email_admin_case_insensitive(self):
        blocked, _ = should_block_prod(user_email="FEREZINTH@HOTMAIL.COM")
        assert blocked is True

    def test_email_admin_com_espacos(self):
        blocked, _ = should_block_prod(user_email="  ferezinth@hotmail.com  ")
        assert blocked is True

    def test_email_cliente_normal_liberado(self):
        blocked, reason = should_block_prod(user_email="cliente@empresa.com.br")
        assert blocked is False
        assert reason is None

    def test_sem_parametros_liberado(self):
        blocked, reason = should_block_prod()
        assert blocked is False
        assert reason is None

    def test_cnpj_vazio_liberado(self):
        blocked, _ = should_block_prod(cert_cnpj="")
        assert blocked is False

    def test_cert_bloqueado_override_email_normal(self):
        # Cert bloqueado vence mesmo com email normal — protege cliente
        # que subiu cert de terceiro por engano
        blocked, reason = should_block_prod(
            cert_cnpj="01786983000368",
            user_email="cliente@empresa.com.br",
        )
        assert blocked is True
        assert "01786983000368" in reason


class TestSafeAmbiente:
    """Força homolog se contexto é bloqueado; passa transparente caso contrário."""

    def test_prod_com_cert_bloqueado_vira_homolog(self, caplog):
        import logging
        caplog.set_level(logging.ERROR)
        result = safe_ambiente("1", cert_cnpj="01786983000368")
        assert result == "2"
        # Deve logar ERROR pra sinalizar que algo tentou burlar o guard
        assert any("AMBIENTE FORCADO" in r.message for r in caplog.records)

    def test_prod_com_email_admin_vira_homolog(self):
        result = safe_ambiente("1", user_email="ferezinth@hotmail.com")
        assert result == "2"

    def test_prod_com_cert_liberado_permanece_prod(self):
        result = safe_ambiente("1", cert_cnpj="12345678000190")
        assert result == "1"

    def test_homolog_nunca_muda(self):
        # Mesmo com cert bloqueado, se já era homolog continua homolog
        result = safe_ambiente("2", cert_cnpj="01786983000368")
        assert result == "2"

    def test_sem_contexto_passa_transparente(self):
        # Sem cert_cnpj nem user_email, não há motivo pra bloquear
        result = safe_ambiente("1")
        assert result == "1"


class TestBlacklistIntegridade:
    """Regressão: garante que BEIERSDORF e email admin estão na blacklist."""

    def test_beiersdorf_presente(self):
        # Se alguém remover do código, o teste falha
        assert "01786983000368" in NEVER_PROD_CERT_CNPJS

    def test_email_admin_presente(self):
        assert "ferezinth@hotmail.com" in NEVER_PROD_USER_EMAILS

    def test_cnpjs_sao_so_digitos(self):
        # Evita regressão do tipo "adicionei com máscara e quebrou match"
        for cnpj in NEVER_PROD_CERT_CNPJS:
            assert cnpj.isdigit(), f"CNPJ '{cnpj}' deve conter só dígitos"
            assert len(cnpj) == 14, f"CNPJ '{cnpj}' deve ter 14 dígitos"
