"""TestSAPClient — HTTP client real in-process simulando o SAP DRC.

Diferente de um mock de função: faz requests HTTP de verdade via
`fastapi.testclient.TestClient` (wrapper sobre httpx) contra o FastAPI app
do DFeAxis. Exercita middleware -> router -> service -> DB, mas roda
in-process (sem precisar subir servidor).

Fala dois protocolos:
1. **SAP DRC compat layer** (`/sap-drc/v1/*`) — formato SAP DRC
   (NotaFiscalFragment, EventFragment, InboundInvoiceRetrieveRequest).
   É onde o SAP real bateria numa implantação ao vivo.
2. **DFeAxis nativo** (`/api/v1/*`) — endpoints nativos (polling/trigger,
   manifestacao, documentos) que o SAP DRC layer não expõe.

Use junto com `FakeSefazClient` (Fase 2.1) e `FakeStripeClient` (Fase 2.2)
para cenários E2E determinísticos.

Fase 2.3 do plano de orquestração.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestSAPClient:
    """HTTP client real que simula o SAP DRC batendo no DFeAxis.

    Parameters
    ----------
    app:
        Instância do FastAPI (normalmente `from main import app`).
    api_key:
        API key do tenant a ser enviada no header `X-API-Key`. É o modo
        principal de autenticação, espelhando o que o SAP real usa.
    jwt_token:
        Opcional. JWT do dashboard, usado pelos métodos que chamam
        endpoints protegidos por `Authorization: Bearer` em vez de
        X-API-Key.

    Notes
    -----
    Todos os métodos retornam um dict uniforme no formato::

        {
            "status_code": int,
            "body": dict | str,        # JSON quando possível, texto cru senão
            "headers": dict[str, str],
            "ok": bool,                # 200 <= status_code < 300
        }

    A exceção é `download_official_document`, que retorna o XML cru em
    `content` (o endpoint responde `application/xml`, não JSON).
    """

    def __init__(
        self,
        app: FastAPI,
        api_key: str,
        jwt_token: str | None = None,
    ) -> None:
        self._app = app
        self._client = TestClient(app)
        self._api_key = api_key
        self._jwt = jwt_token
        # Prefixos conforme main.py (verificados contra include_router)
        self._sap_prefix = "/sap-drc"
        self._native_prefix = "/api/v1"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Fecha o TestClient subjacente (recomendado em tear-down)."""
        try:
            self._client.close()
        except Exception:
            pass

    def __enter__(self) -> "TestSAPClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Headers
    # ------------------------------------------------------------------

    def _api_headers(self) -> dict[str, str]:
        """Headers para calls autenticadas por API key (sap_drc + nativo)."""
        return {"X-API-Key": self._api_key}

    def _jwt_headers(self) -> dict[str, str]:
        """Headers para calls autenticadas por JWT (dashboard-like)."""
        return {"Authorization": f"Bearer {self._jwt}"} if self._jwt else {}

    # ==================================================================
    # SAP DRC layer — /sap-drc/v1/*
    # ==================================================================

    def sap_health(self) -> dict[str, Any]:
        """GET /sap-drc/health — health-check do SAP DRC compat layer."""
        resp = self._client.get(f"{self._sap_prefix}/health")
        return self._wrap(resp)

    def retrieve_inbound_invoices(self, cnpjs: list[str]) -> dict[str, Any]:
        """POST /sap-drc/v1/retrieveInboundInvoices — lê a fila de NF-e.

        Retorna a resposta no formato `InboundInvoiceRetrieveResponse`::

            {
                "eventFragmentList": [...],
                "notaFiscalFragmentList": [...],
            }

        Apenas documentos com `status='available'` e `xml_content` não nulo
        são devolvidos. É o método que o SAP real chama para drenar a caixa.
        """
        resp = self._client.post(
            f"{self._sap_prefix}/v1/retrieveInboundInvoices",
            json={"cnpj": cnpjs},
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    def download_official_document(
        self,
        access_key: str,
        event_sequence: str | None = None,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        """GET /sap-drc/v1/downloadOfficialDocument?accessKey=...

        Retorna dict especial (não o wrapper padrão)::

            {
                "status_code": int,
                "content": str,          # XML raw (application/xml)
                "headers": dict[str, str],
                "ok": bool,
            }
        """
        params: dict[str, Any] = {"accessKey": access_key}
        if event_sequence is not None:
            params["eventSequence"] = event_sequence
        if event_type is not None:
            params["eventType"] = event_type

        resp = self._client.get(
            f"{self._sap_prefix}/v1/downloadOfficialDocument",
            params=params,
            headers=self._api_headers(),
        )
        return {
            "status_code": resp.status_code,
            "content": resp.text,
            "headers": dict(resp.headers),
            "ok": 200 <= resp.status_code < 300,
        }

    def receive_official_document(self, xml: str) -> dict[str, Any]:
        """POST /sap-drc/v1/receiveOfficialDocument — push model.

        Usado quando o SAP ENVIA um XML pro DFeAxis (ex: XML recebido
        direto via EDI / canal fora do polling SEFAZ). O backend parseia
        o XML, extrai chave/CNPJ e grava em `documents`.
        """
        resp = self._client.post(
            f"{self._sap_prefix}/v1/receiveOfficialDocument",
            json={"xml": xml},
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    def delete_inbound_invoices(self, uuid_list: list[str]) -> dict[str, Any]:
        """DELETE /sap-drc/v1/deleteInboundInvoices — confirmação em lote.

        Equivalente ao "confirmar em lote" via UUIDs. Zera o `xml_content`,
        marca `status='delivered'` e incrementa o contador de consumo
        (trial ou mensal) apenas pelos UUIDs que efetivamente transicionaram
        (idempotência garantida pelo filtro `status=available`).
        """
        resp = self._client.request(
            "DELETE",
            f"{self._sap_prefix}/v1/deleteInboundInvoices",
            json={"uuidList": uuid_list},
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    def delete_official_document(
        self,
        access_key: str,
        event_sequence: str | None = None,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        """DELETE /sap-drc/v1/deleteOfficialDocument?accessKey=...

        Equivalente ao "confirmar single" via chave de acesso. Mesma
        semântica de contador do `delete_inbound_invoices` (single).
        """
        params: dict[str, Any] = {"accessKey": access_key}
        if event_sequence is not None:
            params["eventSequence"] = event_sequence
        if event_type is not None:
            params["eventType"] = event_type

        resp = self._client.request(
            "DELETE",
            f"{self._sap_prefix}/v1/deleteOfficialDocument",
            params=params,
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    # ==================================================================
    # DFeAxis nativo — /api/v1/*
    # Endpoints que o SAP DRC layer não expõe mas o produto oferece.
    # ==================================================================

    def trigger_polling(self, cnpj: str, tipos: list[str]) -> dict[str, Any]:
        """POST /api/v1/polling/trigger — dispara captura manual na SEFAZ.

        Note
        ----
        O SAP DRC real não tem método equivalente —
        `retrieveInboundInvoices` só drena a fila local, não força nova
        busca. No DFeAxis, este endpoint é chamado para provocar um ciclo
        de polling on-demand (usado muito em testes E2E).
        """
        resp = self._client.post(
            f"{self._native_prefix}/polling/trigger",
            json={"cnpj": cnpj, "tipos": tipos},
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    def list_documentos(
        self,
        cnpj: str,
        desde_nsu: str | None = None,
        tipo: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/v1/documentos?cnpj=... — listagem nativa de documentos."""
        params: dict[str, Any] = {"cnpj": cnpj}
        if desde_nsu is not None:
            params["desde"] = desde_nsu
        if tipo is not None:
            params["tipo"] = tipo
        resp = self._client.get(
            f"{self._native_prefix}/documentos",
            params=params,
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    def confirmar_documento_nativo(self, chave: str) -> dict[str, Any]:
        """POST /api/v1/documentos/{chave}/confirmar — confirmação nativa.

        Caminho nativo, equivalente semântico de `delete_official_document`
        (SAP DRC). Mesma racional de contador e idempotência.
        """
        resp = self._client.post(
            f"{self._native_prefix}/documentos/{chave}/confirmar",
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    # ==================================================================
    # Manifestação — /api/v1/manifestacao/*
    # ==================================================================

    def send_manifestacao(
        self,
        chave: str,
        tipo_evento: str,
        justificativa: str = "",
    ) -> dict[str, Any]:
        """POST /api/v1/manifestacao — envia um evento (ciência/confirmação/etc)."""
        resp = self._client.post(
            f"{self._native_prefix}/manifestacao",
            json={
                "chave_acesso": chave,
                "tipo_evento": tipo_evento,
                "justificativa": justificativa,
            },
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    def send_manifestacao_batch(
        self,
        chaves: list[str],
        tipo_evento: str,
        justificativa: str = "",
    ) -> dict[str, Any]:
        """POST /api/v1/manifestacao/batch — manifestação em lote."""
        resp = self._client.post(
            f"{self._native_prefix}/manifestacao/batch",
            json={
                "chaves": chaves,
                "tipo_evento": tipo_evento,
                "justificativa": justificativa,
            },
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    def list_pendentes_manifestacao(self, cnpj: str) -> dict[str, Any]:
        """GET /api/v1/manifestacao/pendentes?cnpj=... — docs aguardando ciência."""
        resp = self._client.get(
            f"{self._native_prefix}/manifestacao/pendentes",
            params={"cnpj": cnpj},
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    def historico_manifestacao(
        self,
        cnpj: str | None = None,
        chave: str | None = None,
        tipo_evento: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """GET /api/v1/manifestacao/historico — log de eventos enviados."""
        params: dict[str, Any] = {"limit": limit}
        if cnpj is not None:
            params["cnpj"] = cnpj
        if chave is not None:
            params["chave_acesso"] = chave
        if tipo_evento is not None:
            params["tipo_evento"] = tipo_evento
        resp = self._client.get(
            f"{self._native_prefix}/manifestacao/historico",
            params=params,
            headers=self._api_headers(),
        )
        return self._wrap(resp)

    # ------------------------------------------------------------------
    # Helper comum
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap(resp: Any) -> dict[str, Any]:
        """Embala a response do httpx num dict uniforme."""
        try:
            body: Any = resp.json()
        except Exception:
            body = resp.text
        return {
            "status_code": resp.status_code,
            "body": body,
            "headers": dict(resp.headers),
            "ok": 200 <= resp.status_code < 300,
        }
