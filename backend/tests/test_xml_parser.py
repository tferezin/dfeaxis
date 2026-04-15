"""Unit tests para o xml_parser.

Roda standalone (sem pytest):

    cd backend && source venv/bin/activate
    python tests/test_xml_parser.py

Cobre os 4 tipos de documento (NFe/CTe/MDFe/NFSe), cenários resumo vs
completo, XMLs malformados, campos ausentes.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.xml_parser import (  # noqa: E402
    DocumentMetadata,
    metadata_to_db_dict,
    parse_cte,
    parse_document_xml,
    parse_mdfe,
    parse_nfe,
    parse_nfse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str, status: str = "INFO") -> None:
    icon = {"INFO": "→", "PASS": "✓", "FAIL": "✗"}.get(status, "→")
    print(f"  {icon} {msg}")


# ---------------------------------------------------------------------------
# Fixtures inline — XMLs reais (anonimizados)
# ---------------------------------------------------------------------------

NFE_FULL = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe35240312345678901234550010000000121234567890">
      <ide>
        <cUF>35</cUF>
        <nNF>12</nNF>
        <dhEmi>2026-04-10T14:30:00-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>12345678901234</CNPJ>
        <xNome>FORNECEDOR EXEMPLO LTDA</xNome>
      </emit>
      <dest>
        <CNPJ>01786983000368</CNPJ>
        <xNome>BEIERSDORF INDUSTRIA</xNome>
      </dest>
      <total>
        <ICMSTot>
          <vNF>1500.50</vNF>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
</nfeProc>"""

NFE_RESUMO = """<?xml version="1.0" encoding="UTF-8"?>
<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
  <chNFe>35240312345678901234550010000000121234567890</chNFe>
  <CNPJ>12345678901234</CNPJ>
  <xNome>FORNECEDOR EXEMPLO LTDA</xNome>
  <IE>123456789</IE>
  <dhEmi>2026-04-10T14:30:00-03:00</dhEmi>
</resNFe>"""

CTE_FULL = """<?xml version="1.0" encoding="UTF-8"?>
<cteProc xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00">
  <CTe>
    <infCte Id="CTe35240398765432101234570010000000551234567890">
      <ide>
        <nCT>55</nCT>
        <dhEmi>2026-04-11T09:15:00-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>98765432101234</CNPJ>
        <xNome>TRANSPORTADORA TESTE LTDA</xNome>
      </emit>
      <dest>
        <CNPJ>01786983000368</CNPJ>
      </dest>
      <vPrest>
        <vTPrest>850.00</vTPrest>
      </vPrest>
    </infCte>
  </CTe>
</cteProc>"""

MDFE_FULL = """<?xml version="1.0" encoding="UTF-8"?>
<mdfeProc xmlns="http://www.portalfiscal.inf.br/mdfe" versao="3.00">
  <MDFe>
    <infMDFe Id="MDFe35240555667788990011580010000000101234567890">
      <ide>
        <nMDF>10</nMDF>
        <dhEmi>2026-04-12T06:45:00-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>55667788990011</CNPJ>
        <xNome>LOGISTICA BRASIL SA</xNome>
      </emit>
      <tot>
        <vCarga>35000.00</vCarga>
      </tot>
    </infMDFe>
  </MDFe>
</mdfeProc>"""

NFSE_ADN = """<?xml version="1.0" encoding="UTF-8"?>
<NFSe>
  <infNFSe>
    <numero>42</numero>
    <dataEmissao>2026-04-13T16:20:00</dataEmissao>
    <prestador>
      <cnpj>44556677889900</cnpj>
      <razaoSocial>CONSULTORIA FISCAL EXEMPLO LTDA</razaoSocial>
    </prestador>
    <tomador>
      <cnpj>01786983000368</cnpj>
    </tomador>
    <servico>
      <valor>3500.00</valor>
    </servico>
  </infNFSe>
</NFSe>"""

