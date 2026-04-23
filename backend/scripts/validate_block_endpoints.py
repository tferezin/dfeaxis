#!/usr/bin/env python3
"""Valida que o soft block granular esta respondendo o certo em cada endpoint.

Roda DEPOIS de simular past_due no tenant (via simulate_past_due.py).
Chama cada endpoint relevante e confere se retorna 402 (bloqueado) ou
200/404 (liberado) conforme a regra:

- Read (GET): SEMPRE liberado
- /billing/*, /alerts, /chat/: SEMPRE liberado (mesmo em POST)
- /polling/trigger, /manifestacao (POST): BLOQUEADO quando past_due > 5d

Uso:
    export API_URL="https://api.dfeaxis.com.br/api/v1"
    export TEST_JWT="eyJ..."                      # JWT do tenant em teste
    export TEST_CNPJ="12345678000199"             # CNPJ do tenant

    python validate_block_endpoints.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _call(
    method: str, path: str, body: dict | None = None
) -> tuple[int, str]:
    api_url = os.environ.get("API_URL", "").rstrip("/")
    jwt = os.environ.get("TEST_JWT", "")
    if not api_url or not jwt:
        sys.exit(
            "ERRO: API_URL e TEST_JWT precisam estar no env. "
            "Ex: export API_URL='https://dfeaxis-production.up.railway.app/api/v1'"
        )

    full_url = f"{api_url}/{path.lstrip('/')}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        full_url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8")[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")[:200]
    except Exception as e:
        return 0, f"ERROR: {e}"


def main() -> None:
    cnpj = os.environ.get("TEST_CNPJ", "")

    cases = [
        ("GET /alerts", "GET", "alerts", None, None),
        ("GET /tenants/me", "GET", "tenants/me", None, None),
        ("GET /documentos", "GET", f"documentos?cnpj={cnpj}&tipo=nfe", None, None),
        ("GET /sefaz/status", "GET", "sefaz/status", None, None),
        ("GET /manifestacao/historico", "GET", "manifestacao/historico", None, None),
        ("POST /polling/trigger (write)", "POST", "polling/trigger",
         {"cnpj": cnpj, "tipos": ["cte"]}, 402),
        ("POST /polling/nfe-resumos (write)", "POST", "polling/nfe-resumos",
         {"cnpj": cnpj}, 402),
    ]

    print(f"Testando API_URL = {os.environ.get('API_URL')}")
    print(f"CNPJ de teste = {cnpj or '(nao setado)'}")
    print()

    all_ok = True
    for desc, method, path, body, expected_block in cases:
        status, snippet = _call(method, path, body)
        if expected_block == 402:
            ok = status == 402
            verdict = "BLOQUEADO OK" if ok else f"FALHOU: esperado 402, veio {status}"
        else:
            ok = status in (200, 404)
            verdict = (
                f"LIBERADO OK ({status})" if ok
                else f"FALHOU: veio {status} em endpoint que deveria liberar"
            )

        if not ok:
            all_ok = False
        print(f"  {verdict} — {desc}")
        if not ok and snippet:
            print(f"    {snippet}")

    print()
    if all_ok:
        print("TODOS os checks passaram. Soft block funcionando corretamente.")
        sys.exit(0)
    else:
        print("Algum check falhou. Revisar middleware.")
        sys.exit(1)


if __name__ == "__main__":
    main()
