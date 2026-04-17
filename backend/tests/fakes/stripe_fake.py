"""FakeStripeClient — drop-in para o módulo `stripe` real nos testes.

Mimica só a superfície que o nosso código usa:
  - stripe.Customer.create / retrieve
  - stripe.Subscription.retrieve
  - stripe.Invoice.create / finalize_invoice / pay / retrieve
  - stripe.InvoiceItem.create
  - stripe.checkout.Session.create
  - stripe.billingPortal.Session.create
  - stripe.Webhook.construct_event
  - stripe.error.{SignatureVerificationError,InvalidRequestError,StripeError}

Objetos retornados suportam tanto acesso por chave (`obj["id"]`) quanto
por atributo (`obj.id`), porque o código real mistura os dois estilos —
`checkout.py` faz `session.id` mas `subscriptions.py` faz `sub.get("id")`.

Uso nos testes:

    fake = FakeStripeClient()
    fake.preload_subscription("sub_123", status="active",
                              price_id="price_starter_monthly",
                              metadata={"tenant_id": "tnt_abc"})

    # monkeypatch em services.billing.stripe_client.get_stripe
    monkeypatch.setattr(
        "services.billing.stripe_client.get_stripe",
        lambda: fake,
    )

    # depois dos asserts:
    assert len(fake.get_calls("InvoiceItem.create")) == 1
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Error namespace (stripe.error.*)
# ---------------------------------------------------------------------------

class _FakeStripeErrors:
    """Namespace que imita `stripe.error`."""

    class StripeError(Exception):
        pass

    class SignatureVerificationError(StripeError):
        def __init__(self, message: str = "Invalid signature", sig_header: str = ""):
            super().__init__(message)
            self.sig_header = sig_header

    class InvalidRequestError(StripeError):
        pass


# ---------------------------------------------------------------------------
# Objeto fake com dupla interface (dict + attr)
# ---------------------------------------------------------------------------

class FakeStripeObject(dict):
    """Dict que também expõe as chaves como atributos.

    O código real do DFeAxis mistura `obj["id"]` e `obj.id` dependendo do
    arquivo. Isso cobre os dois caminhos sem precisar trocar nada do lado
    do caller.
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        try:
            del self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


# ---------------------------------------------------------------------------
# Collections (stripe.Subscription, stripe.InvoiceItem, ...)
# ---------------------------------------------------------------------------

class FakeStripeCollection:
    """Mimica `stripe.<Resource>` com create/retrieve/list."""

    def __init__(self, name: str, fake: "FakeStripeClient"):
        self._name = name
        self._fake = fake

    # ------------------------------------------------------------------ CREATE
    def create(self, **kwargs) -> FakeStripeObject:
        call_id = self._fake._log_call(f"{self._name}.create", kwargs)
        obj = self._fake._build_object(self._name, call_id, kwargs)
        # Armazena pra permitir retrieve posterior
        self._fake._stored[(self._name, obj["id"])] = obj
        return obj

    # ---------------------------------------------------------------- RETRIEVE
    def retrieve(self, id: str, **kwargs) -> FakeStripeObject:  # noqa: A002
        self._fake._log_call(
            f"{self._name}.retrieve", {"id": id, **kwargs}
        )
        stored = self._fake._stored.get((self._name, id))
        if stored is not None:
            return stored
        return self._fake._default(self._name, id)

    # -------------------------------------------------------------------- LIST
    def list(self, **kwargs) -> FakeStripeObject:
        self._fake._log_call(f"{self._name}.list", kwargs)
        items = [
            obj
            for (coll, _id), obj in self._fake._stored.items()
            if coll == self._name
        ]
        return FakeStripeObject(object="list", data=items, has_more=False)

    # -------------------------------------------------------------- invoice ops
    def finalize_invoice(self, id: str, **kwargs) -> FakeStripeObject:  # noqa: A002
        self._fake._log_call(
            f"{self._name}.finalize_invoice", {"id": id, **kwargs}
        )
        inv = self._fake._stored.get((self._name, id)) or self._fake._default(
            self._name, id
        )
        inv["status"] = "open"
        return inv

    def pay(self, id: str, **kwargs) -> FakeStripeObject:  # noqa: A002
        self._fake._log_call(f"{self._name}.pay", {"id": id, **kwargs})
        inv = self._fake._stored.get((self._name, id)) or self._fake._default(
            self._name, id
        )
        inv["status"] = "paid"
        inv["paid"] = True
        return inv


# ---------------------------------------------------------------------------
# Webhook (stripe.Webhook.construct_event)
# ---------------------------------------------------------------------------

