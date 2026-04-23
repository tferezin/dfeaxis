"""Tests for enriched DocumentoOut — evita ERP cliente parsear XML.

Campos adicionados na migration 015 + expostos no response /api/v1/documentos:
supplier_cnpj, supplier_name, company_cnpj, nota_numero, data_emissao, valor_total.

Testes puros do schema (sem Supabase). Se alguém remover campos do schema
sem migrar consumers, esses testes quebram.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.schemas import DocumentoOut  # noqa: E402


class TestDocumentoOutCamposEnriquecidos:
    """Garante que DocumentoOut carrega os metadados extraídos do XML."""

    def test_documento_completo_com_metadados(self):
        doc = DocumentoOut(
            chave="35260301786983000368550010000000011234567890",
            tipo="NFE",
            nsu="000000000000100",
            xml_b64="PD94bWw=",
            fetched_at=datetime(2026, 4, 23, 10, 30, tzinfo=timezone.utc),
            manifestacao_status="ciencia",
            is_resumo=False,
            supplier_cnpj="12345678000190",
            supplier_name="FORNECEDOR TESTE LTDA",
            company_cnpj="98765432000100",
            nota_numero="000001234",
            data_emissao=datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc),
            valor_total=15750.50,
        )
        assert doc.supplier_cnpj == "12345678000190"
        assert doc.supplier_name == "FORNECEDOR TESTE LTDA"
        assert doc.company_cnpj == "98765432000100"
        assert doc.nota_numero == "000001234"
        assert doc.data_emissao.year == 2026
        assert doc.valor_total == 15750.50

    def test_resumo_sem_metadados_tambem_funciona(self):
        """Resumos (is_resumo=True) não têm XML completo, então metadados
        são NULL. Schema deve aceitar sem quebrar."""
        doc = DocumentoOut(
            chave="35260301786983000368550010000000011234567890",
            tipo="NFE",
            nsu="000000000000100",
            xml_b64="",
            fetched_at=datetime(2026, 4, 23, tzinfo=timezone.utc),
            is_resumo=True,
        )
        assert doc.supplier_cnpj is None
        assert doc.supplier_name is None
        assert doc.nota_numero is None
        assert doc.data_emissao is None
        assert doc.valor_total is None

    def test_campos_opcionais_nao_quebram_consumer_antigo(self):
        """Regressão: consumer que não conhece os campos novos ainda funciona
        porque eles têm default None. Resposta continua sendo valida se o
        cliente só lê chave/tipo/nsu/xml_b64."""
        doc = DocumentoOut(
            chave="352603017869830003685500100000000112345678",
            tipo="NFE",
            nsu="000000000000001",
            xml_b64="PD94bWw=",
            fetched_at=datetime.now(timezone.utc),
        )
        # Campos "velhos" do contrato — consumer antigo ainda lê sem erro
        assert doc.chave.startswith("35")
        assert doc.tipo == "NFE"
        assert doc.xml_b64 == "PD94bWw="


class TestDocumentoOutSerializacao:
    """Garante que o JSON emitido tem os campos novos pra cliente deserializar."""

    def test_json_inclui_todos_os_campos_enriquecidos(self):
        doc = DocumentoOut(
            chave="x" * 44,
            tipo="NFE",
            nsu="1",
            xml_b64="PD94bWw=",
            fetched_at=datetime.now(timezone.utc),
            supplier_cnpj="12345678000190",
            nota_numero="42",
            valor_total=100.0,
        )
        dumped = doc.model_dump()
        # Campos enriquecidos presentes na serialização
        assert "supplier_cnpj" in dumped
        assert "supplier_name" in dumped
        assert "company_cnpj" in dumped
        assert "nota_numero" in dumped
        assert "data_emissao" in dumped
        assert "valor_total" in dumped

    def test_json_com_valores_none_ainda_emite_chaves(self):
        """Cliente ABAP/ADVPL precisa saber que o campo existe mesmo
        quando vazio — evita erro 'field not found' em parsers rígidos."""
        doc = DocumentoOut(
            chave="x" * 44,
            tipo="CTE",
            nsu="1",
            xml_b64="",
            fetched_at=datetime.now(timezone.utc),
            is_resumo=True,
        )
        dumped = doc.model_dump()
        assert dumped["supplier_cnpj"] is None
        assert dumped["valor_total"] is None
