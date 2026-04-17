"""Unit tests para /health com dependências reais.

Roda standalone (sem pytest):

    cd backend && source venv/bin/activate
    python tests/test_health_check.py

Cobre 5 cenários com mocks:
  1. Todas as deps OK  → 200, status="ok"
  2. Supabase down     → 503, status="down"
  3. Stripe not_configured → 200, status="ok"
  4. Resend timeout    → 200, status="degraded"
  5. Timeout geral     → 503, status="down"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Evita que o scheduler de polling tente conectar ao Supabase no import de main.
os.environ.setdefault("SCHEDULER_DISABLED", "1")
os.environ.setdefault("ENVIRONMENT", "test")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from main import DependencyStatus, app  # noqa: E402


client = TestClient(app)


def _reset_config(monkey: dict) -> None:
    """Força settings para o cenário desejado."""
    from config import settings

    for k, v in monkey.items():
        setattr(settings, k, v)


async def _fake_ok_supabase():
    return DependencyStatus(name="supabase", status="ok", latency_ms=5)


async def _fake_down_supabase():
    return DependencyStatus(
        name="supabase", status="down", latency_ms=2000, error="Timeout > 2s"
    )


async def _fake_ok_stripe():
    return DependencyStatus(name="stripe", status="ok", latency_ms=10)


async def _fake_notconfig_stripe():
    return DependencyStatus(name="stripe", status="not_configured")


async def _fake_ok_resend():
    return DependencyStatus(name="resend", status="ok", latency_ms=20)


async def _fake_down_resend():
    return DependencyStatus(
        name="resend", status="down", latency_ms=2000, error="TimeoutException: "
    )


async def _slow_supabase():
    await asyncio.sleep(10)
    return DependencyStatus(name="supabase", status="ok", latency_ms=10000)


# --- Test cases ---

def test_all_ok() -> None:
    with patch.object(main, "_check_supabase", _fake_ok_supabase), \
         patch.object(main, "_check_stripe", _fake_ok_stripe), \
         patch.object(main, "_check_resend", _fake_ok_resend):
        resp = client.get("/health")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    body = resp.json()
    assert body["status"] == "ok", body
    names = {d["name"] for d in body["dependencies"]}
    assert names == {"supabase", "stripe", "resend", "sefaz"}
    sefaz = next(d for d in body["dependencies"] if d["name"] == "sefaz")
    assert sefaz["status"] == "skipped"
    print("  [ok] test_all_ok")


def test_supabase_down() -> None:
    with patch.object(main, "_check_supabase", _fake_down_supabase), \
         patch.object(main, "_check_stripe", _fake_ok_stripe), \
         patch.object(main, "_check_resend", _fake_ok_resend):
        resp = client.get("/health")
    assert resp.status_code == 503, f"expected 503, got {resp.status_code}"
    body = resp.json()
    assert body["status"] == "down", body
    sb = next(d for d in body["dependencies"] if d["name"] == "supabase")
    assert sb["status"] == "down"
    print("  [ok] test_supabase_down")


def test_stripe_not_configured() -> None:
    with patch.object(main, "_check_supabase", _fake_ok_supabase), \
         patch.object(main, "_check_stripe", _fake_notconfig_stripe), \
         patch.object(main, "_check_resend", _fake_ok_resend):
        resp = client.get("/health")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    body = resp.json()
    # not_configured não é "down" nem "degraded" — overall fica "ok".
    assert body["status"] == "ok", body
    st = next(d for d in body["dependencies"] if d["name"] == "stripe")
    assert st["status"] == "not_configured"
    print("  [ok] test_stripe_not_configured")


def test_resend_down_is_degraded() -> None:
    with patch.object(main, "_check_supabase", _fake_ok_supabase), \
         patch.object(main, "_check_stripe", _fake_ok_stripe), \
         patch.object(main, "_check_resend", _fake_down_resend):
        resp = client.get("/health")
    # Resend down é não-crítico → 200 overall degraded.
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    body = resp.json()
    assert body["status"] == "degraded", body
    rs = next(d for d in body["dependencies"] if d["name"] == "resend")
    assert rs["status"] == "down"
    print("  [ok] test_resend_down_is_degraded")


def test_overall_timeout() -> None:
    # Força timeout geral encurtando a janela via patch em asyncio.wait_for
    # (substitui a chamada na função por uma versão com timeout=0.01).
    real_wait_for = asyncio.wait_for

    async def fast_wait_for(awaitable, timeout):
        return await real_wait_for(awaitable, timeout=0.01)

    with patch.object(main, "_check_supabase", _slow_supabase), \
         patch.object(main, "_check_stripe", _fake_ok_stripe), \
         patch.object(main, "_check_resend", _fake_ok_resend), \
         patch("main.asyncio.wait_for", side_effect=fast_wait_for):
        resp = client.get("/health")
    assert resp.status_code == 503, f"expected 503, got {resp.status_code}"
    body = resp.json()
    assert body["status"] == "down", body
    hc = next(d for d in body["dependencies"] if d["name"] == "health_check")
    assert hc["status"] == "down"
    assert "Overall timeout" in (hc.get("error") or "")
    print("  [ok] test_overall_timeout")


def main_runner() -> int:
    print("Running test_health_check.py")
    failures = 0
    for fn in (
        test_all_ok,
        test_supabase_down,
        test_stripe_not_configured,
        test_resend_down_is_degraded,
        test_overall_timeout,
    ):
        try:
            fn()
        except AssertionError as exc:
            failures += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
        except Exception as exc:
            failures += 1
            print(f"  [ERROR] {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"Done: {5 - failures}/5 passing")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main_runner())
