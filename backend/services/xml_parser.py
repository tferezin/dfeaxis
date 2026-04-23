"""Parser de XMLs fiscais (NFe, CTe, MDFe, NFSe) pra extrair metadata padronizada.

Usado pelo pipeline de captura pra popular as colunas `cnpj_emitente`,
`razao_social_emitente`, `cnpj_destinatario`, `numero_documento`,
`data_emissao`, `valor_total` da tabela `documents` (migration 015).

NUNCA levanta exceção — se o XML estiver malformado ou um campo estiver
ausente, retorna DocumentMetadata com campos None. O caller pode então
gravar o que conseguiu extrair e deixar o resto NULL no banco.

Suporta os 4 tipos (NFe, CTe, MDFe, NFSe) e também os formatos "resumo"
que a SEFAZ distribui antes do cliente confirmar recepção — resumos
têm menos campos (tipicamente só chave + CNPJ emitente).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from lxml import etree

logger = logging.getLogger("dfeaxis.xml_parser")

# Namespaces padrão SEFAZ
NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_MDFE = "http://www.portalfiscal.inf.br/mdfe"


@dataclass
class DocumentMetadata:
    """Metadata extraída de um XML fiscal. Todos os campos opcionais."""

    cnpj_emitente: Optional[str] = None
    razao_social_emitente: Optional[str] = None
    cnpj_destinatario: Optional[str] = None
    numero_documento: Optional[str] = None
    data_emissao: Optional[datetime] = None
    valor_total: Optional[Decimal] = None
    # Campos de debug/tracking (não vão pro banco)
    parse_errors: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        """True se nada foi extraído — útil pra logging."""
        return not any(
            [
                self.cnpj_emitente,
                self.razao_social_emitente,
                self.cnpj_destinatario,
                self.numero_documento,
                self.data_emissao,
                self.valor_total,
            ]
        )


# ---------------------------------------------------------------------------
# Helpers de parsing
# ---------------------------------------------------------------------------


def _clean_cnpj(raw: str | None) -> Optional[str]:
    """Remove não-dígitos e valida que sobraram 14 chars. None se inválido."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 14:
        return None
    return digits


def _find_text(root: etree._Element, xpath: str, ns: dict) -> Optional[str]:
    """Retorna texto do primeiro match XPath, ou None."""
    try:
        el = root.find(xpath, ns)
    except SyntaxError:
        return None
    if el is None:
        return None
    text = el.text or ""
    text = text.strip()
    return text or None


def _find_text_any(root: etree._Element, xpaths: list[tuple[str, dict]]) -> Optional[str]:
    """Tenta múltiplos XPaths (com ou sem namespace). Retorna o primeiro match."""
    for xpath, ns in xpaths:
        text = _find_text(root, xpath, ns)
        if text:
            return text
    return None


