"""Unit tests do ResponseSanitizerMiddleware + whitelist de rotas.

Roda standalone (sem pytest):

    cd backend && source venv/bin/activate
    python tests/test_lgpd_sanitizer.py

Valida que:
- Rotas de dados fiscais (documentos, certificates, nfse, manifestacao,
  sap-drc/*, sefaz/*) NÃO são sanitizadas — SAP precisa do CNPJ raw pra
  rotear documentos.
- Rotas fora da whitelist (ex: /api/v1/tenants/me) SÃO sanitizadas.
- Responses JSON com CNPJ/email no corpo continuam sendo mascarados
  quando o path não está whitelisted.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from starlette.applications import Starlette  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import JSONResponse, Response  # noqa: E402
from starlette.routing import Route  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from middleware.lgpd import (  # noqa: E402
    ResponseSanitizerMiddleware,
    _is_sanitize_whitelisted,
    _SANITIZE_WHITELIST_PREFIXES,
    sanitize_text,
)


# ---------------------------------------------------------------------------
# Fixtures: app Starlette mínimo com alguns endpoints de teste
# ---------------------------------------------------------------------------

RAW_PAYLOAD = {
    "cnpj_emitente": "01786983000368",
    "cnpj_destinatario": "12345678000199",
    "email": "fornecedor@acme.com.br",
    "valor": "1000.00",
}


async def _docs_endpoint(request: Request) -> Response:
    # Rota whitelisted: retorna CNPJs raw
    return JSONResponse(RAW_PAYLOAD)


async def _tenants_endpoint(request: Request) -> Response:
    # Rota NÃO whitelisted: deve ser sanitizada
    return JSONResponse(RAW_PAYLOAD)


async def _sap_drc_endpoint(request: Request) -> Response:
    # Layer /sap-drc/* — whitelisted
    return JSONResponse({"inboundInvoices": [RAW_PAYLOAD]})


def _build_app() -> Starlette:
    app = Starlette(
        routes=[
            Route("/api/v1/documentos", _docs_endpoint),
            Route("/api/v1/tenants/me", _tenants_endpoint),
            Route("/sap-drc/v1/retrieveInboundInvoices", _sap_drc_endpoint),
        ],
    )
    app.add_middleware(ResponseSanitizerMiddleware)
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAILURES: list[str] = []


def _assert(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok  — {msg}")
    else:
        print(f"  FAIL — {msg}")
        FAILURES.append(msg)


# ---------------------------------------------------------------------------
# Testes puros de _is_sanitize_whitelisted (sem HTTP)
# ---------------------------------------------------------------------------


def test_whitelist_predicate() -> None:
    print("\n[test_whitelist_predicate]")
    whitelisted_paths = [
        "/api/v1/documentos",
        "/api/v1/documentos/12345",
        "/api/v1/certificates",
        "/api/v1/certificates/upload",
        "/api/v1/nfse/listar",
        "/api/v1/manifestacao/historico",
        "/sap-drc/v1/retrieveInboundInvoices",
        "/sap-drc/v1/downloadOfficialDocument",
        "/api/v1/sefaz/status",
    ]
    for path in whitelisted_paths:
        _assert(
            _is_sanitize_whitelisted(path),
            f"{path} deve estar whitelisted",
        )

    non_whitelisted = [
        "/api/v1/tenants/me",
        "/api/v1/auth/login",
        "/api/v1/credits",
        "/api/v1/billing/checkout",
        "/health",
        "/api/v1/api_keys",
        "/",
    ]
    for path in non_whitelisted:
        _assert(
            not _is_sanitize_whitelisted(path),
            f"{path} NÃO deve estar whitelisted",
        )

    _assert(
        isinstance(_SANITIZE_WHITELIST_PREFIXES, tuple)
        and len(_SANITIZE_WHITELIST_PREFIXES) >= 5,
        "lista de prefixos contém pelo menos 5 entradas",
    )


# ---------------------------------------------------------------------------
# Testes end-to-end via TestClient
# ---------------------------------------------------------------------------


def test_documentos_raw_passthrough() -> None:
    print("\n[test_documentos_raw_passthrough]")
    app = _build_app()
    client = TestClient(app)
    resp = client.get("/api/v1/documentos")
    _assert(resp.status_code == 200, "status 200")
    body = resp.json()
    _assert(
        body["cnpj_emitente"] == "01786983000368",
        "cnpj_emitente passa raw (não mascarado)",
    )
    _assert(
        body["cnpj_destinatario"] == "12345678000199",
        "cnpj_destinatario passa raw",
    )
    _assert(
        body["email"] == "fornecedor@acme.com.br",
        "email passa raw (rota whitelisted)",
    )


def test_tenants_sanitized() -> None:
    print("\n[test_tenants_sanitized]")
    app = _build_app()
    client = TestClient(app)
    resp = client.get("/api/v1/tenants/me")
    _assert(resp.status_code == 200, "status 200")
    body = resp.json()
    _assert(
        "X" in body["cnpj_emitente"],
        f"cnpj_emitente mascarado em rota fora da whitelist (got={body['cnpj_emitente']})",
    )
    _assert(
        body["email"].startswith("f***"),
        f"email mascarado em rota fora da whitelist (got={body['email']})",
    )


def test_sap_drc_raw_passthrough() -> None:
    print("\n[test_sap_drc_raw_passthrough]")
    app = _build_app()
    client = TestClient(app)
    resp = client.get("/sap-drc/v1/retrieveInboundInvoices")
    _assert(resp.status_code == 200, "status 200")
    body = resp.json()
    inv = body["inboundInvoices"][0]
    _assert(
        inv["cnpj_emitente"] == "01786983000368",
        "SAP DRC recebe CNPJ emitente raw",
    )
    _assert(
        inv["cnpj_destinatario"] == "12345678000199",
        "SAP DRC recebe CNPJ destinatario raw",
    )


def test_sanitize_text_still_masks() -> None:
    """Sanity check: sanitize_text ainda funciona fora do middleware."""
    print("\n[test_sanitize_text_still_masks]")
    raw = json.dumps(RAW_PAYLOAD)
    masked = sanitize_text(raw)
    _assert("01786983000368" not in masked, "cnpj cru foi removido")
    _assert("0003" in masked, "filial preservada no masked")
    _assert("fornecedor@" not in masked, "email masked")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    test_whitelist_predicate()
    test_documentos_raw_passthrough()
    test_tenants_sanitized()
    test_sap_drc_raw_passthrough()
    test_sanitize_text_still_masks()

    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for msg in FAILURES:
            print(f"  - {msg}")
        return 1
    print("OK — todos os testes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
