"""Serviço de Manifestação do Destinatário (NF-e).

Envia eventos ao webservice RecepcaoEvento da SEFAZ:
- 210210: Ciência da Operação
- 210200: Confirmação da Operação
- 210220: Desconhecimento da Operação
- 210240: Operação não Realizada
"""

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests
from lxml import etree
from zeep import Client as ZeepClient
from zeep.transports import Transport

from services.cert_manager import decrypt_pfx, temp_cert_files
from services.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

# Evento de Manifestação do Destinatário — NF-e
RECEPCAO_EVENTO_ENDPOINTS = {
    "1": "https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx?wsdl",
    "2": "https://hom1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx?wsdl",
}

NFE_NS = "http://www.portalfiscal.inf.br/nfe"

EVENTO_DESCRICAO = {
    "210210": "Ciencia da Operacao",
    "210200": "Confirmacao da Operacao",
    "210220": "Desconhecimento da Operacao",
    "210240": "Operacao nao Realizada",
}


@dataclass
class ManifestacaoResponse:
    """Resposta do envio de evento de manifestação."""
    cstat: str
    xmotivo: str
    protocolo: Optional[str]
    latency_ms: int
    success: bool


class ManifestacaoService:
    """Envia eventos de Manifestação do Destinatário à SEFAZ."""

    def __init__(self):
        self.ambiente = os.getenv("SEFAZ_AMBIENTE", "2")

    def enviar_evento(
        self,
        chave_acesso: str,
        cnpj: str,
        tipo_evento: str,
        pfx_encrypted: bytes,
        pfx_iv: bytes,
        tenant_id: str,
        pfx_password: str,
        justificativa: str = "",
    ) -> ManifestacaoResponse:
        """Envia evento de manifestação para uma NF-e.

        Args:
            chave_acesso: Chave de acesso da NF-e (44 dígitos)
            cnpj: CNPJ do destinatário
            tipo_evento: '210210', '210200', '210220' ou '210240'
            pfx_encrypted: Certificado cifrado
            pfx_iv: IV da cifragem
            tenant_id: ID do tenant
            pfx_password: Senha do .pfx
            justificativa: Obrigatória para 210240 (min 15 chars)
        """
        if tipo_evento not in EVENTO_DESCRICAO:
            return ManifestacaoResponse(
                cstat="999",
                xmotivo=f"Tipo de evento inválido: {tipo_evento}",
                protocolo=None,
                latency_ms=0,
                success=False,
            )

        if tipo_evento == "210240" and len(justificativa) < 15:
            return ManifestacaoResponse(
                cstat="999",
                xmotivo="Justificativa obrigatória (min 15 chars) para evento 210240",
                protocolo=None,
                latency_ms=0,
                success=False,
            )

        # Circuit breaker
        cb_key = f"manif_{cnpj}"
        if not circuit_breaker.can_execute(cb_key, "evento"):
            return ManifestacaoResponse(
                cstat="999",
                xmotivo="Circuit breaker aberto para manifestação",
                protocolo=None,
                latency_ms=0,
                success=False,
            )

        pfx_bytes = decrypt_pfx(pfx_encrypted, pfx_iv, tenant_id)

        start_time = time.time()
        try:
            result = self._soap_call(
                chave_acesso, cnpj, tipo_evento, pfx_bytes,
                pfx_password, justificativa,
            )
            circuit_breaker.record_success(cb_key, "evento")
            return result
        except Exception as e:
            circuit_breaker.record_failure(cb_key, "evento")
            latency = int((time.time() - start_time) * 1000)
            logger.error(f"Manifestação error {chave_acesso}: {e}")
            return ManifestacaoResponse(
                cstat="999",
                xmotivo=str(e),
                protocolo=None,
                latency_ms=latency,
                success=False,
            )

    def _soap_call(
        self,
        chave_acesso: str,
        cnpj: str,
        tipo_evento: str,
        pfx_bytes: bytes,
        pfx_password: str,
        justificativa: str,
    ) -> ManifestacaoResponse:
        """Executa chamada SOAP ao RecepcaoEvento."""
        endpoint = RECEPCAO_EVENTO_ENDPOINTS[self.ambiente]
        start_time = time.time()

        with temp_cert_files(pfx_bytes, pfx_password) as (cert_path, key_path):
            session = requests.Session()
            session.cert = (cert_path, key_path)
            session.verify = True

            transport = Transport(session=session, timeout=30)
            client = ZeepClient(wsdl=endpoint, transport=transport)

            xml_evento = self._build_evento_xml(
                chave_acesso, cnpj, tipo_evento, justificativa,
            )

            response = client.service.nfeRecepcaoEvento(nfeDadosMsg=xml_evento)

        latency_ms = int((time.time() - start_time) * 1000)
        return self._parse_response(response, latency_ms)

    def _build_evento_xml(
        self,
        chave_acesso: str,
        cnpj: str,
        tipo_evento: str,
        justificativa: str,
    ) -> etree._Element:
        """Monta XML do envEvento para Manifestação do Destinatário."""
        nsmap = {None: NFE_NS}

        # envEvento
        env_evento = etree.Element("envEvento", nsmap=nsmap)
        env_evento.set("versao", "1.00")

        etree.SubElement(env_evento, "idLote").text = str(int(time.time()))

        # evento
        evento = etree.SubElement(env_evento, "evento")
        evento.set("versao", "1.00")

        inf_evento = etree.SubElement(evento, "infEvento")
        # ID = "ID" + tpEvento + chave + nSeqEvento(01)
        inf_evento.set("Id", f"ID{tipo_evento}{chave_acesso}01")

        etree.SubElement(inf_evento, "cOrgao").text = "91"  # AN (Ambiente Nacional)
        etree.SubElement(inf_evento, "tpAmb").text = self.ambiente
        etree.SubElement(inf_evento, "CNPJ").text = cnpj
        etree.SubElement(inf_evento, "chNFe").text = chave_acesso
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S-00:00")
        etree.SubElement(inf_evento, "dhEvento").text = now
        etree.SubElement(inf_evento, "tpEvento").text = tipo_evento
        etree.SubElement(inf_evento, "nSeqEvento").text = "1"
        etree.SubElement(inf_evento, "verEvento").text = "1.00"

        det_evento = etree.SubElement(inf_evento, "detEvento")
        det_evento.set("versao", "1.00")
        etree.SubElement(det_evento, "descEvento").text = EVENTO_DESCRICAO[tipo_evento]

        if tipo_evento == "210240" and justificativa:
            etree.SubElement(det_evento, "xJust").text = justificativa

        return env_evento

    def _parse_response(
        self, response, latency_ms: int
    ) -> ManifestacaoResponse:
        """Parse da resposta do RecepcaoEvento."""
        if isinstance(response, str):
            root = etree.fromstring(response.encode())
        elif isinstance(response, bytes):
            root = etree.fromstring(response)
        else:
            root = response

        nsmap = {"ns": NFE_NS}

        # Busca retEvento/infEvento
        cstat = self._find_text(root, ".//ns:cStat", nsmap)
        xmotivo = self._find_text(root, ".//ns:xMotivo", nsmap) or ""
        protocolo = self._find_text(root, ".//ns:nProt", nsmap)

        # cStat 135 = Evento registrado e vinculado
        # cStat 573 = Duplicidade de evento (já manifestou antes — ok)
        success = cstat in ("135", "136", "573")

        return ManifestacaoResponse(
            cstat=cstat or "999",
            xmotivo=xmotivo,
            protocolo=protocolo,
            latency_ms=latency_ms,
            success=success,
        )

    def _find_text(
        self, root: etree._Element, xpath: str, nsmap: dict
    ) -> Optional[str]:
        elem = root.find(xpath, nsmap)
        return elem.text if elem is not None else None


# Instância global
manifestacao_service = ManifestacaoService()
