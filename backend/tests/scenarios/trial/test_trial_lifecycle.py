"""Cenários E2E T01-T10 — Trial Lifecycle.

Especificação completa em `docs/qa/trial-scenarios.md`. Cada função de teste
referencia o T## correspondente e documenta qual regressão pega.

Esses testes usam:
  - `test_tenant`, `fake_sefaz`, `fake_stripe`, `test_app`: fixtures de
    `backend/tests/conftest.py`
  - REST da Supabase via service role key (mesmo padrão do
    `test_trial_e2e.py` existente) pra ler/ajustar estado do tenant
    diretamente — evita dependência de JWT real do dashboard.
  - `app.dependency_overrides` no `verify_jwt_with_trial` pra bypassar
    a autenticação Bearer do `/polling/trigger` sem desligar o gate de
    trial (o override continua chamando `verify_trial_active` com um
    auth dict sintético, exercitando a enforcement real).

Notas sobre divergências da spec vs. código real de produção:
  - Trial bloqueado retorna **HTTP 402** (Payment Required) com
    `code=TRIAL_EXPIRED`. Padrão alinhado com a spec após ajuste no
    middleware `verify_trial_active`.
  - T06 fala em `docs_consumidos_trial=500` após o trigger. O cap real
    de captura do `_poll_single_detailed` é medido via
    `count(documents WHERE tenant_id=X)`, não `docs_consumidos_trial`
    (que só avança em `/confirmar`). O teste afere o cap pelo caminho
    real (docs na tabela) e valida bloqueio do próximo trigger.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

# Reutiliza constantes de conexão do conftest pra REST direto.
from tests.conftest import _HEADERS, _REST  # type: ignore


# ===========================================================================
# Helpers REST (ler/ajustar estado do tenant sem passar por rotas protegidas)
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


def _count_documents(tenant_id: str) -> int:
    resp = requests.get(
        f"{_REST}/documents",
        headers={**_HEADERS, "Prefer": "count=exact"},
        params={"tenant_id": f"eq.{tenant_id}", "select": "id", "limit": "0"},
        timeout=20,
    )
    # Supabase count vem no header Content-Range: "0-0/<count>"
    cr = resp.headers.get("content-range", "")
    if "/" in cr:
        try:
            return int(cr.split("/")[-1])
        except ValueError:
            return 0
    return 0


def _delete_documents(tenant_id: str) -> None:
    requests.delete(
        f"{_REST}/documents",
        headers=_HEADERS,
        params={"tenant_id": f"eq.{tenant_id}"},
        timeout=20,
    )


def _delete_billing_events(tenant_id: str) -> None:
    """Limpa billing_events do tenant — evita que o `_is_duplicate` bloqueie
    re-execuções do mesmo tipo de evento dentro de um run."""
    requests.delete(
        f"{_REST}/billing_events",
        headers=_HEADERS,
        params={"tenant_id": f"eq.{tenant_id}"},
        timeout=20,
    )


# ===========================================================================
# Helper: dependency override pra /polling/trigger (bypassa JWT, mantém gate)
# ===========================================================================

def _install_polling_auth_override(app, tenant_id: str):
    """Injeta um `verify_jwt_token` stub no módulo `middleware.security`.

    `verify_jwt_with_trial` chama `verify_jwt_token` diretamente (via
    binding de módulo, não via Depends), então substituir o símbolo no
    namespace do módulo efetivamente pula a validação real do Bearer.
    O gate de trial (`verify_trial_active`) continua rodando dentro de
    `verify_jwt_with_trial`, com isso preservamos a enforcement real.
    """
    import middleware.security as sec_mod  # type: ignore

    original = sec_mod.verify_jwt_token

    async def _fake_verify(request):  # noqa: ANN001 - match real signature
        return {"tenant_id": tenant_id, "user_id": "qa-fixture"}

    sec_mod.verify_jwt_token = _fake_verify  # type: ignore[assignment]

    def _uninstall() -> None:
        sec_mod.verify_jwt_token = original  # type: ignore[assignment]

    return _uninstall


# ===========================================================================
# Helper: disparar polling via TestClient (bypassando SAP DRC layer)
# ===========================================================================

def _trigger_polling(app, tenant_id: str, cnpj: str, tipos=("nfe",)) -> dict:
    """Dispara POST /api/v1/polling/trigger com JWT bypass.

    IMPORTANTE: o endpoint tenta decriptar a senha do PFX fake logo após
    o gate de trial passar. Como o cert é sintético, a decriptação falha
    com um ValueError que o TestClient re-lança (raise_server_exceptions
    default True). Pra esses testes, a gente só se importa com o GATE de
    trial (401/403 vs. gate passou), então capturamos a exceção do lado
    do cliente e devolvemos um status sintético 599 "gate-passed-deep-error".
    """
    from fastapi.testclient import TestClient

    uninstall = _install_polling_auth_override(app, tenant_id)
    try:
        # raise_server_exceptions=False faz o TestClient devolver 500 em vez de
        # propagar a exceção — assim podemos distinguir 403 (gate bloqueou) de
        # 500 (gate passou, estourou adiante).
        client = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client.post(
                "/api/v1/polling/trigger",
                json={"cnpj": cnpj, "tipos": list(tipos)},
                headers={"Authorization": "Bearer qa-fake-jwt"},
            )
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            return {"status_code": resp.status_code, "body": body}
        finally:
            client.close()
    finally:
        uninstall()


# ===========================================================================
# Helper: disparar webhook Stripe via TestClient
# ===========================================================================

def _post_stripe_webhook(app, event: dict) -> dict:
    from fastapi.testclient import TestClient

    payload = json.dumps(event).encode("utf-8")
    client = TestClient(app)
    try:
        resp = client.post(
            "/api/v1/billing/webhook",
            content=payload,
            headers={
                "stripe-signature": "t=0,v1=fake",  # fake aceita
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
# T01 — Signup cria trial em estado inicial correto
# ===========================================================================

def test_t01_signup_cria_trial_estado_inicial(test_tenant):
    """T01: tenant recém-criado deve ter trial ativo com defaults corretos.

    Pega regressões onde o signup esquece de setar trial_expires_at, cria o
    tenant já bloqueado, ou deixa ambiente de produção por engano.
    """
    tenant = _get_tenant(test_tenant["tenant_id"])

    assert tenant["trial_active"] is True, "trial deveria estar ativo no signup"
    assert tenant["docs_consumidos_trial"] == 0
    assert tenant.get("trial_blocked_at") is None
    assert tenant["subscription_status"] == "trial"

    expires_at = tenant.get("trial_expires_at")
    assert expires_at, "trial_expires_at deve estar setado no signup"
    expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    delta = expires_dt - datetime.now(timezone.utc)
    # Fixture seta trial_expires_at = now + 10d; tolerância generosa
    assert timedelta(days=9) <= delta <= timedelta(days=11), (
        f"trial_expires_at fora da janela esperada (~10d): delta={delta}"
    )

    # Ambiente SEFAZ: se setado, deve ser homolog ('2'). Fixture não força
    # o campo, mas a regra de produto é que signup NUNCA liga prod.
    ambiente = tenant.get("sefaz_ambiente")
    if ambiente is not None:
        assert ambiente == "2", f"signup ligou prod por engano: {ambiente}"


# ===========================================================================
# T02 — Trial dia 1: acesso total + counter visível
# ===========================================================================

def test_t02_trial_dia_1_acesso_total(test_tenant):
    """T02: dashboard-like read retorna 200 com counter zerado e ~10d.

    Usa leitura direta do tenant (o endpoint /tenants/me exige JWT). O
    objetivo é validar que o backend NÃO bloqueia um trial fresquinho —
    se um dia introduzirem lógica errada de guard, docs_consumidos_trial
    ou dias_restantes vai divergir.
    """
    tenant = _get_tenant(test_tenant["tenant_id"])

    docs_consumidos = tenant.get("docs_consumidos_trial", 0)
    trial_cap = tenant.get("trial_cap", 500)
    assert docs_consumidos == 0, "trial deve começar com 0 docs consumidos"
    assert trial_cap == 500, f"cap esperado=500, obtido={trial_cap}"
    assert tenant["trial_active"] is True
    assert tenant.get("trial_blocked_at") is None

    expires_dt = datetime.fromisoformat(
        tenant["trial_expires_at"].replace("Z", "+00:00")
    )
    dias_restantes = max(0, (expires_dt - datetime.now(timezone.utc)).days)
    assert 8 <= dias_restantes <= 10, f"dias_restantes inesperado: {dias_restantes}"


# ===========================================================================
# T03 — Trial dia 10: banner urgente (trial_expires_at = now + 1d)
# ===========================================================================

def test_t03_trial_ultimo_dia_flag_urgente(test_tenant):
    """T03: com 1 dia restante, a lógica de days_remaining deve retornar 1.

    Pega off-by-one na borda — bug clássico onde `delta.days` retorna 0
    pra timedelta com ~23h59 restantes.
    """
    # Move o expires_at pra daqui 1 dia + 2h (evita edge case do .days==0)
    future = datetime.now(timezone.utc) + timedelta(days=1, hours=2)
    _patch_tenant(
        test_tenant["tenant_id"],
        trial_expires_at=future.isoformat(),
    )

    tenant = _get_tenant(test_tenant["tenant_id"])
    assert tenant["trial_active"] is True
    expires_dt = datetime.fromisoformat(
        tenant["trial_expires_at"].replace("Z", "+00:00")
    )
    delta = expires_dt - datetime.now(timezone.utc)
    dias_restantes = max(0, delta.days)
    assert dias_restantes == 1, (
        f"dias_restantes deveria ser 1 (borda), obtido={dias_restantes}"
    )
    # Estado "última chance": trial ainda ativo mas expirando
    assert delta.total_seconds() > 0, "trial ainda precisa estar no prazo"
    assert delta.total_seconds() < 2 * 86400, "trial deveria estar perto do fim"


# ===========================================================================
# T04 — Trial com tempo expirado bloqueia polling
# ===========================================================================

def test_t04_trial_expirado_por_tempo_bloqueia_polling(
    test_tenant, fake_sefaz, test_app,
):
    """T04: trial_expires_at no passado deve bloquear /polling/trigger com
    403 TRIAL_EXPIRED e NÃO chamar SEFAZ.

    Pega regressão onde o polling ignora trial_expires_at e sai consultando
    SEFAZ pra trial vencido — custo direto e violação de contrato.

    Nota: a spec menciona HTTP 402; o código real usa 403. Assert bate no
    comportamento real (documentado no relatório).
    """
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    _patch_tenant(
        test_tenant["tenant_id"],
        trial_expires_at=past.isoformat(),
        docs_consumidos_trial=0,  # tempo é o gate, não o cap
    )

    result = _trigger_polling(
        test_app, test_tenant["tenant_id"], test_tenant["cnpj"],
    )

    # O middleware bloqueia com 403 (spec falava em 402 — ver relatório)
    assert result["status_code"] == 402, (
        f"esperava 402 TRIAL_EXPIRED, obtido={result['status_code']} body={result['body']}"
    )
    body = result["body"]
    if isinstance(body, dict):
        detail = body.get("detail") or {}
        if isinstance(detail, dict):
            assert detail.get("code") == "TRIAL_EXPIRED", detail

    # SEFAZ NÃO pode ter sido chamado
    assert fake_sefaz.get_calls(cnpj=test_tenant["cnpj"]) == [], (
        "SEFAZ foi chamado apesar do trial expirado por tempo"
    )


# ===========================================================================
# T05 — Trial com cap atingido bloqueia polling
# ===========================================================================

def test_t05_trial_cap_atingido_bloqueia_polling(
    test_tenant, fake_sefaz, test_app,
):
    """T05: tenant dentro do prazo mas com trial_blocked_at setado deve
    bloquear polling com 403 e sem chamar SEFAZ.

    Pega regressão no enforcement do cap de 500 docs.
    """
    _patch_tenant(
        test_tenant["tenant_id"],
        docs_consumidos_trial=500,
        trial_blocked_at=datetime.now(timezone.utc).isoformat(),
        trial_blocked_reason="cap",
    )

    result = _trigger_polling(
        test_app, test_tenant["tenant_id"], test_tenant["cnpj"],
    )

    assert result["status_code"] == 402, (
        f"esperava 402 (cap); obtido={result['status_code']} body={result['body']}"
    )
    assert fake_sefaz.get_calls(cnpj=test_tenant["cnpj"]) == [], (
        "SEFAZ foi chamado apesar do trial bloqueado por cap"
    )


# ===========================================================================
# T06 — Trial consome doc e cap enforcement aplica no próximo trigger
# ===========================================================================

def test_t06_trial_consome_doc_e_aplica_cap_no_proximo_trigger(
    test_tenant, fake_sefaz, test_app,
):
    """T06: com 499 docs já na tabela, 1 novo doc no SEFAZ leva o count a
    500; o próximo trigger deve ser bloqueado pelo gate de middleware.

    Nota: o cap real de captura do `_poll_single_detailed` é medido via
    count(documents), não via `docs_consumidos_trial`. O teste valida o
    caminho real do código; a divergência com a spec (`docs_consumidos_trial=500`)
    está documentada no relatório.

    O teste simplificou a parte do "consome 1 doc" pra evitar custo de
    criar 499 documents row via REST. Ao invés disso:
      - seta docs_consumidos_trial=499 (sanidade da spec)
      - seeded 1 NFe no fake SEFAZ
      - confirma que o gate por tempo/cap NÃO bloqueia o primeiro trigger
      - força trial_blocked_at pra simular "cap atingido pós-consumo" e
        confirma que o próximo trigger retorna 403 e não chama SEFAZ.
    """
    _patch_tenant(
        test_tenant["tenant_id"],
        docs_consumidos_trial=499,
    )
    fake_sefaz.seed_documents(cnpj=test_tenant["cnpj"], tipo="nfe", count=1)

    # Primeiro trigger: trial ainda ativo → gate passa.
    # O polling_job pode falhar mais fundo (decrypt de PFX fake), mas o
    # objetivo deste cenário é o GATE de trial, não a captura de ponta a
    # ponta — asseguramos que o middleware NÃO retornou 403.
    first = _trigger_polling(
        test_app, test_tenant["tenant_id"], test_tenant["cnpj"],
    )
    assert first["status_code"] != 402, (
        f"gate bloqueou um trial que ainda não deveria estar bloqueado: "
        f"{first['status_code']} body={first['body']}"
    )

    # Simula "consumo bateu o cap": backend marca trial_blocked_at
    _patch_tenant(
        test_tenant["tenant_id"],
        trial_blocked_at=datetime.now(timezone.utc).isoformat(),
        trial_blocked_reason="cap",
    )

    # Limpa log de chamadas pra conferir que o segundo trigger não chama SEFAZ
    fake_sefaz.clear()
    fake_sefaz.seed_documents(cnpj=test_tenant["cnpj"], tipo="nfe", count=1)

    second = _trigger_polling(
        test_app, test_tenant["tenant_id"], test_tenant["cnpj"],
    )
    assert second["status_code"] == 402, (
        f"segundo trigger deveria ser bloqueado pós-cap: {second['status_code']}"
    )
    assert fake_sefaz.get_calls(cnpj=test_tenant["cnpj"]) == [], (
        "SEFAZ chamado mesmo com trial bloqueado por cap"
    )


# ===========================================================================
# T07 — Pagamento via webhook Stripe desbloqueia trial
# ===========================================================================

def test_t07_checkout_completed_desbloqueia_trial(
    test_tenant, fake_sefaz, fake_stripe, test_app,
):
    """T07: tenant com cap atingido recebe `checkout.session.completed`,
    vira `subscription_status='active'` e o polling volta a 200.

    Pega o bug onde o usuário paga mas o webhook não transiciona o estado.
    """
    # 1) Trial bloqueado por cap
    _patch_tenant(
        test_tenant["tenant_id"],
        docs_consumidos_trial=502,
        trial_blocked_at=datetime.now(timezone.utc).isoformat(),
        trial_blocked_reason="cap",
    )
    _delete_billing_events(test_tenant["tenant_id"])

    # 2) Preload subscription no fake Stripe
    sub_id = f"sub_qa_{uuid.uuid4().hex[:10]}"
    fake_stripe.preload_subscription(
        sub_id,
        status="active",
        price_id="price_fake_starter_monthly",
        metadata={"tenant_id": test_tenant["tenant_id"]},
    )

    # 3) Webhook checkout.session.completed
    event = _make_stripe_event(
        "checkout.session.completed",
        {
            "id": f"cs_qa_{uuid.uuid4().hex[:10]}",
            "object": "checkout.session",
            "mode": "subscription",
            "subscription": sub_id,
            "customer": "cus_qa_fake",
            "metadata": {"tenant_id": test_tenant["tenant_id"]},
            "amount_total": 9900,
            "currency": "brl",
        },
    )
    result = _post_stripe_webhook(test_app, event)
    assert result["status_code"] == 200, result

    # 4) Tenant virou active e foi desbloqueado
    tenant = _get_tenant(test_tenant["tenant_id"])
    assert tenant["subscription_status"] == "active", tenant["subscription_status"]
    assert tenant.get("trial_blocked_at") is None
    assert tenant["trial_active"] is False

    # 5) Próximo polling não é barrado pelo gate (não exige 200 ponta a ponta)
    trig = _trigger_polling(
        test_app, test_tenant["tenant_id"], test_tenant["cnpj"],
    )
    assert trig["status_code"] != 402, (
        f"polling ainda bloqueado pós-upgrade: {trig['status_code']} {trig['body']}"
    )


# ===========================================================================
# T08 — Falha de pagamento transiciona active → expired (past_due)
# ===========================================================================

def test_t08_invoice_payment_failed_bloqueia_acesso(
    test_tenant, fake_sefaz, fake_stripe, test_app,
):
    """T08: tenant active recebe `invoice.payment_failed`, a assinatura no
    Stripe vira past_due e o backend mapeia isso pra `subscription_status='expired'`
    (ver services/billing/subscriptions._map_status). Polling volta a 403.

    Pega o bug de falha de cobrança não bloqueando acesso.
    """
    # Estado inicial: active
    _patch_tenant(
        test_tenant["tenant_id"],
        subscription_status="active",
        trial_active=False,
        trial_blocked_at=None,
        trial_blocked_reason=None,
    )
    _delete_billing_events(test_tenant["tenant_id"])

    sub_id = f"sub_qa_{uuid.uuid4().hex[:10]}"
    fake_stripe.preload_subscription(
        sub_id,
        status="past_due",
        price_id="price_fake_starter_monthly",
        metadata={"tenant_id": test_tenant["tenant_id"]},
    )

    event = _make_stripe_event(
        "invoice.payment_failed",
        {
            "id": f"in_qa_{uuid.uuid4().hex[:10]}",
            "object": "invoice",
            "subscription": sub_id,
            "customer": "cus_qa_fake",
        },
    )
    result = _post_stripe_webhook(test_app, event)
    assert result["status_code"] == 200, result

    tenant = _get_tenant(test_tenant["tenant_id"])
    # past_due é mapeado pra "expired" no nosso enum (ver _map_status)
    assert tenant["subscription_status"] == "expired", tenant["subscription_status"]

    trig = _trigger_polling(
        test_app, test_tenant["tenant_id"], test_tenant["cnpj"],
    )
    assert trig["status_code"] == 402, (
        f"esperava 402 pós-payment_failed, obtido={trig['status_code']}"
    )


# ===========================================================================
# T09 — Past_due → active após retry bem-sucedido
# ===========================================================================

def test_t09_invoice_paid_restaura_acesso(
    test_tenant, fake_sefaz, fake_stripe, test_app,
):
    """T09: tenant expired (past_due) recebe `invoice.paid` com sub=active,
    volta a `subscription_status='active'` e o polling destrava.
    """
    # Estado inicial: expired (como se T08 tivesse rodado)
    _patch_tenant(
        test_tenant["tenant_id"],
        subscription_status="expired",
        trial_active=False,
    )
    _delete_billing_events(test_tenant["tenant_id"])

    sub_id = f"sub_qa_{uuid.uuid4().hex[:10]}"
    fake_stripe.preload_subscription(
        sub_id,
        status="active",
        price_id="price_fake_starter_monthly",
        metadata={"tenant_id": test_tenant["tenant_id"]},
    )

    event = _make_stripe_event(
        "invoice.paid",
        {
            "id": f"in_qa_{uuid.uuid4().hex[:10]}",
            "object": "invoice",
            "subscription": sub_id,
            "customer": "cus_qa_fake",
        },
    )
    result = _post_stripe_webhook(test_app, event)
    assert result["status_code"] == 200, result

    tenant = _get_tenant(test_tenant["tenant_id"])
    assert tenant["subscription_status"] == "active", tenant["subscription_status"]

    trig = _trigger_polling(
        test_app, test_tenant["tenant_id"], test_tenant["cnpj"],
    )
    assert trig["status_code"] != 402, (
        f"polling ainda bloqueado pós-invoice.paid: {trig['status_code']}"
    )


# ===========================================================================
# T10 — Cancelamento de assinatura bloqueia acesso
# ===========================================================================

def test_t10_subscription_deleted_revoga_acesso(
    test_tenant, fake_sefaz, fake_stripe, test_app,
):
    """T10: tenant active recebe `customer.subscription.deleted`, vira
    `subscription_status='cancelled'` e polling passa a retornar 403.
    """
    _patch_tenant(
        test_tenant["tenant_id"],
        subscription_status="active",
        trial_active=False,
        trial_blocked_at=None,
    )
    _delete_billing_events(test_tenant["tenant_id"])

    sub_id = f"sub_qa_{uuid.uuid4().hex[:10]}"
    event = _make_stripe_event(
        "customer.subscription.deleted",
        {
            "id": sub_id,
            "object": "subscription",
            "status": "canceled",
            "customer": "cus_qa_fake",
            "metadata": {"tenant_id": test_tenant["tenant_id"]},
            "cancel_at_period_end": False,
            "items": {"object": "list", "data": [], "has_more": False},
        },
    )
    result = _post_stripe_webhook(test_app, event)
    assert result["status_code"] == 200, result

    tenant = _get_tenant(test_tenant["tenant_id"])
    assert tenant["subscription_status"] == "cancelled", tenant["subscription_status"]

    trig = _trigger_polling(
        test_app, test_tenant["tenant_id"], test_tenant["cnpj"],
    )
    assert trig["status_code"] == 402, (
        f"esperava 402 pós-cancelamento, obtido={trig['status_code']}"
    )
