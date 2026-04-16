"""Cenários E2E P01-P06 — Plano Pago + Overage.

Especificação completa em `docs/qa/pago-scenarios.md`. Cada função referencia
o P## correspondente e documenta qual regressão/bug pega.

Infraestrutura usada:
  - Fixtures `test_tenant`, `fake_stripe`, `test_app` de `conftest.py`.
  - Supabase REST direto (service role) pra ler/ajustar estado do tenant e
    inspecionar tabelas auxiliares (`monthly_overage_charges`), seguindo o
    mesmo padrão dos cenários de trial (T01-T10).
  - Fake Stripe montado pelo `conftest` patcha `get_stripe` em todos os
    módulos de billing + `scheduler.monthly_overage_job`, então o código
    real roda sem tocar em stripe.com.

Divergências spec vs. backend real (ver relatório do agente):
  - P01: rota é POST `/api/v1/billing/checkout` e retorna 201 (não 200),
    com body `{session_id, url}` — campo se chama `url`, não `checkout_url`.
  - P03: spec fala em `billing_period_end`; no DB a coluna se chama
    `current_period_end`. Além disso, o webhook `invoice.paid` atual NÃO
    reseta `docs_consumidos_mes` — isso só acontece no `monthly_overage_job`
    do dia 1. Marcado xfail até o produto decidir onde zerar.
  - P05: `monthly_overage_job` EXISTE (`scheduler/monthly_overage_job.py`),
    função `process_monthly_overage`. Testamos via chamada direta.
  - P06: `portal.py` usa `stripe.billing_portal.Session.create`
    (snake_case). O FakeStripeClient só expunha `billingPortal` —
    adicionado alias `billing_portal = billingPortal` no fake pra
    espelhar o SDK real (bug de fake, não de produto).
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import requests
from fastapi.testclient import TestClient

from tests.conftest import _HEADERS, _REST  # type: ignore


# ===========================================================================
# Helpers REST (ler/ajustar tenant + tabelas auxiliares)
# ===========================================================================

def _get_tenant(tenant_id: str) -> dict:
    resp = requests.get(
        f"{_REST}/tenants",
        headers=_HEADERS,
        params={"id": f"eq.{tenant_id}", "select": "*"},
        timeout=20,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert rows, f"tenant {tenant_id} não encontrado"
    return rows[0]


def _patch_tenant(tenant_id: str, **fields) -> dict:
    resp = requests.patch(
        f"{_REST}/tenants",
        headers=_HEADERS,
        params={"id": f"eq.{tenant_id}"},
        json=fields,
        timeout=20,
    )
    assert resp.status_code in (200, 204), resp.text
    return _get_tenant(tenant_id)


def _delete_billing_events(tenant_id: str) -> None:
    requests.delete(
        f"{_REST}/billing_events",
        headers=_HEADERS,
        params={"tenant_id": f"eq.{tenant_id}"},
        timeout=20,
    )


def _delete_overage_rows(tenant_id: str) -> None:
    requests.delete(
        f"{_REST}/monthly_overage_charges",
        headers=_HEADERS,
        params={"tenant_id": f"eq.{tenant_id}"},
        timeout=20,
    )


def _get_overage_rows(tenant_id: str) -> list[dict]:
    resp = requests.get(
        f"{_REST}/monthly_overage_charges",
        headers=_HEADERS,
        params={"tenant_id": f"eq.{tenant_id}", "select": "*"},
        timeout=20,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ===========================================================================
# Helper: JWT bypass (mesmo padrão do trial)
# ===========================================================================

def _install_jwt_override(app, tenant_id: str):
    """Injeta `dependency_overrides` no FastAPI app pra bypassar o JWT real
    nas rotas `Depends(verify_jwt_token)`.

    O router de billing usa `Depends(verify_jwt_token)` com referência
    capturada no registro da rota — por isso `monkeypatch` do símbolo no
    módulo NÃO surte efeito. A via correta é `app.dependency_overrides`.
    """
    from middleware.security import verify_jwt_token

    async def _fake_verify() -> dict:
        return {"tenant_id": tenant_id, "user_id": "qa-pago"}

    app.dependency_overrides[verify_jwt_token] = _fake_verify

    def _uninstall() -> None:
        app.dependency_overrides.pop(verify_jwt_token, None)

    return _uninstall


# ===========================================================================
# Helper: POST webhook Stripe via TestClient
# ===========================================================================

def _post_stripe_webhook(app, event: dict) -> dict:
    payload = json.dumps(event).encode("utf-8")
    client = TestClient(app)
    try:
        resp = client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={
                "stripe-signature": "t=0,v1=fake",
                "content-type": "application/json",
            },
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return {"status_code": resp.status_code, "body": body}
    finally:
        client.close()


def _make_stripe_event(event_type: str, data_object: dict, event_id: str | None = None) -> dict:
    return {
        "id": event_id or f"evt_qa_{uuid.uuid4().hex[:16]}",
        "object": "event",
        "type": event_type,
        "data": {"object": data_object},
        "api_version": "2024-04-10",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "livemode": False,
    }


# ===========================================================================
# P01 — Checkout session criada com plano válido
# ===========================================================================

def test_p01_checkout_session_criada_plano_valido(
    test_tenant, fake_stripe, test_app,
):
    """P01: POST /api/v1/billing/checkout com price_id do Starter cria uma
    Stripe Checkout Session válida e registra a chamada no fake Stripe.

    Pega bug onde a rota não propaga metadata pro Stripe (tenant_id,
    billing_day) ou onde o checkout quebra por env var faltando.
    """
    from services.billing import plans as plans_module

    plans_module.reset_cache()
    starter = plans_module.get_plan_by_key("starter")
    assert starter is not None, "plano starter não encontrado no catálogo"
    price_id = starter.price_id_monthly
    assert price_id, "price_id_monthly do starter vazio — seed não rodou"

    uninstall = _install_jwt_override(test_app, test_tenant["tenant_id"])
    try:
        client = TestClient(test_app)
        try:
            resp = client.post(
                "/api/v1/billing/checkout",
                json={"price_id": price_id, "billing_day": 5},
                headers={"Authorization": "Bearer qa-fake-jwt"},
            )
        finally:
            client.close()
    finally:
        uninstall()

    assert resp.status_code == 201, (
        f"esperava 201, obtido={resp.status_code} body={resp.text}"
    )
    body = resp.json()
    assert "session_id" in body, body
    assert "url" in body, body
    assert body["url"].startswith("https://checkout.stripe"), body["url"]

    # Fake Stripe registrou a criação do Customer (lazy) e da Session
    customer_calls = fake_stripe.get_calls("Customer.create")
    assert len(customer_calls) == 1, customer_calls
    cust_args = customer_calls[0]["args"]
    assert cust_args.get("email") == test_tenant["email"]
    assert (cust_args.get("metadata") or {}).get("tenant_id") == test_tenant["tenant_id"]

    session_calls = fake_stripe.get_calls("CheckoutSession.create")
    assert len(session_calls) == 1, session_calls
    sess_args = session_calls[0]["args"]
    assert sess_args.get("mode") == "subscription"
    assert sess_args.get("client_reference_id") == test_tenant["tenant_id"]
    assert (sess_args.get("metadata") or {}).get("tenant_id") == test_tenant["tenant_id"]
    assert (sess_args.get("metadata") or {}).get("billing_day") == "5"
    line_items = sess_args.get("line_items") or []
    assert line_items and line_items[0].get("price") == price_id, line_items
    # success_url / cancel_url vêm do settings (padrão localhost em test)
    assert sess_args.get("success_url"), sess_args
    assert sess_args.get("cancel_url"), sess_args


# ===========================================================================
# P02 — Webhook checkout.session.completed ativa subscription
# ===========================================================================

def test_p02_webhook_checkout_completed_ativa_subscription(
    test_tenant, fake_stripe, test_app,
):
    """P02: `checkout.session.completed` promove tenant de trial pra active,
    persiste stripe_subscription_id/plan/limites e libera polling.

    Pega bugs onde o webhook não persiste plano, não libera o tenant, não
    seta limites mensais.
    """
    from services.billing.plans import load_plans

    _delete_billing_events(test_tenant["tenant_id"])

    starter_plan = next(p for p in load_plans() if p.key == "starter")
    price_id = starter_plan.price_id_monthly

    sub_id = f"sub_qa_{uuid.uuid4().hex[:10]}"
    customer_id = f"cus_qa_{uuid.uuid4().hex[:10]}"
    # stripe_customer_id precisa estar setado antes (checkout cria lazy).
    _patch_tenant(test_tenant["tenant_id"], stripe_customer_id=customer_id)

    fake_stripe.preload_subscription(
        sub_id,
        status="active",
        price_id=price_id,
        customer=customer_id,
        metadata={"tenant_id": test_tenant["tenant_id"], "billing_day": "5"},
        current_period_end=int(
            (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        ),
    )

    event = _make_stripe_event(
        "checkout.session.completed",
        {
            "id": f"cs_qa_{uuid.uuid4().hex[:10]}",
            "object": "checkout.session",
            "mode": "subscription",
            "subscription": sub_id,
            "customer": customer_id,
            "metadata": {"tenant_id": test_tenant["tenant_id"]},
            "amount_total": 29000,
            "currency": "brl",
        },
    )
    result = _post_stripe_webhook(test_app, event)
    assert result["status_code"] == 200, result

    tenant = _get_tenant(test_tenant["tenant_id"])
    assert tenant["subscription_status"] == "active", tenant["subscription_status"]
    assert tenant["trial_active"] is False
    assert tenant.get("trial_blocked_at") is None
    assert tenant.get("stripe_subscription_id") == sub_id
    assert tenant.get("stripe_price_id") == price_id
    assert tenant.get("plan") == "starter", tenant.get("plan")
    assert tenant.get("docs_included_mes") == starter_plan.docs_included
    assert tenant.get("max_cnpjs") == starter_plan.max_cnpjs


# ===========================================================================
# P03 — Renewal mensal reseta contador de docs
# ===========================================================================

def test_p03_invoice_paid_reseta_contador_e_avanca_period(
    test_tenant, fake_stripe, test_app,
):
    """P03: tenant perto do cap recebe `invoice.paid` (renewal) e deve ter
    `docs_consumidos_mes=0` + `current_period_end` avançado +30d.

    Pega bug onde renewal não zera contador (cliente ficaria bloqueado
    indevidamente no mês 2) ou não avança o período.
    """
    from services.billing.plans import load_plans

    _delete_billing_events(test_tenant["tenant_id"])
    starter = next(p for p in load_plans() if p.key == "starter")
    price_id = starter.price_id_monthly

    sub_id = f"sub_qa_{uuid.uuid4().hex[:10]}"
    customer_id = f"cus_qa_{uuid.uuid4().hex[:10]}"
    past_period_end = datetime.now(timezone.utc) - timedelta(hours=1)
    _patch_tenant(
        test_tenant["tenant_id"],
        subscription_status="active",
        trial_active=False,
        plan="starter",
        stripe_customer_id=customer_id,
        stripe_subscription_id=sub_id,
        stripe_price_id=price_id,
        docs_consumidos_mes=2800,
        docs_included_mes=starter.docs_included,
        current_period_end=past_period_end.isoformat(),
    )

    new_period_end = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
    )
    fake_stripe.preload_subscription(
        sub_id,
        status="active",
        price_id=price_id,
        customer=customer_id,
        metadata={"tenant_id": test_tenant["tenant_id"]},
        current_period_end=new_period_end,
    )

    event = _make_stripe_event(
        "invoice.paid",
        {
            "id": f"in_qa_{uuid.uuid4().hex[:10]}",
            "object": "invoice",
            "subscription": sub_id,
            "customer": customer_id,
        },
    )
    result = _post_stripe_webhook(test_app, event)
    assert result["status_code"] == 200, result

    tenant = _get_tenant(test_tenant["tenant_id"])
    assert tenant["subscription_status"] == "active"
    # Assert que deveria passar se o bug for corrigido:
    assert tenant.get("docs_consumidos_mes") == 0, (
        f"renewal deveria zerar docs_consumidos_mes, obtido="
        f"{tenant.get('docs_consumidos_mes')}"
    )
    # current_period_end avançou
    period_end_iso = tenant.get("current_period_end")
    assert period_end_iso, tenant
    new_dt = datetime.fromisoformat(period_end_iso.replace("Z", "+00:00"))
    assert new_dt > datetime.now(timezone.utc) + timedelta(days=25), new_dt


# ===========================================================================
# P04 — Upgrade de plano atualiza limites
# ===========================================================================

def test_p04_subscription_updated_propaga_novos_limites(
    test_tenant, fake_stripe, test_app,
):
    """P04: tenant Starter recebe `customer.subscription.updated` trocando
    pra Business, deve virar plan=business com docs_included_mes e
    max_cnpjs do novo plano.

    Pega bug onde upgrade webhook não propaga novos limites (cliente paga
    mais mas fica com limites do plano antigo).
    """
    from services.billing.plans import load_plans

    plans = load_plans()
    starter = next(p for p in plans if p.key == "starter")
    business = next(p for p in plans if p.key == "business")

    _delete_billing_events(test_tenant["tenant_id"])

    sub_id = f"sub_qa_{uuid.uuid4().hex[:10]}"
    customer_id = f"cus_qa_{uuid.uuid4().hex[:10]}"
    _patch_tenant(
        test_tenant["tenant_id"],
        subscription_status="active",
        trial_active=False,
        plan="starter",
        stripe_customer_id=customer_id,
        stripe_subscription_id=sub_id,
        stripe_price_id=starter.price_id_monthly,
        docs_included_mes=starter.docs_included,
        max_cnpjs=starter.max_cnpjs,
    )

    # Constrói o subscription object direto no payload (subscription.updated
    # chega com o objeto completo — _on_subscription_change usa o próprio
    # payload, não faz retrieve).
    item = {
        "id": f"si_qa_{uuid.uuid4().hex[:8]}",
        "object": "subscription_item",
        "price": {"id": business.price_id_monthly, "object": "price"},
        "current_period_end": int(
            (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        ),
    }
    updated_sub = {
        "id": sub_id,
        "object": "subscription",
        "status": "active",
        "customer": customer_id,
        "metadata": {"tenant_id": test_tenant["tenant_id"]},
        "cancel_at_period_end": False,
        "items": {"object": "list", "data": [item], "has_more": False},
    }

    event = _make_stripe_event("customer.subscription.updated", updated_sub)
    result = _post_stripe_webhook(test_app, event)
    assert result["status_code"] == 200, result

    tenant = _get_tenant(test_tenant["tenant_id"])
    assert tenant["subscription_status"] == "active"
    assert tenant.get("plan") == "business", tenant.get("plan")
    assert tenant.get("stripe_price_id") == business.price_id_monthly
    assert tenant.get("docs_included_mes") == business.docs_included
    assert tenant.get("max_cnpjs") == business.max_cnpjs


# ===========================================================================
# P05 — Overage: estouro do cap mensal é medido e registrado
# ===========================================================================

def test_p05_monthly_overage_job_registra_excedente(
    test_tenant, fake_stripe,
):
    """P05: tenant Starter com docs_consumidos_mes=3001 (1 acima do cap)
    processado pelo `monthly_overage_job` gera:
      - 1 linha em `monthly_overage_charges` com excedente_docs=1 e
        excedente_cents=12 (starter overage=12 cents/doc)
      - 1 chamada InvoiceItem.create no Stripe com amount=12

    Pega bug onde o overage não é calculado/registrado (cliente usa mais
    do que paga sem cobrança extra).
    """
    from services.billing.plans import load_plans
    from scheduler.monthly_overage_job import process_monthly_overage

    starter = next(p for p in load_plans() if p.key == "starter")
    price_id = starter.price_id_monthly
    customer_id = f"cus_qa_{uuid.uuid4().hex[:10]}"

    _delete_overage_rows(test_tenant["tenant_id"])
    _patch_tenant(
        test_tenant["tenant_id"],
        subscription_status="active",
        trial_active=False,
        plan="starter",
        stripe_customer_id=customer_id,
        stripe_price_id=price_id,
        docs_consumidos_mes=3001,
        docs_included_mes=starter.docs_included,  # 3000
    )

    try:
        process_monthly_overage()

        rows = _get_overage_rows(test_tenant["tenant_id"])
        assert len(rows) == 1, f"esperava 1 linha de overage, obtido={len(rows)}"
        row = rows[0]
        assert row["excedente_docs"] == 1, row
        assert row["excedente_cents"] == starter.overage_cents_per_doc, row
        assert row["stripe_invoice_item_id"], row

        invoice_item_calls = fake_stripe.get_calls("InvoiceItem.create")
        assert len(invoice_item_calls) == 1, invoice_item_calls
        args = invoice_item_calls[0]["args"]
        assert args.get("customer") == customer_id
        assert args.get("amount") == starter.overage_cents_per_doc
        assert args.get("currency") == "brl"
        meta = args.get("metadata") or {}
        assert meta.get("tenant_id") == test_tenant["tenant_id"]
        assert meta.get("excedente_docs") == "1"
    finally:
        # Cleanup (linhas criadas pelo job — teardown do test_tenant só
        # deleta tenant/api_keys/certs, não monthly_overage_charges)
        _delete_overage_rows(test_tenant["tenant_id"])


# ===========================================================================
# P06 — Billing portal session criada
# ===========================================================================

def test_p06_billing_portal_session_criada(
    test_tenant, fake_stripe, test_app,
):
    """P06: POST /api/v1/billing/portal cria uma Portal Session válida pro
    customer do tenant e registra a chamada no fake Stripe.

    Pega bug onde o portal quebra (impacto alto em retenção — cliente não
    consegue trocar cartão, cancelar ou fazer upgrade).
    """
    customer_id = f"cus_qa_{uuid.uuid4().hex[:10]}"
    _patch_tenant(
        test_tenant["tenant_id"],
        subscription_status="active",
        trial_active=False,
        stripe_customer_id=customer_id,
    )

    uninstall = _install_jwt_override(test_app, test_tenant["tenant_id"])
    try:
        client = TestClient(test_app)
        try:
            resp = client.post(
                "/api/v1/billing/portal",
                json={},
                headers={"Authorization": "Bearer qa-fake-jwt"},
            )
        finally:
            client.close()
    finally:
        uninstall()

    assert resp.status_code == 200, (
        f"esperava 200, obtido={resp.status_code} body={resp.text}"
    )
    body = resp.json()
    assert "session_id" in body, body
    assert "url" in body, body
    assert body["url"].startswith("https://billing.stripe"), body["url"]

    portal_calls = fake_stripe.get_calls("BillingPortalSession.create")
    assert len(portal_calls) == 1, portal_calls
    args = portal_calls[0]["args"]
    assert args.get("customer") == customer_id
    assert args.get("return_url"), args
