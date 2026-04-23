"""Unit tests para admin_guards.py — defesa contra conta admin virar prod.

Bloqueio pela identidade da CONTA (user_id, tenant_id, email), não pelo
CNPJ do cert — se um dia o mesmo CNPJ aparecer em conta de cliente real,
ele não é afetado.

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
    NEVER_PROD_TENANT_IDS,
    NEVER_PROD_USER_EMAILS,
    NEVER_PROD_USER_IDS,
    safe_ambiente,
    should_block_prod,
)

# UUIDs reais da conta admin (gravados no código)
ADMIN_USER_ID = "3e9c9d9b-9682-4713-8552-6e1abf3514bc"
ADMIN_TENANT_ID = "dfe11fdb-fa54-403e-b563-24aef3b7b406"
ADMIN_EMAIL = "admin@dfeaxis.com.br"


class TestShouldBlockProd:
    """Detecta conta admin que nunca pode ir pra produção."""

    def test_user_id_admin_bloqueado(self):
        blocked, reason = should_block_prod(user_id=ADMIN_USER_ID)
        assert blocked is True
        assert reason is not None
        # Exibe só prefixo do UUID pra não poluir o erro
        assert ADMIN_USER_ID[:8] in reason

    def test_tenant_id_admin_bloqueado(self):
        blocked, reason = should_block_prod(tenant_id=ADMIN_TENANT_ID)
        assert blocked is True
        assert ADMIN_TENANT_ID[:8] in reason

    def test_email_admin_bloqueado(self):
        blocked, reason = should_block_prod(user_email=ADMIN_EMAIL)
        assert blocked is True
        assert ADMIN_EMAIL in reason

    def test_email_admin_case_insensitive(self):
        blocked, _ = should_block_prod(user_email="ADMIN@DFEAXIS.COM.BR")
        assert blocked is True

    def test_email_admin_com_espacos(self):
        blocked, _ = should_block_prod(user_email="  admin@dfeaxis.com.br  ")
        assert blocked is True

    def test_user_id_cliente_liberado(self):
        blocked, reason = should_block_prod(
            user_id="00000000-0000-0000-0000-000000000001",
        )
        assert blocked is False
        assert reason is None

    def test_tenant_id_cliente_liberado(self):
        blocked, _ = should_block_prod(
            tenant_id="ffffffff-ffff-ffff-ffff-ffffffffffff",
        )
        assert blocked is False

    def test_email_cliente_liberado(self):
        blocked, _ = should_block_prod(user_email="cliente@empresa.com.br")
        assert blocked is False

    def test_sem_parametros_liberado(self):
        blocked, reason = should_block_prod()
        assert blocked is False
        assert reason is None

    def test_user_id_admin_com_email_cliente(self):
        # user_id admin vence email genérico — protege se alguém só passa
        # o user_id sem email
        blocked, reason = should_block_prod(
            user_id=ADMIN_USER_ID,
            user_email="cliente@empresa.com.br",
        )
        assert blocked is True
        assert ADMIN_USER_ID[:8] in reason

    def test_bloqueio_independe_de_cnpj(self):
        """Regressão: mesmo passando CNPJ BEIERSDORF, NÃO bloqueia se a
        conta é cliente legítimo. O bloqueio é pela identidade, não pelo
        cert. Se a BEIERSDORF virar cliente real, ela pode ir pra prod.
        """
        blocked, _ = should_block_prod(
            user_id="11111111-1111-1111-1111-111111111111",  # cliente hipotético
            tenant_id="22222222-2222-2222-2222-222222222222",
            user_email="fiscal@beiersdorf.com.br",
        )
        assert blocked is False


class TestSafeAmbiente:
    """Força homolog se contexto é bloqueado; passa transparente caso contrário."""

    def test_prod_com_user_id_admin_vira_homolog(self, caplog):
        import logging
        caplog.set_level(logging.ERROR)
        result = safe_ambiente("1", user_id=ADMIN_USER_ID)
        assert result == "2"
        assert any("AMBIENTE FORCADO" in r.message for r in caplog.records)

    def test_prod_com_tenant_id_admin_vira_homolog(self):
        result = safe_ambiente("1", tenant_id=ADMIN_TENANT_ID)
        assert result == "2"

    def test_prod_com_email_admin_vira_homolog(self):
        result = safe_ambiente("1", user_email=ADMIN_EMAIL)
        assert result == "2"

    def test_prod_cliente_normal_permanece_prod(self):
        result = safe_ambiente(
            "1",
            user_id="11111111-1111-1111-1111-111111111111",
            tenant_id="22222222-2222-2222-2222-222222222222",
            user_email="cliente@empresa.com.br",
        )
        assert result == "1"

    def test_homolog_nunca_muda(self):
        # Mesmo contexto admin, se já era homolog continua homolog
        result = safe_ambiente("2", user_id=ADMIN_USER_ID)
        assert result == "2"

    def test_sem_contexto_passa_transparente(self):
        result = safe_ambiente("1")
        assert result == "1"


class TestBlacklistIntegridade:
    """Regressão: garante que as UUIDs/emails da conta admin estão na blacklist."""

    def test_user_id_admin_presente(self):
        assert ADMIN_USER_ID in NEVER_PROD_USER_IDS

    def test_tenant_id_admin_presente(self):
        assert ADMIN_TENANT_ID in NEVER_PROD_TENANT_IDS

    def test_email_admin_presente(self):
        assert ADMIN_EMAIL in NEVER_PROD_USER_EMAILS

    def test_uuids_formato_valido(self):
        # Evita erros tipo whitespace ou truncamento na blacklist
        for uid in NEVER_PROD_USER_IDS | NEVER_PROD_TENANT_IDS:
            assert len(uid) == 36, f"UUID '{uid}' deve ter 36 chars"
            assert uid.count("-") == 4, f"UUID '{uid}' deve ter 4 hífens"