def _parse_decimal(raw: str | None) -> Optional[Decimal]:
    """Parse de string decimal BR → Decimal. None se falhar."""
    if not raw:
        return None
    try:
        # XML SEFAZ usa ponto como separador decimal; BR às vezes vírgula
        normalized = raw.strip().replace(",", ".")
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def _parse_datetime(raw: str | None) -> Optional[datetime]:
    """Parse de ISO datetime ou date. None se falhar."""
    if not raw:
        return None
    raw = raw.strip()
    # Tenta formatos conhecidos
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",   # 2024-01-15T10:30:00-03:00
        "%Y-%m-%dT%H:%M:%S",     # 2024-01-15T10:30:00
        "%Y-%m-%d %H:%M:%S",     # 2024-01-15 10:30:00
        "%Y-%m-%d",              # 2024-01-15
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    # Fallback — tenta o parser ISO nativo
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_parse(xml_str: str) -> Optional[etree._Element]:
    """Parse defensivo. Retorna None se malformado."""
    if not xml_str or not xml_str.strip():
        return None
    try:
        if isinstance(xml_str, str):
            xml_bytes = xml_str.encode("utf-8")
        else:
            xml_bytes = xml_str
        # recover=True tolera XML ligeiramente malformado
        parser = etree.XMLParser(recover=True, remove_blank_text=False)
        root = etree.fromstring(xml_bytes, parser=parser)
        return root
    except (etree.XMLSyntaxError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("xml_parser: falha ao parsear XML: %s", exc)
        return None


def _strip_namespaces(root: etree._Element) -> etree._Element:
    """Remove namespaces de todos os elementos da árvore in-place.

    Necessário pra NFSe porque não há namespace padronizado entre
    padrões (ADN, Paulista, ABRASF 2.04, etc.). Com default namespace
    xmlns="...abrasf.org.br/nfse.xsd" lxml exige mapeamento de prefixo
    em XPath, e os nossos xpaths usam tags puras. Stripar os
    namespaces deixa todos os xpaths funcionando pros 3 padrões.
    """
    for elem in root.iter():
        if isinstance(elem.tag, str) and "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]
    etree.cleanup_namespaces(root)
    return root


# Eventos da NFe/CTe/MDFe (manifestação, cancelamento, carta de correção)
# chegam pelo mesmo canal DistDFe que as notas — precisam ser filtrados
# antes de persistir em `documents`, senão poluem a tabela com rows sem
# emitente/valor/numero e inflam a contagem da competência.
_EVENTO_ROOT_TAGS = frozenset(
    {
        "procEventoNFe",
        "procEventoCTe",
        "procEventoMDFe",
        "evento",
        "eventoNFe",
        "eventoCTe",
        "eventoMDFe",
    }
)


def is_evento_xml(xml_str: str) -> bool:
    """Detecta se um XML é evento SEFAZ (manifestação, cancelamento, etc.)
    em vez de documento fiscal (NFe/CTe/MDFe/NFSe).

    Usado pelo pipeline de polling pra pular upsert em `documents` — eventos
    não devem ser gravados como se fossem notas.

    Retorna False se xml_str for vazio, malformado, ou root tag não for
    um evento conhecido. Never raises.
    """
    if not xml_str:
        return False
    root = _safe_parse(xml_str)
    if root is None:
        return False
    try:
        localname = etree.QName(root).localname
    except ValueError:
        return False
    return localname in _EVENTO_ROOT_TAGS


# ---------------------------------------------------------------------------
# NFe
# ---------------------------------------------------------------------------


def parse_nfe(xml_str: str) -> DocumentMetadata:
    """Extrai metadata de NFe 4.0.

    Suporta tanto `<nfeProc><NFe>` (autorizada) quanto `<resNFe>` (resumo).
    Resumos só têm chNFe + CNPJ emitente — os outros campos ficam None.
    """
    meta = DocumentMetadata()
    root = _safe_parse(xml_str)
    if root is None:
        meta.parse_errors.append("xml_parse_failed")
        return meta

    ns = {"nfe": NS_NFE}

    # Detecta se é resumo (<resNFe>)
    tag_local = etree.QName(root).localname
    if tag_local == "resNFe":
        # Resumo: só CNPJ do emitente
        cnpj = _find_text(root, "./nfe:CNPJ", ns) or _find_text(root, "./CNPJ", {})
        meta.cnpj_emitente = _clean_cnpj(cnpj)
        return meta

    # Full NFe: emit, dest, ide, total
    meta.cnpj_emitente = _clean_cnpj(
        _find_text_any(
            root,
            [
                (".//nfe:emit/nfe:CNPJ", ns),
                (".//emit/CNPJ", {}),
            ],
        )
    )

    meta.razao_social_emitente = _find_text_any(
        root,
        [
            (".//nfe:emit/nfe:xNome", ns),
            (".//emit/xNome", {}),
        ],
    )

    meta.cnpj_destinatario = _clean_cnpj(
        _find_text_any(
            root,
            [
                (".//nfe:dest/nfe:CNPJ", ns),
                (".//dest/CNPJ", {}),
            ],
        )
    )

    meta.numero_documento = _find_text_any(
        root,
        [
            (".//nfe:ide/nfe:nNF", ns),
            (".//ide/nNF", {}),
        ],
    )

    meta.data_emissao = _parse_datetime(
        _find_text_any(
            root,
            [
                (".//nfe:ide/nfe:dhEmi", ns),
                (".//ide/dhEmi", {}),
            ],
        )
    )

    meta.valor_total = _parse_decimal(
        _find_text_any(
            root,
            [
                (".//nfe:total/nfe:ICMSTot/nfe:vNF", ns),
                (".//total/ICMSTot/vNF", {}),
            ],
        )
    )

    return meta


# ---------------------------------------------------------------------------
# CTe
# ---------------------------------------------------------------------------


def parse_cte(xml_str: str) -> DocumentMetadata:
    """Extrai metadata de CT-e (modelo 57) ou CT-e OS (modelo 67).

    Ambos compartilham o namespace NS_CTE e os campos principais de
    ide/emit/ide. A diferença é:
      - CT-e OS tem root `<CTeOS>` em vez de `<CTe>`, resumo `resCTeOS`
        em vez de `resCTe`, envelope autorizado `cteOSProc` vs `cteProc`.
      - CT-e OS usa `<toma>/<toma4>` (tomador) em vez de `<dest>` — é
        transporte de pessoas/valores, não mercadoria.
    Como o namespace é o mesmo (`http://www.portalfiscal.inf.br/cte`) e
    os XPaths com `.//` localizam elementos em qualquer profundidade, o
    mesmo parser serve pros dois — apenas adicionamos fallbacks.
    """
    meta = DocumentMetadata()
    root = _safe_parse(xml_str)
    if root is None:
        meta.parse_errors.append("xml_parse_failed")
        return meta

    ns = {"cte": NS_CTE}

    tag_local = etree.QName(root).localname
    # Resumos (schema reduzido que SEFAZ envia antes da ciência): resCTe
    # pro modelo 57, resCTeOS pro modelo 67. Só trazem CNPJ do emitente.
    if tag_local in ("resCTe", "resCTeOS"):
        cnpj = _find_text(root, "./cte:CNPJ", ns) or _find_text(root, "./CNPJ", {})
        meta.cnpj_emitente = _clean_cnpj(cnpj)
        return meta

    meta.cnpj_emitente = _clean_cnpj(
        _find_text_any(
            root,
            [
                (".//cte:emit/cte:CNPJ", ns),
                (".//emit/CNPJ", {}),
            ],
        )
    )

    meta.razao_social_emitente = _find_text_any(
        root,
        [
            (".//cte:emit/cte:xNome", ns),
            (".//emit/xNome", {}),
        ],
    )

    # CT-e normal (57) tem <dest>, CT-e OS (67) tem <toma> ou <toma4>.
    # Tentamos os 3 — o primeiro que existir ganha.
    meta.cnpj_destinatario = _clean_cnpj(
        _find_text_any(
            root,
            [
                (".//cte:dest/cte:CNPJ", ns),
                (".//dest/CNPJ", {}),
                (".//cte:toma4/cte:CNPJ", ns),
                (".//toma4/CNPJ", {}),
                (".//cte:toma/cte:CNPJ", ns),
                (".//toma/CNPJ", {}),
            ],
        )
    )

    meta.numero_documento = _find_text_any(
        root,
        [
            (".//cte:ide/cte:nCT", ns),
            (".//ide/nCT", {}),
        ],
    )

    meta.data_emissao = _parse_datetime(
        _find_text_any(
            root,
            [
                (".//cte:ide/cte:dhEmi", ns),
                (".//ide/dhEmi", {}),
            ],
        )
    )

    meta.valor_total = _parse_decimal(
        _find_text_any(
            root,
            [
                (".//cte:vPrest/cte:vTPrest", ns),
                (".//vPrest/vTPrest", {}),
            ],
        )
    )

    return meta


# ---------------------------------------------------------------------------
# MDFe
# ---------------------------------------------------------------------------


def parse_mdfe(xml_str: str) -> DocumentMetadata:
    """Extrai metadata de MDFe. Não tem destinatário único (é manifesto)."""
    meta = DocumentMetadata()
    root = _safe_parse(xml_str)
    if root is None:
        meta.parse_errors.append("xml_parse_failed")
        return meta

    ns = {"mdfe": NS_MDFE}

    tag_local = etree.QName(root).localname
    if tag_local == "resMDFe":
        cnpj = _find_text(root, "./mdfe:CNPJ", ns) or _find_text(root, "./CNPJ", {})
        meta.cnpj_emitente = _clean_cnpj(cnpj)
        return meta

    meta.cnpj_emitente = _clean_cnpj(
        _find_text_any(
            root,
            [
                (".//mdfe:emit/mdfe:CNPJ", ns),
                (".//emit/CNPJ", {}),
            ],
        )
    )

    meta.razao_social_emitente = _find_text_any(
        root,
        [
            (".//mdfe:emit/mdfe:xNome", ns),
            (".//emit/xNome", {}),
        ],
    )

    # MDFe não tem <dest> — deixa None

    meta.numero_documento = _find_text_any(
        root,
        [
            (".//mdfe:ide/mdfe:nMDF", ns),
            (".//ide/nMDF", {}),
        ],
    )

    meta.data_emissao = _parse_datetime(
        _find_text_any(
            root,
            [
                (".//mdfe:ide/mdfe:dhEmi", ns),
                (".//ide/dhEmi", {}),
            ],
        )
    )

    meta.valor_total = _parse_decimal(
        _find_text_any(
            root,
            [
                (".//mdfe:tot/mdfe:vCarga", ns),
                (".//tot/vCarga", {}),
            ],
        )
    )

    return meta


# ---------------------------------------------------------------------------
# NFSe — heterogênea (ADN + Paulista + outros)
# ---------------------------------------------------------------------------


def parse_nfse(xml_str: str) -> DocumentMetadata:
    """Extrai metadata de NFSe. Suporta ADN, Paulista e ABRASF 2.04.

    NFSe é heterogênea — cada município tem seu padrão. Os 3 mais comuns:
      - ADN (Ambiente Nacional): `<NFSe><infNFSe><prestador><cnpj>`
      - Paulista (São Paulo legado): sem namespace, tags com PascalCase
      - ABRASF 2.04: `xmlns="http://www.abrasf.org.br/nfse.xsd"` com
        `<CompNfse><Nfse><InfNfse><PrestadorServico>`

    Estratégia: stripa namespaces após parse (para ABRASF cair no mesmo
    XPath sem prefixo do Paulista) e tenta XPaths de cada variante em
    cascata. O primeiro match vence.
    """
    meta = DocumentMetadata()
    root = _safe_parse(xml_str)
    if root is None:
        meta.parse_errors.append("xml_parse_failed")
        return meta

    # ABRASF tem default namespace — strip torna todos os xpaths agnósticos
    root = _strip_namespaces(root)

    # CNPJ emitente (prestador)
    meta.cnpj_emitente = _clean_cnpj(
        _find_text_any(
            root,
            [
                # ADN
                (".//infNFSe/prestador/cnpj", {}),
                (".//infNFSe/prestador/CNPJ", {}),
                # ABRASF 2.04
                (".//PrestadorServico/IdentificacaoPrestador/CpfCnpj/Cnpj", {}),
                (".//PrestadorServico/IdentificacaoPrestador/Cnpj", {}),
                # Paulista legado
                (".//Prestador/CpfCnpj/Cnpj", {}),
                (".//prestador/CpfCnpj/Cnpj", {}),
                (".//prestadorServico/identificacaoPrestador/cnpj", {}),
                # Fallback: IdentificacaoPrestador direto em qualquer lugar
                (".//IdentificacaoPrestador/CpfCnpj/Cnpj", {}),
                (".//IdentificacaoPrestador/Cnpj", {}),
            ],
        )
    )

    meta.razao_social_emitente = _find_text_any(
        root,
        [
            (".//infNFSe/prestador/xNome", {}),
            (".//infNFSe/prestador/razaoSocial", {}),
            # ABRASF 2.04
            (".//PrestadorServico/RazaoSocial", {}),
            # Paulista
            (".//Prestador/RazaoSocial", {}),
            (".//prestadorServico/razaoSocial", {}),
        ],
    )

    meta.cnpj_destinatario = _clean_cnpj(
        _find_text_any(
            root,
            [
                (".//infNFSe/tomador/cnpj", {}),
                # ABRASF 2.04
                (".//TomadorServico/IdentificacaoTomador/CpfCnpj/Cnpj", {}),
                (".//TomadorServico/IdentificacaoTomador/Cnpj", {}),
                # Paulista
                (".//Tomador/CpfCnpj/Cnpj", {}),
                (".//tomador/CpfCnpj/Cnpj", {}),
                # Fallback
                (".//IdentificacaoTomador/CpfCnpj/Cnpj", {}),
            ],
        )
    )

    meta.numero_documento = _find_text_any(
        root,
        [
            (".//infNFSe/numero", {}),
            (".//InfNfse/Numero", {}),
            (".//IdentificacaoNfse/Numero", {}),
            (".//Numero", {}),
        ],
    )

    meta.data_emissao = _parse_datetime(
        _find_text_any(
            root,
            [
                (".//infNFSe/dataEmissao", {}),
                (".//InfNfse/DataEmissao", {}),
                (".//DataEmissao", {}),
            ],
        )
    )

    meta.valor_total = _parse_decimal(
        _find_text_any(
            root,
            [
                (".//infNFSe/servico/valor", {}),
                (".//Servico/Valores/ValorServicos", {}),
                (".//servico/valores/valorServicos", {}),
                (".//ValorServicos", {}),
            ],
        )
    )

    return meta


# ---------------------------------------------------------------------------
# Dispatch público
# ---------------------------------------------------------------------------


def parse_document_xml(xml_str: str, tipo: str) -> DocumentMetadata:
    """Dispatch por tipo de documento. Case-insensitive.

    Parameters
    ----------
    xml_str : str
        Conteúdo XML do documento.
    tipo : str
        "NFE" | "CTE" | "CTEOS" | "MDFE" | "NFSE" (case-insensitive).
        CTEOS é o CT-e Outros Serviços (modelo 67) — transporte de
        passageiros e valores. Usa o mesmo parser do CT-e 57 porque
        namespace e estrutura core são idênticos.

    Returns
    -------
    DocumentMetadata
        Nunca None. Campos podem ser None individualmente. Verifique
        `meta.empty` pra saber se nada foi extraído.
    """
    if not xml_str:
        return DocumentMetadata(parse_errors=["empty_xml"])

    tipo_upper = (tipo or "").strip().upper()
    if tipo_upper == "NFE":
        return parse_nfe(xml_str)
    # CT-e (57) e CT-e OS (67) usam o mesmo parser — mesmo namespace,
    # mesmos XPaths core. Distinção acontece no dispatcher de captura
    # ao persistir no banco (tipo="CTE" vs "CTEOS" conforme schema do
    # docZip retornado pelo DistDFe).
    if tipo_upper in ("CTE", "CTEOS"):
        return parse_cte(xml_str)
    if tipo_upper == "MDFE":
        return parse_mdfe(xml_str)
    if tipo_upper == "NFSE":
        return parse_nfse(xml_str)

    logger.warning("xml_parser: tipo desconhecido %r", tipo)
    return DocumentMetadata(parse_errors=[f"unknown_tipo:{tipo}"])


def metadata_to_db_dict(meta: DocumentMetadata) -> dict:
    """Converte DocumentMetadata em dict pronto pra upsert no Supabase.

    Usa apenas colunas não-NULL pra não sobrescrever dados já existentes
    (útil em backfill e em re-parse). Formata timestamps em ISO.
    """
    out: dict = {}
    if meta.cnpj_emitente:
        out["cnpj_emitente"] = meta.cnpj_emitente
    if meta.razao_social_emitente:
        out["razao_social_emitente"] = meta.razao_social_emitente[:255]
    if meta.cnpj_destinatario:
        out["cnpj_destinatario"] = meta.cnpj_destinatario
    if meta.numero_documento:
        out["numero_documento"] = meta.numero_documento[:64]
    if meta.data_emissao:
        out["data_emissao"] = meta.data_emissao.isoformat()
    if meta.valor_total is not None:
        # Converte Decimal pra float pra JSON serialization do Supabase
        out["valor_total"] = float(meta.valor_total)
    return out
