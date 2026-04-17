"""Smoke tests for TestSAPClient.

Estes testes validam o próprio client (importável, API coesa, headers
corretos, wrapper uniforme). Não dependem de DB real — usam um FastAPI
app mínimo com o router `sap_drc` apenas para o health-check, e um app
stub in-file para os demais casos.

Rodar::

    ./backend/venv/bin/python backend/tests/fakes/test_sap_client.py
"""

from __future__ import annotations

import os
import sys
import traceback

# Resolve imports to work whether invoked from repo root or from backend/
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402

from tests.fakes.sap_client import TestSAPClient  # noqa: E402


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

_PASSED: list[str] = []
_FAILED: list[tuple[str, str]] = []


def case(name: str):
    def deco(fn):
        def runner():
            try:
                fn()
            except AssertionError as e:
                _FAILED.append((name, f"AssertionError: {e}"))
                print(f"FAIL {name}: {e}")
            except Exception as e:  # noqa: BLE001
                _FAILED.append((name, f"{type(e).__name__}: {e}"))
                print(f"ERROR {name}: {type(e).__name__}: {e}")
                traceback.print_exc()
            else:
                _PASSED.append(name)
                print(f"PASS {name}")
        runner._name = name  # type: ignore[attr-defined]
        return runner
    return deco


# ---------------------------------------------------------------------------
# Fixtures — apps FastAPI minimalistas para isolar testes
# ---------------------------------------------------------------------------


def _make_stub_app() -> FastAPI:
    """App stub com rotas falsas nos mesmos paths que o TestSAPClient bate.

    Não depende de DB, supabase, ou qualquer serviço real. Serve para
    verificar que o client monta as URLs corretas, passa headers certos e
    embala respostas no formato uniforme.
    """
    app = FastAPI()

    # --- SAP DRC layer ---

    @app.get("/sap-drc/health")
    def _health() -> dict:
        return {"status": "ok"}

    def _require_api_key(x_api_key: str | None = Header(default=None)) -> str:
        if not x_api_key or x_api_key == "invalid":
            raise HTTPException(status_code=401, detail="invalid api key")
        return x_api_key

    @app.post("/sap-drc/v1/retrieveInboundInvoices")
    def _retrieve(body: dict, _: str = Depends(_require_api_key)) -> dict:  # type: ignore[assignment]
        return {
            "eventFragmentList": [],
            "notaFiscalFragmentList": [],
            "echo_cnpj": body.get("cnpj", []),
        }

    @app.get("/sap-drc/v1/downloadOfficialDocument")
    def _download(accessKey: str, _: str = Depends(_require_api_key)):  # type: ignore[assignment]
        from fastapi.responses import Response
        xml = f"<NFe><chave>{accessKey}</chave></NFe>"
        return Response(content=xml, media_type="application/xml")

    @app.post("/sap-drc/v1/receiveOfficialDocument", status_code=202)
    def _receive(body: dict, _: str = Depends(_require_api_key)) -> dict:  # type: ignore[assignment]
        return {"received_len": len(body.get("xml", ""))}

    @app.delete("/sap-drc/v1/deleteInboundInvoices", status_code=204)
    def _delete_batch(body: dict, _: str = Depends(_require_api_key)):  # type: ignore[assignment]
        from fastapi.responses import Response
        return Response(status_code=204)

    @app.delete("/sap-drc/v1/deleteOfficialDocument", status_code=204)
    def _delete_single(accessKey: str, _: str = Depends(_require_api_key)):  # type: ignore[assignment]
        from fastapi.responses import Response
        return Response(status_code=204)

    # --- Native layer (mimics /api/v1/*) ---

    @app.get("/api/v1/documentos")
    def _docs(cnpj: str, _: str = Depends(_require_api_key)) -> dict:  # type: ignore[assignment]
        return {"cnpj": cnpj, "documentos": []}

    @app.post("/api/v1/documentos/{chave}/confirmar")
    def _confirmar(chave: str, _: str = Depends(_require_api_key)) -> dict:  # type: ignore[assignment]
        return {"chave": chave, "confirmed": True}

    @app.post("/api/v1/polling/trigger")
    def _trigger(body: dict, _: str = Depends(_require_api_key)) -> dict:  # type: ignore[assignment]
        return {"triggered": True, "cnpj": body.get("cnpj")}

    @app.post("/api/v1/manifestacao")
    def _manif(body: dict, _: str = Depends(_require_api_key)) -> dict:  # type: ignore[assignment]
        return {"ok": True, "tipo": body.get("tipo_evento")}

    @app.post("/api/v1/manifestacao/batch")
    def _manif_batch(body: dict, _: str = Depends(_require_api_key)) -> dict:  # type: ignore[assignment]
        return {"ok": True, "count": len(body.get("chaves", []))}

    @app.get("/api/v1/manifestacao/pendentes")
    def _pend(cnpj: str, _: str = Depends(_require_api_key)) -> dict:  # type: ignore[assignment]
        return {"cnpj": cnpj, "pendentes": []}

    @app.get("/api/v1/manifestacao/historico")
    def _hist(_: str = Depends(_require_api_key)) -> dict:  # type: ignore[assignment]
        return {"historico": []}

    return app


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@case("1. sap_health returns 200 with {'status': 'ok'}")
def t1():
    client = TestSAPClient(_make_stub_app(), api_key="valid-key")
    r = client.sap_health()
    assert r["status_code"] == 200, r
    assert r["body"] == {"status": "ok"}, r
    assert r["ok"] is True
    client.close()


