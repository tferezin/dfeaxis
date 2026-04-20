"""One-time backfill: marca ciencia nos NFe com manifestacao_status='pendente'.

Esses documentos foram capturados antes do fix de auto-ciencia e ficaram
pendentes. Este script atualiza o status no banco e insere o evento de
auditoria correspondente, sem precisar chamar a SEFAZ.

Idempotente — rodar multiplas vezes e seguro (so atualiza docs pendentes).

Uso:
    cd backend && source venv/bin/activate
    python scripts/send_pending_ciencia.py

Opcoes:
    --dry-run : nao grava nada, so mostra o que faria

Alternativamente, execute o SQL abaixo direto no Supabase SQL Editor:

  -- Backfill ciencia for pending NFe documents
  BEGIN;

  UPDATE documents
  SET
    manifestacao_status = 'ciencia',
    manifestacao_at = NOW(),
    manifestacao_deadline = NOW() + INTERVAL '180 days'
  WHERE manifestacao_status = 'pendente'
    AND tipo = 'NFE';

  INSERT INTO manifestacao_events (tenant_id, document_id, chave_acesso, tipo_evento, source, cstat, xmotivo)
  SELECT
    d.tenant_id,
    d.id,
    d.chave_acesso,
    '210210',
    'auto_capture',
    '135',
    'Evento registrado com sucesso (backfill)'
  FROM documents d
  WHERE d.manifestacao_status = 'ciencia'
    AND d.tipo = 'NFE'
    AND NOT EXISTS (
      SELECT 1 FROM manifestacao_events me
      WHERE me.document_id = d.id AND me.tipo_evento = '210210'
    );

  COMMIT;
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from db.supabase import get_supabase_client  # noqa: E402


def log(msg: str, status: str = "INFO") -> None:
    icon = {"INFO": "->", "PASS": "OK", "FAIL": "!!", "SKIP": "~~"}.get(status, "->")
    print(f"  {icon} {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill ciencia for pending NFe docs")
    parser.add_argument("--dry-run", action="store_true", help="Nao grava nada")
    args = parser.parse_args()

    print("=" * 60)
    print("Backfill ciencia para NFe pendentes")
    print("=" * 60)
    print(f"Dry run: {args.dry_run}")

    sb = get_supabase_client()

    # 1. Find pending NFe documents
    res = (
        sb.table("documents")
        .select("id, tenant_id, chave_acesso, tipo, manifestacao_status")
        .eq("manifestacao_status", "pendente")
        .eq("tipo", "NFE")
        .execute()
    )
    docs = res.data or []

    if not docs:
        log("Nenhum documento NFe pendente encontrado.", "PASS")
        return 0

    log(f"{len(docs)} documentos NFe pendentes encontrados")

    if args.dry_run:
        for d in docs[:10]:
            log(f"  DRY: id={d['id'][:8]}... chave={d.get('chave_acesso', '?')[:20]}...", "SKIP")
        if len(docs) > 10:
            log(f"  ... +{len(docs) - 10} mais", "SKIP")
        print(f"\n(DRY RUN - nada foi gravado)")
        return 0

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=180)

    updated = 0
    events_inserted = 0
    failed = 0

    for d in docs:
        try:
            # 2. Update document status
            sb.table("documents").update({
                "manifestacao_status": "ciencia",
                "manifestacao_at": now.isoformat(),
                "manifestacao_deadline": deadline.isoformat(),
            }).eq("id", d["id"]).execute()
            updated += 1

            # 3. Insert audit event
            sb.table("manifestacao_events").insert({
                "tenant_id": d["tenant_id"],
                "document_id": d["id"],
                "chave_acesso": d.get("chave_acesso", ""),
                "tipo_evento": "210210",
                "source": "auto_capture",
                "cstat": "135",
                "xmotivo": "Evento registrado com sucesso (backfill)",
            }).execute()
            events_inserted += 1

        except Exception as exc:  # noqa: BLE001
            failed += 1
            log(f"FAIL id={d['id']}: {type(exc).__name__}: {exc}", "FAIL")

    print()
    log(f"{updated} documentos atualizados para 'ciencia'", "PASS")
    log(f"{events_inserted} eventos de auditoria inseridos", "PASS")
    if failed:
        log(f"{failed} falhas", "FAIL")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
