"""Unit tests for cStat masking functions in routers/polling.py.

Covers the pure helpers `_friendly_status_from_cstat` and
`_sanitize_result_for_erp` that shield ERP external consumers (X-API-Key)
from raw SEFAZ cStat codes.

Pure functions — no Supabase or network required. Runs in milliseconds.
"""

from __future__ import annotations

import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from routers.polling import (  # noqa: E402
    _friendly_status_from_cstat,
    _sanitize_result_for_erp,
)


class TestFriendlyStatusFromCstat:
    """Mapeamento cStat SEFAZ → friendly_status neutro pro ERP."""

    def test_138_means_documents_available(self):
        status, retry = _friendly_status_from_cstat("138")
        assert status == "documents_available"
        assert retry is None

    def test_137_means_no_new_documents_with_1h_retry(self):
        status, retry = _friendly_status_from_cstat("137")
        assert status == "no_new_documents"
        # NT 2014.002: aguardar 1h após 137. 3660s = 61min (margem SEFAZ).
        assert retry == 3660

    def test_656_means_rate_limited_with_longer_retry(self):
        status, retry = _friendly_status_from_cstat("656")
        assert status == "rate_limited"
        # 62min = 60min SEFAZ + 2min margem extra pós-bloqueio real.
        assert retry == 3720

    def test_empty_cstat_is_unknown(self):
        status, retry = _friendly_status_from_cstat("")
        assert status == "unknown"
        assert retry is None

    def test_zero_cstat_is_unknown(self):
        status, retry = _friendly_status_from_cstat("0")
        assert status == "unknown"
        assert retry is None

    def test_other_cstats_are_generic_sefaz_error(self):
        # Códigos diversos de erro SEFAZ viram "sefaz_error" com retry curto.
        for cstat in ("215", "542", "999", "100"):
            status, retry = _friendly_status_from_cstat(cstat)
            assert status == "sefaz_error", f"cstat {cstat} não mapeou"
            assert retry == 900  # 15 min


class TestSanitizeResultForErp:
    """Sanitização do dict de resultado pro ERP externo.

    cstat e xmotivo DEVEM ser apagados; friendly_status + retry_after
    preenchem o lugar. Outros campos (tipo, docs_found, saved_to_db)
    passam transparentes.
    """

    def test_cstat_and_xmotivo_are_masked(self):
        result = {
            "tipo": "CTE",
            "status": "success",
            "cstat": "656",
            "xmotivo": "Rejeicao: Consumo Indevido",
            "docs_found": 0,
            "latency_ms": 820,
            "saved_to_db": False,
        }
        sanitized = _sanitize_result_for_erp(result)
        assert sanitized["cstat"] == ""
        assert sanitized["xmotivo"] == ""
        # Textos SEFAZ crus não devem vazar
        assert "Rejeicao" not in str(sanitized)
        assert "Consumo" not in str(sanitized)

    def test_friendly_status_replaces_cstat(self):
        result = {
            "tipo": "CTE", "status": "success",
            "cstat": "137", "xmotivo": "Nenhum documento",
            "docs_found": 0, "latency_ms": 500, "saved_to_db": False,
        }
        sanitized = _sanitize_result_for_erp(result)
        assert sanitized["friendly_status"] == "no_new_documents"
        assert sanitized["retry_after_seconds"] == 3660

    def test_transparent_fields_preserved(self):
        result = {
            "tipo": "MDFE", "status": "success",
            "cstat": "138", "xmotivo": "Documento",
            "docs_found": 7, "latency_ms": 1200, "saved_to_db": True,
        }
        sanitized = _sanitize_result_for_erp(result)
        assert sanitized["tipo"] == "MDFE"
        assert sanitized["status"] == "success"
        assert sanitized["docs_found"] == 7
        assert sanitized["latency_ms"] == 1200
        assert sanitized["saved_to_db"] is True
        assert sanitized["friendly_status"] == "documents_available"

    def test_error_field_is_truncated_to_200_chars(self):
        # Evita vazar stack traces longos com info sensível
        long_error = "x" * 500
        result = {
            "tipo": "NFSE", "status": "error",
            "cstat": "999", "xmotivo": "Erro",
            "docs_found": 0, "latency_ms": 0, "saved_to_db": False,
            "error": long_error,
        }
        sanitized = _sanitize_result_for_erp(result)
        assert len(sanitized["error"]) == 200

    def test_missing_error_field_omitted(self):
        result = {
            "tipo": "CTE", "status": "success",
            "cstat": "138", "xmotivo": "",
            "docs_found": 1, "latency_ms": 100, "saved_to_db": True,
        }
        sanitized = _sanitize_result_for_erp(result)
        assert "error" not in sanitized


class TestErpNeverSeesConsumoIndevido:
    """Regressão: nenhum valor de saída contém palavras SEFAZ críticas."""

    @pytest.mark.parametrize("cstat,xmotivo", [
        ("656", "Rejeicao: Consumo Indevido (Deve ser aguardado 1 hora para efetuar nova solicitacao)"),
        ("137", "Nenhum documento localizado"),
        ("215", "Falha no Schema XML do lote de NFe"),
    ])
    def test_no_sefaz_raw_text_leaks(self, cstat, xmotivo):
        result = {
            "tipo": "CTE", "status": "success",
            "cstat": cstat, "xmotivo": xmotivo,
            "docs_found": 0, "latency_ms": 500, "saved_to_db": False,
        }
        sanitized = _sanitize_result_for_erp(result)
        sanitized_text = str(sanitized)
        # Palavras que NUNCA devem vazar pra ERP externo
        forbidden = ["Consumo Indevido", "Rejeicao", "Falha no Schema"]
        for word in forbidden:
            assert word not in sanitized_text, (
                f"vazou '{word}' em sanitized: {sanitized}"
            )
