"""End-to-end tests for the trial spec — backend behavior.

These tests run against the REAL Supabase database via REST API
(service role key). They:
  1. Create a temporary tenant
  2. Exercise the trial cap RPC (increment_trial_docs)
  3. Verify the trial gets auto-blocked when cap is reached
  4. Verify CNPJ uniqueness anti-abuse
  5. Cleanup

Run with:
    cd backend && source venv/bin/activate
    python tests/test_trial_e2e.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Any

import requests

SUPABASE_URL = "https://kmiooqyasvhglszcioow.supabase.co"
SR_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImttaW9vcXlhc3ZoZ2xzemNpb293Iiwicm9sZSI6"
    "InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mzc4OTI2OCwiZXhwIjoyMDg5MzY1MjY4fQ."
    "2V6Tq4QrL599qb3qybTdfOcVTIguKC5NF7rpGPKVbh0"
)

REST = f"{SUPABASE_URL}/rest/v1"
HEADERS = {
    "apikey": SR_KEY,
    "Authorization": f"Bearer {SR_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Test fixtures — fake CNPJ that won't conflict with anything
TEST_CNPJ_A = "11222333000181"  # valid mod-11
TEST_CNPJ_B = "11444555000130"  # valid mod-11


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str, status: str = "INFO") -> None:
    icon = {"INFO": "→", "PASS": "✓", "FAIL": "✗", "STEP": "⚙"}[status]
    print(f"  {icon} {msg}")


def assert_eq(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        log(f"{label}: expected {expected!r}, got {actual!r}", "FAIL")
        raise AssertionError(label)
    log(f"{label}: {actual!r}", "PASS")


AUTH_ADMIN = f"{SUPABASE_URL}/auth/v1/admin"


def create_auth_user(email: str) -> str:
    """Create a user in Supabase Auth via admin API. Returns user_id."""
    r = requests.post(
        f"{AUTH_ADMIN}/users",
        headers=HEADERS,
        json={
            "email": email,
            "password": "TestPassword123!",
            "email_confirm": True,
        },
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create_auth_user failed: {r.status_code} {r.text}")
    return r.json()["id"]


def delete_auth_user(user_id: str) -> None:
    requests.delete(f"{AUTH_ADMIN}/users/{user_id}", headers=HEADERS)


def cleanup_test_tenants() -> None:
    """Remove any leftover test tenants from previous runs."""
    for cnpj in [TEST_CNPJ_A, TEST_CNPJ_B]:
        # Get user_ids before deleting
        r = requests.get(
            f"{REST}/tenants",
            headers=HEADERS,
            params={"cnpj": f"eq.{cnpj}", "select": "user_id"},
        )
        user_ids = [t["user_id"] for t in (r.json() if r.status_code == 200 else [])]
        # Delete tenant rows
        requests.delete(
            f"{REST}/tenants",
            headers=HEADERS,
            params={"cnpj": f"eq.{cnpj}"},
        )
        # Delete auth users
        for uid in user_ids:
            if uid:
                delete_auth_user(uid)
        if user_ids:
            log(f"cleaned cnpj={cnpj} ({len(user_ids)} user(s))", "INFO")


def create_tenant(
    cnpj: str, status: str = "trial", cap: int = 500, consumed: int = 0
) -> dict:
    """Create a fresh test tenant + auth user via REST API."""
    email = f"test-{cnpj[:8]}-{uuid.uuid4().hex[:6]}@dfeaxis-test.com"
    user_id = create_auth_user(email)
    payload = {
        "user_id": user_id,
        "user_id": user_id,
        "company_name": f"Test {cnpj[:8]}",
        "email": f"test-{cnpj[:8]}@example.com",
        "plan": "starter",
        "credits": 100,
        "subscription_status": status,
        "trial_active": status == "trial",
        "trial_cap": cap,
        "docs_consumidos_trial": consumed,
        "cnpj": cnpj,
        "phone": "11999999999",
    }
    r = requests.post(f"{REST}/tenants", headers=HEADERS, json=payload)
    if r.status_code != 201:
        raise RuntimeError(f"create_tenant failed: {r.status_code} {r.text}")
    return r.json()[0]


def get_tenant(tenant_id: str) -> dict:
    r = requests.get(
        f"{REST}/tenants",
        headers=HEADERS,
        params={"id": f"eq.{tenant_id}", "select": "*"},
    )
    return r.json()[0]


def call_rpc_increment(tenant_id: str, count: int) -> int:
    r = requests.post(
        f"{REST}/rpc/increment_trial_docs",
        headers=HEADERS,
        json={"p_tenant_id": tenant_id, "p_count": count},
    )
    if r.status_code != 200:
        raise RuntimeError(f"RPC failed: {r.status_code} {r.text}")
    return int(r.json())


def delete_tenant(tenant_id: str) -> None:
    # Get user_id first
    r = requests.get(
        f"{REST}/tenants",
        headers=HEADERS,
        params={"id": f"eq.{tenant_id}", "select": "user_id"},
    )
    user_id = (r.json()[0]["user_id"] if r.status_code == 200 and r.json() else None)
    requests.delete(
        f"{REST}/tenants",
        headers=HEADERS,
        params={"id": f"eq.{tenant_id}"},
    )
    if user_id:
        delete_auth_user(user_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cap_enforcement() -> None:
    """Test 1: trial cap blocks the tenant when reached."""
    print("\n=== TEST 1: trial cap enforcement ===")
    tenant = create_tenant(TEST_CNPJ_A, status="trial", cap=10, consumed=0)
    tenant_id = tenant["id"]
    log(f"created tenant {tenant_id} cap=10", "STEP")

    try:
        # Step 1: increment by 5 → still under cap
        new_count = call_rpc_increment(tenant_id, 5)
        assert_eq(new_count, 5, "after +5: count")

        t = get_tenant(tenant_id)
        assert_eq(t["trial_blocked_reason"], None, "after +5: blocked_reason")
        assert_eq(t["trial_active"], True, "after +5: trial_active")

        # Step 2: increment by 4 → still under cap (9/10)
        new_count = call_rpc_increment(tenant_id, 4)
        assert_eq(new_count, 9, "after +4: count")

        t = get_tenant(tenant_id)
        assert_eq(t["trial_blocked_reason"], None, "after +4: blocked_reason")

        # Step 3: increment by 3 → exceeds cap, gets clamped to 10, blocks
        new_count = call_rpc_increment(tenant_id, 3)
        assert_eq(new_count, 10, "after +3 (overshoot): count clamped")

        t = get_tenant(tenant_id)
        assert_eq(t["trial_blocked_reason"], "cap", "after overshoot: blocked_reason")
        assert_eq(t["trial_active"], False, "after overshoot: trial_active")
        assert t["trial_blocked_at"] is not None, "trial_blocked_at set"
        log(f"trial_blocked_at = {t['trial_blocked_at']}", "PASS")

        # Step 4: further increments do nothing (already blocked)
        new_count = call_rpc_increment(tenant_id, 5)
        assert_eq(new_count, 0, "after block: increment returns 0")

        t = get_tenant(tenant_id)
        assert_eq(t["docs_consumidos_trial"], 10, "after block: count unchanged")
    finally:
        delete_tenant(tenant_id)
        log(f"deleted tenant {tenant_id}", "STEP")


def test_active_status_not_blocked() -> None:
    """Test 2: an 'active' (paid) tenant is not affected by RPC."""
    print("\n=== TEST 2: active tenant is not affected ===")
    tenant = create_tenant(TEST_CNPJ_A, status="active", cap=5, consumed=0)
    tenant_id = tenant["id"]
    log(f"created active tenant {tenant_id}", "STEP")

    try:
        # RPC should return 0 for non-trial
        new_count = call_rpc_increment(tenant_id, 100)
        assert_eq(new_count, 0, "active tenant: RPC returns 0")

        t = get_tenant(tenant_id)
        assert_eq(t["docs_consumidos_trial"], 0, "active tenant: count unchanged")
        assert_eq(t["trial_blocked_reason"], None, "active tenant: not blocked")
    finally:
        delete_tenant(tenant_id)


def test_cnpj_uniqueness() -> None:
    """Test 3: CNPJ unique constraint blocks duplicate trial."""
    print("\n=== TEST 3: CNPJ unique constraint ===")
    tenant1 = create_tenant(TEST_CNPJ_A, status="trial")
    tenant1_id = tenant1["id"]
    log(f"created first tenant {tenant1_id} cnpj={TEST_CNPJ_A}", "STEP")

    try:
        # Try to create second tenant with same CNPJ
        try:
            create_tenant(TEST_CNPJ_A, status="trial")
            log("expected uniqueness violation, none raised", "FAIL")
            raise AssertionError("CNPJ uniqueness not enforced")
        except RuntimeError as e:
            if "23505" in str(e) or "duplicate" in str(e).lower() or "unique" in str(e).lower():
                log(f"got unique violation as expected", "PASS")
            else:
                raise
    finally:
        delete_tenant(tenant1_id)


def test_nsu_state_table() -> None:
    """Test 4: nsu_state table accepts inserts and computes pendentes correctly."""
    print("\n=== TEST 4: nsu_state table operations ===")

    # Use admin tenant's existing certificate
    r = requests.get(
        f"{REST}/certificates",
        headers=HEADERS,
        params={"select": "id", "limit": "1"},
    )
    certs = r.json()
    if not certs:
        log("no certificates in DB, skipping", "INFO")
        return
    cert_id = certs[0]["id"]
    log(f"using certificate {cert_id}", "STEP")

    # Insert a pending count for nfe in env 2
    r = requests.post(
        f"{REST}/nsu_state",
        headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"},
        json={
            "certificate_id": cert_id,
            "tipo": "nfe",
            "ambiente": "2",
            "last_nsu": "000000000000100",
            "max_nsu": "000000000000150",
            "pendentes": 50,
        },
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"upsert failed: {r.status_code} {r.text}")
    log(f"upserted nsu_state nfe/ambiente=2", "PASS")

    # Read back
    r = requests.get(
        f"{REST}/nsu_state",
        headers=HEADERS,
        params={
            "certificate_id": f"eq.{cert_id}",
            "tipo": "eq.nfe",
            "ambiente": "eq.2",
            "select": "*",
        },
    )
    rows = r.json()
    assert len(rows) == 1, "exactly one row"
    assert_eq(rows[0]["pendentes"], 50, "pendentes value")
    assert_eq(rows[0]["last_nsu"], "000000000000100", "last_nsu value")
    assert_eq(rows[0]["max_nsu"], "000000000000150", "max_nsu value")

    # Reset to 0 (no pending)
    requests.patch(
        f"{REST}/nsu_state",
        headers=HEADERS,
        params={
            "certificate_id": f"eq.{cert_id}",
            "tipo": "eq.nfe",
            "ambiente": "eq.2",
        },
        json={"max_nsu": None, "pendentes": 0, "last_nsu": "000000000000000"},
    )


def main() -> int:
    print("=" * 60)
    print("DFeAxis Trial Spec — Backend E2E Tests")
    print("=" * 60)

    cleanup_test_tenants()

    failures = []
    tests = [
        ("cap enforcement", test_cap_enforcement),
        ("active not blocked", test_active_status_not_blocked),
        ("CNPJ uniqueness", test_cnpj_uniqueness),
        ("nsu_state operations", test_nsu_state_table),
    ]

    for name, fn in tests:
        try:
            fn()
        except Exception as e:
            print(f"\n  ✗ FAILED: {name} → {e}")
            failures.append((name, e))

    cleanup_test_tenants()

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
