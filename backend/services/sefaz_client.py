"""Cliente SOAP para captura automática de documentos fiscais recebidos da SEFAZ (NF-e, CT-e, MDF-e).

Usa zeep para SOAP + mTLS com certificado A1 do cliente.
Captura notas de fornecedores via distribuição de DF-e.
"""

import base64
import gzip
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests
from lxml import etree
from zeep import Client as ZeepClient
from zeep.transports import Transport

from middleware.lgpd import mask_cnpj
from services.cert_manager import decrypt_pfx, temp_cert_files
from services.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

# Endpoints SEFAZ por tipo e ambiente
SEFAZ_ENDPOINTS = {
    "nfe": {
        "1": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx?wsdl",
        "2": "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx?wsdl",
    },
    "cte": {
        "1": "https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx?wsdl",
        "2": "https://hom1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx?wsdl",
    },
    "mdfe": {
        "1": "https://mdfe.svrs.rs.gov.br/ws/MDFeDistribuicaoDFe/MDFeDistribuicaoDFe.asmx?wsdl",
        "2": "https://mdfe-homologacao.svrs.rs.gov.br/ws/MDFeDistribuicaoDFe/MDFeDistribuicaoDFe.asmx?wsdl",
    },
}

# Namespaces por tipo
NAMESPACES = {
    "nfe": "http://www.portalfiscal.inf.br/nfe",
    "cte": "http://www.portalfiscal.inf.br/cte",
    "mdfe": "http://www.portalfiscal.inf.br/mdfe",
}


@dataclass
class SefazDocument:
    """Documento retornado pela SEFAZ."""
    chave: str
    tipo: str
    nsu: str
    xml_content: str  # XML original (descompactado)
    schema: str  # resNFe, procNFe, etc.


@dataclass
class SefazResponse:
    """Resposta de uma consulta DistDFeInteresse."""
    cstat: str
    xmotivo: str
    ult_nsu: str
    max_nsu: str
    documents: list[SefazDocument]
    latency_ms: int


