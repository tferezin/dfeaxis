"""Testes de coexistencia CNPJ numerico + alfanumerico (Reforma Tributaria 2026).

Cobertura:
1. Regressao: CNPJs numericos atuais continuam validando IDENTICO
2. Novos: CNPJs alfanumericos validam corretamente
3. Coexistencia: ambos os formatos no mesmo fluxo (validate, mask, parser)
4. Casos invalidos: DV errado, todos iguais, formato errado, letras minusculas

Referencia: NT 2025.001 RFB. Vigente jul/2026.
"""

from __future__ import annotations

import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.schemas import _validate_cnpj  # noqa: E402
from services.xml_parser import _clean_cnpj  # noqa: E402
from middleware.lgpd import mask_cnpj, sanitize_text  # noqa: E402


# CNPJs numericos atuais (DV calculado com algoritmo tradicional int(c))
NUMERIC_VALID = [
    "01786983000368",  # usado em test_lgpd_sanitizer.py
    "12345678000195",
    "11222333000181",
]

# CNPJs alfanumericos validos (DV calculado com ord(c)-48 conforme NT 2025.001)
# Gerados programaticamente — algoritmo confere com a propria funcao validate_cnpj
ALFA_VALID = [
    "12ABC34501DE35",
    "AB12CD34000184",
    "XY99ZZ88000131",
    "ABCDEF00000160",
]


# ============================================================================
# REGRESSAO — CNPJs numericos continuam validando como antes
# ============================================================================

@pytest.mark.parametrize("cnpj", NUMERIC_VALID)
def test_regressao_cnpj_numerico_valida(cnpj: str):
    """CNPJs numericos atuais validam identico ao comportamento pre-mudanca."""
    result = _validate_cnpj(cnpj)
    assert result == cnpj


@pytest.mark.parametrize("cnpj", NUMERIC_VALID)
def test_regressao_cnpj_numerico_formatado_valida(cnpj: str):
    """CNPJ numerico com formatacao (.- /) tambem valida."""
    formatted = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    result = _validate_cnpj(formatted)
    assert result == cnpj


def test_regressao_dv_invalido_ainda_falha():
    """CNPJ numerico com DV errado continua sendo rejeitado."""
    with pytest.raises(ValueError, match="digito verificador"):
        _validate_cnpj("12345678000196")  # DV correto seria 95


def test_regressao_todos_zeros_ainda_invalido():
    """CNPJ all-zero continua rejeitado."""
    with pytest.raises(ValueError):
        _validate_cnpj("00000000000000")


def test_regressao_todos_iguais_invalido():
    """CNPJ all-same-digit continua rejeitado."""
    with pytest.raises(ValueError):
        _validate_cnpj("11111111111111")


# ============================================================================
# NOVOS — CNPJs alfanumericos validam
# ============================================================================

@pytest.mark.parametrize("cnpj", ALFA_VALID)
def test_cnpj_alfanumerico_valida(cnpj: str):
    """CNPJ alfanumerico (Reforma Tributaria 2026) valida corretamente."""
    result = _validate_cnpj(cnpj)
    assert result == cnpj


@pytest.mark.parametrize("cnpj", ALFA_VALID)
def test_cnpj_alfanumerico_formatado_valida(cnpj: str):
    """CNPJ alfanumerico com formatacao tambem valida."""
    formatted = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    result = _validate_cnpj(formatted)
    assert result == cnpj


def test_cnpj_alfanumerico_lowercase_normaliza_pra_upper():
    """CNPJ alfanumerico em lowercase e normalizado pra UPPER."""
    result = _validate_cnpj("ab12cd34000184")
    assert result == "AB12CD34000184"


def test_cnpj_alfanumerico_dv_deve_ser_numerico():
    """CNPJ com letras nas 2 ultimas posicoes (DV) e rejeitado."""
    with pytest.raises(ValueError, match="14 caracteres"):
        _validate_cnpj("12ABC34501DEAB")


def test_cnpj_alfanumerico_dv_invalido_falha():
    """CNPJ alfanumerico com DV errado e rejeitado."""
    with pytest.raises(ValueError, match="digito verificador"):
        _validate_cnpj("12ABC34501DE99")  # DV correto seria 35


def test_cnpj_alfanumerico_acentos_rejeitado():
    """CNPJ com acentos (ÃÇ etc) e rejeitado — Reforma usa ASCII A-Z."""
    with pytest.raises(ValueError):
        _validate_cnpj("ABÇÃEF00000160")


# ============================================================================
# XML PARSER — _clean_cnpj aceita ambos
# ============================================================================

@pytest.mark.parametrize("cnpj", NUMERIC_VALID + ALFA_VALID)
def test_xml_parser_aceita_ambos_formatos(cnpj: str):
    """_clean_cnpj preserva tanto numericos quanto alfanumericos."""
    assert _clean_cnpj(cnpj) == cnpj


