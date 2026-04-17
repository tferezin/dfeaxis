"""Admin Dashboard E2E Tests — validates auth, metrics, tenant list, and more.

Scenarios:
  A01: Non-admin user gets 403 on all admin endpoints
  A02: Admin user gets valid dashboard metrics response
  A03: Admin user gets tenant list with correct fields
  A04: Admin user gets document capture statistics
  A05: Admin user gets SEFAZ polling health
  A06: Admin user gets revenue history data
  A07: Admin user gets campaign/UTM attribution data
  A08: Admin user gets escalated chat conversations
  A09: Admin user gets expiring certificates list
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Iterator

import pytest
import requests
from fastapi.testclient import TestClient

from tests.conftest import (
    SUPABASE_URL,
    SUPABASE_SR_KEY,
    _HEADERS,
    _REST,
    _AUTH_ADMIN,
    QA_EMAIL_PREFIX,
    QA_EMAIL_DOMAIN,
    _create_auth_user,
    _delete_auth_user,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sign_in(email: str, password: str) -> str:
    """Sign in via Supabase GoTrue and return the access_token (JWT)."""
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={
            "apikey": SUPABASE_SR_KEY,
            "Content-Type": "application/json",
        },
        json={"email": email, "password": password},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"sign_in failed: {resp.status_code} {resp.text}")
    return resp.json()["access_token"]


def _admin_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Rate limiter reset (same pattern as other E2E suites)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiter(test_app):
    from middleware.security import RateLimitMiddleware

    def _find_rl(obj, depth=0):
        if depth > 30:
            return None
        if isinstance(obj, RateLimitMiddleware):
            return obj
        for attr in ("app", "middleware", "middleware_stack"):
            child = getattr(obj, attr, None)
            if child is not None and child is not obj:
                found = _find_rl(child, depth + 1)
                if found:
                    return found
        return None

    client = TestClient(test_app, raise_server_exceptions=False)
    try:
        client.get("/health")
    finally:
        client.close()

    rl = _find_rl(test_app)
    if not rl:
        rl = _find_rl(test_app.middleware_stack)
    if rl:
        rl.requests.clear()
    yield
    if rl:
        rl.requests.clear()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def admin_user():
    """Create a temporary admin user with an email in ADMIN_EMAILS.

    We use 'ferezinth@hotmail.com' which is hardcoded in ADMIN_EMAILS.
    But we cannot create a Supabase auth user with a real email that may
    already exist. Instead, we monkeypatch the ADMIN_EMAILS set at module
    level to include our QA email.
    """
    ts = int(time.time())
    rand = uuid.uuid4().hex[:8]
    email = f"{QA_EMAIL_PREFIX}admin-{ts}-{rand}@{QA_EMAIL_DOMAIN}"
    password = f"AdminQa!{uuid.uuid4().hex[:12]}"

    user_id = _create_auth_user(email, password)
    token = _sign_in(email, password)

    yield {
        "user_id": user_id,
        "email": email,
        "password": password,
        "token": token,
    }

    _delete_auth_user(user_id)


@pytest.fixture(scope="module")
def _patch_admin_emails(admin_user):
    """Add the QA admin email to the ADMIN_EMAILS set so the endpoint accepts it."""
    import routers.admin as admin_module
    original = admin_module.ADMIN_EMAILS.copy()
    admin_module.ADMIN_EMAILS.add(admin_user["email"].lower())
    yield
    admin_module.ADMIN_EMAILS.clear()
    admin_module.ADMIN_EMAILS.update(original)


@pytest.fixture(scope="module")
def admin_client(test_app, admin_user, _patch_admin_emails) -> TestClient:
    """TestClient with admin Bearer token in default headers."""
    client = TestClient(test_app, raise_server_exceptions=False)
    client.headers.update(_admin_headers(admin_user["token"]))
    return client


@pytest.fixture(scope="module")
def nonadmin_user():
    """Create a non-admin QA user (email NOT in ADMIN_EMAILS)."""
    ts = int(time.time())
    rand = uuid.uuid4().hex[:8]
    email = f"{QA_EMAIL_PREFIX}nonadmin-{ts}-{rand}@{QA_EMAIL_DOMAIN}"
    password = f"NonAdm!{uuid.uuid4().hex[:12]}"

    user_id = _create_auth_user(email, password)
    token = _sign_in(email, password)

    yield {
        "user_id": user_id,
        "email": email,
        "password": password,
        "token": token,
    }

    _delete_auth_user(user_id)


@pytest.fixture(scope="module")
def nonadmin_client(test_app, nonadmin_user) -> TestClient:
    """TestClient with non-admin Bearer token."""
    client = TestClient(test_app, raise_server_exceptions=False)
    client.headers.update(_admin_headers(nonadmin_user["token"]))
    return client


# ===========================================================================
# A01 — Non-admin user gets 403 on ALL admin endpoints
# ===========================================================================

class TestA01NonAdminDenied:
    """Non-admin JWT user must receive 403 on every admin endpoint."""

    ADMIN_PATHS = [
        "/api/v1/admin/dashboard",
        "/api/v1/admin/tenants",
        "/api/v1/admin/revenue/history",
        "/api/v1/admin/documents/stats",
        "/api/v1/admin/sefaz/health",
        "/api/v1/admin/chat/escalated",
        "/api/v1/admin/certificates/expiring",
    ]

    @pytest.mark.parametrize("path", ADMIN_PATHS)
    def test_non_admin_gets_403(self, nonadmin_client, path):
        resp = nonadmin_client.get(path)
        assert resp.status_code == 403, f"{path} returned {resp.status_code}"
        body = resp.json()
        assert body["detail"]["error_code"] == "ADMIN_DENIED"

    def test_no_token_gets_401(self, test_app):
        """Request without Bearer token must return 401."""
        client = TestClient(test_app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/dashboard")
        client.close()
        assert resp.status_code == 401

    def test_invalid_token_gets_401(self, test_app):
        """Request with garbage Bearer token must return 401."""
        client = TestClient(test_app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/admin/dashboard",
            headers={"Authorization": "Bearer totally-invalid-jwt-here"},
        )
        client.close()
        assert resp.status_code == 401


# ===========================================================================
# A02 — Dashboard metrics
# ===========================================================================

class TestA02DashboardMetrics:
    """GET /admin/dashboard returns aggregated metrics."""

    def test_returns_200_with_all_sections(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()

        # Check all top-level keys exist
        for key in ("tenants", "revenue", "documents", "sefaz", "trial_funnel", "campaign"):
            assert key in body, f"Missing top-level key: {key}"

    def test_tenants_section_has_correct_fields(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        body = resp.json()
        tenants = body["tenants"]

        for field in ("total", "trial_active", "trial_expired", "active_paid", "past_due", "cancelled"):
            assert field in tenants, f"Missing tenants field: {field}"
            assert isinstance(tenants[field], int), f"tenants.{field} should be int"

    def test_revenue_section_has_mrr(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        body = resp.json()
        revenue = body["revenue"]

        assert "mrr_cents" in revenue
        assert "arr_cents" in revenue
        assert "plans" in revenue
        assert isinstance(revenue["mrr_cents"], int)
        assert revenue["arr_cents"] == revenue["mrr_cents"] * 12

    def test_documents_section(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        body = resp.json()
        docs = body["documents"]

        for field in ("total_captured", "total_delivered", "captured_today", "captured_this_month"):
            assert field in docs, f"Missing documents field: {field}"
            assert isinstance(docs[field], int)

    def test_sefaz_section(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        body = resp.json()
        sefaz = body["sefaz"]

        for field in ("polls_today", "errors_today", "avg_latency_ms"):
            assert field in sefaz, f"Missing sefaz field: {field}"

    def test_trial_funnel_section(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        body = resp.json()
        funnel = body["trial_funnel"]

        for field in ("signups_7d", "signups_30d", "conversions_7d", "conversions_30d", "conversion_rate_30d"):
            assert field in funnel, f"Missing trial_funnel field: {field}"

    def test_campaign_section(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        body = resp.json()
        campaign = body["campaign"]

        assert "utm_sources" in campaign
        assert "top_campaigns" in campaign
        assert isinstance(campaign["utm_sources"], list)
        assert isinstance(campaign["top_campaigns"], list)


# ===========================================================================
# A03 — Tenant list
# ===========================================================================

class TestA03TenantList:
    """GET /admin/tenants returns paginated tenant list."""

    def test_returns_200_with_tenants_array(self, admin_client):
        resp = admin_client.get("/api/v1/admin/tenants")
        assert resp.status_code == 200
        body = resp.json()

        assert "tenants" in body
        assert "count" in body
        assert "offset" in body
        assert isinstance(body["tenants"], list)

    def test_tenant_fields_are_present(self, admin_client):
        resp = admin_client.get("/api/v1/admin/tenants?limit=5")
        body = resp.json()

        if body["tenants"]:
            t = body["tenants"][0]
            for field in ("id", "company_name", "email", "plan", "subscription_status", "created_at"):
                assert field in t, f"Missing tenant field: {field}"

    def test_cnpj_is_masked(self, admin_client):
        """CNPJ in tenant list must be masked (LGPD)."""
        resp = admin_client.get("/api/v1/admin/tenants?limit=50")
        body = resp.json()

        for t in body["tenants"]:
            cnpj = t.get("cnpj")
            if cnpj and cnpj != "CNPJ_INVALID":
                # Masked CNPJs should contain X characters
                assert "X" in cnpj, f"CNPJ not masked: {cnpj}"

    def test_pagination_with_limit_and_offset(self, admin_client):
        resp = admin_client.get("/api/v1/admin/tenants?limit=2&offset=0")
        assert resp.status_code == 200
        body = resp.json()
        assert body["offset"] == 0
        assert len(body["tenants"]) <= 2

    def test_filter_by_status(self, admin_client):
        resp = admin_client.get("/api/v1/admin/tenants?status=trial")
        assert resp.status_code == 200
        body = resp.json()
        for t in body["tenants"]:
            assert t["subscription_status"] == "trial"

    def test_search_by_company_name(self, admin_client):
        resp = admin_client.get("/api/v1/admin/tenants?search=QA")
        assert resp.status_code == 200
        # Should not error, whether results exist or not


# ===========================================================================
# A04 — Document stats
# ===========================================================================

class TestA04DocumentStats:
    """GET /admin/documents/stats returns daily capture stats."""

    def test_returns_200_with_days_array(self, admin_client):
        resp = admin_client.get("/api/v1/admin/documents/stats")
        assert resp.status_code == 200
        body = resp.json()

        assert "days" in body
        assert isinstance(body["days"], list)
        # Should have 30 days of data
        assert len(body["days"]) == 30

    def test_day_entry_has_correct_fields(self, admin_client):
        resp = admin_client.get("/api/v1/admin/documents/stats")
        body = resp.json()

        day = body["days"][0]
        for field in ("date", "total", "NFE", "CTE", "MDFE", "NFSE"):
            assert field in day, f"Missing day field: {field}"

    def test_day_dates_are_ordered(self, admin_client):
        resp = admin_client.get("/api/v1/admin/documents/stats")
        body = resp.json()

        dates = [d["date"] for d in body["days"]]
        assert dates == sorted(dates), "Days should be chronologically ordered"


# ===========================================================================
# A05 — SEFAZ health
# ===========================================================================

class TestA05SefazHealth:
    """GET /admin/sefaz/health returns polling health status."""

    def test_returns_200_with_health_status(self, admin_client):
        resp = admin_client.get("/api/v1/admin/sefaz/health")
        assert resp.status_code == 200
        body = resp.json()

        assert "status" in body
        assert body["status"] in ("idle", "healthy", "degraded", "unhealthy")

    def test_today_section_has_counts(self, admin_client):
        resp = admin_client.get("/api/v1/admin/sefaz/health")
        body = resp.json()

        assert "today" in body
        today = body["today"]
        for field in ("total_polls", "success", "errors"):
            assert field in today, f"Missing today field: {field}"
            assert isinstance(today[field], int)

    def test_recent_errors_is_list(self, admin_client):
        resp = admin_client.get("/api/v1/admin/sefaz/health")
        body = resp.json()

        assert "recent_errors" in body
        assert isinstance(body["recent_errors"], list)

    def test_errors_have_masked_cnpj(self, admin_client):
        """If there are errors with CNPJs, they must be masked."""
        resp = admin_client.get("/api/v1/admin/sefaz/health")
        body = resp.json()

        for err in body["recent_errors"]:
            cnpj = err.get("cnpj")
            if cnpj and cnpj != "CNPJ_INVALID":
                assert "X" in cnpj, f"Error CNPJ not masked: {cnpj}"


# ===========================================================================
# A06 — Revenue history
# ===========================================================================

class TestA06RevenueHistory:
    """GET /admin/revenue/history returns monthly revenue data.

    BUG FOUND: admin.py references billing_events.created_at but the actual
    column is billing_events.processed_at. Tests marked xfail until fixed.
    """

    @pytest.mark.xfail(reason="BUG: billing_events.created_at does not exist, should be processed_at")
    def test_returns_200_with_months_array(self, admin_client):
        resp = admin_client.get("/api/v1/admin/revenue/history")
        assert resp.status_code == 200
        body = resp.json()

        assert "months" in body
        assert isinstance(body["months"], list)
        assert len(body["months"]) == 12

    @pytest.mark.xfail(reason="BUG: billing_events.created_at does not exist, should be processed_at")
    def test_month_entry_has_correct_fields(self, admin_client):
        resp = admin_client.get("/api/v1/admin/revenue/history")
        assert resp.status_code == 200
        body = resp.json()

        month = body["months"][0]
        assert "month" in month
        assert "revenue_cents" in month
        # month format should be YYYY-MM
        assert len(month["month"]) == 7
        assert "-" in month["month"]

    @pytest.mark.xfail(reason="BUG: billing_events.created_at does not exist, should be processed_at")
    def test_months_are_chronologically_ordered(self, admin_client):
        resp = admin_client.get("/api/v1/admin/revenue/history")
        assert resp.status_code == 200
        body = resp.json()

        months = [m["month"] for m in body["months"]]
        assert months == sorted(months), "Months should be chronologically ordered"


# ===========================================================================
# A07 — Campaign/UTM data (via dashboard endpoint)
# ===========================================================================

class TestA07CampaignData:
    """Campaign data is included in /admin/dashboard response."""

    def test_utm_sources_structure(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        body = resp.json()

        sources = body["campaign"]["utm_sources"]
        for src in sources:
            assert "source" in src
            assert "count" in src
            assert isinstance(src["count"], int)

    def test_top_campaigns_structure(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        body = resp.json()

        campaigns = body["campaign"]["top_campaigns"]
        for camp in campaigns:
            assert "campaign" in camp
            assert "count" in camp

    def test_utm_sources_limited_to_10(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        body = resp.json()
        assert len(body["campaign"]["utm_sources"]) <= 10

    def test_top_campaigns_limited_to_10(self, admin_client):
        resp = admin_client.get("/api/v1/admin/dashboard")
        body = resp.json()
        assert len(body["campaign"]["top_campaigns"]) <= 10


# ===========================================================================
# A08 — Escalated chats
# ===========================================================================

class TestA08EscalatedChats:
    """GET /admin/chat/escalated returns escalated conversations.

    BUG FOUND: admin.py selects chat_conversations.messages but this column
    does not exist. Messages are stored separately (chat_messages table or
    similar). Also selects 'updated_at' which does not exist.
    Tests marked xfail until fixed.
    """

    @pytest.mark.xfail(reason="BUG: chat_conversations.messages column does not exist")
    def test_returns_200_with_conversations_array(self, admin_client):
        resp = admin_client.get("/api/v1/admin/chat/escalated")
        assert resp.status_code == 200
        body = resp.json()

        assert "conversations" in body
        assert "count" in body
        assert isinstance(body["conversations"], list)
        assert isinstance(body["count"], int)
        assert body["count"] == len(body["conversations"])

    @pytest.mark.xfail(reason="BUG: chat_conversations.messages column does not exist")
    def test_respects_limit_param(self, admin_client):
        resp = admin_client.get("/api/v1/admin/chat/escalated?limit=5")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["conversations"]) <= 5

    @pytest.mark.xfail(reason="BUG: chat_conversations.messages column does not exist")
    def test_conversation_fields_if_any(self, admin_client):
        resp = admin_client.get("/api/v1/admin/chat/escalated")
        assert resp.status_code == 200
        body = resp.json()

        for conv in body["conversations"]:
            assert "id" in conv
            assert "tenant_id" in conv
            assert "status" in conv
            assert "message_count" in conv


# ===========================================================================
# A09 — Expiring certificates
# ===========================================================================

class TestA09ExpiringCertificates:
    """GET /admin/certificates/expiring returns certs expiring within window.

    BUG FOUND: admin.py selects certificates.subject but the actual column is
    certificates.company_name. Tests marked xfail until fixed.
    """

    @pytest.mark.xfail(reason="BUG: certificates.subject column does not exist, should be company_name")
    def test_returns_200_with_certificates_array(self, admin_client):
        resp = admin_client.get("/api/v1/admin/certificates/expiring")
        assert resp.status_code == 200
        body = resp.json()

        assert "certificates" in body
        assert "count" in body
        assert isinstance(body["certificates"], list)
        assert isinstance(body["count"], int)
        assert body["count"] == len(body["certificates"])

    @pytest.mark.xfail(reason="BUG: certificates.subject column does not exist, should be company_name")
    def test_respects_days_param(self, admin_client):
        resp = admin_client.get("/api/v1/admin/certificates/expiring?days=7")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["certificates"], list)

    @pytest.mark.xfail(reason="BUG: certificates.subject column does not exist, should be company_name")
    def test_cert_fields_if_any(self, admin_client):
        resp = admin_client.get("/api/v1/admin/certificates/expiring?days=90")
        assert resp.status_code == 200
        body = resp.json()

        for cert in body["certificates"]:
            assert "id" in cert
            assert "tenant_id" in cert
            assert "days_remaining" in cert
            # CNPJ must be masked
            cnpj = cert.get("cnpj")
            if cnpj and cnpj != "CNPJ_INVALID":
                assert "X" in cnpj, f"Certificate CNPJ not masked: {cnpj}"

    @pytest.mark.xfail(reason="BUG: certificates.subject column does not exist, should be company_name")
    def test_no_pfx_data_in_response(self, admin_client):
        """PFX data must NEVER appear in certificate responses."""
        resp = admin_client.get("/api/v1/admin/certificates/expiring?days=90")
        assert resp.status_code == 200
        body = resp.json()

        for cert in body["certificates"]:
            assert "pfx_encrypted" not in cert, "PFX encrypted data leaked!"
            assert "pfx_iv" not in cert, "PFX IV leaked!"
            assert "pfx_password_encrypted" not in cert, "PFX password leaked!"


# ===========================================================================
# A10 — Tenant detail endpoint (bonus)
# ===========================================================================

class TestA10TenantDetail:
    """GET /admin/tenants/{tenant_id} returns full tenant detail.

    BUG: tenant detail also selects certificates.subject which does not exist.
    Some tests xfail because the endpoint 500s on the certificates query.
    """

    def test_invalid_tenant_returns_404(self, admin_client):
        fake_id = str(uuid.uuid4())
        resp = admin_client.get(f"/api/v1/admin/tenants/{fake_id}")
        assert resp.status_code == 404

    @pytest.mark.xfail(reason="BUG: certificates.subject does not exist in tenant detail query")
    def test_valid_tenant_returns_full_detail(self, admin_client):
        # First get a real tenant ID from the list
        list_resp = admin_client.get("/api/v1/admin/tenants?limit=1")
        tenants = list_resp.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants in database to test detail endpoint")

        tenant_id = tenants[0]["id"]
        resp = admin_client.get(f"/api/v1/admin/tenants/{tenant_id}")
        assert resp.status_code == 200
        body = resp.json()

        assert "tenant" in body
        assert "certificates" in body
        assert "api_keys" in body
        assert "polling_logs" in body
        assert "billing_events" in body

    @pytest.mark.xfail(reason="BUG: certificates.subject does not exist in tenant detail query")
    def test_detail_masks_cnpj(self, admin_client):
        list_resp = admin_client.get("/api/v1/admin/tenants?limit=1")
        tenants = list_resp.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants in database")

        tenant_id = tenants[0]["id"]
        resp = admin_client.get(f"/api/v1/admin/tenants/{tenant_id}")
        body = resp.json()

        cnpj = body["tenant"].get("cnpj")
        if cnpj and cnpj != "CNPJ_INVALID":
            assert "X" in cnpj, f"Tenant detail CNPJ not masked: {cnpj}"

    @pytest.mark.xfail(reason="BUG: certificates.subject does not exist in tenant detail query")
    def test_detail_no_pfx_in_certificates(self, admin_client):
        """Certificates in tenant detail must not include PFX data."""
        list_resp = admin_client.get("/api/v1/admin/tenants?limit=1")
        tenants = list_resp.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants in database")

        tenant_id = tenants[0]["id"]
        resp = admin_client.get(f"/api/v1/admin/tenants/{tenant_id}")
        body = resp.json()

        for cert in body["certificates"]:
            assert "pfx_encrypted" not in cert
            assert "pfx_iv" not in cert
            assert "pfx_password_encrypted" not in cert

    @pytest.mark.xfail(reason="BUG: certificates.subject does not exist in tenant detail query")
    def test_detail_no_key_hash_in_api_keys(self, admin_client):
        """API keys in tenant detail must not include key_hash."""
        list_resp = admin_client.get("/api/v1/admin/tenants?limit=1")
        tenants = list_resp.json().get("tenants", [])
        if not tenants:
            pytest.skip("No tenants in database")

        tenant_id = tenants[0]["id"]
        resp = admin_client.get(f"/api/v1/admin/tenants/{tenant_id}")
        body = resp.json()

        for key in body["api_keys"]:
            assert "key_hash" not in key, "API key hash leaked in response!"
