"""Fixtures pytest pra cenários E2E do DFeAxis — Fase 2.4.

Arquivo carregado automaticamente pelo pytest em `backend/tests/`. Expõe:

- `fake_sefaz`    — FakeSefazClient monkey-patchado nos sites de uso do
                    `services.sefaz_client.sefaz_client` (função scope).
- `fake_stripe`   — FakeStripeClient monkey-patchado em todos os módulos
                    que importam `get_stripe` (função scope).
- `test_tenant`   — cria tenant real no Supabase com prefixo `qa-<ts>` +
                    cert fake + api_key, retorna dict com credenciais,
                    cleanup no teardown.
- `test_app`      — FastAPI app (session scope). Não aciona lifespan
                    (TestClient não é usado como context manager), então
                    o scheduler NÃO sobe durante os testes.
- `sap_client`    — TestSAPClient já configurado com a api_key do
                    `test_tenant`, escopo função.

Decisão de design:
    Usamos Supabase REAL (REST API + service role key) em vez de um
    FakeSupabaseClient em memória. Razão: o produto usa tabelas reais
    + RLS + RPCs (increment_trial_docs, etc) e recriar tudo in-memory
    esconderia bugs que só aparecem contra o banco de verdade. A
    segurança vem do prefixo `qa-` no e-mail + CNPJ sintético +
    teardown estrito: só linhas criadas pela fixture são removidas.

Rodar com:
    ./venv/bin/python -m pytest backend/tests/ -v
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import pytest
import requests

# ---------------------------------------------------------------------------
# sys.path — garantir que `services`, `routers`, `scheduler`, `main`, etc
# sejam importáveis do diretório `backend/`, igual aos testes existentes.
# ---------------------------------------------------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
_REPO_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))
# Ordem: tests/ primeiro (pra achar pacote `fakes`), depois backend/ (pra
# achar `services`, `routers`, `scheduler`, `main`, etc).
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Load .env antes de qualquer import que dependa de config.Settings
# (services.billing.stripe_client, main, etc carregam no import-time).
try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore

    for _env_path in (
        os.path.join(_REPO_ROOT, ".env"),
        os.path.join(_BACKEND_DIR, ".env"),
    ):
        if os.path.isfile(_env_path):
            _load_dotenv(_env_path, override=False)
            break
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Supabase test-mode credentials — replicam o pattern de test_trial_e2e.py.
# Service role key embutida pra rodar sem env extra; pode ser sobrescrita via
# SUPABASE_SERVICE_ROLE_KEY. Em CI: setar a env var do ambiente de teste.
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL") or "https://kmiooqyasvhglszcioow.supabase.co"
SUPABASE_SR_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_SR_KEY:
    raise RuntimeError(
        "SUPABASE_SERVICE_ROLE_KEY env var is required for tests. "
        "Set it in .env or export it in your shell."
    )

_REST = f"{SUPABASE_URL}/rest/v1"
_AUTH_ADMIN = f"{SUPABASE_URL}/auth/v1/admin"
_HEADERS: dict[str, str] = {
    "apikey": SUPABASE_SR_KEY,
    "Authorization": f"Bearer {SUPABASE_SR_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Prefixo de segurança — NUNCA delete tenants que não batam com esse prefix.
QA_EMAIL_PREFIX = "qa-"
QA_EMAIL_DOMAIN = "test.dfeaxis.com.br"


def _is_qa_tenant(email: str | None, cnpj: str | None) -> bool:
    """Guard — só permite teardown de linhas criadas pela fixture."""
    if not email:
        return False
    if not email.startswith(QA_EMAIL_PREFIX):
        return False
    if QA_EMAIL_DOMAIN not in email:
        return False
    # CNPJ sintético deve começar com 99 (reservado pra testes)
    if cnpj and not cnpj.startswith("99"):
        return False
    return True


# ---------------------------------------------------------------------------
# fake_sefaz
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def fake_sefaz(monkeypatch) -> Iterator[Any]:
    """Instancia FakeSefazClient e patcha em todos os call sites.

    Call sites descobertos via grep:
      - services.sefaz_client.sefaz_client  (instância global do módulo)
      - scheduler.polling_job.sefaz_client  (alias do import `from services.sefaz_client import sefaz_client`)
      - routers.documents.sefaz_client       (idem — usado no /status dos tipos)
    """
    from fakes.sefaz_fake import FakeSefazClient  # type: ignore

    fake = FakeSefazClient()

    # Patch 1: a instância global no módulo de origem
    import services.sefaz_client as sefaz_module  # noqa: WPS433
    monkeypatch.setattr(sefaz_module, "sefaz_client", fake)

    # Patch 2: alias no scheduler (import bind-at-import-time)
    import scheduler.polling_job as polling_job_module  # noqa: WPS433
    monkeypatch.setattr(polling_job_module, "sefaz_client", fake)

    # Patch 3: alias no router de documentos (usa sefaz_client.check_status)
    import routers.documents as documents_router_module  # noqa: WPS433
    monkeypatch.setattr(documents_router_module, "sefaz_client", fake)

    try:
        yield fake
    finally:
        fake.clear()


# ---------------------------------------------------------------------------
# fake_manifestacao
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def fake_manifestacao(monkeypatch) -> Iterator[Any]:
    """Instancia FakeManifestacaoService e patcha em todos os call sites.

    Call sites:
      - services.manifestacao.manifestacao_service (instância global)
      - scheduler.polling_job.manifestacao_service (alias do import)
      - routers.manifestacao.manifestacao_service (alias do import)
    """
    from fakes.manifestacao_fake import FakeManifestacaoService  # type: ignore

    fake = FakeManifestacaoService()

    import services.manifestacao as manif_module  # noqa: WPS433
    monkeypatch.setattr(manif_module, "manifestacao_service", fake)

    import scheduler.polling_job as polling_module  # noqa: WPS433
    monkeypatch.setattr(polling_module, "manifestacao_service", fake)

    import routers.manifestacao as manif_router_module  # noqa: WPS433
    monkeypatch.setattr(manif_router_module, "manifestacao_service", fake)

    try:
        yield fake
    finally:
        fake.clear()


# ---------------------------------------------------------------------------
# fake_stripe
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def fake_stripe(monkeypatch) -> Iterator[Any]:
    """Instancia FakeStripeClient e patcha `get_stripe` em todos os módulos.

    Como cada arquivo faz `from .stripe_client import get_stripe`, o símbolo
    vira um binding local ao módulo importador. É necessário patchar TODOS
    os importers, além da fonte canônica.
    """
    from fakes.stripe_fake import FakeStripeClient  # type: ignore

    fake = FakeStripeClient()

    def _get_stripe_fake():
        return fake

    # Fonte canônica
    monkeypatch.setattr(
        "services.billing.stripe_client.get_stripe", _get_stripe_fake,
    )

    # Call sites que fazem `from .stripe_client import get_stripe` — o símbolo
    # vira um binding local ao módulo. Patchamos cada um.
    for module_path in (
        "services.billing.webhooks",
        "services.billing.checkout",
        "services.billing.customers",
        "services.billing.portal",
        "services.billing",  # o __init__.py re-exporta get_stripe no pkg
        "scheduler.monthly_overage_job",
    ):
        try:
            monkeypatch.setattr(f"{module_path}.get_stripe", _get_stripe_fake)
        except (AttributeError, ImportError):
            # O módulo pode não estar importado ainda (em alguns cenários de
            # teste isolado). O importlib abaixo força o import e retenta.
            import importlib

            try:
                importlib.import_module(module_path)
                monkeypatch.setattr(f"{module_path}.get_stripe", _get_stripe_fake)
            except Exception:
                # Se realmente não existe (ex: script deletado), ignora.
                pass

    try:
        yield fake
    finally:
        fake.clear()


# ---------------------------------------------------------------------------
# test_tenant
# ---------------------------------------------------------------------------

def _cnpj_dv(base12: str) -> str:
    """Calcula os 2 DVs mod-11 de um CNPJ (retorna string de 2 dígitos)."""
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s1 = sum(int(base12[i]) * w1[i] for i in range(12))
    d1 = 0 if (s1 % 11) < 2 else 11 - (s1 % 11)
    s2 = sum(int((base12 + str(d1))[i]) * w2[i] for i in range(13))
    d2 = 0 if (s2 % 11) < 2 else 11 - (s2 % 11)
    return f"{d1}{d2}"


def _qa_cnpj() -> str:
    """Gera um CNPJ sintético VÁLIDO (mod-11) com base que começa com '99'.

    O backend/DB valida mod-11 via `chk_certificates_cnpj`, então não dá pra
    usar CNPJ aleatório. Base '99' garante baixíssima probabilidade de colisão
    com CNPJ real (faixa raramente usada no registro da Receita).
    """
    # 12 dígitos: '99' + 6 derivados de ts (ms truncado) + '0001' (matriz)
    middle = f"{int(time.time() * 1000) % 1_000_000:06d}"
    base12 = f"99{middle}0001"  # 2+6+4 = 12
    return base12 + _cnpj_dv(base12)


def _create_auth_user(email: str, password: str) -> str:
    resp = requests.post(
        f"{_AUTH_ADMIN}/users",
        headers=_HEADERS,
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
        },
        timeout=20,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"create_auth_user failed: {resp.status_code} {resp.text}")
    return resp.json()["id"]


def _delete_auth_user(user_id: str) -> None:
    try:
        requests.delete(f"{_AUTH_ADMIN}/users/{user_id}", headers=_HEADERS, timeout=20)
    except requests.RequestException:
        pass


def _insert_tenant(user_id: str, email: str, cnpj: str) -> dict:
    trial_expires = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    payload = {
        "user_id": user_id,
        "company_name": f"QA Fixture {cnpj[:6]}",
        "email": email,
        "plan": "trial",
        "credits": 0,
        "subscription_status": "trial",
        "trial_active": True,
        "trial_cap": 500,
        "docs_consumidos_trial": 0,
        "trial_expires_at": trial_expires,
        "cnpj": cnpj,
        "phone": "11999999999",
    }
    resp = requests.post(f"{_REST}/tenants", headers=_HEADERS, json=payload, timeout=20)
    if resp.status_code != 201:
        raise RuntimeError(f"insert_tenant failed: {resp.status_code} {resp.text}")
    return resp.json()[0]


def _insert_certificate(tenant_id: str, cnpj: str) -> str:
    """Insere um certificate row fake. FakeSefazClient não valida cert — só
    precisamos satisfazer a FK + colunas NOT NULL."""
    valid_from = datetime.now(timezone.utc).isoformat()
    valid_until = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    payload = {
        "tenant_id": tenant_id,
        "cnpj": cnpj,
        "pfx_encrypted": "deadbeef" * 8,  # hex fake, 64 chars
        "pfx_iv": None,
        "pfx_password_encrypted": "fake-enc-pwd",
        "company_name": f"QA Cert {cnpj[:6]}",
        "valid_from": valid_from,
        "valid_until": valid_until,
        "is_active": True,
    }
    resp = requests.post(
        f"{_REST}/certificates", headers=_HEADERS, json=payload, timeout=20,
    )
    if resp.status_code != 201:
        raise RuntimeError(f"insert_certificate failed: {resp.status_code} {resp.text}")
    return resp.json()[0]["id"]


def _insert_api_key(tenant_id: str) -> tuple[str, str, str]:
    """Cria uma api_key fake. Retorna (raw_key, key_hash, id)."""
    raw_key = f"dfa_qa_{secrets.token_urlsafe(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    payload = {
        "tenant_id": tenant_id,
        "key_hash": key_hash,
        "key_prefix": raw_key[:8],
        "description": "qa-fixture",
        "is_active": True,
    }
    resp = requests.post(
        f"{_REST}/api_keys", headers=_HEADERS, json=payload, timeout=20,
    )
    if resp.status_code != 201:
        raise RuntimeError(f"insert_api_key failed: {resp.status_code} {resp.text}")
    return raw_key, key_hash, resp.json()[0]["id"]


def _delete_tenant_chain(tenant_id: str, email: str, cnpj: str, user_id: str) -> None:
    """Teardown estrito — só deleta se _is_qa_tenant retornar True."""
    if not _is_qa_tenant(email, cnpj):
        # Segurança: nunca deletar tenant que não foi criado pela fixture.
        return
    # Ordem: filhas primeiro (evitar violação de FK).
    try:
        requests.delete(
            f"{_REST}/api_keys",
            headers=_HEADERS,
            params={"tenant_id": f"eq.{tenant_id}"},
            timeout=20,
        )
    except requests.RequestException:
        pass
    try:
        requests.delete(
            f"{_REST}/certificates",
            headers=_HEADERS,
            params={"tenant_id": f"eq.{tenant_id}"},
            timeout=20,
        )
    except requests.RequestException:
        pass
    try:
        requests.delete(
            f"{_REST}/tenants",
            headers=_HEADERS,
            params={"id": f"eq.{tenant_id}"},
            timeout=20,
        )
    except requests.RequestException:
        pass
    if user_id:
        _delete_auth_user(user_id)


@pytest.fixture(scope="function")
def test_tenant() -> Iterator[dict]:
    """Cria tenant qa-* com cert fake + api_key, retorna credenciais.

    Teardown deleta tudo — protegido pelo guard `_is_qa_tenant`.
    """
    ts = int(time.time())
    rand = uuid.uuid4().hex[:8]
    email = f"{QA_EMAIL_PREFIX}{ts}-{rand}@{QA_EMAIL_DOMAIN}"
    password = f"QaPwd!{uuid.uuid4().hex[:12]}"
    cnpj = _qa_cnpj()

    user_id: str = ""
    tenant_id: str = ""
    cert_id: str = ""
    api_key_id: str = ""
    api_key_raw: str = ""
    api_key_hash: str = ""

    try:
        user_id = _create_auth_user(email, password)
        tenant = _insert_tenant(user_id, email, cnpj)
        tenant_id = tenant["id"]
        cert_id = _insert_certificate(tenant_id, cnpj)
        api_key_raw, api_key_hash, api_key_id = _insert_api_key(tenant_id)

        yield {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "email": email,
            "password": password,
            "cnpj": cnpj,
            "api_key_raw": api_key_raw,
            "api_key_hash": api_key_hash,
            "api_key_id": api_key_id,
            "certificate_id": cert_id,
        }
    finally:
        _delete_tenant_chain(tenant_id, email, cnpj, user_id)


# ---------------------------------------------------------------------------
# test_app — FastAPI app, session scope, sem acionar lifespan/scheduler
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_app():
    """FastAPI app importado uma vez por sessão.

    IMPORTANTE: não usamos `with TestClient(app):` porque isso dispara o
    lifespan (que sobe o APScheduler). Os testes chamam endpoints via
    TestClient comum, que não ativa startup/shutdown.
    """
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("ENVIRONMENT", "test")
    from main import app  # type: ignore  # noqa: WPS433
    return app


# ---------------------------------------------------------------------------
# sap_client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def sap_client(test_app, test_tenant) -> Iterator[Any]:
    """TestSAPClient instanciado com a api_key do tenant qa-*."""
    from fakes.sap_client import TestSAPClient  # type: ignore

    client = TestSAPClient(test_app, api_key=test_tenant["api_key_raw"])
    try:
        yield client
    finally:
        client.close()
