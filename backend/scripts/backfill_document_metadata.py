"""Backfill script: popula metadata extraído do XML em documents existentes
+ normaliza NSUs que foram gravados sem zero-padding.

Roda uma única vez após aplicar migration 015 em produção. Lê todos os
documents que têm `xml_content IS NOT NULL AND cnpj_emitente IS NULL`,
passa pelo xml_parser, e atualiza as novas colunas. Também normaliza NSUs
(LPAD 15 chars) de todos os documents.

Idempotente — rodar múltiplas vezes é seguro.

Uso:
    cd backend && source venv/bin/activate
    python scripts/backfill_document_metadata.py

Opções:
    --dry-run : não grava nada, só mostra o que faria
    --tenant <id> : limita a um tenant específico
    --limit <n> : processa apenas os primeiros N documents (default: todos)
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from db.supabase import get_supabase_client  # noqa: E402
from services.xml_parser import metadata_to_db_dict, parse_document_xml  # noqa: E402


def log(msg: str, status: str = "INFO") -> None:
    icon = {"INFO": "→", "PASS": "✓", "FAIL": "✗", "SKIP": "·"}.get(status, "→")
    print(f"  {icon} {msg}")


def normalize_nsu_in_db(sb, dry_run: bool, tenant_filter: str | None) -> int:
    """Normaliza NSUs que estão com menos de 15 chars (LPAD zero)."""
    print()
    print("[Fase 1] Normalizando NSUs sem zero-padding...")

    query = sb.table("documents").select("id, nsu, tenant_id")
    if tenant_filter:
        query = query.eq("tenant_id", tenant_filter)

    # Pagina tudo (Supabase limita a 1000 por request)
    all_rows: list[dict] = []
    offset = 0
    while True:
        res = query.range(offset, offset + 999).execute()
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000

    to_fix = [
        r for r in all_rows
        if r.get("nsu") and len(str(r["nsu"])) < 15 and str(r["nsu"]).isdigit()
    ]

    if not to_fix:
        log(f"Todos os {len(all_rows)} NSUs já estão normalizados", "PASS")
        return 0

    log(f"{len(to_fix)} NSUs precisam de normalização (de {len(all_rows)} totais)")

    if dry_run:
        for r in to_fix[:5]:
            log(f"  DRY: {r['nsu']!r} → {str(r['nsu']).zfill(15)!r}", "SKIP")
        if len(to_fix) > 5:
            log(f"  ... +{len(to_fix) - 5} mais", "SKIP")
        return len(to_fix)

    fixed = 0
    for r in to_fix:
        new_nsu = str(r["nsu"]).zfill(15)
        try:
            sb.table("documents").update({"nsu": new_nsu}).eq("id", r["id"]).execute()
            fixed += 1
        except Exception as exc:  # noqa: BLE001
            log(f"FAIL id={r['id']}: {exc}", "FAIL")

    log(f"{fixed} NSUs normalizados", "PASS")
    return fixed


def backfill_xml_metadata(
    sb, dry_run: bool, tenant_filter: str | None, limit: int | None
) -> int:
    """Extrai metadata do xml_content dos documents que ainda não têm."""
    print()
    print("[Fase 2] Extraindo metadata do xml_content...")

    # Pega os docs que TÊM xml e NÃO TÊM emitente ainda
    query = (
        sb.table("documents")
        .select("id, tipo, xml_content")
        .not_.is_("xml_content", "null")
        .is_("cnpj_emitente", "null")
    )
    if tenant_filter:
        query = query.eq("tenant_id", tenant_filter)

    # Pagina até o limit
    all_rows: list[dict] = []
    offset = 0
    batch_size = 200  # não pega xml_content enorme muitas de uma vez
    target = limit if limit else None
    while True:
        res = query.range(offset, offset + batch_size - 1).execute()
        rows = res.data or []
        all_rows.extend(rows)
        if len(rows) < batch_size:
            break
        if target and len(all_rows) >= target:
            all_rows = all_rows[:target]
            break
        offset += batch_size

    log(f"{len(all_rows)} documents sem metadata extraída")

    if not all_rows:
        return 0

    if dry_run:
        # Mostra o que extrairia dos primeiros 5
        for r in all_rows[:5]:
            meta = parse_document_xml(r["xml_content"] or "", r["tipo"])
            d = metadata_to_db_dict(meta)
            log(f"  DRY id={r['id'][:8]} tipo={r['tipo']} → {d}", "SKIP")
        if len(all_rows) > 5:
            log(f"  ... +{len(all_rows) - 5} mais", "SKIP")
        return len(all_rows)

    updated = 0
    failed = 0
    for r in all_rows:
        try:
            meta = parse_document_xml(r.get("xml_content") or "", r.get("tipo", ""))
            update_dict = metadata_to_db_dict(meta)
            if not update_dict:
                # XML não forneceu nada útil — marca como "processado" via um campo
                # sentinela mínimo, ou só skippa. Vou só skippar.
                continue
            sb.table("documents").update(update_dict).eq("id", r["id"]).execute()
            updated += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log(f"FAIL id={r['id']}: {type(exc).__name__}: {exc}", "FAIL")

    log(f"{updated} documents atualizados, {failed} falhas", "PASS")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill document metadata")
    parser.add_argument("--dry-run", action="store_true", help="Não grava nada")
    parser.add_argument("--tenant", help="Limita a um tenant_id")
    parser.add_argument("--limit", type=int, help="Processa no máximo N docs")
    args = parser.parse_args()

    print("=" * 60)
    print("Backfill document metadata")
    print("=" * 60)
    print(f"Dry run: {args.dry_run}")
    if args.tenant:
        print(f"Tenant filter: {args.tenant}")
    if args.limit:
        print(f"Limit: {args.limit}")

    sb = get_supabase_client()

    n_nsu = normalize_nsu_in_db(sb, args.dry_run, args.tenant)
    n_meta = backfill_xml_metadata(sb, args.dry_run, args.tenant, args.limit)

    print()
    print("=" * 60)
    print(f"Total: {n_nsu} NSUs normalizados, {n_meta} metadatas extraídas")
    if args.dry_run:
        print("(DRY RUN — nada foi gravado)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