class FakeWebhook:
    """Mimica `stripe.Webhook.construct_event`.

    No teste pulamos a validação HMAC — o objetivo do fake é deixar a
    gente simular um webhook chegando sem precisar assinar com o
    STRIPE_WEBHOOK_SECRET real. Se `force_signature_error()` foi
    chamado antes, a próxima chamada levanta SignatureVerificationError
    (pra testar o caminho de erro).
    """

    def __init__(self, fake: "FakeStripeClient"):
        self._fake = fake

    def construct_event(
        self,
        payload: bytes | str,
        sig_header: str,
        secret: str,
        **kwargs,
    ) -> FakeStripeObject:
        self._fake._log_call(
            "Webhook.construct_event",
            {"sig_header": sig_header, "secret": secret, **kwargs},
        )
        if self._fake._force_signature_error:
            # Consume a flag — só força 1x, depois volta ao normal
            self._fake._force_signature_error = False
            raise self._fake.error.SignatureVerificationError(
                "Invalid signature (forced by FakeStripeClient)",
                sig_header=sig_header,
            )

        if isinstance(payload, (bytes, bytearray)):
            payload_str = payload.decode("utf-8")
        else:
            payload_str = payload
        data = json.loads(payload_str)
        return FakeStripeObject(**data)


# ---------------------------------------------------------------------------
# Namespaces aninhados (checkout.Session, billingPortal.Session)
# ---------------------------------------------------------------------------

class _FakeNamespace:
    """Container trivial pra aninhar collections sob um nome."""

    def __init__(self, **children):
        for key, value in children.items():
            setattr(self, key, value)


# ---------------------------------------------------------------------------
# FakeStripeClient — módulo fake
# ---------------------------------------------------------------------------

