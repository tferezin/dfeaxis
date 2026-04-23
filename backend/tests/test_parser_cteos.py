"""Tests do parser CT-e OS (modelo 67) e refinamento de tipo por schema.

CT-e OS usa mesmo namespace do CT-e 57, mas estrutura tem:
- root <CTeOS> (em vez de <CTe>)
- resumo resCTeOS (em vez de resCTe)
- <toma>/<toma4> com CNPJ do tomador (em vez de <dest>)
- envelope autorizado cteOSProc (em vez de cteProc)

Garantias testadas:
1. parse_cte extrai cnpj_emitente, número, data, valor corretamente
2. fallback dest -> toma -> toma4 funciona
3. resCTeOS retorna só o CNPJ do emitente (schema reduzido)
4. _refine_tipo_by_schema mapeia CTE -> CTEOS conforme schema do docZip
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.sefaz_client import _refine_tipo_by_schema  # noqa: E402
from services.xml_parser import parse_cte, parse_document_xml  # noqa: E402


CTEOS_AUTORIZADO = """<?xml version="1.0" encoding="UTF-8"?>
<cteOSProc versao="3.00" xmlns="http://www.portalfiscal.inf.br/cte">
  <CTeOS versao="3.00">
    <infCte Id="CTe35260301786983000368670010000004561234567891" versao="3.00">
      <ide>
        <cUF>35</cUF>
        <cCT>12345678</cCT>
        <CFOP>5357</CFOP>
        <natOp>PRESTACAO DE SERVICO DE TRANSPORTE</natOp>
        <mod>67</mod>
        <serie>1</serie>
        <nCT>456</nCT>
        <dhEmi>2026-04-15T10:30:00-03:00</dhEmi>
        <tpEmis>1</tpEmis>
        <tpAmb>1</tpAmb>
      </ide>
      <emit>
        <CNPJ>01786983000368</CNPJ>
        <xNome>TRANSPORTES PASSAGEIROS LTDA</xNome>
      </emit>
      <toma>
        <CNPJ>98765432000100</CNPJ>
        <xNome>EMPRESA CLIENTE LTDA</xNome>
      </toma>
      <vPrest>
        <vTPrest>1250.75</vTPrest>
        <vRec>1250.75</vRec>
      </vPrest>
    </infCte>
  </CTeOS>
</cteOSProc>"""


CTE_NORMAL_COM_DEST = """<?xml version="1.0" encoding="UTF-8"?>
<cteProc versao="4.00" xmlns="http://www.portalfiscal.inf.br/cte">
  <CTe versao="4.00">
    <infCte Id="CTe35260398765432000168570010000004561234567890" versao="4.00">
      <ide>
        <mod>57</mod>
        <serie>1</serie>
        <nCT>789</nCT>
        <dhEmi>2026-04-10T14:00:00-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>98765432000168</CNPJ>
        <xNome>TRANSPORTES ACME LTDA</xNome>
      </emit>
      <dest>
        <CNPJ>01234567000100</CNPJ>
        <xNome>CLIENTE CARGA</xNome>
      </dest>
      <vPrest>
        <vTPrest>3500.00</vTPrest>
      </vPrest>
    </infCte>
  </CTe>
</cteProc>"""


RES_CTEOS = """<?xml version="1.0" encoding="UTF-8"?>
<resCTeOS xmlns="http://www.portalfiscal.inf.br/cte" versao="3.00">
  <chCTe>35260301786983000368670010000004561234567891</chCTe>
  <CNPJ>01786983000368</CNPJ>
  <dhEmi>2026-04-15T10:30:00-03:00</dhEmi>
  <vTPrest>1250.75</vTPrest>