class SefazClient:
    """Cliente para captura automática de documentos recebidos da SEFAZ via SOAP + mTLS."""

    def __init__(self):
        self.ambiente = os.getenv("SEFAZ_AMBIENTE", "2")  # default homologação

    def consultar_distribuicao(
        self,
        cnpj: str,
        tipo: str,
        ult_nsu: str,
        pfx_encrypted,
        pfx_iv,
        tenant_id: str,
        pfx_password: str,
        cuf_autor: str = "35",  # SP default
        ambiente: str | None = None,  # per-tenant override
    ) -> SefazResponse:
        """Consulta documentos recebidos (notas de fornecedores) na SEFAZ.

        Args:
            cnpj: CNPJ da empresa (documentos recebidos)
            tipo: 'nfe', 'cte' ou 'mdfe'
            ult_nsu: Último NSU processado
            pfx_encrypted: Certificado .pfx cifrado — hex string from DB
                           (v2 format: "v2:<hex>" or legacy raw hex)
            pfx_iv: IV hex string (legacy v1) or None (v2)
            tenant_id: ID do tenant (para derivar chave AES)
            pfx_password: Senha do .pfx
            cuf_autor: Código UF do autor (default 35 = SP)
        """
        # Verifica circuit breaker
        if not circuit_breaker.can_execute(cnpj, tipo):
            state = circuit_breaker.get_state(cnpj, tipo)
            return SefazResponse(
                cstat="999",
                xmotivo=f"Circuit breaker {state.value} para {mask_cnpj(cnpj)}/{tipo}",
                ult_nsu=ult_nsu,
                max_nsu=ult_nsu,
                documents=[],
                latency_ms=0,
            )

        # Decifra o .pfx — auto-detect v1/v2 format
        pfx_encrypted_str = pfx_encrypted if isinstance(pfx_encrypted, str) else pfx_encrypted.hex() if isinstance(pfx_encrypted, bytes) else str(pfx_encrypted)

        if pfx_encrypted_str.startswith("v2:"):
            blob = bytes.fromhex(pfx_encrypted_str[3:])
            pfx_bytes = decrypt_pfx(blob, None, tenant_id)
        else:
            # Legacy v1: pfx_encrypted and pfx_iv are separate hex strings
            enc_bytes = bytes.fromhex(pfx_encrypted_str) if isinstance(pfx_encrypted_str, str) else pfx_encrypted
            iv_bytes = bytes.fromhex(pfx_iv) if isinstance(pfx_iv, str) else pfx_iv
            pfx_bytes = decrypt_pfx(enc_bytes, iv_bytes, tenant_id)

        effective_ambiente = ambiente or self.ambiente

        start_time = time.time()
        try:
            result = self._soap_call(
                cnpj, tipo, ult_nsu, pfx_bytes, pfx_password, cuf_autor,
                effective_ambiente,
            )
            circuit_breaker.record_success(cnpj, tipo)
            return result
        except Exception as e:
            circuit_breaker.record_failure(cnpj, tipo)
            latency = int((time.time() - start_time) * 1000)
            logger.error(f"SEFAZ error {mask_cnpj(cnpj)}/{tipo}: {e}")
            return SefazResponse(
                cstat="999",
                xmotivo=str(e),
                ult_nsu=ult_nsu,
                max_nsu=ult_nsu,
                documents=[],
                latency_ms=latency,
            )

    def _soap_call(
        self,
        cnpj: str,
        tipo: str,
        ult_nsu: str,
        pfx_bytes: bytes,
        pfx_password: str,
        cuf_autor: str,
        ambiente: str | None = None,
    ) -> SefazResponse:
        """Executa a chamada SOAP real à SEFAZ."""
        effective_ambiente = ambiente or self.ambiente
        ns = NAMESPACES[tipo]
        endpoint = SEFAZ_ENDPOINTS[tipo][effective_ambiente]

        start_time = time.time()

        with temp_cert_files(pfx_bytes, pfx_password) as (cert_path, key_path):
            # Sessão HTTP com mTLS
            session = requests.Session()
            session.cert = (cert_path, key_path)
            # MDF-e RS homologação usa cert SSL que não está na cadeia padrão
            session.verify = (tipo != "mdfe")

            transport = Transport(session=session, timeout=30)
            client = ZeepClient(wsdl=endpoint, transport=transport)

            # Monta o XML do request
            xml_request = self._build_dist_dfe_xml(
                cnpj, tipo, ult_nsu, cuf_autor, ns, effective_ambiente,
            )

            # Nome do service/operation e parâmetro variam por tipo
            service_name = self._get_service_name(tipo)
            param_name = {"nfe": "nfeDadosMsg", "cte": "cteDadosMsg", "mdfe": "_value_1"}[tipo]

            if tipo == "mdfe":
                # MDF-e: raw_response para evitar ComplexType
                with client.settings(raw_response=True):
                    raw_resp = client.service[service_name](**{param_name: xml_request})
                raw_root = etree.fromstring(raw_resp.content)
                # Busca retDistDFeInt dentro do SOAP envelope
                response = raw_root.find(f".//{{{ns}}}retDistDFeInt")
                if response is None:
                    for elem in raw_root.iter():
                        tag_local = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                        if tag_local == 'retDistDFeInt':
                            response = elem
                            break
                if response is None:
                    response = raw_root
            else:
                response = client.service[service_name](**{param_name: xml_request})

        latency_ms = int((time.time() - start_time) * 1000)
        return self._parse_response(response, tipo, latency_ms)

    def _build_dist_dfe_xml(
        self, cnpj: str, tipo: str, ult_nsu: str, cuf_autor: str, ns: str,
        ambiente: str | None = None,
    ) -> etree._Element:
        """Monta o XML distDFeInt."""
        effective_ambiente = ambiente or self.ambiente
        tag_prefix = {"nfe": "nfe", "cte": "cte", "mdfe": "mdfe"}[tipo]
        nsmap = {None: ns}

        root = etree.Element(f"distDFeInt", nsmap=nsmap)
        root.set("versao", "1.01")

        etree.SubElement(root, "tpAmb").text = effective_ambiente
        etree.SubElement(root, "cUFAutor").text = cuf_autor
        etree.SubElement(root, "CNPJ").text = cnpj

        dist_nsu = etree.SubElement(root, "distNSU")
        etree.SubElement(dist_nsu, "ultNSU").text = ult_nsu

        return root

    def _get_service_name(self, tipo: str) -> str:
        return {
            "nfe": "nfeDistDFeInteresse",
            "cte": "cteDistDFeInteresse",
            "mdfe": "mdfeDistDFeInteresse",
        }[tipo]

    def _parse_response(
        self, response, tipo: str, latency_ms: int
    ) -> SefazResponse:
        """Faz parse da resposta SOAP da SEFAZ."""
        # A resposta pode ser string XML ou objeto zeep
        if isinstance(response, str):
            root = etree.fromstring(response.encode())
        elif isinstance(response, bytes):
            root = etree.fromstring(response)
        elif hasattr(response, '_raw_elements'):
            # zeep retornou objeto com elementos XML internos
            root = response._raw_elements[0] if response._raw_elements else etree.Element("empty")
        else:
            # zeep pode retornar ComplexType; serializar via helpers
            from zeep.helpers import serialize_object
            serialized = serialize_object(response)
            # Tenta extrair campos diretamente do dict
            if isinstance(serialized, dict):
                cstat = str(serialized.get("cStat", "999"))
                xmotivo = str(serialized.get("xMotivo", ""))
                ult_nsu = str(serialized.get("ultNSU", "000000000000000"))
                max_nsu = str(serialized.get("maxNSU", ult_nsu))
                documents: list[SefazDocument] = []
                # Extrai documentos do loteDistDFe
                lote = serialized.get("loteDistDFe")
                if lote and hasattr(lote, 'get'):
                    doc_zips = lote.get("docZip", []) or []
                elif lote and hasattr(lote, 'docZip'):
                    doc_zips = lote.docZip or []
                else:
                    doc_zips = []
                for dz in doc_zips:
                    if hasattr(dz, '_value_1'):
                        b64_content = dz._value_1
                        nsu = getattr(dz, 'NSU', '') or ''
                        schema = getattr(dz, 'schema', '') or ''
                    elif isinstance(dz, dict):
                        b64_content = dz.get('_value_1', '')
                        nsu = dz.get('NSU', '')
                        schema = dz.get('schema', '')
                    else:
                        continue
                    if b64_content:
                        try:
                            xml_bytes = gzip.decompress(base64.b64decode(b64_content))
                            xml_str = xml_bytes.decode("utf-8")
                            chave = self._extract_chave(xml_str, tipo)
                            documents.append(SefazDocument(
                                chave=chave or f"unknown_{nsu}",
                                tipo=tipo.upper(),
                                nsu=nsu,
                                xml_content=xml_str,
                                schema=schema,
                            ))
                        except Exception as e:
                            logger.warning(f"Erro ao decodificar docZip NSU={nsu}: {e}")
                return SefazResponse(
                    cstat=cstat, xmotivo=xmotivo, ult_nsu=ult_nsu,
                    max_nsu=max_nsu, documents=documents, latency_ms=latency_ms,
                )
            root = etree.Element("empty")

        ns = NAMESPACES[tipo]
        nsmap = {"ns": ns}

        # Extrai campos do retDistDFeInt
        cstat = self._find_text(root, ".//ns:cStat", nsmap) or "999"
        xmotivo = self._find_text(root, ".//ns:xMotivo", nsmap) or ""
        ult_nsu = self._find_text(root, ".//ns:ultNSU", nsmap) or "000000000000000"
        max_nsu = self._find_text(root, ".//ns:maxNSU", nsmap) or ult_nsu

        documents: list[SefazDocument] = []

        # Extrai documentos dos loteDistDFe/docZip
        for doc_zip in root.iter(f"{{{ns}}}docZip"):
            nsu = doc_zip.get("NSU", "")
            schema = doc_zip.get("schema", "")

            # Conteúdo é base64 + gzip
            b64_content = doc_zip.text
            if b64_content:
                try:
                    xml_bytes = gzip.decompress(base64.b64decode(b64_content))
                    xml_str = xml_bytes.decode("utf-8")

                    # Extrai chave de acesso do XML
                    chave = self._extract_chave(xml_str, tipo)

                    documents.append(SefazDocument(
                        chave=chave or f"unknown_{nsu}",
                        tipo=tipo.upper(),
                        nsu=nsu,
                        xml_content=xml_str,
                        schema=schema,
                    ))
                except Exception as e:
                    logger.warning(f"Erro ao decodificar docZip NSU={nsu}: {e}")

        return SefazResponse(
            cstat=cstat,
            xmotivo=xmotivo,
            ult_nsu=ult_nsu,
            max_nsu=max_nsu,
            documents=documents,
            latency_ms=latency_ms,
        )

    def _extract_chave(self, xml_str: str, tipo: str) -> Optional[str]:
        """Extrai chave de acesso (44 dígitos) do XML do documento."""
        try:
            root = etree.fromstring(xml_str.encode())
            ns = NAMESPACES[tipo]
            # Tenta encontrar a chave em vários caminhos possíveis
            for tag in ["chNFe", "chCTe", "chMDFe", "chave"]:
                elem = root.find(f".//{{{ns}}}{tag}")
                if elem is not None and elem.text:
                    return elem.text
            # Fallback: busca qualquer tag que contenha 44 dígitos
            for elem in root.iter():
                if elem.text and len(elem.text.strip()) == 44 and elem.text.strip().isdigit():
                    return elem.text.strip()
        except Exception:
            pass
        return None

    def _find_text(
        self, root: etree._Element, xpath: str, nsmap: dict
    ) -> Optional[str]:
        elem = root.find(xpath, nsmap)
        return elem.text if elem is not None else None

    def check_status(self, tipo: str) -> dict:
        """Health check do endpoint SEFAZ."""
        endpoint = SEFAZ_ENDPOINTS.get(tipo, {}).get(self.ambiente)
        if not endpoint:
            return {"tipo": tipo, "status": "unknown", "ambiente": self.ambiente}

        try:
            start = time.time()
            resp = requests.get(
                endpoint.replace("?wsdl", ""),
                timeout=10,
                verify=True,
            )
            latency = int((time.time() - start) * 1000)
            return {
                "tipo": tipo,
                "ambiente": "homologação" if self.ambiente == "2" else "produção",
                "status": "online" if resp.status_code < 500 else "degraded",
                "latency_ms": latency,
            }
        except Exception as e:
            return {
                "tipo": tipo,
                "ambiente": "homologação" if self.ambiente == "2" else "produção",
                "status": "offline",
                "latency_ms": None,
            }


# Instância global
sefaz_client = SefazClient()
