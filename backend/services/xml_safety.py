"""Parser XML endurecido — defesa em profundidade contra XXE / billion laughs / SSRF.

Modulo compartilhado pra todos os call sites que parseiam XML do SEFAZ ou
de cliente. Promovido de routers/sap_drc.py durante auditoria de seguranca
(item #2 do auto-review pos-merge).

Uso:
    from services.xml_safety import safe_fromstring
    root = safe_fromstring(xml_bytes_or_str)
"""

from __future__ import annotations

from lxml import etree


def safe_xml_parser(*, recover: bool = False, remove_blank_text: bool = False) -> etree.XMLParser:
    """Parser endurecido contra ataques XML.

    - resolve_entities=False: bloqueia expansao de entidades (XXE classico
      e billion laughs). XMLs de NFe/CTe/MDFe/NFSe nao usam entidades.
    - no_network=True: bloqueia SYSTEM/PUBLIC com URL externa (DTD/entity
      external resolution = SSRF).
    - huge_tree=False: rejeita arvores absurdamente grandes (DoS).
    - load_dtd=False: nao processa DTD inline.

    Args:
        recover: se True, parser tenta continuar em XMLs malformados (uso
                 raro — alguns XMLs do polling chegam truncados).
        remove_blank_text: se True, normaliza whitespace.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        load_dtd=False,
        recover=recover,
        remove_blank_text=remove_blank_text,
    )


def safe_fromstring(content: bytes | str, **parser_kwargs) -> etree._Element:
    """Wrapper de etree.fromstring que SEMPRE usa parser endurecido.

    Aceita bytes ou str (converte automaticamente). Os kwargs sao passados
    pra safe_xml_parser (ex: recover=True).
    """
    parser = safe_xml_parser(**parser_kwargs)
    if isinstance(content, str):
        # lxml exige bytes — converte UTF-8 default
        content = content.encode("utf-8")
    return etree.fromstring(content, parser)