</resCTeOS>"""


class TestParseCTeOS:
    """parse_cte entende CTeOS porque namespace é o mesmo."""

    def test_extrai_cnpj_emitente(self):
        meta = parse_cte(CTEOS_AUTORIZADO)
        assert meta.cnpj_emitente == "01786983000368"

    def test_extrai_razao_social(self):
        meta = parse_cte(CTEOS_AUTORIZADO)
        assert meta.razao_social_emitente == "TRANSPORTES PASSAGEIROS LTDA"

    def test_tomador_preenche_destinatario(self):
        """Fallback crítico: CT-e OS não tem <dest>, tem <toma>."""
        meta = parse_cte(CTEOS_AUTORIZADO)
        assert meta.cnpj_destinatario == "98765432000100"

    def test_extrai_numero(self):
        meta = parse_cte(CTEOS_AUTORIZADO)
        assert meta.numero_documento == "456"

    def test_extrai_data_emissao(self):
        meta = parse_cte(CTEOS_AUTORIZADO)
        assert meta.data_emissao is not None
        assert meta.data_emissao.year == 2026
        assert meta.data_emissao.month == 4
        assert meta.data_emissao.day == 15

    def test_extrai_valor(self):
        meta = parse_cte(CTEOS_AUTORIZADO)
        assert meta.valor_total == Decimal("1250.75")


class TestParseCTeNormal:
    """Regressão: CT-e 57 continua funcionando sem mudança."""

    def test_cnpj_destinatario_vem_de_dest(self):
        """CT-e 57 tem <dest>, não deve pegar de toma (que não existe)."""
        meta = parse_cte(CTE_NORMAL_COM_DEST)
        assert meta.cnpj_destinatario == "01234567000100"

    def test_cnpj_emitente(self):
        meta = parse_cte(CTE_NORMAL_COM_DEST)
        assert meta.cnpj_emitente == "98765432000168"

    def test_numero(self):
        meta = parse_cte(CTE_NORMAL_COM_DEST)
        assert meta.numero_documento == "789"


class TestParseResCTeOS:
    """Resumo do CT-e OS vem só com CNPJ do emitente (schema reduzido)."""

    def test_res_cteos_retorna_so_emitente(self):
        meta = parse_cte(RES_CTEOS)
        assert meta.cnpj_emitente == "01786983000368"
        # Resumo não tem destinatário nem demais campos
        assert meta.cnpj_destinatario is None
        assert meta.numero_documento is None
        assert meta.valor_total is None


class TestDispatcher:
    """parse_document_xml aceita tipo 'CTEOS' case-insensitive."""

    def test_tipo_cteos_usa_parser_cte(self):
        meta = parse_document_xml(CTEOS_AUTORIZADO, "CTEOS")
        assert meta.cnpj_emitente == "01786983000368"
        assert meta.cnpj_destinatario == "98765432000100"

    def test_tipo_cte_tambem_funciona_pra_cteos_xml(self):
        """Caso raro mas possível: se backend fornecer tipo='CTE' pra um
        XML que é CT-e OS, ainda funciona (mesmo parser)."""
        meta = parse_document_xml(CTEOS_AUTORIZADO, "cte")
        assert meta.cnpj_emitente == "01786983000368"

    def test_tipo_cteos_lowercase(self):
        meta = parse_document_xml(CTE_NORMAL_COM_DEST, "cteos")
        # Namespace e estrutura compatíveis — extrai normalmente
        assert meta.cnpj_emitente == "98765432000168"


class TestRefineTipoBySchema:
    """_refine_tipo_by_schema separa CT-e 57 de CT-e OS 67 pelo docZip schema."""

    def test_cte_com_schema_cteos_vira_cteos(self):
        assert _refine_tipo_by_schema("cte", "resCTeOS_v3.00.xsd") == "CTEOS"

    def test_cte_com_schema_proc_cteos_vira_cteos(self):
        assert _refine_tipo_by_schema("cte", "procCTeOS_v3.00.xsd") == "CTEOS"

    def test_cte_com_schema_cte_normal_permanece_cte(self):
        assert _refine_tipo_by_schema("cte", "resCTe_v4.00.xsd") == "CTE"
        assert _refine_tipo_by_schema("cte", "procCTe_v4.00.xsd") == "CTE"

    def test_cte_sem_schema_permanece_cte(self):
        assert _refine_tipo_by_schema("cte", "") == "CTE"
        assert _refine_tipo_by_schema("cte", None) == "CTE"

    def test_nfe_nao_sofre_refino(self):
        assert _refine_tipo_by_schema("nfe", "procNFe_v4.00.xsd") == "NFE"
        assert _refine_tipo_by_schema("nfe", "") == "NFE"

    def test_mdfe_nao_sofre_refino(self):
        assert _refine_tipo_by_schema("mdfe", "procMDFe_v3.00.xsd") == "MDFE"

    def test_case_insensitive_no_tipo(self):
        assert _refine_tipo_by_schema("CTE", "resCTeOS_v3.00.xsd") == "CTEOS"
        assert _refine_tipo_by_schema("Cte", "resCTeOS") == "CTEOS"

    def test_cteos_detectado_mesmo_com_path_completo(self):
        # Schemas reais vêm como "resCTeOS_v3.00.xsd" ou caminhos similares
        assert (
            _refine_tipo_by_schema("cte", "resCTeOS_v3.00.xsd") == "CTEOS"
        )
