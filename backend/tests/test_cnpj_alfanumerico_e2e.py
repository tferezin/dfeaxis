"""Testes E2E de coexistencia CNPJ numerico + alfanumerico em fluxos reais.

Cobre fluxos via Pydantic + mocks de Supabase/Stripe — sem precisar subir
backend uvicorn. Garantia: o sistema processa CNPJs dos dois formatos em
todos os pontos do fluxo de cadastro -> checkout -> mascaramento.

Cenarios:
1. POST /certificates body validation com CNPJ alfanumerico
2. POST /certificates body validation com CNPJ numerico (regressao)
3. POST /billing/checkout gate com tenant tendo CNPJ alfanumerico no banco
4. Lookup .eq("cnpj", X) com CNPJ alfanumerico (case sensitive ok pos upper)
5. Sanitizer fluxo completo: log com CNPJs mistos vira mascarado
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

from models.schemas import _validate_cnpj  # noqa: E402
from middleware.lgpd import sanitize_text, mask_cnpj  # noqa: E402
from routers.billing import checkout, CheckoutRequest  # noqa: E402
from services.billing.plans import load_plans  # noqa: E402


# CNPJs validos pra testes (DV calculado com algoritmo unificado ord(c)-48)
NUMERIC_CNPJ = "01786983000368"
ALFA_CNPJ_1 = "12ABC34501DE35"
ALFA_CNPJ_2 = "AB12CD34000184"


# ============================================================================
# 1. CADASTRO DE CERTIFICADO — Pydantic body validation
# ============================================================================

def test_cadastro_aceita_cnpj_numerico_regressao():
    """Endpoint POST /certificates aceita CNPJ numerico (cliente atual)."""
    # Simula validacao do form body:
    # routers/certificates.py linha 50: cnpj = _validate_cnpj(cnpj)
    cnpj_validated = _validate_cnpj(NUMERIC_CNPJ)
    assert cnpj_validated == NUMERIC_CNPJ


def test_cadastro_aceita_cnpj_alfanumerico_novo():
    """Endpoint POST /certificates aceita CNPJ alfanumerico (cliente jul/26+)."""
    cnpj_validated = _validate_cnpj(ALFA_CNPJ_1)
    assert cnpj_validated == ALFA_CNPJ_1


def test_cadastro_aceita_cnpj_alfanumerico_formatado():
    """Frontend envia CNPJ alfanumerico formatado (XX.XXX.XXX/XXXX-XX)."""
    formatted = "12.ABC.345/01DE-35"
    cnpj_validated = _validate_cnpj(formatted)
    assert cnpj_validated == ALFA_CNPJ_1


def test_cadastro_aceita_cnpj_alfanumerico_lowercase():
    """Lowercase e normalizado (cliente cola CNPJ em case errado)."""
    cnpj_validated = _validate_cnpj("ab12cd34000184")
    assert cnpj_validated == ALFA_CNPJ_2


# ============================================================================
# 2. GATE DE CNPJ NO CHECKOUT — funciona com mistura de formatos
# ============================================================================

def _mock_sb_with_cert_count(count: int) -> MagicMock:
    """Mock supabase client retornando N certs ativos."""
    sb = MagicMock()
    res = MagicMock()
    res.count = count
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = res
    return sb


def _call_checkout(price_id: str, cert_count: int) -> HTTPException | dict:
    """Chama checkout() com mocks; retorna exception ou response."""
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
                  return_value={"id": "cs_test", "url": "https://stripe.test/x"}):
        try:
            return asyncio.run(_run())
        except HTTPException as e:
            return e


def _starter_price_id() -> str:
    for p in load_plans():
        if p.key == "starter":
            return p.price_id_monthly
    raise RuntimeError("starter plan not in catalog")


def _business_price_id() -> str:
    for p in load_plans():
        if p.key == "business":
            return p.price_id_monthly
    raise RuntimeError("business plan not in catalog")


def test_checkout_gate_bloqueia_starter_com_2_cnpjs_alfanumericos():
    """Tenant com 2 CNPJs alfanumericos NAO pode escolher Starter (max=1)."""
    result = _call_checkout(_starter_price_id(), cert_count=2)
    assert isinstance(result, HTTPException)
    assert result.status_code == 422
    assert result.detail["error_code"] == "PLAN_CNPJ_LIMIT_EXCEEDED"


def test_checkout_gate_aceita_business_com_5_cnpjs_mistos():
    """Tenant com 5 CNPJs (mistura numericos + alfanumericos) pode Business (max=5)."""
    # O gate conta certificados, nao distingue formato. Coexistencia OK.
    result = _call_checkout(_business_price_id(), cert_count=5)
    # Sucesso (CheckoutResponse Pydantic, nao exception)
    assert not isinstance(result, HTTPException)
    assert hasattr(result, "url") and result.url.startswith("https://")


# ============================================================================
# 3. LOOKUP CASE-INSENSITIVE — CNPJ alfanumerico salvo upper, busca upper
# ============================================================================

def test_validate_cnpj_normaliza_pra_upper_garante_lookup_consistente():
    """
    Garantia de coexistencia em lookups: validate_cnpj sempre retorna upper.
    Insert e busca usam o mesmo formato — sem case mismatch.
    """
    inputs = [
        ("ab12cd34000184", "AB12CD34000184"),
        ("AB12CD34000184", "AB12CD34000184"),
        ("Ab12Cd34000184", "AB12CD34000184"),
        ("ab.12c.d34/0001-84", "AB12CD34000184"),
    ]
    # Todos os inputs devem normalizar pra MESMA representacao
    results = [_validate_cnpj(inp) for inp, _ in inputs]
    assert len(set(results)) == 1, f"normalizacao inconsistente: {results}"
    assert results[0] == "AB12CD34000184"


def test_cnpj_numerico_nao_e_afetado_pelo_upper():
    """CNPJ numerico passa pelo upper sem mudanca (digitos nao tem case)."""
    assert _validate_cnpj(NUMERIC_CNPJ) == NUMERIC_CNPJ
    assert _validate_cnpj(NUMERIC_CNPJ).upper() == NUMERIC_CNPJ


# ============================================================================
# 4. LGPD SANITIZER — log misto sai mascarado
# ============================================================================

def test_sanitizer_mascara_cnpj_numerico_em_log():
    """Log com CNPJ numerico cru e mascarado."""
    log = f"Cliente {NUMERIC_CNPJ} fez upload de certificado"
    sanitized = sanitize_text(log)
    assert NUMERIC_CNPJ not in sanitized
    assert "X" in sanitized  # tem mascaramento


def test_sanitizer_mascara_cnpj_alfanumerico_em_log():
    """Log com CNPJ alfanumerico cru tambem e mascarado (P0 do audit anterior)."""
    log = f"Cliente {ALFA_CNPJ_1} fez upload de certificado"
    sanitized = sanitize_text(log)
    assert ALFA_CNPJ_1 not in sanitized
    assert "X" in sanitized


def test_sanitizer_mascara_lote_misto_no_mesmo_log():
    """Sistema com mistura: log com varios CNPJs (numericos + alfanumericos)."""
    log = (
        f"Polling iniciado. Tenants ativos: "
        f"{NUMERIC_CNPJ} (cliente atual), "
        f"{ALFA_CNPJ_1} (cliente novo jul/26), "
        f"{ALFA_CNPJ_2} (cliente novo)"
    )
    sanitized = sanitize_text(log)
    # Nenhum CNPJ original sobrevive
    assert NUMERIC_CNPJ not in sanitized
    assert ALFA_CNPJ_1 not in sanitized
    assert ALFA_CNPJ_2 not in sanitized
    # Mas o resto do texto fica intacto
    assert "Polling iniciado" in sanitized
    assert "Tenants ativos" in sanitized


# ============================================================================
# 5. FLUXO INTEGRADO — cadastro + lookup + mask
# ============================================================================

def test_fluxo_completo_cliente_alfanumerico():
    """
    Fluxo end-to-end:
    1. Cliente envia CNPJ alfanumerico no form (lowercase, formatado)
    2. Backend valida e normaliza
    3. Insert no banco usa formato normalizado
    4. Lookup posterior bate (mesmo formato)
    5. Logs sao sanitizados
    """
    # 1. Frontend envia
    user_input = "ab.12c.d34/0001-84"

    # 2. Backend valida
    db_value = _validate_cnpj(user_input)
    assert db_value == "AB12CD34000184"

    # 3. Insert (simulado): banco recebe upper sem formatacao
    db_table = {"cnpj": db_value, "tenant_id": "tenant-x"}

    # 4. Lookup posterior (cliente busca pelo CNPJ que cadastrou)
    user_search = "AB12CD34000184"  # frontend ja normaliza
    search_value = _validate_cnpj(user_search)
    assert search_value == db_table["cnpj"], "lookup falha por mismatch de case"

    # 5. Log sanitizado (CNPJ nao vaza)
    log = f"Cliente {db_value} fez polling"
    sanitized = sanitize_text(log)
    assert db_value not in sanitized
    assert "Cliente" in sanitized


def test_fluxo_completo_cliente_numerico_regressao():
    """Mesmo fluxo, mas com CNPJ numerico (cliente atual nao e afetado)."""
    user_input = "01.786.983/0003-68"
    db_value = _validate_cnpj(user_input)
    assert db_value == NUMERIC_CNPJ

    db_table = {"cnpj": db_value, "tenant_id": "tenant-y"}

    search_value = _validate_cnpj(NUMERIC_CNPJ)
    assert search_value == db_table["cnpj"]

    log = f"Cliente {db_value} fez polling"
    sanitized = sanitize_text(log)
    assert db_value not in sanitized