class FakeStripeClient:
    """Módulo fake que substitui o stripe real nos testes.

    Deve ser usado como drop-in replacement do retorno de
    `services.billing.stripe_client.get_stripe()`.
    """

    def __init__(self) -> None:
        self._call_log: list[dict] = []
        self._stored: dict[tuple[str, str], FakeStripeObject] = {}
        self._force_signature_error: bool = False

        # Collections "top-level"
        self.Subscription = FakeStripeCollection("Subscription", self)
        self.InvoiceItem = FakeStripeCollection("InvoiceItem", self)
        self.Invoice = FakeStripeCollection("Invoice", self)
        self.Customer = FakeStripeCollection("Customer", self)

        # Namespaces aninhados
        self.checkout = _FakeNamespace(
            Session=FakeStripeCollection("CheckoutSession", self),
        )
        self.billingPortal = _FakeNamespace(
            Session=FakeStripeCollection("BillingPortalSession", self),
        )
        # Real stripe SDK expõe `billing_portal` como alias snake_case de
        # `billingPortal`. O código de portal.py usa o snake_case.
        self.billing_portal = self.billingPortal

        # Webhook + erros
        self.Webhook = FakeWebhook(self)
        self.error = _FakeStripeErrors()

        # Atributos que `get_stripe()` real mexe — aceitamos set, ignoramos valor
        self.api_key: Optional[str] = "sk_test_fake"
        self.max_network_retries: int = 0

    # ================================================================= SETUP
    def preload_subscription(
        self,
        subscription_id: str,
        *,
        status: str = "active",
        price_id: str = "price_fake_starter_monthly",
        customer: str = "cus_fake",
        metadata: Optional[dict] = None,
        current_period_end: Optional[int] = None,
        cancel_at_period_end: bool = False,
        items_extra: Optional[dict] = None,
    ) -> FakeStripeObject:
        """Pre-carrega um Subscription que o código vai tentar retrieve."""
        item = FakeStripeObject(
            id=f"si_{uuid.uuid4().hex[:12]}",
            object="subscription_item",
            price=FakeStripeObject(id=price_id, object="price"),
            current_period_end=current_period_end,
            **(items_extra or {}),
        )
        sub = FakeStripeObject(
            id=subscription_id,
            object="subscription",
            status=status,
            customer=customer,
            metadata=metadata or {},
            cancel_at_period_end=cancel_at_period_end,
            current_period_end=current_period_end,
            items=FakeStripeObject(object="list", data=[item], has_more=False),
        )
        self._stored[("Subscription", subscription_id)] = sub
        return sub

    def preload_customer(
        self,
        customer_id: str,
        *,
        email: str = "fake@dfeaxis.com",
        name: str = "Fake Co",
        metadata: Optional[dict] = None,
    ) -> FakeStripeObject:
        cust = FakeStripeObject(
            id=customer_id,
            object="customer",
            email=email,
            name=name,
            metadata=metadata or {},
        )
        self._stored[("Customer", customer_id)] = cust
        return cust

    # =========================================================== INSPEÇÃO
    def get_calls(self, method: Optional[str] = None) -> list[dict]:
        """Retorna log de chamadas (filtra por nome exato se passado)."""
        if method is None:
            return list(self._call_log)
        return [c for c in self._call_log if c["method"] == method]

    def clear(self) -> None:
        """Limpa todo o estado — use no teardown das fixtures."""
        self._call_log.clear()
        self._stored.clear()
        self._force_signature_error = False

    def force_signature_error(self) -> None:
        """Próxima Webhook.construct_event vai levantar SignatureVerificationError."""
        self._force_signature_error = True

    # ============================================================== INTERNOS
    def _log_call(self, method: str, kwargs: dict) -> str:
        call_id = f"fake_{uuid.uuid4().hex[:16]}"
        self._call_log.append(
            {"method": method, "args": dict(kwargs), "id": call_id}
        )
        return call_id

    def _build_object(
        self, collection: str, call_id: str, kwargs: dict
    ) -> FakeStripeObject:
        """Monta um objeto fake com os campos que o Stripe devolveria."""
        prefix = _ID_PREFIX.get(collection, "obj")
        obj_id = f"{prefix}_{call_id.replace('fake_', '')}"

        base = FakeStripeObject(
            id=obj_id,
            object=_OBJECT_NAME.get(collection, collection.lower()),
        )
        # Merge kwargs — o Stripe real ecoa quase tudo que você passou
        for key, value in kwargs.items():
            base[key] = value

        if collection == "InvoiceItem":
            base.setdefault("amount", kwargs.get("amount", 0))
            base.setdefault("currency", kwargs.get("currency", "brl"))
            base.setdefault("livemode", False)
        elif collection == "Invoice":
            base.setdefault("status", "draft")
            base.setdefault("paid", False)
            base.setdefault("amount_due", 0)
            base.setdefault("currency", "brl")
        elif collection == "Customer":
            base.setdefault("email", kwargs.get("email"))
            base.setdefault("name", kwargs.get("name"))
        elif collection == "Subscription":
            base.setdefault("status", "active")
            base.setdefault(
                "items",
                FakeStripeObject(object="list", data=[], has_more=False),
            )
        elif collection == "CheckoutSession":
            base.setdefault("url", f"https://checkout.stripe.fake/{obj_id}")
            base.setdefault("payment_status", "unpaid")
            base.setdefault("mode", kwargs.get("mode", "subscription"))
            base.setdefault("status", "open")
        elif collection == "BillingPortalSession":
            base.setdefault("url", f"https://billing.stripe.fake/{obj_id}")
            base.setdefault("return_url", kwargs.get("return_url"))
        return base

    def _default(self, collection: str, id: str) -> FakeStripeObject:  # noqa: A002
        """Objeto default devolvido por retrieve() quando nada foi preloaded."""
        base = FakeStripeObject(
            id=id,
            object=_OBJECT_NAME.get(collection, collection.lower()),
        )
        if collection == "Subscription":
            base["status"] = "active"
            base["customer"] = "cus_fake_default"
            base["metadata"] = {}
            base["cancel_at_period_end"] = False
            base["current_period_end"] = None
            base["items"] = FakeStripeObject(
                object="list",
                data=[
                    FakeStripeObject(
                        id=f"si_default_{id}",
                        object="subscription_item",
                        price=FakeStripeObject(
                            id="price_fake_default", object="price"
                        ),
                        current_period_end=None,
                    )
                ],
                has_more=False,
            )
        elif collection == "Customer":
            base["email"] = None
            base["name"] = None
            base["metadata"] = {}
        elif collection == "Invoice":
            base["status"] = "draft"
            base["paid"] = False
        return base


_ID_PREFIX = {
    "Subscription": "sub",
    "InvoiceItem": "ii",
    "Invoice": "in",
    "Customer": "cus",
    "CheckoutSession": "cs",
    "BillingPortalSession": "bps",
}

_OBJECT_NAME = {
    "Subscription": "subscription",
    "InvoiceItem": "invoiceitem",
    "Invoice": "invoice",
    "Customer": "customer",
    "CheckoutSession": "checkout.session",
    "BillingPortalSession": "billing_portal.session",
}


__all__ = [
    "FakeStripeClient",
    "FakeStripeCollection",
    "FakeStripeObject",
    "FakeWebhook",
]
