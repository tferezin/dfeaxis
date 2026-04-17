"""Testes standalone do FakeStripeClient.

Rodar: ./venv/bin/python backend/tests/fakes/test_stripe_fake.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Permite rodar standalone a partir da raiz do repo
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from tests.fakes.stripe_fake import FakeStripeClient  # noqa: E402


def _ok(label: str) -> None:
    print(f"  [ok] {label}")


def _fail(label: str, exc: BaseException) -> None:
    print(f"  [FAIL] {label}: {exc}")


def test_invoice_item_create_logs_and_returns_fields() -> None:
    print("test_invoice_item_create_logs_and_returns_fields")
    fake = FakeStripeClient()
    item = fake.InvoiceItem.create(
        amount=6000,
        currency="brl",
        customer="cus_x",
        description="Excedente 10 docs",
        metadata={"tenant_id": "tnt_1"},
    )

    assert item["amount"] == 6000, item
    assert item["currency"] == "brl", item
    assert item["customer"] == "cus_x", item
    # Ambos os estilos de acesso precisam funcionar
    assert item.id == item["id"]
    assert item.id.startswith("ii_")
    assert item["object"] == "invoiceitem"

    calls = fake.get_calls("InvoiceItem.create")
    assert len(calls) == 1, calls
    assert calls[0]["args"]["amount"] == 6000
    assert calls[0]["args"]["customer"] == "cus_x"
    _ok("InvoiceItem.create retorna id/amount/currency e registra no log")


def test_subscription_retrieve_default_then_preloaded() -> None:
    print("test_subscription_retrieve_default_then_preloaded")
    fake = FakeStripeClient()

    default = fake.Subscription.retrieve("sub_123")
    assert default["id"] == "sub_123"
    assert default["status"] == "active"  # default status
    assert default["items"]["data"][0]["price"]["id"] == "price_fake_default"

    fake.preload_subscription(
        "sub_123",
        status="past_due",
        price_id="price_fake_starter_monthly",
        metadata={"tenant_id": "tnt_abc"},
        current_period_end=1800000000,
    )

    sub = fake.Subscription.retrieve("sub_123")
    assert sub["status"] == "past_due", sub
    assert sub["metadata"] == {"tenant_id": "tnt_abc"}
    item = sub["items"]["data"][0]
    assert item["price"]["id"] == "price_fake_starter_monthly"
    assert item["current_period_end"] == 1800000000
    # attribute-style também
    assert sub.status == "past_due"
    _ok("retrieve antes do preload devolve default; depois devolve o preloaded")


def test_webhook_construct_event_parses_payload_without_hmac() -> None:
    print("test_webhook_construct_event_parses_payload_without_hmac")
    fake = FakeStripeClient()
    payload_dict = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_test_1", "subscription": "sub_123"}},
    }
    payload_bytes = json.dumps(payload_dict).encode()

    event = fake.Webhook.construct_event(
        payload=payload_bytes,
        sig_header="t=0,v1=deadbeef",
        secret="whsec_fake",
    )
    assert event["id"] == "evt_test_1"
    assert event["type"] == "checkout.session.completed"
    assert event["data"]["object"]["subscription"] == "sub_123"

    # Testa também com payload string (alguns frameworks entregam str)
    event2 = fake.Webhook.construct_event(
        payload=json.dumps(payload_dict),
        sig_header="t=0,v1=ff",
        secret="whsec_fake",
    )
    assert event2["id"] == "evt_test_1"
    _ok("construct_event parseia JSON (bytes e str) sem exigir HMAC válido")


def test_force_signature_error_raises_once() -> None:
    print("test_force_signature_error_raises_once")
    fake = FakeStripeClient()
    fake.force_signature_error()

    payload = json.dumps({"id": "evt_x", "type": "invoice.paid"}).encode()

    try:
        fake.Webhook.construct_event(
            payload=payload, sig_header="bad", secret="whsec_fake"
        )
    except fake.error.SignatureVerificationError as exc:
        assert "Invalid signature" in str(exc)
    else:
        raise AssertionError("esperava SignatureVerificationError")

    # Depois de falhar 1x, a flag deve resetar
    event = fake.Webhook.construct_event(
        payload=payload, sig_header="bad", secret="whsec_fake"
    )
    assert event["id"] == "evt_x"
    _ok("force_signature_error levanta 1x depois volta ao normal")


def test_get_calls_filter_by_method() -> None:
    print("test_get_calls_filter_by_method")
    fake = FakeStripeClient()

    fake.InvoiceItem.create(amount=100, currency="brl", customer="cus_1")
    fake.InvoiceItem.create(amount=200, currency="brl", customer="cus_2")
    fake.Customer.create(email="a@b.com", name="A")
    fake.Subscription.retrieve("sub_zzz")

    all_calls = fake.get_calls()
    assert len(all_calls) == 4, all_calls

    ii_calls = fake.get_calls("InvoiceItem.create")
    assert len(ii_calls) == 2
    assert all(c["method"] == "InvoiceItem.create" for c in ii_calls)
    assert ii_calls[0]["args"]["amount"] == 100
    assert ii_calls[1]["args"]["amount"] == 200

    cust_calls = fake.get_calls("Customer.create")
    assert len(cust_calls) == 1
    _ok("get_calls filtra log por nome exato do método")


def test_nested_namespaces_checkout_and_billing_portal() -> None:
    print("test_nested_namespaces_checkout_and_billing_portal")
    fake = FakeStripeClient()

    session = fake.checkout.Session.create(
        mode="subscription",
        customer="cus_1",
        line_items=[{"price": "price_starter", "quantity": 1}],
        success_url="https://x/ok",
        cancel_url="https://x/no",
        client_reference_id="tnt_1",
        metadata={"tenant_id": "tnt_1", "billing_day": "5"},
    )
    # checkout.py real usa `session.id` e `session.url`
    assert session.id.startswith("cs_")
    assert session.url.startswith("https://checkout.stripe.fake/")
    assert session.mode == "subscription"
    assert session["metadata"]["tenant_id"] == "tnt_1"

    portal = fake.billingPortal.Session.create(
        customer="cus_1", return_url="https://x/back"
    )
    assert portal.url.startswith("https://billing.stripe.fake/")
    assert portal["return_url"] == "https://x/back"

    assert len(fake.get_calls("CheckoutSession.create")) == 1
    assert len(fake.get_calls("BillingPortalSession.create")) == 1
    _ok("checkout.Session e billingPortal.Session funcionam como namespaces")


def test_clear_resets_state() -> None:
    print("test_clear_resets_state")
    fake = FakeStripeClient()
    fake.InvoiceItem.create(amount=1, currency="brl", customer="cus_1")
    fake.preload_subscription("sub_1")
    fake.force_signature_error()

    fake.clear()
    assert fake.get_calls() == []
    # Após clear, retrieve devolve default (não o preloaded)
    sub = fake.Subscription.retrieve("sub_1")
    # status default é "active" mas price_id é o default (não o preloaded)
    assert sub["items"]["data"][0]["price"]["id"] == "price_fake_default"
    _ok("clear() zera log, stored e flags")


TESTS = [
    test_invoice_item_create_logs_and_returns_fields,
    test_subscription_retrieve_default_then_preloaded,
    test_webhook_construct_event_parses_payload_without_hmac,
    test_force_signature_error_raises_once,
    test_get_calls_filter_by_method,
    test_nested_namespaces_checkout_and_billing_portal,
    test_clear_resets_state,
]


def main() -> int:
    passed = 0
    failed = 0
    for test in TESTS:
        try:
            test()
            passed += 1
        except AssertionError as exc:
            _fail(test.__name__, exc)
            failed += 1
        except Exception as exc:  # noqa: BLE001
            _fail(test.__name__, exc)
            failed += 1
    print()
    print(f"Resultado: {passed}/{len(TESTS)} passaram, {failed} falharam")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
