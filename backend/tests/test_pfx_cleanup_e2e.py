"""End-to-end tests for the pfx cleanup job (LGPD inactivity).

Validates:
  1. Tenants in 'expired'/'cancelled' get pfx_inactive_since set
  2. Trial-blocked tenants also get pfx_inactive_since set
  3. Tenants returning to 'active' have pfx_inactive_since reset
  4. Certificates of tenants past retention get pfx purged

Run with:
    cd backend && source venv/bin/activate && python tests/test_pfx_cleanup_e2e.py
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

# Ensure the backend module path is loadable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SUPABASE_URL = os.environ.get("SUPABASE_URL") or "https://kmiooqyasvhglszcioow.supabase.co"
SR_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if not SR_KEY:
    sys.exit(
        "ERRO: variável SUPABASE_SERVICE_ROLE_KEY não definida. "
        "Exporte antes de rodar: `export SUPABASE_SERVICE_ROLE_KEY=...`"
    )

os.environ.setdefault("SUPABASE_URL", SUPABASE_URL)
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", SR_KEY)
os.environ.setdefault("SUPABASE_ANON_KEY", SR_KEY)
os.environ.setdefault("CERT_MASTER_SECRET", "this-is-a-test-master-secret-32chars-min")
os.environ.setdefault("JWT_SECRET", "this-is-a-test-jwt-secret-32chars-min")
os.environ.setdefault("RESEND_API_KEY", "")
REST = f"{SUPABASE_URL}/rest/v1"
AUTH_ADMIN = f"{SUPABASE_URL}/auth/v1/admin"

HEADERS = {
    "apikey": SR_KEY,
    "Authorization": f"Bearer {SR_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

TEST_CNPJ = "11222333000181"


def log(msg: str, status: str = "INFO") -> None:
    icon = {"INFO": "→", "PASS": "✓", "FAIL": "✗", "STEP": "⚙"}[status]
    print(f"  {icon} {msg}")


def assert_eq(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        log(f"{label}: expected {expected!r}, got {actual!r}", "FAIL")
        raise AssertionError(label)
    log(f"{label}: {actual!r}", "PASS")


def assert_truthy(value: Any, label: str) -> None:
    if not value:
        log(f"{label}: expected truthy, got {value!r}", "FAIL")
        raise AssertionError(label)
    log(f"{label}: {value!r}", "PASS")


def assert_falsy(value: Any, label: str) -> None:
    if value:
        log(f"{label}: expected falsy, got {value!r}", "FAIL")
        raise AssertionError(label)
    log(f"{label}: {value!r}", "PASS")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_auth_user(email: str) -> str:
    r = requests.post(
        f"{AUTH_ADMIN}/users",
        headers=HEADERS,
        json={"email": email, "password": "Test123!", "email_confirm": True},
    )
    r.raise_for_status()
    return r.json()["id"]


def delete_auth_user(user_id: str) -> None:
    requests.delete(f"{AUTH_ADMIN}/users/{user_id}", headers=HEADERS)


def create_test_tenant(
    cnpj: str,
    status: str,
    trial_blocked: bool = False,
    pfx_inactive_since: str | None = None,
) -> dict:
    email = f"pfx-test-{uuid.uuid4().hex[:8]}@dfeaxis-test.com"
    user_id = create_auth_user(email)
    payload = {
        "user_id": user_id,
        "company_name": "PFX Cleanup Test",
        "email": email,
        "plan": "starter",
        "credits": 100,
        "subscription_status": status,
        "trial_active": status == "trial" and not trial_blocked,
        "cnpj": cnpj,
    }
    if trial_blocked:
        payload["trial_blocked_at"] = datetime.now(timezone.utc).isoformat()
        payload["trial_blocked_reason"] = "cap"
    if pfx_inactive_since:
        payload["pfx_inactive_since"] = pfx_inactive_since

    r = requests.post(f"{REST}/tenants", headers=HEADERS, json=payload)
    if r.status_code != 201:
        raise RuntimeError(f"create tenant failed: {r.text}")
    return r.json()[0]


def create_test_certificate(tenant_id: str, cnpj: str) -> dict:
    payload = {
        "tenant_id": tenant_id,
        "cnpj": cnpj,
        "company_name": "PFX Cleanup Test Cert",
        "pfx_encrypted": "v2:deadbeef" + "00" * 60,
        "pfx_iv": None,
        "pfx_password_encrypted": "v2:cafebabe" + "00" * 60,
        "valid_from": "2026-01-01",
        "valid_until": "2027-01-01",
        "is_active": True,
    }
    r = requests.post(f"{REST}/certificates", headers=HEADERS, json=payload)
    if r.status_code != 201:
        raise RuntimeError(f"create cert failed: {r.text}")
    return r.json()[0]


def get_tenant(tenant_id: str) -> dict:
    r = requests.get(
        f"{REST}/tenants",
        headers=HEADERS,
        params={"id": f"eq.{tenant_id}", "select": "*"},
    )
    return r.json()[0]


def get_certificate(cert_id: str) -> dict:
    r = requests.get(
        f"{REST}/certificates",
        headers=HEADERS,
        params={"id": f"eq.{cert_id}", "select": "*"},
    )
    return r.json()[0]


def cleanup_test_data() -> None:
    r = requests.get(
        f"{REST}/tenants",
        headers=HEADERS,
        params={"cnpj": f"eq.{TEST_CNPJ}", "select": "user_id,id"},
    )
    rows = r.json() if r.status_code == 200 else []
    for row in rows:
        tid = row["id"]
        # Tabelas com FK para tenants — deletar antes
        for table in (
            "audit_log",
            "credit_transactions",
            "polling_log",
            "manifestacao_events",
            "documents",
            "api_keys",
            "certificates",
        ):
            requests.delete(
                f"{REST}/{table}",
                headers=HEADERS,
                params={"tenant_id": f"eq.{tid}"},
            )
    requests.delete(
        f"{REST}/tenants",
        headers=HEADERS,
        params={"cnpj": f"eq.{TEST_CNPJ}"},
    )
    for row in rows:
        if row.get("user_id"):
            delete_auth_user(row["user_id"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_marks_expired_tenant() -> None:
    print("\n=== TEST 1: marca tenant 'expired' como inativo ===")
    cleanup_test_data()
    tenant = create_test_tenant(TEST_CNPJ, status="expired")
    tenant_id = tenant["id"]
    log(f"created expired tenant {tenant_id}", "STEP")

    try:
        from scheduler.pfx_cleanup_job import _mark_inactive_tenants
        from db.supabase import get_supabase_client

        sb = get_supabase_client()
        marked = _mark_inactive_tenants(sb)
        assert_truthy(marked, f"marked count >= 1 (got {marked})")

        t = get_tenant(tenant_id)
        assert_truthy(t["pfx_inactive_since"], "pfx_inactive_since set")
    finally:
        cleanup_test_data()


def test_marks_blocked_trial() -> None:
    print("\n=== TEST 2: marca trial bloqueado por cap ===")
    cleanup_test_data()
    tenant = create_test_tenant(TEST_CNPJ, status="trial", trial_blocked=True)
    tenant_id = tenant["id"]
    log(f"created blocked trial tenant {tenant_id}", "STEP")

    try:
        from scheduler.pfx_cleanup_job import _mark_inactive_tenants
        from db.supabase import get_supabase_client

        sb = get_supabase_client()
        _mark_inactive_tenants(sb)

        t = get_tenant(tenant_id)
        assert_truthy(t["pfx_inactive_since"], "pfx_inactive_since set on blocked trial")
    finally:
        cleanup_test_data()


def test_resets_returning_tenant() -> None:
    print("\n=== TEST 3: reseta inactive_since quando volta active ===")
    cleanup_test_data()
    # Tenant active mas com inactive_since setado (cenário pós-pagamento)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    tenant = create_test_tenant(
        TEST_CNPJ, status="active", pfx_inactive_since=yesterday
    )
    tenant_id = tenant["id"]
    log(f"created active tenant with stale inactive_since", "STEP")

    try:
        from scheduler.pfx_cleanup_job import _reset_returning_tenants
        from db.supabase import get_supabase_client

        sb = get_supabase_client()
        reset_count = _reset_returning_tenants(sb)
        assert_truthy(reset_count, f"reset count >= 1 (got {reset_count})")

        t = get_tenant(tenant_id)
        assert_falsy(t["pfx_inactive_since"], "pfx_inactive_since cleared")
    finally:
        cleanup_test_data()


def test_purges_pfx_after_retention() -> None:
    print("\n=== TEST 4: purga .pfx após 30 dias de inatividade ===")
    cleanup_test_data()
    # Tenant expired há 31 dias
    long_ago = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    tenant = create_test_tenant(
        TEST_CNPJ, status="expired", pfx_inactive_since=long_ago
    )
    tenant_id = tenant["id"]
    cert = create_test_certificate(tenant_id, TEST_CNPJ)
    cert_id = cert["id"]
    log(f"created expired tenant + cert, inactive 31d ago", "STEP")

    try:
        from scheduler.pfx_cleanup_job import _purge_expired_pfx
        from db.supabase import get_supabase_client

        sb = get_supabase_client()
        purged = _purge_expired_pfx(sb)
        assert_truthy(purged, f"purged count >= 1 (got {purged})")

        c = get_certificate(cert_id)
        # pfx_encrypted é NOT NULL no schema — usamos string vazia ('' ou '\\x') como marcador
        pfx = c["pfx_encrypted"] or ""
        assert pfx in ("", "\\x"), f"pfx_encrypted not cleared: got {pfx!r}"
        log("pfx_encrypted cleared (empty)", "PASS")
        pwd = c["pfx_password_encrypted"] or ""
        assert pwd == "", f"pfx_password_encrypted not cleared: got {pwd!r}"
        log("pfx_password_encrypted cleared (empty)", "PASS")
        assert_eq(c["is_active"], False, "is_active = false")

        # Outros campos preservados
        assert_eq(c["cnpj"], TEST_CNPJ, "cnpj preservado")
        assert_truthy(c["company_name"], "company_name preservado")
    finally:
        cleanup_test_data()


def test_does_not_purge_within_retention() -> None:
    print("\n=== TEST 5: NÃO purga se ainda dentro dos 30 dias ===")
    cleanup_test_data()
    # Tenant expired há 5 dias — ainda dentro do período
    five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    tenant = create_test_tenant(
        TEST_CNPJ, status="expired", pfx_inactive_since=five_days_ago
    )
    tenant_id = tenant["id"]
    cert = create_test_certificate(tenant_id, TEST_CNPJ)
    cert_id = cert["id"]
    log(f"created expired tenant + cert, inactive 5d ago", "STEP")

    try:
        from scheduler.pfx_cleanup_job import _purge_expired_pfx
        from db.supabase import get_supabase_client

        sb = get_supabase_client()
        # Pode purgar OUTROS tenants residuais — então não checamos retorno absoluto,
        # só checamos que ESTE cert não foi tocado.
        _purge_expired_pfx(sb)

        c = get_certificate(cert_id)
        assert_truthy(c["pfx_encrypted"], "pfx_encrypted ainda presente")
        assert_truthy(c["pfx_password_encrypted"], "pfx_password_encrypted ainda presente")
        assert_eq(c["is_active"], True, "is_active ainda true")
    finally:
        cleanup_test_data()


def test_full_job_e2e() -> None:
    """Test 6: roda o job completo cleanup_inactive_pfx() e verifica execução."""
    print("\n=== TEST 6: job completo cleanup_inactive_pfx() ===")
    cleanup_test_data()
    tenant = create_test_tenant(TEST_CNPJ, status="expired")
    tenant_id = tenant["id"]
    log(f"created expired tenant {tenant_id}", "STEP")

    try:
        from scheduler.pfx_cleanup_job import cleanup_inactive_pfx

        result = cleanup_inactive_pfx()
        log(f"job result: {result}", "INFO")

        assert "marked" in result, "result has 'marked' key"
        assert "reset" in result, "result has 'reset' key"
        assert "purged" in result, "result has 'purged' key"
        assert "error" not in result, f"no error: {result.get('error')}"

        t = get_tenant(tenant_id)
        assert_truthy(t["pfx_inactive_since"], "tenant marcado pelo job")
    finally:
        cleanup_test_data()


def main() -> int:
    print("=" * 60)
    print("DFeAxis pfx_cleanup_job — Backend E2E Tests")
    print("=" * 60)

    cleanup_test_data()

    failures = []
    tests = [
        ("marks expired tenant", test_marks_expired_tenant),
        ("marks blocked trial", test_marks_blocked_trial),
        ("resets returning tenant", test_resets_returning_tenant),
        ("purges pfx after retention", test_purges_pfx_after_retention),
        ("preserves pfx within retention", test_does_not_purge_within_retention),
        ("full job e2e", test_full_job_e2e),
    ]

    for name, fn in tests:
        try:
            fn()
        except Exception as e:
            print(f"\n  ✗ FAILED: {name} → {e}")
            failures.append((name, e))

    cleanup_test_data()

    print()
    print("=" * 60)
    if failures:
        print(f"FAILED: {len(failures)}/{len(tests)} tests")
        for name, err in failures:
            print(f"  - {name}: {err}")
        return 1
    print(f"PASSED: {len(tests)}/{len(tests)} tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
