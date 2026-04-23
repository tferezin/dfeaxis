"""Cliente para Ambiente Nacional de NFS-e (ADN).

REST API com mTLS — mesmo certificado A1 usado para NF-e/CT-e.

NOTA: O ADN (Ambiente Nacional de NFS-e) foi instituido pela Reforma Tributaria
(vigente desde 01/2026). Nem todos os municipios aderiram ao sistema nacional.
Consultas para municipios nao integrados retornarao lista vazia ou erro 404.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from middleware.lgpd import mask_cnpj
from services.cert_manager import decrypt_pfx, temp_cert_files
from services.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

# Endpoints ADN por ambiente
NFSE_ADN_ENDPOINTS = {
    "1": "https://adn.nfse.gov.br",
    "2": "https://adn.producaorestrita.nfse.gov.br",
}

# Timeout para requisicoes REST ao ADN (segundos)
ADN_TIMEOUT = 30


@dataclass
class NfseDocument:
    """Documento NFS-e retornado pelo ADN."""
    chave: str
    nsu: str
    xml_content: str  # XML da NFS-e (embedded no JSON de resposta)
    codigo_municipio: Optional[str] = None
    codigo_servico: Optional[str] = None
    data_emissao: Optional[str] = None
    valor_servico: Optional[str] = None


@dataclass
class NfseResponse:
    """Resposta de uma consulta ao ADN."""
    success: bool
    status_code: int
    message: str
    ult_nsu: str
    documents: list[NfseDocument] = field(default_factory=list)
    latency_ms: int = 0


class NfseClient:
    """Cliente REST para consultar NFS-e no Ambiente Nacional (ADN)."""

    def __init__(self):
        self.ambiente = os.getenv("SEFAZ_AMBIENTE", "2")  # default homologacao

    @property
    def base_url(self) -> str:
        return NFSE_ADN_ENDPOINTS[self.ambiente]

    def _decrypt_and_get_pfx(
        self,
        pfx_encrypted,
        pfx_iv,
        tenant_id: str,
    ) -> bytes:
        """Decifra o .pfx — auto-detect v1/v2 format."""
        pfx_encrypted_str = (
            pfx_encrypted
            if isinstance(pfx_encrypted, str)
            else pfx_encrypted.hex()
            if isinstance(pfx_encrypted, bytes)
            else str(pfx_encrypted)
        )

        if pfx_encrypted_str.startswith("v2:"):
            blob = bytes.fromhex(pfx_encrypted_str[3:])
            return decrypt_pfx(blob, None, tenant_id)
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
            return decrypt_pfx(enc_bytes, iv_bytes, tenant_id)

    def _create_mtls_session(
        self, cert_path: str, key_path: str
    ) -> requests.Session:
        """Cria sessao HTTP com mTLS."""
        session = requests.Session()
        session.cert = (cert_path, key_path)
        session.verify = True
        session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        return session

    def consultar_nfse_por_cnpj(
        self,
        cnpj: str,
        data_inicio: str,
        data_fim: str,
        pfx_encrypted,
        pfx_iv,
        tenant_id: str,
        pfx_password: str,
        pagina: int = 1,
    ) -> NfseResponse:
        """Lista NFS-e recebidas por um CNPJ em um periodo.

        Args:
            cnpj: CNPJ do tomador de servico
            data_inicio: Data inicio (YYYY-MM-DD)
            data_fim: Data fim (YYYY-MM-DD)
            pfx_encrypted: Certificado .pfx cifrado
            pfx_iv: IV (v1) ou None (v2)
            tenant_id: ID do tenant
            pfx_password: Senha do .pfx
            pagina: Pagina de resultados (default 1)
        """
        # Circuit breaker
        if not circuit_breaker.can_execute(cnpj, "nfse"):
            state = circuit_breaker.get_state(cnpj, "nfse")
            return NfseResponse(
                success=False,
                status_code=503,
                message=f"Circuit breaker {state.value} para {mask_cnpj(cnpj)}/nfse",
                ult_nsu="000000000000000",
            )

        pfx_bytes = self._decrypt_and_get_pfx(pfx_encrypted, pfx_iv, tenant_id)
        start_time = time.time()

        try:
            with temp_cert_files(pfx_bytes, pfx_password) as (cert_path, key_path):
                session = self._create_mtls_session(cert_path, key_path)
                url = f"{self.base_url}/contribuintes/DFe/0"
                params = {"tipoNSU": "DISTRIBUICAO"}
                resp = session.get(url, params=params, timeout=ADN_TIMEOUT)

            latency_ms = int((time.time() - start_time) * 1000)
            circuit_breaker.record_success(cnpj, "nfse")
            return self._parse_list_response(resp, latency_ms)

        except Exception as e:
            circuit_breaker.record_failure(cnpj, "nfse")
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"ADN error consultar_por_cnpj {mask_cnpj(cnpj)}: {e}")
            return NfseResponse(
                success=False,
                status_code=500,
                message=str(e),
                ult_nsu="000000000000000",
                latency_ms=latency_ms,
            )

    def consultar_nfse_por_chave(
        self,
        chave_acesso: str,
        pfx_encrypted,
        pfx_iv,
        tenant_id: str,
        pfx_password: str,
    ) -> NfseResponse:
        """Consulta uma NFS-e especifica por chave de acesso.

        Args:
            chave_acesso: Chave de acesso da NFS-e
            pfx_encrypted: Certificado .pfx cifrado
            pfx_iv: IV (v1) ou None (v2)
            tenant_id: ID do tenant
            pfx_password: Senha do .pfx
        """
        # Circuit breaker usa cnpj generico pois nao temos o CNPJ aqui
        cb_key = "nfse_chave"
        if not circuit_breaker.can_execute(cb_key, "nfse"):
            state = circuit_breaker.get_state(cb_key, "nfse")
            return NfseResponse(
                success=False,
                status_code=503,
                message=f"Circuit breaker {state.value} para nfse/chave",
                ult_nsu="000000000000000",
            )

        pfx_bytes = self._decrypt_and_get_pfx(pfx_encrypted, pfx_iv, tenant_id)
        start_time = time.time()

        try:
            with temp_cert_files(pfx_bytes, pfx_password) as (cert_path, key_path):
                session = self._create_mtls_session(cert_path, key_path)
                url = f"{self.base_url}/contribuintes/NFSe/{chave_acesso}/Eventos"
                resp = session.get(url, timeout=ADN_TIMEOUT)

            latency_ms = int((time.time() - start_time) * 1000)
            circuit_breaker.record_success(cb_key, "nfse")
            return self._parse_single_response(resp, latency_ms)

        except Exception as e:
            circuit_breaker.record_failure(cb_key, "nfse")
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"ADN error consultar_por_chave {chave_acesso[:10]}...: {e}")
            return NfseResponse(
                success=False,
                status_code=500,
                message=str(e),
                ult_nsu="000000000000000",
                latency_ms=latency_ms,
            )

    def consultar_dps_distribuicao(
        self,
        cnpj: str,
        ult_nsu: str,
        pfx_encrypted,
        pfx_iv,
        tenant_id: str,
        pfx_password: str,
    ) -> NfseResponse:
        """Consulta distribuicao de DPS (similar a DistDFeInt da SEFAZ).

        Retorna NFS-e a partir do ultimo NSU processado.

        Args:
            cnpj: CNPJ do tomador
            ult_nsu: Ultimo NSU processado
            pfx_encrypted: Certificado .pfx cifrado
            pfx_iv: IV (v1) ou None (v2)
            tenant_id: ID do tenant
            pfx_password: Senha do .pfx
        """
        if not circuit_breaker.can_execute(cnpj, "nfse"):
            state = circuit_breaker.get_state(cnpj, "nfse")
            return NfseResponse(
                success=False,
                status_code=503,
                message=f"Circuit breaker {state.value} para {mask_cnpj(cnpj)}/nfse",
                ult_nsu=ult_nsu,
            )

        pfx_bytes = self._decrypt_and_get_pfx(pfx_encrypted, pfx_iv, tenant_id)
        start_time = time.time()

        try:
            with temp_cert_files(pfx_bytes, pfx_password) as (cert_path, key_path):
                session = self._create_mtls_session(cert_path, key_path)
                url = f"{self.base_url}/contribuintes/DFe/{ult_nsu}"
                params = {"tipoNSU": "DISTRIBUICAO"}
                resp = session.get(url, params=params, timeout=ADN_TIMEOUT)

            latency_ms = int((time.time() - start_time) * 1000)
            circuit_breaker.record_success(cnpj, "nfse")
            return self._parse_distribuicao_response(resp, ult_nsu, latency_ms)

        except Exception as e:
            circuit_breaker.record_failure(cnpj, "nfse")
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"ADN error distribuicao {mask_cnpj(cnpj)}: {e}")
            return NfseResponse(
                success=False,
                status_code=500,
                message=str(e),
                ult_nsu=ult_nsu,
                latency_ms=latency_ms,
            )

    # --- Parsers de resposta ---

    def _parse_list_response(
        self, resp: requests.Response, latency_ms: int
    ) -> NfseResponse:
        """Parse da resposta de listagem por CNPJ/periodo."""
        if resp.status_code == 404:
            # Municipio nao integrado ao ADN ou sem dados
            return NfseResponse(
                success=True,
                status_code=404,
                message="Nenhuma NFS-e encontrada. O município pode não estar integrado ao ADN.",
                ult_nsu="000000000000000",
                latency_ms=latency_ms,
            )

        if resp.status_code != 200:
            return NfseResponse(
                success=False,
                status_code=resp.status_code,
                message=f"Erro ADN: HTTP {resp.status_code}",
                ult_nsu="000000000000000",
                latency_ms=latency_ms,
            )

        data = resp.json()
        documents = self._extract_documents(data.get("nfses", []))

        return NfseResponse(
            success=True,
            status_code=200,
            message="OK",
            ult_nsu=data.get("ultNSU", "000000000000000"),
            documents=documents,
            latency_ms=latency_ms,
        )

    def _parse_single_response(
        self, resp: requests.Response, latency_ms: int
    ) -> NfseResponse:
        """Parse da resposta de consulta por chave."""
        if resp.status_code == 404:
            return NfseResponse(
                success=True,
                status_code=404,
                message="NFS-e não encontrada.",
                ult_nsu="000000000000000",
                latency_ms=latency_ms,
            )

        if resp.status_code != 200:
            return NfseResponse(
                success=False,
                status_code=resp.status_code,
                message=f"Erro ADN: HTTP {resp.status_code}",
                ult_nsu="000000000000000",
                latency_ms=latency_ms,
            )

        data = resp.json()
        documents = self._extract_documents([data] if data else [])

        return NfseResponse(
            success=True,
            status_code=200,
            message="OK",
            ult_nsu="000000000000000",
            documents=documents,
            latency_ms=latency_ms,
        )

    def _parse_distribuicao_response(
        self, resp: requests.Response, ult_nsu: str, latency_ms: int
    ) -> NfseResponse:
        """Parse da resposta de distribuicao DPS."""
        if resp.status_code == 404:
            return NfseResponse(
                success=True,
                status_code=404,
                message="Nenhum documento novo na distribuicao.",
                ult_nsu=ult_nsu,
                latency_ms=latency_ms,
            )

        if resp.status_code != 200:
            return NfseResponse(
                success=False,
                status_code=resp.status_code,
                message=f"Erro ADN: HTTP {resp.status_code}",
                ult_nsu=ult_nsu,
                latency_ms=latency_ms,
            )

        data = resp.json()
        documents = self._extract_documents(data.get("documentos", []))
        new_ult_nsu = data.get("ultNSU", ult_nsu)

        return NfseResponse(
            success=True,
            status_code=200,
            message="OK",
            ult_nsu=new_ult_nsu,
            documents=documents,
            latency_ms=latency_ms,
        )

    def _extract_documents(self, items: list) -> list[NfseDocument]:
        """Extrai documentos NFS-e de uma lista de items JSON."""
        documents: list[NfseDocument] = []
        for item in items:
            try:
                doc = NfseDocument(
                    chave=item.get("chave", item.get("chaveAcesso", "")),
                    nsu=str(item.get("nsu", "")).zfill(15),
                    xml_content=item.get("xml", item.get("xmlNfse", "")),
                    codigo_municipio=item.get("codigoMunicipio"),
                    codigo_servico=item.get("codigoServico"),
                    data_emissao=item.get("dataEmissao"),
                    valor_servico=str(item.get("valorServico", ""))
                    if item.get("valorServico") is not None
                    else None,
                )
                if doc.chave:
                    documents.append(doc)
            except Exception as e:
                logger.warning(f"Erro ao extrair NFS-e do ADN: {e}")
        return documents


# Instancia global
nfse_client = NfseClient()
