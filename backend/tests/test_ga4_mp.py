"""Unit tests for GA4 Measurement Protocol sender.

Segue o padrão dos outros testes do repositório (script standalone que
pode ser rodado com `python tests/test_ga4_mp.py`). Não usa pytest
fixtures nem HTTP mocking libraries — faz monkey-patch direto no
`requests.post` através do `unittest.mock`.

Cobertura:
  1. send_purchase_event sem api_secret → skipped (não levanta)
  2. send_purchase_event com api_secret + client_id → POST correto,
     payload tem estrutura esperada do Measurement Protocol
  3. send_purchase_event sem client_id → usa fallback "server.<txn>"
  4. Network error não levanta — retorna status error
  5. GA4 retornando 400 não levanta — retorna status error
  6. Webhook _on_checkout_completed chama send_purchase_event com
     os parâmetros corretos quando o tenant tem ga_client_id

Run with:
    cd backend && source venv/bin/activate
    python tests/test_ga4_mp.py
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure backend module path is loadable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# Reimport config after loading .env so settings picks up any vars
from config import settings  # noqa: E402
from services.tracking.ga4_mp import send_purchase_event, MP_ENDPOINT  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str, status: str = "INFO") -> None:
    icon = {"INFO": "→", "PASS": "✓", "FAIL": "✗"}.get(status, "→")
    print(f"  {icon} {msg}")


def _make_mock_response(status_code: int, body: str = "") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.text = body
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_skipped_without_api_secret() -> None:
    print("\n[1] send_purchase_event sem GA4_API_SECRET configurado")
    # Força o secret a ficar vazio temporariamente
    original = settings.ga4_api_secret
    try:
        settings.ga4_api_secret = ""
        with patch("services.tracking.ga4_mp.requests.post") as mock_post:
            result = send_purchase_event(
                client_id="123.456",
                transaction_id="sub_test_1",
                value_brl=290.0,
            )
        assert result["status"] == "skipped", f"expected skipped, got {result}"
        assert result["reason"] == "api_secret_missing"
        mock_post.assert_not_called()
    finally:
        settings.ga4_api_secret = original
    log("skipped quando api_secret ausente (sem chamada HTTP)", "PASS")


def test_sends_correct_payload() -> None:
    print("\n[2] send_purchase_event com secret + client_id → POST correto")
    original = settings.ga4_api_secret
    try:
        settings.ga4_api_secret = "test_secret_abc"
        with patch("services.tracking.ga4_mp.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(204)
            result = send_purchase_event(
                client_id="1234567890.9876543210",
                transaction_id="sub_ABC123",
                value_brl=290.0,
                currency="BRL",
                item_id="starter",
                item_name="DFeAxis Starter",
            )

        assert result["status"] == "sent", f"expected sent, got {result}"
        assert result["http_status"] == 204

        # Inspeciona a chamada ao requests.post
        call = mock_post.call_args
        assert call is not None, "requests.post não foi chamado"

        url = call.args[0] if call.args else call.kwargs.get("url", "")
        assert MP_ENDPOINT in url, f"URL não contém endpoint MP: {url}"
        assert "measurement_id=" in url, f"URL sem measurement_id: {url}"
        assert "api_secret=test_secret_abc" in url, f"URL sem api_secret: {url}"

        payload = call.kwargs.get("json")
        assert payload is not None, "POST sem payload JSON"

        assert payload["client_id"] == "1234567890.9876543210"
        assert payload["non_personalized_ads"] is False
        assert len(payload["events"]) == 1

        event = payload["events"][0]
        assert event["name"] == "purchase"
        assert event["params"]["currency"] == "BRL"
        assert event["params"]["value"] == 290.0
        assert event["params"]["transaction_id"] == "sub_ABC123"

        items = event["params"]["items"]
        assert len(items) == 1
        assert items[0]["item_id"] == "starter"
        assert items[0]["item_name"] == "DFeAxis Starter"
        assert items[0]["price"] == 290.0
        assert items[0]["quantity"] == 1

        timeout = call.kwargs.get("timeout")
        assert timeout is not None and timeout <= 5, f"timeout muito alto: {timeout}"
    finally:
        settings.ga4_api_secret = original
    log("payload válido enviado ao endpoint correto", "PASS")


def test_fallback_client_id_when_missing() -> None:
    print("\n[3] send_purchase_event sem client_id → fallback server.<txn>")
    original = settings.ga4_api_secret
    try:
        settings.ga4_api_secret = "test_secret_xyz"
        with patch("services.tracking.ga4_mp.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(204)
            result = send_purchase_event(
                client_id=None,
                transaction_id="sub_fallback_42",
                value_brl=690.0,
            )

        assert result["status"] == "sent"

        payload = mock_post.call_args.kwargs.get("json")
        assert payload["client_id"] == "server.sub_fallback_42", (
            f"fallback client_id errado: {payload['client_id']}"
        )
    finally:
        settings.ga4_api_secret = original
    log("fallback client_id=server.<txn> quando None", "PASS")


def test_network_error_does_not_raise() -> None:
    print("\n[4] Erro de rede não levanta exceção")
    import requests as req_mod

    original = settings.ga4_api_secret
    try:
        settings.ga4_api_secret = "test_secret"
        with patch("services.tracking.ga4_mp.requests.post") as mock_post:
            mock_post.side_effect = req_mod.ConnectionError("simulated network fail")
            # Este call não pode levantar — tracking não quebra fluxo.
            result = send_purchase_event(
                client_id="a.b",
                transaction_id="sub_nope",
                value_brl=100.0,
            )
        assert result["status"] == "error"
        assert "network" in result["reason"]
    finally:
        settings.ga4_api_secret = original
    log("RequestException engolida, retorno gracioso", "PASS")


def test_4xx_response_does_not_raise() -> None:
    print("\n[5] GA4 retornando 400 não levanta")
    original = settings.ga4_api_secret
    try:
        settings.ga4_api_secret = "test_secret"
        with patch("services.tracking.ga4_mp.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(400, '{"error":"invalid"}')
            result = send_purchase_event(
                client_id="a.b",
                transaction_id="sub_bad",
                value_brl=1.0,
            )
        assert result["status"] == "error"
        assert result["reason"] == "http_400"
    finally:
        settings.ga4_api_secret = original
    log("resposta 4xx retorna error sem levantar", "PASS")


def test_webhook_integration_fires_purchase() -> None:
    """Valida que _fire_ga4_purchase puxa ga_client_id do tenant e chama MP."""
    print("\n[6] Webhook _fire_ga4_purchase integra com send_purchase_event")

    from services.billing import webhooks as wh_mod

    fake_session = {
        "id": "cs_test_session",
        "mode": "subscription",
        "amount_total": 29000,  # R$ 290,00 em centavos
        "currency": "brl",
        "subscription": "sub_ABC",
        "metadata": {"tenant_id": "tenant-uuid-1"},
    }
    fake_subscription = {
        "id": "sub_ABC",
        "status": "active",
        "items": {
            "data": [
                {
                    "price": {"id": "price_starter_monthly"},
                    "current_period_end": 1735689600,
                }
            ]
        },
        "metadata": {"tenant_id": "tenant-uuid-1"},
    }

    # Mock do supabase para retornar ga_client_id do tenant
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"ga_client_id": "9999.8888"}
    ]

    # Mock do get_plan_by_price_id
    fake_plan_lookup = MagicMock()
    fake_plan_lookup.plan.key = "starter"
    fake_plan_lookup.plan.name = "Starter"
    fake_plan_lookup.plan.monthly_amount_cents = 29000
    fake_plan_lookup.plan.yearly_amount_cents = 278400
    fake_plan_lookup.period = "monthly"

    with patch.object(wh_mod, "get_supabase_client", return_value=mock_sb):
        with patch.object(wh_mod, "get_plan_by_price_id", return_value=fake_plan_lookup):
            with patch.object(wh_mod, "send_purchase_event") as mock_send:
                wh_mod._fire_ga4_purchase(
                    session=fake_session,
                    subscription=fake_subscription,
                    tenant_id="tenant-uuid-1",
                )

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["client_id"] == "9999.8888"
    assert kwargs["transaction_id"] == "sub_ABC"
    assert kwargs["value_brl"] == 290.0
    assert kwargs["currency"] == "BRL"
    assert kwargs["item_id"] == "starter"
    assert kwargs["item_name"] == "DFeAxis Starter"
    log("_fire_ga4_purchase repassa os dados corretos", "PASS")


def test_outer_try_except_catches_non_request_errors() -> None:
    """Valida que o outer try/except engole erros que não sejam RequestException."""
    print("\n[8] send_purchase_event engole exceções inesperadas (outer try/except)")

    original = settings.ga4_api_secret
    try:
        settings.ga4_api_secret = "test_secret"
        # Simula um TypeError durante serialização/montagem do payload,
        # emulando um valor inválido que escaparia do try/except interno.
        with patch(
            "services.tracking.ga4_mp.requests.post",
            side_effect=TypeError("fake non-request error"),
        ):
            result = send_purchase_event(
                client_id="a.b",
                transaction_id="sub_oops",
                value_brl=100.0,
            )
        assert result["status"] == "error"
        assert "unexpected" in result["reason"]
        assert "TypeError" in result["reason"]
    finally:
        settings.ga4_api_secret = original
    log("TypeError engolido pelo outer try/except", "PASS")


def test_webhook_integration_without_ga_client_id() -> None:
    """Tenant sem ga_client_id → send_purchase_event chamado com client_id=None."""
    print("\n[7] Webhook _fire_ga4_purchase sem ga_client_id no tenant")

    from services.billing import webhooks as wh_mod

    fake_session = {
        "id": "cs_test_nocid",
        "amount_total": 69000,
        "currency": "brl",
        "subscription": "sub_NOCID",
    }
    fake_subscription = {
        "id": "sub_NOCID",
        "items": {"data": [{"price": {"id": "price_business"}}]},
    }

    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"ga_client_id": None}
    ]

    fake_plan_lookup = MagicMock()
    fake_plan_lookup.plan.key = "business"
    fake_plan_lookup.plan.name = "Business"
    fake_plan_lookup.plan.monthly_amount_cents = 69000
    fake_plan_lookup.plan.yearly_amount_cents = 662400
    fake_plan_lookup.period = "monthly"

    with patch.object(wh_mod, "get_supabase_client", return_value=mock_sb):
        with patch.object(wh_mod, "get_plan_by_price_id", return_value=fake_plan_lookup):
            with patch.object(wh_mod, "send_purchase_event") as mock_send:
                wh_mod._fire_ga4_purchase(
                    session=fake_session,
                    subscription=fake_subscription,
                    tenant_id="tenant-uuid-2",
                )

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["client_id"] is None, f"esperava None, got {kwargs['client_id']}"
    assert kwargs["transaction_id"] == "sub_NOCID"
    assert kwargs["value_brl"] == 690.0
    log("None do DB propaga corretamente pro fallback", "PASS")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("GA4 Measurement Protocol — unit tests")
    print("=" * 60)

    tests = [
        test_skipped_without_api_secret,
        test_sends_correct_payload,
        test_fallback_client_id_when_missing,
        test_network_error_does_not_raise,
        test_4xx_response_does_not_raise,
        test_outer_try_except_catches_non_request_errors,
        test_webhook_integration_fires_purchase,
        test_webhook_integration_without_ga_client_id,
    ]

    failures: list[str] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            log(f"FAIL: {t.__name__}: {e}", "FAIL")
            failures.append(t.__name__)
        except Exception as e:
            log(f"ERROR: {t.__name__}: {type(e).__name__}: {e}", "FAIL")
            failures.append(t.__name__)

    print()
    print("=" * 60)
    if failures:
        print(f"✗ {len(failures)}/{len(tests)} tests failed: {', '.join(failures)}")
        return 1
    print(f"✓ all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
