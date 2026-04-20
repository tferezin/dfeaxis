"""Background jobs for NFe polling v2 architecture.

NFe requires a 2-step process with SEFAZ:
  1. DistDFe returns resumos (resNFe) -- lightweight summaries
  2. Ciencia (210210) must be sent to unlock full XML (procNFe)
  3. After ~30 min, SEFAZ makes the full XML available via DistDFe

This module implements two background jobs running on offset schedules:
  - poll_nfe_resumos(): every 60 min -- fetches resumos + sends ciencia
  - fetch_nfe_xml_completo(): every 60 min (offset 30 min) -- fetches full XML

Both jobs use the nfe_ciencia_queue table as coordination mechanism.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from db.supabase import get_supabase_client
from middleware.lgpd import mask_cnpj
from services.manifestacao import manifestacao_service
from services.sefaz_client import sefaz_client
from services.nsu_controller import nsu_controller
from services.xml_parser import (
    is_evento_xml,
    metadata_to_db_dict,
    parse_document_xml,
)
from scheduler.polling_job import (
    _build_document_row,
    _get_pfx_password,
    _normalize_pfx_blob,
)

logger = logging.getLogger(__name__)

# Max retries before giving up on fetching XML for a queue entry
_MAX_XML_FETCH_ATTEMPTS = 5


def poll_nfe_resumos() -> None:
    """Job 1: Poll SEFAZ DistDFe for NFe resumos + send ciencia.

    Runs every 60 minutes. For each active certificate:
    1. Calls SEFAZ DistDFe to get resumos
    2. For each resNFe found, inserts into nfe_ciencia_queue
    3. Sends ciencia (210210) via manifestacao_service
    4. Updates queue entry with ciencia status
    5. Advances NSU cursor
    """
    sb = get_supabase_client()
    logger.info("nfe_poll_resumos: iniciando rodada")

    # Fetch all active certificates
    cert_result = sb.table("certificates").select(
        "id, tenant_id, cnpj, pfx_encrypted, pfx_iv, "
        "last_nsu_nfe, last_nsu_cte, last_nsu_mdfe, last_nsu_nfse"
    ).eq("is_active", True).execute()

    if not cert_result.data:
        logger.debug("nfe_poll_resumos: nenhum certificado ativo")
        return

    processed_tenants: set[str] = set()

    for cert in cert_result.data:
        tenant_id = cert["tenant_id"]

        # Avoid processing the same tenant multiple times if they have
        # multiple certificates (unlikely but defensive)
        if tenant_id in processed_tenants:
            continue

        # Fetch tenant data
        tenant_res = sb.table("tenants").select(
            "id, polling_mode, manifestacao_mode, credits, sefaz_ambiente, "
            "subscription_status, docs_consumidos_trial, trial_cap, "
            "trial_blocked_at, trial_blocked_reason"
        ).eq("id", tenant_id).single().execute()

        if not tenant_res.data:
            continue

        tenant_data = tenant_res.data

        # Skip tenants that are expired/cancelled/blocked
        status = tenant_data.get("subscription_status")
        if status in ("expired", "cancelled"):
            logger.info(
                "nfe_poll_resumos: tenant %s status=%s, pulando",
                tenant_id, status,
            )
            processed_tenants.add(tenant_id)
            continue

        if tenant_data.get("trial_blocked_at"):
            logger.info(
                "nfe_poll_resumos: tenant %s trial bloqueado, pulando",
                tenant_id,
            )
            processed_tenants.add(tenant_id)
            continue

        # Skip tenants without credits (legacy model) and without subscription
        if status not in ("active", "past_due", "trial") and tenant_data.get("credits", 0) <= 0:
            logger.info(
                "nfe_poll_resumos: tenant %s sem creditos e sem subscription, pulando",
                tenant_id,
            )
            continue

        try:
            _poll_resumos_for_cert(cert, tenant_data)
        except Exception as exc:
            logger.exception(
                "nfe_poll_resumos: erro processando cert %s tenant %s: %s",
                cert["id"], tenant_id, exc,
            )

        processed_tenants.add(tenant_id)

        # Rate limiting between different CNPJs
        time.sleep(1)

    logger.info(
        "nfe_poll_resumos: rodada finalizada, %d tenants processados",
        len(processed_tenants),
    )


def _poll_resumos_for_cert(cert: dict, tenant_data: dict) -> None:
    """Process a single certificate: fetch resumos from SEFAZ and send ciencia."""
    sb = get_supabase_client()
    tenant_id = cert["tenant_id"]
    cnpj = cert["cnpj"]
    ambiente = tenant_data.get("sefaz_ambiente", "2")

    pfx_password = _get_pfx_password(cert["id"], tenant_id)
    if not pfx_password:
        logger.warning(
            "nfe_poll_resumos: sem senha pfx para cert %s, pulando",
            cert["id"],
        )
        return

    pfx_encrypted, pfx_iv = _normalize_pfx_blob(
        cert["pfx_encrypted"], cert["pfx_iv"]
    )

    # Get current NSU cursor
    try:
        ult_nsu = nsu_controller.get_cursor(cert["id"], "nfe", ambiente)
    except Exception:
        ult_nsu = cert.get("last_nsu_nfe", "000000000000000")

    # Call SEFAZ DistDFe
    try:
        response = sefaz_client.consultar_distribuicao(
            cnpj=cnpj,
            tipo="nfe",
            ult_nsu=ult_nsu,
            pfx_encrypted=pfx_encrypted,
            pfx_iv=pfx_iv,
            tenant_id=tenant_id,
            pfx_password=pfx_password,
            ambiente=ambiente,
        )
    except Exception as exc:
        logger.error(
            "nfe_poll_resumos: SEFAZ call failed cert=%s cnpj=%s: %s",
            cert["id"], mask_cnpj(cnpj), exc,
        )
        sb.table("polling_log").insert({
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "tipo": "nfe",
            "triggered_by": "nfe_poll_resumos",
            "status": "error",
            "error_message": f"{type(exc).__name__}: {exc}",
        }).execute()
        return

    # cStat 656 = Consumo Indevido — SEFAZ blocked this CNPJ for ~1h.
    # Do NOT retry — it only renews the block. Open circuit breaker to
    # prevent the next scheduled run from calling again.
    if response.cstat == "656":
        logger.warning(
            "nfe_poll_resumos: cStat 656 Consumo Indevido cnpj=%s — "
            "backing off (circuit breaker open for 70 min)",
            mask_cnpj(cnpj),
        )
        # Force circuit breaker open for 70 min (SEFAZ requires 1h)
        from services.circuit_breaker import circuit_breaker as cb
        cb.force_open(cnpj, "nfe", recovery_s=4200)  # 70 min
        sb.table("polling_log").insert({
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "tipo": "nfe",
            "triggered_by": "nfe_poll_resumos",
            "status": "error",
            "docs_found": 0,
            "ult_nsu": response.ult_nsu,
            "latency_ms": response.latency_ms,
            "error_message": f"cStat 656: {response.xmotivo}",
        }).execute()
        return

    docs = list(response.documents)
    docs_found = len(docs)

    # Log the polling result
    sb.table("polling_log").insert({
        "tenant_id": tenant_id,
        "cnpj": cnpj,
        "tipo": "nfe",
        "triggered_by": "nfe_poll_resumos",
        "status": "success" if response.cstat in ("137", "138") else "error",
        "docs_found": docs_found,
        "ult_nsu": response.ult_nsu,
        "latency_ms": response.latency_ms,
        "error_message": response.xmotivo if response.cstat not in ("137", "138") else None,
    }).execute()

    if docs_found == 0:
        # Update max_nsu for pending count visibility
        if response.max_nsu:
            nsu_controller.update_pending_count(
                cert["id"], "nfe", ambiente, response.max_nsu
            )
        return

    resumos_enqueued = 0
    completos_saved = 0

    for doc in docs:
        is_resumo = doc.schema.startswith("res")

        if is_resumo:
            # NFe resumo: enqueue for ciencia + XML fetch
            _enqueue_and_ciencia(
                sb=sb,
                cert=cert,
                tenant_data=tenant_data,
                doc=doc,
                pfx_encrypted=pfx_encrypted,
                pfx_iv=pfx_iv,
                pfx_password=pfx_password,
                ambiente=ambiente,
            )
            resumos_enqueued += 1
        else:
            # procNFe (full XML already available, e.g. from previous ciencia)
            row = _build_document_row(
                tenant_id=tenant_id,
                cnpj=cnpj,
                doc=doc,
                is_resumo=False,
                doc_status="available",
                manif_status="ciencia",
            )
            if row is not None:
                sb.table("documents").upsert(
                    row, on_conflict="tenant_id,chave_acesso"
                ).execute()
                completos_saved += 1

        # Small delay between SEFAZ-related operations
        time.sleep(0.5)

    # Advance NSU cursor
    nsu_controller.update_cursor(
        cert["id"], "nfe", ambiente, response.ult_nsu,
        response.max_nsu or response.ult_nsu,
    )
    nsu_controller.update_last_nsu(cert["id"], "nfe", response.ult_nsu)

    logger.info(
        "nfe_poll_resumos: cert=%s cnpj=%s — %d resumos enqueued, "
        "%d completos saved, ult_nsu=%s",
        cert["id"], mask_cnpj(cnpj), resumos_enqueued,
        completos_saved, response.ult_nsu,
    )


def _enqueue_and_ciencia(
    *,
    sb,
    cert: dict,
    tenant_data: dict,
    doc,
    pfx_encrypted,
    pfx_iv,
    pfx_password: str,
    ambiente: str,
) -> None:
    """Insert a resumo into nfe_ciencia_queue and send ciencia."""
    tenant_id = cert["tenant_id"]
    cnpj = cert["cnpj"]

    # Insert into queue (ignore if already exists via UNIQUE constraint)
    try:
        sb.table("nfe_ciencia_queue").upsert(
            {
                "tenant_id": tenant_id,
                "certificate_id": cert["id"],
                "cnpj": cnpj,
                "chave_acesso": doc.chave,
                "nsu": doc.nsu,
            },
            on_conflict="tenant_id,chave_acesso",
        ).execute()
    except Exception as exc:
        logger.warning(
            "nfe_poll_resumos: falha ao enfileirar chave=%s: %s",
            doc.chave, exc,
        )
        return

    # Skip ciencia if manifestacao_mode is manual_only
    if tenant_data.get("manifestacao_mode") == "manual_only":
        logger.info(
            "nfe_poll_resumos: manifestacao_mode=manual_only, "
            "ciencia nao enviada para chave=%s",
            doc.chave,
        )
        return

    # Send ciencia (210210)
    # manifestacao_service expects bytes for pfx_encrypted/pfx_iv.
    # _normalize_pfx_blob may return str for v2 certs ("v2:...").
    _pfx_enc = pfx_encrypted if isinstance(pfx_encrypted, bytes) else pfx_encrypted.encode("utf-8") if isinstance(pfx_encrypted, str) else pfx_encrypted
    _pfx_iv = pfx_iv if isinstance(pfx_iv, bytes) else pfx_iv if pfx_iv is None else bytes(pfx_iv) if isinstance(pfx_iv, (bytearray, memoryview)) else pfx_iv
    try:
        result = manifestacao_service.enviar_evento(
            chave_acesso=doc.chave,
            cnpj=cnpj,
            tipo_evento="210210",
            pfx_encrypted=_pfx_enc,
            pfx_iv=_pfx_iv,
            tenant_id=tenant_id,
            pfx_password=pfx_password,
            ambiente=ambiente,
        )

        # Audit event
        sb.table("manifestacao_events").insert({
            "tenant_id": tenant_id,
            "document_id": None,
            "chave_acesso": doc.chave,
            "tipo_evento": "210210",
            "cstat": result.cstat,
            "xmotivo": result.xmotivo,
            "protocolo": result.protocolo,
            "latency_ms": result.latency_ms,
            "source": "auto_capture",
        }).execute()

        if result.success:
            # Update queue: ciencia sent successfully
            sb.table("nfe_ciencia_queue").update({
                "ciencia_enviada": True,
                "ciencia_enviada_at": datetime.now(timezone.utc).isoformat(),
                "ciencia_cstat": result.cstat,
            }).eq("tenant_id", tenant_id).eq(
                "chave_acesso", doc.chave,
            ).execute()

            logger.info(
                "nfe_poll_resumos: ciencia OK chave=%s cstat=%s",
                doc.chave, result.cstat,
            )
        elif result.cstat in ("575", "596"):
            # Rejeição permanente — descartar da fila
            sb.table("nfe_ciencia_queue").update({
                "ciencia_enviada": True,
                "ciencia_enviada_at": datetime.now(timezone.utc).isoformat(),
                "ciencia_cstat": result.cstat,
                "xml_fetched": True,
                "xml_fetched_at": datetime.now(timezone.utc).isoformat(),
                "ultimo_erro": f"descartado: cstat={result.cstat} {result.xmotivo}",
            }).eq("tenant_id", tenant_id).eq(
                "chave_acesso", doc.chave,
            ).execute()

            logger.info(
                "nfe_poll_resumos: descartado chave=%s cstat=%s (%s)",
                doc.chave, result.cstat, result.xmotivo,
            )
        else:
            # Ciencia failed -- update queue with error (retentável)
            sb.table("nfe_ciencia_queue").update({
                "ciencia_cstat": result.cstat,
                "ultimo_erro": f"ciencia falhou: cstat={result.cstat} {result.xmotivo}",
                "tentativas": 1,
            }).eq("tenant_id", tenant_id).eq(
                "chave_acesso", doc.chave,
            ).execute()

            logger.warning(
                "nfe_poll_resumos: ciencia FALHA chave=%s cstat=%s xmotivo=%s",
                doc.chave, result.cstat, result.xmotivo,
            )

    except Exception as exc:
        err_msg = str(exc) or repr(exc)
        logger.error(
            "nfe_poll_resumos: ciencia erro chave=%s: %s: %s",
            doc.chave, type(exc).__name__, err_msg,
        )
        sb.table("nfe_ciencia_queue").update({
            "ultimo_erro": f"ciencia exception: {type(exc).__name__}: {err_msg}",
            "tentativas": 1,
        }).eq("tenant_id", tenant_id).eq(
            "chave_acesso", doc.chave,
        ).execute()


# ────────────────────────────────────────────────────────────────────
# Job 2: Fetch full XML for ciencia'd resumos
# ────────────────────────────────────────────────────────────────────

def fetch_nfe_xml_completo() -> None:
    """Job 2: Fetch full NFe XML for entries where ciencia was sent.

    Runs every 60 minutes (offset 30 min from Job 1).
    Processes queue entries where:
      - ciencia_enviada = true
      - xml_fetched = false
      - ciencia_enviada_at < now() - 30 min (SEFAZ needs time to process)
      - tentativas < _MAX_XML_FETCH_ATTEMPTS
    """
    sb = get_supabase_client()
    logger.info("nfe_fetch_xml: iniciando rodada")

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()

    # Fetch pending queue entries
    queue_result = sb.table("nfe_ciencia_queue").select("*").eq(
        "ciencia_enviada", True,
    ).eq(
        "xml_fetched", False,
    ).lt(
        "ciencia_enviada_at", cutoff,
    ).lt(
        "tentativas", _MAX_XML_FETCH_ATTEMPTS,
    ).execute()

    if not queue_result.data:
        logger.debug("nfe_fetch_xml: nenhuma entrada pendente na fila")
        return

    # Group entries by certificate_id for efficient SEFAZ calls
    entries_by_cert: dict[str, list[dict]] = {}
    for entry in queue_result.data:
        cert_id = entry["certificate_id"]
        entries_by_cert.setdefault(cert_id, []).append(entry)

    total_fetched = 0
    total_failed = 0

    for cert_id, entries in entries_by_cert.items():
        # Fetch certificate data
        cert_res = sb.table("certificates").select(
            "id, tenant_id, cnpj, pfx_encrypted, pfx_iv"
        ).eq("id", cert_id).eq("is_active", True).execute()

        if not cert_res.data:
            logger.warning(
                "nfe_fetch_xml: cert %s nao encontrado ou inativo, "
                "pulando %d entries",
                cert_id, len(entries),
            )
            continue

        cert = cert_res.data[0]
        tenant_id = cert["tenant_id"]

        # Fetch tenant for ambiente
        tenant_res = sb.table("tenants").select(
            "id, sefaz_ambiente"
        ).eq("id", tenant_id).single().execute()

        if not tenant_res.data:
            continue

        ambiente = tenant_res.data.get("sefaz_ambiente", "2")

        pfx_password = _get_pfx_password(cert["id"], tenant_id)
        if not pfx_password:
            logger.warning(
                "nfe_fetch_xml: sem senha pfx para cert %s, pulando",
                cert["id"],
            )
            continue

        pfx_encrypted, pfx_iv = _normalize_pfx_blob(
            cert["pfx_encrypted"], cert["pfx_iv"]
        )

        # Build set of chaves we need to find
        pending_chaves = {e["chave_acesso"]: e for e in entries}

        # Call SEFAZ DistDFe to look for procNFe
        # We use the lowest NSU from pending entries as starting point
        min_nsu = min(
            (e["nsu"] for e in entries),
            key=lambda n: int(n) if n else 0,
        )

        try:
            response = sefaz_client.consultar_distribuicao(
                cnpj=cert["cnpj"],
                tipo="nfe",
                ult_nsu=min_nsu,
                pfx_encrypted=pfx_encrypted,
                pfx_iv=pfx_iv,
                tenant_id=tenant_id,
                pfx_password=pfx_password,
                ambiente=ambiente,
            )
        except Exception as exc:
            logger.error(
                "nfe_fetch_xml: SEFAZ call failed cert=%s: %s",
                cert_id, exc,
            )
            # Increment tentativas for all entries in this batch
            for entry in entries:
                sb.table("nfe_ciencia_queue").update({
                    "tentativas": entry["tentativas"] + 1,
                    "ultimo_erro": f"SEFAZ call failed: {type(exc).__name__}: {exc}",
                }).eq("id", entry["id"]).execute()
                total_failed += 1
            continue

        # Index full XML docs by chave_acesso
        full_docs_by_chave: dict[str, object] = {}
        for doc in response.documents:
            if not doc.schema.startswith("res") and doc.chave in pending_chaves:
                full_docs_by_chave[doc.chave] = doc

        # Process each pending entry
        for chave, entry in pending_chaves.items():
            if chave in full_docs_by_chave:
                # Found full XML -- save to documents table
                full_doc = full_docs_by_chave[chave]
                row = _build_document_row(
                    tenant_id=tenant_id,
                    cnpj=cert["cnpj"],
                    doc=full_doc,
                    is_resumo=False,
                    doc_status="available",
                    manif_status="ciencia",
                )
                if row is not None:
                    now = datetime.now(timezone.utc)
                    row["manifestacao_at"] = now.isoformat()
                    row["manifestacao_deadline"] = (
                        now + timedelta(days=180)
                    ).isoformat()

                    sb.table("documents").upsert(
                        row, on_conflict="tenant_id,chave_acesso"
                    ).execute()

                    # Mark queue entry as fetched
                    sb.table("nfe_ciencia_queue").update({
                        "xml_fetched": True,
                        "xml_fetched_at": now.isoformat(),
                    }).eq("id", entry["id"]).execute()

                    total_fetched += 1
                    logger.info(
                        "nfe_fetch_xml: XML salvo chave=%s nsu=%s",
                        chave, full_doc.nsu,
                    )
                else:
                    # _build_document_row returned None (event XML, not a doc)
                    # Mark as fetched to avoid infinite retry
                    sb.table("nfe_ciencia_queue").update({
                        "xml_fetched": True,
                        "xml_fetched_at": datetime.now(timezone.utc).isoformat(),
                        "ultimo_erro": "XML era evento SEFAZ, nao documento fiscal",
                    }).eq("id", entry["id"]).execute()
            else:
                # Not found yet -- SEFAZ still processing
                new_tentativas = entry["tentativas"] + 1
                update_data: dict = {
                    "tentativas": new_tentativas,
                    "ultimo_erro": "procNFe nao encontrado na resposta SEFAZ",
                }

                if new_tentativas >= _MAX_XML_FETCH_ATTEMPTS:
                    update_data["ultimo_erro"] = (
                        f"Maximo de {_MAX_XML_FETCH_ATTEMPTS} tentativas atingido. "
                        "procNFe nunca retornado pela SEFAZ."
                    )
                    logger.error(
                        "nfe_fetch_xml: max tentativas atingido chave=%s "
                        "tenant=%s (tentativas=%d)",
                        chave, tenant_id, new_tentativas,
                    )

                sb.table("nfe_ciencia_queue").update(
                    update_data
                ).eq("id", entry["id"]).execute()

                total_failed += 1
                logger.info(
                    "nfe_fetch_xml: chave=%s nao encontrada, "
                    "tentativa %d/%d",
                    chave, new_tentativas, _MAX_XML_FETCH_ATTEMPTS,
                )

        # Rate limiting between certificates
        time.sleep(1)

    logger.info(
        "nfe_fetch_xml: rodada finalizada — %d XMLs salvos, %d pendentes/falhos",
        total_fetched, total_failed,
    )
