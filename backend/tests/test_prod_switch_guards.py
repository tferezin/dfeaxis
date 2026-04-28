"""Tests pros Guards 3 (cert) e 4 (captura em homolog) do PATCH /tenants/settings.

Implementados em routers/tenants.py:194-225. Exercita cada um
isoladamente bypassando o Guard 2 (PROD_ACCESS_ALLOWED=true) e
manipulando linhas via service role pra cair no caminho desejado:

    - Guard 3 → tenant SEM certificado → espera msg "certificado A1"
    - Guard 4 → tenant COM cert mas SEM documents → espera msg "captura em Homologação"
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock

import pytest
import requests
from fastapi import HTTPException

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from routers.tenants import update_settings  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL") or "https://kmiooqyasvhglszcioow.supabase.co"
SR_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
HEADERS = {
    "apikey": SR_KEY or "",
    "Authorization": f"Bearer {SR_KEY or ''}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def _delete_certs(tenant_id: str) -> None:
    """Apaga TODOS os certificados do tenant (pra exercitar Guard 3)."""
    requests.delete(
        f"{SUPABASE_URL}/rest/v1/certificates",
        headers=HEADERS,
        params={"tenant_id": f"eq.{tenant_id}"},
        timeout=20,
    )


def _call_update_settings(tenant: dict, ambiente: str) -> HTTPException:
    """Chama update_settings sync (via asyncio.run) e retorna a exceção
    levantada — todos os caminhos de guard levantam HTTPException."""
    request = MagicMock()
    request.client = None

    auth = {
        "user_id": tenant["user_id"],
        "tenant_id": tenant["tenant_id"],
        "email": tenant["email"],
    }

    async def _run():
        return await update_settings(
            request=request,
            polling_mode=None,
            manifestacao_mode=None,
            sefaz_ambiente=ambiente,
            auth=auth,
        )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_run())
    return exc_info.value


def test_guard_3_sem_certificado_bloqueia_prod(test_tenant, monkeypatch):
    """Tenant SEM cert → 403 com mensagem de Guard 3."""
    # Bypass Guard 2 (allowlist) pra alcançar os guards novos
    monkeypatch.setenv("PROD_ACCESS_ALLOWED", "true")

    # Fixture cria com cert — apagamos pra exercitar Guard 3
    _delete_certs(test_tenant["tenant_id"])

    exc = _call_update_settings(test_tenant, ambiente="1")

    assert exc.status_code == 403, f"esperava 403, got {exc.status_code}: {exc.detail}"
    assert "certificado A1" in str(exc.detail), f"esperava msg de cert, got: {exc.detail}"


def test_guard_4_sem_captura_bloqueia_prod(test_tenant, monkeypatch):
    """Tenant COM cert mas SEM captura em homolog → 403 com mensagem de Guard 4.

    A fixture já cria com cert e nenhum documento — perfeito pra esse caminho.
    """
    monkeypatch.setenv("PROD_ACCESS_ALLOWED", "true")

    exc = _call_update_settings(test_tenant, ambiente="1")

    assert exc.status_code == 403, f"esperava 403, got {exc.status_code}: {exc.detail}"
    assert "captura em Homologação" in str(exc.detail) or "Homologa" in str(exc.detail), (
        f"esperava msg de captura em homolog, got: {exc.detail}"
    )


def test_homologacao_continua_livre(test_tenant, monkeypatch):
    """Mudar pra Homologação NÃO dispara guards — caminho seguro."""
    monkeypatch.setenv("PROD_ACCESS_ALLOWED", "true")

    # Não levanta exceção — ambiente="2" (homolog) pula todo o bloco de guards
    request = MagicMock()
    request.client = None
    auth = {
        "user_id": test_tenant["user_id"],
        "tenant_id": test_tenant["tenant_id"],
        "email": test_tenant["email"],
    }

    async def _run():
        return await update_settings(
            request=request,
            polling_mode=None,
            manifestacao_mode=None,
            sefaz_ambiente="2",
            auth=auth,
        )

    result = asyncio.run(_run())
    assert result is not None  # endpoint retorna dict de update — basta não erro