@case("2. retrieve_inbound_invoices with invalid api key returns 401")
def t2():
    client = TestSAPClient(_make_stub_app(), api_key="invalid")
    r = client.retrieve_inbound_invoices(["12345678000199"])
    assert r["status_code"] == 401, r
    assert r["ok"] is False
    client.close()


@case("3. list_documentos without auth (missing header) returns 401")
def t3():
    # Pass api_key="" -> the stub treats missing/invalid as 401.
    # But TestSAPClient still sends the header with empty value — stub's
    # _require_api_key rejects empty, so this exercises the "no auth" path.
    client = TestSAPClient(_make_stub_app(), api_key="")
    r = client.list_documentos("12345678000199")
    assert r["status_code"] == 401, r
    client.close()


@case("4. X-API-Key header is forwarded correctly")
def t4():
    # Hit an endpoint that accepts — the request must include X-API-Key,
    # otherwise the stub returns 401. A successful 200 proves the header
    # is being forwarded.
    client = TestSAPClient(_make_stub_app(), api_key="abc-123")
    r = client.retrieve_inbound_invoices(["11111111000111"])
    assert r["status_code"] == 200, r
    assert r["body"]["echo_cnpj"] == ["11111111000111"], r
    # Sanity: also verify _api_headers structure directly
    h = client._api_headers()
    assert h == {"X-API-Key": "abc-123"}, h
    client.close()


@case("5. All endpoints return uniform dict {status_code, body, headers, ok}")
def t5():
    client = TestSAPClient(_make_stub_app(), api_key="valid")

    calls = [
        ("sap_health", lambda: client.sap_health()),
        ("retrieve", lambda: client.retrieve_inbound_invoices(["1"])),
        ("receive", lambda: client.receive_official_document("<xml/>")),
        ("delete_batch", lambda: client.delete_inbound_invoices(["u1"])),
        ("delete_single", lambda: client.delete_official_document("K" * 44)),
        ("trigger_polling", lambda: client.trigger_polling("1", ["NFE"])),
        ("list_documentos", lambda: client.list_documentos("1")),
        ("confirmar_nativo", lambda: client.confirmar_documento_nativo("K" * 44)),
        ("manif", lambda: client.send_manifestacao("K" * 44, "ciencia")),
        ("manif_batch", lambda: client.send_manifestacao_batch(["K" * 44], "ciencia")),
        ("pendentes", lambda: client.list_pendentes_manifestacao("1")),
        ("historico", lambda: client.historico_manifestacao(cnpj="1")),
    ]

    for name, fn in calls:
        r = fn()
        assert isinstance(r, dict), f"{name}: not a dict"
        assert set(r.keys()) == {"status_code", "body", "headers", "ok"}, (
            f"{name}: wrong keys {set(r.keys())}"
        )
        assert isinstance(r["status_code"], int), f"{name}: status_code not int"
        assert isinstance(r["headers"], dict), f"{name}: headers not dict"
        assert isinstance(r["ok"], bool), f"{name}: ok not bool"

    # download_official_document has a different schema (xml raw)
    d = client.download_official_document("K" * 44)
    assert set(d.keys()) == {"status_code", "content", "headers", "ok"}, d
    assert d["ok"] is True
    assert "<NFe>" in d["content"]

    client.close()


@case("6. TestSAPClient imports the real FastAPI app without side-effects")
def t6():
    """Sanity: ensure we can instantiate against the real backend `app`.

    This doesn't hit any real endpoint (DB would be required) — just
    confirms the app is importable and the client constructs cleanly.
    If this breaks, it's a signal that importing main.py triggered
    scheduler or another side-effect we need to gate.
    """
    try:
        from main import app as real_app  # noqa: WPS433
    except Exception as e:  # noqa: BLE001
        raise AssertionError(f"could not import real main.app: {e}") from e

    client = TestSAPClient(real_app, api_key="fake")
    assert client._api_headers() == {"X-API-Key": "fake"}
    # Health endpoint on real app is unauthenticated and cheap
    r = client.sap_health()
    assert r["status_code"] == 200, r
    assert r["body"] == {"status": "ok"}, r
    client.close()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    tests = [t1, t2, t3, t4, t5, t6]
    print(f"Running {len(tests)} test cases for TestSAPClient\n")
    for t in tests:
        t()
    print(f"\n{len(_PASSED)} passed, {len(_FAILED)} failed")
    if _FAILED:
        for name, msg in _FAILED:
            print(f"  - {name}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