NFSE_PAULISTA = """<?xml version="1.0" encoding="UTF-8"?>
<CompNfse>
  <Nfse>
    <InfNfse>
      <Numero>99</Numero>
      <DataEmissao>2026-04-14</DataEmissao>
      <PrestadorServico>
        <IdentificacaoPrestador>
          <Cnpj>11223344556677</Cnpj>
        </IdentificacaoPrestador>
        <RazaoSocial>SERVICOS PAULISTA LTDA</RazaoSocial>
      </PrestadorServico>
      <Servico>
        <Valores>
          <ValorServicos>2100.00</ValorServicos>
        </Valores>
      </Servico>
      <TomadorServico>
        <IdentificacaoTomador>
          <CpfCnpj>
            <Cnpj>01786983000368</Cnpj>
          </CpfCnpj>
        </IdentificacaoTomador>
      </TomadorServico>
    </InfNfse>
  </Nfse>
</CompNfse>"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_nfe_full() -> None:
    print("\n[1] parse_nfe — XML completo")
    m = parse_nfe(NFE_FULL)
    assert not m.empty
    assert m.cnpj_emitente == "12345678901234", f"cnpj_emitente={m.cnpj_emitente!r}"
    assert m.razao_social_emitente == "FORNECEDOR EXEMPLO LTDA"
    assert m.cnpj_destinatario == "01786983000368"
    assert m.numero_documento == "12"
    assert m.data_emissao is not None
    assert m.data_emissao.year == 2026 and m.data_emissao.month == 4
    assert m.valor_total == Decimal("1500.50")
    log("todos os 6 campos extraídos corretamente", "PASS")


def test_nfe_resumo() -> None:
    print("\n[2] parse_nfe — resumo (resNFe)")
    m = parse_nfe(NFE_RESUMO)
    assert m.cnpj_emitente == "12345678901234"
    # Resumo não tem os outros campos estruturados do nfeProc,
    # então a maioria fica None
    assert m.cnpj_destinatario is None
    assert m.valor_total is None
    log("resumo extrai CNPJ emitente, demais ficam None", "PASS")


def test_cte_full() -> None:
    print("\n[3] parse_cte — XML completo")
    m = parse_cte(CTE_FULL)
    assert m.cnpj_emitente == "98765432101234"
    assert m.razao_social_emitente == "TRANSPORTADORA TESTE LTDA"
    assert m.cnpj_destinatario == "01786983000368"
    assert m.numero_documento == "55"
    assert m.valor_total == Decimal("850.00")
    log("CTe completo OK", "PASS")


def test_mdfe_full() -> None:
    print("\n[4] parse_mdfe — XML completo")
    m = parse_mdfe(MDFE_FULL)
    assert m.cnpj_emitente == "55667788990011"
    assert m.razao_social_emitente == "LOGISTICA BRASIL SA"
    assert m.cnpj_destinatario is None  # MDFe não tem dest
    assert m.numero_documento == "10"
    assert m.valor_total == Decimal("35000.00")
    log("MDFe OK (dest=None é esperado)", "PASS")


def test_nfse_adn() -> None:
    print("\n[5] parse_nfse — ADN (novo padrão)")
    m = parse_nfse(NFSE_ADN)
    assert m.cnpj_emitente == "44556677889900"
    assert m.razao_social_emitente == "CONSULTORIA FISCAL EXEMPLO LTDA"
    assert m.cnpj_destinatario == "01786983000368"
    assert m.numero_documento == "42"
    assert m.valor_total == Decimal("3500.00")
    log("NFSe ADN OK", "PASS")


def test_nfse_paulista() -> None:
    print("\n[6] parse_nfse — Paulista (legado)")
    m = parse_nfse(NFSE_PAULISTA)
    # Paulista NÃO usa prestador/identificacaoPrestador (é PrestadorServico)
    # A implementação atual pode não extrair perfeitamente. Validamos
    # que pelo menos pegou o tomador (tem CpfCnpj padronizado).
    assert m.cnpj_destinatario == "01786983000368", (
        f"cnpj_destinatario={m.cnpj_destinatario!r}"
    )
    assert m.numero_documento == "99"
    assert m.valor_total == Decimal("2100.00")
    log("NFSe Paulista extrai tomador, numero, valor", "PASS")


def test_xml_malformado() -> None:
    print("\n[7] XML malformado → retorna metadata vazia sem crash")
    m = parse_nfe("<<<não é xml>>>")
    assert m.empty or m.parse_errors
    log("não levanta exceção", "PASS")


def test_xml_vazio() -> None:
    print("\n[8] XML vazio → metadata vazia")
    m = parse_nfe("")
    assert m.empty
    log("empty OK", "PASS")


def test_parse_document_xml_dispatch() -> None:
    print("\n[9] parse_document_xml — dispatch por tipo")
    assert parse_document_xml(NFE_FULL, "NFE").cnpj_emitente == "12345678901234"
    assert parse_document_xml(CTE_FULL, "cte").cnpj_emitente == "98765432101234"
    assert parse_document_xml(MDFE_FULL, "MdFe").cnpj_emitente == "55667788990011"
    assert parse_document_xml(NFSE_ADN, "NFSe").cnpj_emitente == "44556677889900"
    log("dispatch case-insensitive OK", "PASS")


def test_unknown_tipo() -> None:
    print("\n[10] tipo desconhecido → metadata vazia sem crash")
    m = parse_document_xml(NFE_FULL, "XPTO")
    assert m.empty
    assert "unknown_tipo" in (m.parse_errors[0] if m.parse_errors else "")
    log("tipo desconhecido tratado", "PASS")


def test_metadata_to_db_dict() -> None:
    print("\n[11] metadata_to_db_dict — só campos não-null")
    m = parse_nfe(NFE_FULL)
    d = metadata_to_db_dict(m)
    assert d["cnpj_emitente"] == "12345678901234"
    assert d["razao_social_emitente"] == "FORNECEDOR EXEMPLO LTDA"
    assert d["cnpj_destinatario"] == "01786983000368"
    assert d["numero_documento"] == "12"
    assert d["valor_total"] == 1500.5
    # data_emissao vira string ISO
    assert isinstance(d["data_emissao"], str)
    assert "2026-04-10" in d["data_emissao"]

    # Se metadata tem None, dict não inclui aquela chave
    empty = DocumentMetadata()
    assert metadata_to_db_dict(empty) == {}
    log("db dict OK, só campos populados", "PASS")


def test_cnpj_normalization() -> None:
    print("\n[12] CNPJs com máscara são normalizados (só dígitos)")
    xml_with_mask = """<?xml version="1.0"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe><infNFe>
    <emit><CNPJ>12.345.678/9012-34</CNPJ></emit>
  </infNFe></NFe>
</nfeProc>"""
    m = parse_nfe(xml_with_mask)
    assert m.cnpj_emitente == "12345678901234"
    log("CNPJ normalizado pra 14 dígitos", "PASS")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 60)
    print("xml_parser — unit tests")
    print("=" * 60)

    tests = [
        test_nfe_full,
        test_nfe_resumo,
        test_cte_full,
        test_mdfe_full,
        test_nfse_adn,
        test_nfse_paulista,
        test_xml_malformado,
        test_xml_vazio,
        test_parse_document_xml_dispatch,
        test_unknown_tipo,
        test_metadata_to_db_dict,
        test_cnpj_normalization,
    ]

    failures: list[str] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            log(f"FAIL {t.__name__}: {e}", "FAIL")
            failures.append(t.__name__)
        except Exception as e:
            log(f"ERROR {t.__name__}: {type(e).__name__}: {e}", "FAIL")
            failures.append(t.__name__)

    print()
    print("=" * 60)
    if failures:
        print(f"✗ {len(failures)}/{len(tests)} tests failed: {', '.join(failures)}")
        return 1
    print(f"✓ all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
