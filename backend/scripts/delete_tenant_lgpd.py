#!/usr/bin/env python3
"""Direito ao esquecimento (LGPD Art. 18, VI) — apaga tenant + dados associados.

USO:
    python -m backend.scripts.delete_tenant_lgpd <tenant_id>
    # ou:
    python backend/scripts/delete_tenant_lgpd.py <tenant_id>

REQUISITOS:
    - SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY no env
    - Operador deve ter recebido solicitacao formal (e-mail/ticket) do titular
    - Confirmar dupla via prompt interativo (digitar "DELETE <tenant_id>")

EFEITOS:
    Apaga em ordem de FK:
      1. documents (tenant_id)
      2. polling_log (tenant_id)
      3. manifestacao_events / manifestacao_pendentes (tenant_id)
      4. audit_log (tenant_id)
      5. certificates (tenant_id)
      6. api_keys (tenant_id)
      7. billing_events (tenant_id)
      8. monthly_overage_charges (tenant_id) - se existir
      9. chat_conversations + chat_messages + chat_leads (tenant_id)
      10. tenants (id)
      11. auth.users (user_id) — apenas se tenant.user_id existir

E gerado um relatorio JSON em /tmp/lgpd_delete_<tenant_id>.json com contagens
por tabela pra anexar na resposta ao titular (LGPD exige confirmacao da exclusao).

NUNCA executar em producao sem ticket aprovado e backup recente.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Garante que o backend esta no path quando rodado standalone.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from db.supabase import get_supabase_client  # noqa: E402


# Ordem de delecao respeitando FKs. Cada tupla = (tabela, coluna_filtro).
# Tabelas que ainda nao tiverem CASCADE precisam estar listadas aqui.
DELETE_ORDER = [
    ("documents", "tenant_id"),
    ("polling_log", "tenant_id"),
    ("manifestacao_events", "tenant_id"),
    ("manifestacao_pendentes", "tenant_id"),
    ("nfe_ciencia_queue", "tenant_id"),
    ("audit_log", "tenant_id"),
    ("certificates", "tenant_id"),
    ("api_keys", "tenant_id"),
    ("billing_events", "tenant_id"),
    ("monthly_overage_charges", "tenant_id"),
    # chat_messages NAO tem coluna tenant_id direta — eh apagado via
    # ON DELETE CASCADE quando deletar chat_conversations.
    ("chat_leads", "tenant_id"),
    ("chat_conversations", "tenant_id"),
]


def _count(sb, table: str, column: str, tenant_id: str) -> int:
    try:
        res = sb.table(table).select("id", count="exact").eq(column, tenant_id).execute()
        return res.count or 0
    except Exception as exc:  # tabela pode nao existir em ambientes antigos
        print(f"  [skip] {table}: {exc}")
        return -1


def _delete(sb, table: str, column: str, tenant_id: str) -> int:
    """Retorna numero de rows apagadas (best-effort — Supabase nao retorna count)."""
    before = _count(sb, table, column, tenant_id)
    if before <= 0:
        return max(before, 0)
    try:
        sb.table(table).delete().eq(column, tenant_id).execute()
    except Exception as exc:
        print(f"  [ERROR] {table}: {exc}")
        return -1
    return before


def main():
    if len(sys.argv) != 2:
        print("Uso: python delete_tenant_lgpd.py <tenant_id>")
        sys.exit(1)

    tenant_id = sys.argv[1].strip()
    if len(tenant_id) < 8:
        print(f"tenant_id invalido: {tenant_id!r}")
        sys.exit(1)

    sb = get_supabase_client()

    # Valida que tenant existe e mostra dados pra confirmacao
    tenant_res = sb.table("tenants").select(
        "id, company_name, cnpj, email, user_id, created_at"
    ).eq("id", tenant_id).execute()
    if not tenant_res.data:
        print(f"Tenant {tenant_id} nao encontrado.")
        sys.exit(1)

    tenant = tenant_res.data[0]
    print()
    print("=" * 72)
    print("  LGPD - DIREITO AO ESQUECIMENTO")
    print("=" * 72)
    print(f"  ID:       {tenant['id']}")
    print(f"  Empresa:  {tenant.get('company_name', '(sem nome)')}")
    print(f"  CNPJ:     {tenant.get('cnpj', '(sem CNPJ)')}")
    print(f"  Email:    {tenant.get('email', '(sem email)')}")
    print(f"  user_id:  {tenant.get('user_id', '(sem user_id)')}")
    print(f"  Criado:   {tenant.get('created_at', '(sem data)')}")
    print("=" * 72)
    print()

    # Confirmacao dupla — digitar "DELETE <tenant_id>"
    expected = f"DELETE {tenant_id}"
    typed = input(
        f"Pra confirmar a exclusao IRREVERSIVEL, digite literalmente:\n  {expected}\n> "
    ).strip()
    if typed != expected:
        print("Cancelado — texto nao confere.")
        sys.exit(1)

    print()
    print("Iniciando exclusao...")
    print()

    report = {
        "tenant_id": tenant_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "tenant_snapshot": tenant,
        "deletions": {},
    }

    for table, column in DELETE_ORDER:
        deleted = _delete(sb, table, column, tenant_id)
        report["deletions"][table] = deleted
        print(f"  {table:32s} -> {deleted} rows")

    # Apaga tenant em si
    try:
        sb.table("tenants").delete().eq("id", tenant_id).execute()
        report["deletions"]["tenants"] = 1
        print(f"  {'tenants':32s} -> 1 row")
    except Exception as exc:
        report["deletions"]["tenants"] = f"ERROR: {exc}"
        print(f"  [ERROR] tenants: {exc}")

    # Apaga auth.user — somente se tinha user_id linkado.
    # Supabase nao expoe auth.users via PostgREST direto; usar admin.delete_user.
    user_id = tenant.get("user_id")
    if user_id:
        try:
            sb.auth.admin.delete_user(user_id)
            report["deletions"]["auth.users"] = 1
            print(f"  {'auth.users':32s} -> 1 row")
        except Exception as exc:
            report["deletions"]["auth.users"] = f"ERROR: {exc}"
            print(f"  [ERROR] auth.users: {exc}")

    report["completed_at"] = datetime.now(timezone.utc).isoformat()

    out_path = Path(f"/tmp/lgpd_delete_{tenant_id}.json")
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print()
    print(f"Relatorio salvo em: {out_path}")
    print("Anexar este JSON na resposta ao titular (LGPD Art. 19).")
    print()


if __name__ == "__main__":
    main()