def test_xml_parser_alfanumerico_lowercase_normaliza():
    """_clean_cnpj normaliza alfanumericos pra uppercase."""
    assert _clean_cnpj("ab12cd34000184") == "AB12CD34000184"


def test_xml_parser_remove_formatacao():
    """_clean_cnpj remove ponto, barra, hifen, espaco."""
    assert _clean_cnpj("AB.12C.D34/0001-84") == "AB12CD34000184"
    assert _clean_cnpj("12.345.678/0001-95") == "12345678000195"


def test_xml_parser_invalido_retorna_none():
    """Caracteres fora de [A-Z0-9] retornam None."""
    assert _clean_cnpj("AB12CD34000###") is None
    assert _clean_cnpj("only12chars12") is None


# ============================================================================
# LGPD MASK — mascarar funciona pros dois formatos
# ============================================================================

def test_mask_cnpj_numerico_mantem_comportamento():
    """Mascaramento de CNPJ numerico identico ao anterior."""
    assert mask_cnpj("01786983000368") == "XXXXXXXX0003XX"


def test_mask_cnpj_alfanumerico_mascarado():
    """CNPJ alfanumerico tambem e mascarado: XXXXXXXX{filial}XX."""
    assert mask_cnpj("AB12CD34000184") == "XXXXXXXX0001XX"


def test_mask_cnpj_alfanumerico_formatado():
    """CNPJ alfanumerico formatado vira mascara formatada."""
    assert mask_cnpj("AB.12C.D34/0001-84") == "XX.XXX.XXX/0001-XX"


def test_mask_cnpj_lowercase_normaliza():
    """Lowercase e normalizado antes de mascarar."""
    assert mask_cnpj("ab12cd34000184") == "XXXXXXXX0001XX"


def test_mask_cnpj_invalido_retorna_invalid():
    """Input invalido retorna 'CNPJ_INVALID' (mesmo comportamento)."""
    assert mask_cnpj("123") == "CNPJ_INVALID"


# ============================================================================
# COEXISTENCIA — fluxo end-to-end com ambos os formatos no mesmo lote
# ============================================================================

def test_coexistencia_validate_lote_misto():
    """Lote misto (numericos + alfanumericos) valida sem precisar distinguir."""
    cnpjs = NUMERIC_VALID + ALFA_VALID
    for cnpj in cnpjs:
        assert _validate_cnpj(cnpj) == cnpj


def test_coexistencia_clean_lote_misto():
    """_clean_cnpj funciona pros dois formatos no mesmo lote."""
    cnpjs = NUMERIC_VALID + ALFA_VALID
    for cnpj in cnpjs:
        assert _clean_cnpj(cnpj) == cnpj


def test_coexistencia_mask_lote_misto():
    """Mascaramento funciona pros dois formatos."""
    for cnpj in NUMERIC_VALID + ALFA_VALID:
        masked = mask_cnpj(cnpj)
        assert masked != "CNPJ_INVALID"
        # Mascara mantem 4 digitos do meio (filial) e mascara o resto
        assert masked.count("X") == 10
        # Original nao aparece no resultado
        assert cnpj[:2] not in masked or "X" in masked[:2]


def test_coexistencia_sanitize_text_lote_misto():
    """Sanitizer encontra e mascara CNPJs numericos E alfanumericos no mesmo log."""
    log_text = (
        f"Recebido CNPJ {NUMERIC_VALID[0]} do emitente, "
        f"destinatario {ALFA_VALID[0]}. Processando."
    )
    sanitized = sanitize_text(log_text)
    # Nenhum dos CNPJs originais deve sobrar em texto cru
    assert NUMERIC_VALID[0] not in sanitized
    assert ALFA_VALID[0] not in sanitized
    # Mas o restante do texto continua intacto
    assert "Recebido CNPJ" in sanitized
    assert "destinatario" in sanitized


# ============================================================================
# CASOS DE BORDA — comportamentos defensivos
# ============================================================================

def test_string_vazia_rejeitada():
    """String vazia e rejeitada."""
    with pytest.raises(ValueError):
        _validate_cnpj("")


def test_menos_de_14_chars_rejeitado():
    """Menos de 14 chars e rejeitado."""
    with pytest.raises(ValueError):
        _validate_cnpj("AB12CD3400")


def test_mais_de_14_chars_rejeitado():
    """Mais de 14 chars (sem formatacao) e rejeitado."""
    with pytest.raises(ValueError):
        _validate_cnpj("AB12CD34000184X")


def test_apenas_letras_rejeitado_porque_dv_deve_ser_numerico():
    """CNPJ com letras nas posicoes 13-14 e rejeitado (DV deve ser numerico)."""
    with pytest.raises(ValueError):
        _validate_cnpj("ABCDEFGHIJKLMN")


def test_clean_cnpj_input_none_retorna_none():
    """_clean_cnpj com None retorna None (sem crash)."""
    assert _clean_cnpj(None) is None
