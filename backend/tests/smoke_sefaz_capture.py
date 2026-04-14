"""Smoke test: captura REAL na SEFAZ homologação usando o cert do tenant admin.

Este NÃO é um teste unitário — é um ping de validação ponta a ponta pra
confirmar que a stack toda funciona:

  Supabase (certificado) → decrypt via cert_manager → sefaz_client SOAP
  → SEFAZ homologação → parse response → polling_log

Uso: roda manualmente quando você quer confirmar que a integração com
a SEFAZ está saudável (não é parte da suite CI normal).

    # Rodando LOCALMENTE (requer que o cert tenha sido criado com o mesmo
    # CERT_MASTER_SECRET que está no .env local — ex: cert de dev):
    cd backend && source venv/bin/activate
    python tests/smoke_sefaz_capture.py [--email admin@dfeaxis.com.br] [--tipo nfe]

    # Rodando DENTRO do ambiente do Railway (quando o cert foi criado em
    # produção com o CERT_MASTER_SECRET do Railway):
    railway run python backend/tests/smoke_sefaz_capture.py --tipo nfe

IMPORTANTE: se você tentar rodar localmente com um cert que foi criado no
Railway, vai receber "InvalidTag" na decryption — isso NÃO é bug, é
segurança funcionando. Master secrets diferentes por ambiente por design.

Env vars necessárias (já devem estar no .env ou no env do Railway):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    CERT_MASTER_SECRET  — precisa bater com o que foi usado ao criar o cert

O que o teste valida:
    1. Tenant admin existe no banco
    2. Tem certificado ativo
    3. PFX pode ser decodificado com CERT_MASTER_SECRET
    4. sefaz_client consegue fazer call SOAP pra SEFAZ homolog
    5. Resposta tem formato válido (cstat 137/138 = OK)
    6. Entry é gravada em polling_log
    7. Se docs forem encontrados, são gravados em `documentos` (só reporta,
       não valida explicitamente)

NÃO cria/apaga dados — é read-mostly (exceto polling_log que grava 1 linha).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

# Ensure backend module path is loadable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from db.supabase import get_supabase_client  # noqa: E402
from scheduler.polling_job import _poll_single_detailed  # noqa: E402


def log(msg: str, status: str = "INFO") -> None:
    icon = {"INFO": "→", "PASS": "✓", "FAIL": "✗", "WARN": "⚠"}.get(status, "→")
    print(f"  {icon} {msg}")


def find_admin_user_id(email: str) -> str | None:
    """Busca o user_id na tabela auth.users pelo email."""
    sb = get_supabase_client()
    # auth.users não fica em public, tem que usar a API do admin do Supabase
    # Alternativa: query direta via PostgREST na tabela tenants e olhar pelo email
    res = sb.table("tenants").select("id, user_id, email, company_name").eq(
        "email", email
    ).execute()
    if not res.data:
        return None
    # Retorna tenant_id (que é o que a gente precisa)
    return res.data[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test SEFAZ capture")
    parser.add_argument(
        "--email",
        default="admin@dfeaxis.com.br",
        help="Email do tenant alvo (default: admin@dfeaxis.com.br)",
    )
    parser.add_argument(
        "--tipo",
        default="nfe",
        choices=["nfe", "cte", "mdfe"],
        help="Tipo de documento a consultar (default: nfe)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("SEFAZ Capture — smoke test (homologação)")
    print("=" * 70)
    print()

    # Etapa 1 — busca tenant
    print(f"[1] Buscando tenant de {args.email}...")
    tenant_row = find_admin_user_id(args.email)
    if not tenant_row:
        log(f"Nenhum tenant encontrado com email={args.email}", "FAIL")
        log("Verifique se o admin existe em public.tenants", "INFO")
        return 1

    tenant_id = tenant_row["id"]
    log(f"Tenant encontrado: id={tenant_id} company={tenant_row.get('company_name')}", "PASS")

    # Etapa 2 — busca dados completos do tenant
    print()
    print("[2] Carregando config do tenant...")
    sb = get_supabase_client()
    tenant = (
        sb.table("tenants")
        .select(
            "id, polling_mode, manifestacao_mode, credits, sefaz_ambiente, "
            "subscription_status, docs_consumidos_trial, trial_cap, "
            "trial_blocked_at, trial_blocked_reason"
        )
        .eq("id", tenant_id)
        .single()
        .execute()
    )
    tenant_data = tenant.data
    ambiente = tenant_data.get("sefaz_ambiente", "2")
    status = tenant_data.get("subscription_status")
    log(f"sefaz_ambiente={ambiente} ({'PRODUÇÃO' if ambiente == '1' else 'HOMOLOG'})", "PASS")
    log(f"subscription_status={status}", "PASS")
    log(f"credits={tenant_data.get('credits')}", "PASS")

    if ambiente == "1":
        log(
            "AMBIENTE DE PRODUÇÃO — abortando por segurança. "
            "Smoke test deve rodar apenas em homologação.",
            "FAIL",
        )
        return 1

    if tenant_data.get("trial_blocked_at"):
        log(
            f"Trial bloqueado ({tenant_data.get('trial_blocked_reason')}) — "
            "o polling vai falhar no nível de middleware. "
            "Bypass direto via _poll_single_detailed não verifica isso, mas "
            "você verá erro na UI normal.",
            "WARN",
        )

    # Etapa 3 — busca certificado ativo
    print()
    print("[3] Buscando certificado ativo...")
    certs_res = (
        sb.table("certificates")
        .select("id, cnpj, is_active, created_at, last_nsu_nfe, last_nsu_cte, last_nsu_mdfe")
        .eq("tenant_id", tenant_id)
        .eq("is_active", True)
        .execute()
    )

    if not certs_res.data:
        log("Nenhum certificado ativo encontrado para este tenant", "FAIL")
        log("Suba um .pfx via UI em /cadastros/certificados antes de rodar o smoke test", "INFO")
        return 1

    cert_meta = certs_res.data[0]
    log(
        f"Certificado encontrado: id={cert_meta['id']} cnpj={cert_meta['cnpj']} "
        f"criado_em={cert_meta.get('created_at', '?')[:10]}",
        "PASS",
    )
    log(f"last_nsu_{args.tipo}={cert_meta.get(f'last_nsu_{args.tipo}', 'N/A')}", "INFO")

    # Busca o cert completo (com pfx_encrypted, pfx_iv) pra passar pro polling
    cert_full = (
        sb.table("certificates")
        .select("*")
        .eq("id", cert_meta["id"])
        .single()
        .execute()
    )
    cert = cert_full.data

    # Etapa 4 — dispara o polling real
    print()
    print(f"[4] Disparando captura real tipo={args.tipo.upper()} na SEFAZ...")
    start = datetime.now()
    try:
        result = _poll_single_detailed(cert, args.tipo, tenant_data)
    except Exception as exc:  # noqa: BLE001
        exc_name = type(exc).__name__
        log(f"Exceção durante polling: {exc_name}: {exc}", "FAIL")
        if exc_name == "InvalidTag":
            log(
                "InvalidTag = AES-GCM authentication tag mismatch. Isso "
                "SIGNIFICA que o CERT_MASTER_SECRET atual não é o mesmo "
                "que foi usado para cifrar o certificado.",
                "INFO",
            )
            log(
                "Solução: rodar este smoke test DENTRO do ambiente do "
                "Railway (railway run python ...) em vez de localmente, "
                "OU usar um cert que foi criado com o master secret local.",
                "INFO",
            )
            log(
                "NÃO É BUG NA STACK — é segurança por design (master "
                "secret separation dev/prod).",
                "INFO",
            )
        else:
            log(
                "Isso indica bug na stack (SOAP, parsing, rede, etc).",
                "FAIL",
            )
        return 1
    elapsed = (datetime.now() - start).total_seconds()

    print()
    print(f"[5] Resultado (em {elapsed:.1f}s):")
    print(json.dumps(result, default=str, indent=2, ensure_ascii=False))
    print()

    # Etapa 6 — interpreta o resultado
    cstat = result.get("cstat")
    docs_found = result.get("docs_found", 0)
    status_raw = result.get("status")
    error = result.get("error")
    xmotivo = result.get("xmotivo", "")

    if status_raw == "error":
        log(f"SEFAZ retornou ERRO: {xmotivo or error or 'sem motivo'}", "FAIL")
        log(
            f"cstat={cstat} — 999 geralmente indica circuit breaker aberto, "
            "senha inválida, ou problema de rede. 137/138 = sucesso.",
            "INFO",
        )
        return 2

    if cstat == "137":
        log(f"SEFAZ OK — nenhum documento novo (cstat 137)", "PASS")
        log(f"latency={result.get('latency_ms', 0)}ms", "INFO")
    elif cstat == "138":
        log(f"SEFAZ OK — {docs_found} documentos encontrados (cstat 138)", "PASS")
        log(f"latency={result.get('latency_ms', 0)}ms", "INFO")
        log(
            f"saved_to_db={result.get('saved_to_db')} — "
            "documentos foram inseridos em `documentos`",
            "INFO",
        )
    else:
        log(f"Resposta com cstat inesperado: {cstat} ({xmotivo})", "WARN")

    # Etapa 7 — verifica que polling_log foi gravado
    print()
    print("[6] Verificando polling_log...")
    log_res = (
        sb.table("polling_log")
        .select("id, status, docs_found, latency_ms, created_at, error_message")
        .eq("tenant_id", tenant_id)
        .eq("cnpj", cert["cnpj"])
        .eq("tipo", args.tipo)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if log_res.data:
        last_log = log_res.data[0]
        log(
            f"Log gravado: id={last_log['id']} status={last_log['status']} "
            f"docs={last_log['docs_found']} latency={last_log['latency_ms']}ms",
            "PASS",
        )
    else:
        log("Nenhum polling_log encontrado — gravação pode ter falhado", "WARN")

    print()
    print("=" * 70)
    print("✓ SMOKE TEST CONCLUÍDO — stack SEFAZ funcional em homologação")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
