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

import base64
import hashlib

from cryptography.hazmat.primitives import hashes as crypto_hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import Encoding, pkcs12

import requests
from lxml import etree
from services.xml_safety import safe_fromstring

from admin_guards import safe_ambiente
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
        ambiente: str | None = None,  # per-tenant override
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

        # Auto-detect v1/v2 PFX format (same logic as sefaz_client)
        pfx_encrypted_str = (
            pfx_encrypted
            if isinstance(pfx_encrypted, str)
            else pfx_encrypted.decode("utf-8", errors="ignore")
            if isinstance(pfx_encrypted, bytes)
            else str(pfx_encrypted)
        )

        if pfx_encrypted_str.startswith("v2:"):
            blob = bytes.fromhex(pfx_encrypted_str[3:])
            pfx_bytes = decrypt_pfx(blob, None, tenant_id)
        else:
            enc_bytes = (
                bytes.fromhex(pfx_encrypted_str)
                if isinstance(pfx_encrypted_str, str)
                else pfx_encrypted
            )
            iv_bytes = (
                bytes.fromhex(pfx_iv)
                if isinstance(pfx_iv, str)
                else pfx_iv
            )
            pfx_bytes = decrypt_pfx(enc_bytes, iv_bytes, tenant_id)

        # Defesa em profundidade: força homolog se a conta (tenant_id) está
        # na blacklist hardcoded (admin_guards.py). Evita disparar evento
        # em nome de CNPJ alheio caso conta admin vaze pra prod.
        effective_ambiente = safe_ambiente(
            ambiente or self.ambiente, tenant_id=tenant_id,
        )

        start_time = time.time()
        try:
            result = self._soap_call(
                chave_acesso, cnpj, tipo_evento, pfx_bytes,
                pfx_password, justificativa, effective_ambiente,
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
        ambiente: str | None = None,
    ) -> ManifestacaoResponse:
        """Executa chamada SOAP ao RecepcaoEvento via HTTP raw.

        Usa HTTP POST direto com envelope SOAP 1.2 ao invés de zeep,
        porque o WSDL da SEFAZ às vezes confunde a resolução de
        operações do zeep.
        """
        effective_ambiente = ambiente or self.ambiente
        endpoint = RECEPCAO_EVENTO_ENDPOINTS[effective_ambiente]
        # URL sem ?wsdl para o POST
        post_url = endpoint.replace("?wsdl", "")
        start_time = time.time()

        xml_evento = self._build_evento_xml(
            chave_acesso, cnpj, tipo_evento, justificativa,
            effective_ambiente,
        )

        # Sign the infEvento element with the A1 certificate
        self._sign_evento(xml_evento, pfx_bytes, pfx_password)

        xml_evento_str = etree.tostring(xml_evento, encoding="unicode")

        # Signature built manually without namespace prefix (SEFAZ cStat 404)

        # SOAP 1.2 envelope — ASMX expects nfeDadosMsg directly in Body
        soap_envelope = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope"'
            ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            ' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
            '<soap12:Body>'
            '<nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">'
            f'{xml_evento_str}'
            '</nfeDadosMsg>'
            '</soap12:Body>'
            '</soap12:Envelope>'
        )

        # DEBUG: log full envelope for schema debugging
        logger.info(
            "Manifestacao SOAP envelope (first 3000 chars): %s",
            soap_envelope[:3000],
        )

        with temp_cert_files(pfx_bytes, pfx_password) as (cert_path, key_path):
            resp = requests.post(
                post_url,
                data=soap_envelope.encode("utf-8"),
                headers={
                    "Content-Type": "application/soap+xml; charset=utf-8",
                },
                cert=(cert_path, key_path),
                verify=True,
                timeout=30,
            )

        latency_ms = int((time.time() - start_time) * 1000)

        if resp.status_code == 500:
            # SEFAZ returns SOAP Faults with HTTP 500 — try to parse
            try:
                fault_root = safe_fromstring(resp.content)
                # Try SOAP 1.2 fault
                fault_msg = None
                for elem in fault_root.iter():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if tag in ("Text", "faultstring", "Message"):
                        if elem.text:
                            fault_msg = elem.text.strip()
                            break
                if fault_msg:
                    logger.error(
                        "Manifestação SOAP Fault %s: %s",
                        chave_acesso, fault_msg,
                    )
                    return ManifestacaoResponse(
                        cstat="999",
                        xmotivo=f"SEFAZ SOAP Fault: {fault_msg}",
                        protocolo=None,
                        latency_ms=latency_ms,
                        success=False,
                    )
            except Exception:
                pass

            logger.error(
                "Manifestação SOAP HTTP %d para %s: %s",
                resp.status_code, chave_acesso, resp.text[:500],
            )
            return ManifestacaoResponse(
                cstat="999",
                xmotivo=f"SEFAZ HTTP {resp.status_code}: {resp.text[:300]}",
                protocolo=None,
                latency_ms=latency_ms,
                success=False,
            )

        if resp.status_code != 200:
            logger.error(
                "Manifestação SOAP HTTP %d para %s: %s",
                resp.status_code, chave_acesso, resp.text[:500],
            )
            return ManifestacaoResponse(
                cstat="999",
                xmotivo=f"SEFAZ HTTP {resp.status_code}",
                protocolo=None,
                latency_ms=latency_ms,
                success=False,
            )

        return self._parse_response(resp.content, latency_ms)

    def _build_evento_xml(
        self,
        chave_acesso: str,
        cnpj: str,
        tipo_evento: str,
        justificativa: str,
        ambiente: str | None = None,
    ) -> etree._Element:
        """Monta XML do envEvento para Manifestação do Destinatário."""
        effective_ambiente = ambiente or self.ambiente
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
        etree.SubElement(inf_evento, "tpAmb").text = effective_ambiente
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

    def _sign_evento(
        self,
        env_evento: etree._Element,
        pfx_bytes: bytes,
        pfx_password: str,
    ) -> None:
        """Assina o elemento infEvento com XMLDSig RSA-SHA1 (enveloped).

        SEFAZ NF-e exige assinatura com SHA-1 (schema fixo).
        Implementação manual sem signxml para controle total.
        A Signature fica como filho de <evento>, após <infEvento>.
        """
        # Extract private key and certificate from PFX
        private_key, certificate, _ = pkcs12.load_key_and_certificates(
            pfx_bytes, pfx_password.encode()
        )

        if private_key is None or certificate is None:
            raise ValueError("Certificado ou chave privada nao encontrados no PFX")

        # Find evento/infEvento
        evento = env_evento.find("evento")
        if evento is None:
            evento = env_evento.find(f"{{{NFE_NS}}}evento")
        if evento is None:
            raise ValueError("Elemento <evento> nao encontrado")

        inf_evento = evento.find("infEvento")
        if inf_evento is None:
            inf_evento = evento.find(f"{{{NFE_NS}}}infEvento")
        if inf_evento is None:
            raise ValueError("Elemento <infEvento> nao encontrado")

        inf_id = inf_evento.get("Id")

        # 1. Canonicalize infEvento (C14N exclusive, without comments)
        inf_c14n = etree.tostring(inf_evento, method="c14n")

        # 2. SHA-1 digest of the canonicalized infEvento
        digest = hashlib.sha1(inf_c14n).digest()
        digest_b64 = base64.b64encode(digest).decode()

        # 3. Build SignedInfo element
        DSIG = "http://www.w3.org/2000/09/xmldsig#"
        signed_info = etree.Element("SignedInfo", xmlns=DSIG)
        etree.SubElement(signed_info, "CanonicalizationMethod").set(
            "Algorithm", "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
        )
        etree.SubElement(signed_info, "SignatureMethod").set(
            "Algorithm", "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
        )

        reference = etree.SubElement(signed_info, "Reference")
        reference.set("URI", f"#{inf_id}")

        transforms = etree.SubElement(reference, "Transforms")
        etree.SubElement(transforms, "Transform").set(
            "Algorithm", "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
        )
        etree.SubElement(transforms, "Transform").set(
            "Algorithm", "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
        )

        etree.SubElement(reference, "DigestMethod").set(
            "Algorithm", "http://www.w3.org/2000/09/xmldsig#sha1"
        )
        etree.SubElement(reference, "DigestValue").text = digest_b64

        # 4. Canonicalize SignedInfo and sign with RSA-SHA1
        signed_info_c14n = etree.tostring(signed_info, method="c14n")
        signature_value = private_key.sign(
            signed_info_c14n,
            padding.PKCS1v15(),
            crypto_hashes.SHA1(),
        )
        sig_b64 = base64.b64encode(signature_value).decode()

        # 5. Build X509 certificate data
        cert_der = certificate.public_bytes(Encoding.DER)
        cert_b64 = base64.b64encode(cert_der).decode()

        # 6. Assemble Signature element (no namespace prefix!)
        sig_elem = etree.SubElement(evento, "Signature")
        sig_elem.set("xmlns", DSIG)

        sig_elem.append(signed_info)

        sig_value_elem = etree.SubElement(sig_elem, "SignatureValue")
        sig_value_elem.text = sig_b64

        key_info = etree.SubElement(sig_elem, "KeyInfo")
        x509_data = etree.SubElement(key_info, "X509Data")
        x509_cert = etree.SubElement(x509_data, "X509Certificate")
        x509_cert.text = cert_b64

    def _parse_response(
        self, response, latency_ms: int
    ) -> ManifestacaoResponse:
        """Parse da resposta do RecepcaoEvento.

        A resposta SOAP contém dois níveis de cStat:
        - retEnvEvento/cStat (128 = lote processado)
        - retEvento/infEvento/cStat (135 = evento registrado)

        Precisamos do cStat do EVENTO, não do lote.
        """
        if isinstance(response, str):
            root = safe_fromstring(response.encode())
        elif isinstance(response, bytes):
            root = safe_fromstring(response)
        else:
            root = response

        nsmap = {"ns": NFE_NS}

        # Busca cStat dentro de retEvento/infEvento (evento individual)
        # Se não achar, faz fallback pro cStat do lote
        cstat = self._find_text(root, ".//ns:retEvento//ns:cStat", nsmap)
        xmotivo = self._find_text(root, ".//ns:retEvento//ns:xMotivo", nsmap) or ""
        protocolo = self._find_text(root, ".//ns:retEvento//ns:nProt", nsmap)

        if cstat is None:
            # Fallback: cStat do lote (retEnvEvento ou raiz)
            cstat = self._find_text(root, ".//ns:cStat", nsmap)
            xmotivo = self._find_text(root, ".//ns:xMotivo", nsmap) or xmotivo

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
