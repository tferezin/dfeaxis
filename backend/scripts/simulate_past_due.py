#!/usr/bin/env python3
"""Simula past_due num tenant pra testar o fluxo de dunning/bloqueio.

Seta past_due_since na data escolhida (default 7 dias atras, ja dentro
do bloqueio 5+5) + atualiza subscription_status='past_due'. Pra destravar,
rode com --clear.

Uso:
    # Bloqueia tenant (past_due_since = 7 dias atras)
    python simulate_past_due.py --email cliente@teste.com --days-ago 7

    # Simula durante tolerancia (3 dias — ainda nao bloqueou)
    python simulate_past_due.py --email cliente@teste.com --days-ago 3

    # Limpa past_due_since (volta pro estado ativo)
    python simulate_past_due.py --email cliente@teste.com --clear

Requer env var SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY setadas.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


def _supabase_request(
    method: str, path: str, body: dict | None = None
) -> list[dict]:
    """HTTP request pro Supabase REST API usando service role."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        sys.exit(
            "ERRO: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY precisam estar "
            "setadas no env."
        )

    full_url = f"{url}/rest/v1/{path.lstrip('/')}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        full_url,
        data=data,
        method=method,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return []
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="ignore")
        sys.exit(f"ERRO HTTP {e.code}: {body_text}")


def find_tenant(email: str | None, tenant_id: str | None) -> dict:
    if tenant_id:
        path = f"tenants?id=eq.{tenant_id}&select=id,email,subscription_status,past_due_since"
    elif email:
        path = f"tenants?email=eq.{email}&select=id,email,subscription_status,past_due_since"
    else:
        sys.exit("Precisa passar --email ou --tenant-id")

    result = _supabase_request("GET", path)
    if not result:
        sys.exit(f"Tenant nao encontrado: email={email} id={tenant_id}")
    return result[0]


def set_past_due(tenant_id: str, days_ago: int) -> dict:
    past_due_since = datetime.now(timezone.utc) - timedelta(days=days_ago)
    body = {
        "subscription_status": "past_due",
        "past_due_since": past_due_since.isoformat(),
    }
    result = _supabase_request(
        "PATCH", f"tenants?id=eq.{tenant_id}", body
    )
    return result[0] if result else {}


def clear_past_due(tenant_id: str) -> dict:
    body = {
        "subscription_status": "active",
        "past_due_since": None,
    }
    result = _supabase_request(
        "PATCH", f"tenants?id=eq.{tenant_id}", body
    )
    return result[0] if result else {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", help="Email do tenant alvo")
    parser.add_argument("--tenant-id", help="UUID do tenant alvo")
    parser.add_argument(
        "--days-ago", type=int, default=7,
        help="Quantos dias atras colocar past_due_since (default: 7 = bloqueado)"
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Limpa past_due_since e volta subscription_status='active'"
    )
    args = parser.parse_args()

    tenant = find_tenant(args.email, args.tenant_id)
    print(f"Tenant encontrado:")
    print(f"  id: {tenant['id']}")
    print(f"  email: {tenant['email']}")
    print(f"  subscription_status: {tenant['subscription_status']}")
    print(f"  past_due_since: {tenant.get('past_due_since') or '(null)'}")
    print()

    if args.clear:
        updated = clear_past_due(tenant["id"])
        print("✅ past_due_since LIMPO. Status = active.")
        print(f"   new status: {updated.get('subscription_status')}")
        print(f"   past_due_since: {updated.get('past_due_since') or '(null)'}")
        return

    updated = set_past_due(tenant["id"], args.days_ago)
    blocked = args.days_ago > 5
    print(
        f"✅ past_due_since setado {args.days_ago} dia(s) atras. "
        f"Status = past_due."
    )
    print(f"   new past_due_since: {updated.get('past_due_since')}")
    print(
        f"   middleware vai: {'BLOQUEAR 402' if blocked else 'LIBERAR (ainda dentro da tolerancia de 5 dias)'}"
    )
    if blocked:
        print(
            f"   -> banner vermelho + /polling/trigger 402, "
            f"/billing/portal liberado"
        )
    else:
        days_remaining = 5 - args.days_ago
        print(
            f"   -> banner amarelo com countdown ({days_remaining} dia(s)), "
            f"acesso total ainda"
        )


if __name__ == "__main__":
    main()
