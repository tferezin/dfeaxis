"""Endpoints de polling manual e logs."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from db.supabase import get_supabase_client
from middleware.lgpd import mask_cnpj
from middleware.security import verify_jwt_or_api_key, verify_jwt_with_trial
from models.schemas import (
    NfeCnpjRequest,
    NfeResumosResponse,
    NfeRetryCienciaResponse,
    NfeXmlCompletoResponse,
    PollingTipoResult,
    PollingTriggerRequest,
    PollingTriggerResponse,
)
from scheduler.polling_job import (
    _build_document_row,
    _get_pfx_password,
    _normalize_pfx_blob,
    _poll_single_detailed,
)
from services.manifestacao import manifestacao_service
from services.nsu_controller import nsu_controller
from services.sefaz_client import sefaz_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/polling/trigger", response_model=PollingTriggerResponse)
async def trigger_polling(
    body: PollingTriggerRequest,
    auth: dict = Depends(verify_jwt_or_api_key),
):
    """Dispara polling on-demand pro CNPJ. Aceita JWT Bearer (dashboard
    nativo) ou X-API-Key (ERP externo, padrão SAP DRC/TOTVS)."""
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Busca certificado
    cert_result = sb.table("certificates").select("*").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", body.cnpj).eq("is_active", True).execute()

    if not cert_result.data:
        raise HTTPException(status_code=404, detail="CNPJ não encontrado")

    cert = cert_result.data[0]

    # Busca tenant data — inclui campos de trial/billing pra enforcement
    tenant = sb.table("tenants").select(
        "id, polling_mode, credits, sefaz_ambiente, "
        "subscription_status, trial_cap, docs_consumidos_trial, "
        "trial_blocked_at, trial_blocked_reason, manifestacao_mode"
    ).eq("id", tenant_id).single().execute()

    total_docs = 0
    results = []
    for tipo in body.tipos:
        if tipo not in ("nfe", "cte", "mdfe", "nfse"):
            continue

        # NFe uses background polling v2 (resumo → ciência → wait → XML).
        # The trigger endpoint does NOT call SEFAZ for NFe; instead it
        # returns the count of already-available docs captured by the
        # background jobs (poll_nfe_resumos + fetch_nfe_xml_completo).
        if tipo == "nfe":
            docs_available = sb.table("documents").select(
                "id", count="exact", head=True,
            ).eq("tenant_id", tenant_id).eq(
                "tipo", "NFE",
            ).eq("status", "available").execute()
            nfe_count = docs_available.count or 0
            result = {
                "tipo": "NFE",
                "status": "background",
                "cstat": "138" if nfe_count > 0 else "137",
                "xmotivo": (
                    f"NFe capturadas via polling automatico. "
                    f"{nfe_count} documentos disponiveis."
                ),
                "docs_found": nfe_count,
                "latency_ms": 0,
                "saved_to_db": nfe_count > 0,
            }
            results.append(result)
            total_docs += nfe_count
            continue

        result = _poll_single_detailed(cert, tipo, tenant.data)
        results.append(result)
        total_docs += result["docs_found"]

    return PollingTriggerResponse(
        status="completed",
        cnpj=body.cnpj,
        tipos=body.tipos,
        docs_found=total_docs,
        results=[PollingTipoResult(**r) for r in results],
    )


@router.post("/polling/nfe-resumos", response_model=NfeResumosResponse)
async def nfe_resumos(
    body: NfeCnpjRequest,
    auth: dict = Depends(verify_jwt_or_api_key),
):
    """Etapa 1 manual: busca resumos NFe na SEFAZ e envia ciencia automatica.

    Reutiliza a logica de nfe_polling_job._poll_resumos_for_cert mas para um
    unico CNPJ on-demand.
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Busca certificado
    cert_result = sb.table("certificates").select("*").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", body.cnpj).eq("is_active", True).execute()

    if not cert_result.data:
        raise HTTPException(status_code=404, detail="CNPJ nao encontrado ou certificado inativo")

    cert = cert_result.data[0]

    # Busca tenant data
    tenant_res = sb.table("tenants").select(
        "id, polling_mode, manifestacao_mode, credits, sefaz_ambiente, "
        "subscription_status, docs_consumidos_trial, trial_cap, "
        "trial_blocked_at, trial_blocked_reason"
    ).eq("id", tenant_id).single().execute()

    if not tenant_res.data:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")

    tenant_data = tenant_res.data
    ambiente = tenant_data.get("sefaz_ambiente", "2")

    pfx_password = _get_pfx_password(cert["id"], tenant_id)
    if not pfx_password:
        raise HTTPException(status_code=400, detail="Senha do certificado nao encontrada")

    pfx_encrypted, pfx_iv = _normalize_pfx_blob(
        cert["pfx_encrypted"], cert["pfx_iv"]
    )

    # Get current NSU cursor (optionally reset)
    if body.force_reset_nsu:
        ult_nsu = "000000000000000"
        nsu_controller.update_cursor(cert["id"], "nfe", ambiente, ult_nsu)
        nsu_controller.update_last_nsu(cert["id"], "nfe", ult_nsu)
        logger.info("nfe-resumos: NSU resetado para %s (force_reset_nsu=true)", ult_nsu)
    else:
        try:
            ult_nsu = nsu_controller.get_cursor(cert["id"], "nfe", ambiente)
        except Exception:
            ult_nsu = cert.get("last_nsu_nfe", "000000000000000")

    # Call SEFAZ DistDFe — com auto-retry se 656 por cursor desatualizado
    def _call_sefaz(nsu: str):
        return sefaz_client.consultar_distribuicao(
            cnpj=body.cnpj, tipo="nfe", ult_nsu=nsu,
            pfx_encrypted=pfx_encrypted, pfx_iv=pfx_iv,
            tenant_id=tenant_id, pfx_password=pfx_password,
            ambiente=ambiente,
        )

    try:
        response = _call_sefaz(ult_nsu)
    except Exception as exc:
        logger.error(
            "nfe-resumos: SEFAZ call failed cnpj=%s: %s",
            mask_cnpj(body.cnpj), exc,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Erro na consulta SEFAZ: {type(exc).__name__}: {exc}",
        )

    # Se 656 com cursor diferente: corrige e retenta automaticamente
    if response.cstat == "656" and response.ult_nsu and response.ult_nsu != ult_nsu:
        corrected_nsu = response.ult_nsu
        logger.warning(
            "nfe-resumos: 656 detectado (cursor %s desatualizado), "
            "corrigindo para %s e retentando",
            ult_nsu, corrected_nsu,
        )
        nsu_controller.update_cursor(cert["id"], "nfe", ambiente, corrected_nsu)
        nsu_controller.update_last_nsu(cert["id"], "nfe", corrected_nsu)
        ult_nsu = corrected_nsu

        try:
            response = _call_sefaz(corrected_nsu)
        except Exception as exc:
            logger.error(
                "nfe-resumos: retry after 656 fix failed cnpj=%s: %s",
                mask_cnpj(body.cnpj), exc,
            )
            raise HTTPException(
                status_code=502,
                detail=f"Erro na consulta SEFAZ (retry): {type(exc).__name__}: {exc}",
            )

    docs = list(response.documents)
    results = []
    resumos_found = 0
    ciencia_sent = 0
    completos_found = 0

    for doc in docs:
        is_resumo = doc.schema.startswith("res")

        if is_resumo:
            resumos_found += 1

            # Filtro: se o CNPJ na chave (pos 6:20) é o nosso, somos o emitente — skip ciência
            cnpj_emitente = doc.chave[6:20] if len(doc.chave) >= 20 else ""
            if cnpj_emitente == body.cnpj:
                results.append({
                    "chave": doc.chave,
                    "nsu": doc.nsu,
                    "tipo": "resumo",
                    "status": "skipped_emitente",
                    "detail": "NF-e emitida pelo proprio CNPJ — ciencia nao aplicavel",
                })
                continue

            # Enqueue + send ciencia
            try:
                sb.table("nfe_ciencia_queue").upsert(
                    {
                        "tenant_id": tenant_id,
                        "certificate_id": cert["id"],
                        "cnpj": body.cnpj,
                        "chave_acesso": doc.chave,
                        "nsu": doc.nsu,
                    },
                    on_conflict="tenant_id,chave_acesso",
                ).execute()
            except Exception as exc:
                results.append({
                    "chave": doc.chave,
                    "nsu": doc.nsu,
                    "tipo": "resumo",
                    "status": "error",
                    "detail": f"Falha ao enfileirar: {exc}",
                })
                continue

            # Send ciencia unless manual_only
            if tenant_data.get("manifestacao_mode") == "manual_only":
                results.append({
                    "chave": doc.chave,
                    "nsu": doc.nsu,
                    "tipo": "resumo",
                    "status": "enqueued",
                    "detail": "Enfileirado (manifestacao_mode=manual_only, ciencia nao enviada)",
                })
                continue

            # manifestacao_service expects bytes; _normalize_pfx_blob may return str for v2
            _pfx_enc = pfx_encrypted if isinstance(pfx_encrypted, bytes) else pfx_encrypted.encode("utf-8") if isinstance(pfx_encrypted, str) else pfx_encrypted
            _pfx_iv = pfx_iv if pfx_iv is None or isinstance(pfx_iv, bytes) else bytes(pfx_iv)
            try:
                manif_result = manifestacao_service.enviar_evento(
                    chave_acesso=doc.chave,
                    cnpj=body.cnpj,
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
                    "cstat": manif_result.cstat,
                    "xmotivo": manif_result.xmotivo,
                    "protocolo": manif_result.protocolo,
                    "latency_ms": manif_result.latency_ms,
                    "source": "dashboard",
                }).execute()

                if manif_result.success:
                    sb.table("nfe_ciencia_queue").update({
                        "ciencia_enviada": True,
                        "ciencia_enviada_at": datetime.now(timezone.utc).isoformat(),
                        "ciencia_cstat": manif_result.cstat,
                    }).eq("tenant_id", tenant_id).eq(
                        "chave_acesso", doc.chave,
                    ).execute()

                    ciencia_sent += 1
                    results.append({
                        "chave": doc.chave,
                        "nsu": doc.nsu,
                        "tipo": "resumo",
                        "status": "ciencia_ok",
                        "cstat": manif_result.cstat,
                        "xmotivo": manif_result.xmotivo,
                    })
                else:
                    sb.table("nfe_ciencia_queue").update({
                        "ciencia_cstat": manif_result.cstat,
                        "ultimo_erro": f"ciencia falhou: cstat={manif_result.cstat} {manif_result.xmotivo}",
                        "tentativas": 1,
                    }).eq("tenant_id", tenant_id).eq(
                        "chave_acesso", doc.chave,
                    ).execute()

                    results.append({
                        "chave": doc.chave,
                        "nsu": doc.nsu,
                        "tipo": "resumo",
                        "status": "ciencia_failed",
                        "cstat": manif_result.cstat,
                        "xmotivo": manif_result.xmotivo,
                    })
            except Exception as exc:
                results.append({
                    "chave": doc.chave,
                    "nsu": doc.nsu,
                    "tipo": "resumo",
                    "status": "error",
                    "detail": f"Ciencia exception: {type(exc).__name__}: {exc}",
                })

            time.sleep(0.5)
        else:
            # procNFe (full XML already available)
            completos_found += 1
            row = _build_document_row(
                tenant_id=tenant_id,
                cnpj=body.cnpj,
                doc=doc,
                is_resumo=False,
                doc_status="available",
                manif_status="ciencia",
            )
            if row is not None:
                sb.table("documents").upsert(
                    row, on_conflict="tenant_id,chave_acesso"
                ).execute()
                results.append({
                    "chave": doc.chave,
                    "nsu": doc.nsu,
                    "tipo": "procNFe",
                    "status": "saved",
                })
            else:
                results.append({
                    "chave": doc.chave,
                    "nsu": doc.nsu,
                    "tipo": "evento",
                    "status": "skipped",
                    "detail": "Evento SEFAZ, nao documento fiscal",
                })

    # Advance NSU cursor
    if docs:
        nsu_controller.update_cursor(
            cert["id"], "nfe", ambiente, response.ult_nsu,
            response.max_nsu or response.ult_nsu,
        )
        nsu_controller.update_last_nsu(cert["id"], "nfe", response.ult_nsu)

    # Log
    sb.table("polling_log").insert({
        "tenant_id": tenant_id,
        "cnpj": body.cnpj,
        "tipo": "nfe",
        "triggered_by": "nfe-resumos-manual",
        "status": "success" if response.cstat in ("137", "138") else "error",
        "docs_found": len(docs),
        "ult_nsu": response.ult_nsu,
        "latency_ms": response.latency_ms,
        "error_message": response.xmotivo if response.cstat not in ("137", "138") else None,
    }).execute()

    return NfeResumosResponse(
        resumos_found=resumos_found,
        ciencia_sent=ciencia_sent,
        completos_found=completos_found,
        results=results,
        sefaz_cstat=response.cstat,
        sefaz_xmotivo=response.xmotivo,
        ult_nsu_used=ult_nsu,
        ult_nsu_returned=response.ult_nsu,
        max_nsu=response.max_nsu,
        total_docs_in_response=len(docs),
    )


@router.post("/polling/nfe-retry-ciencia", response_model=NfeRetryCienciaResponse)
async def nfe_retry_ciencia(
    body: NfeCnpjRequest,
    auth: dict = Depends(verify_jwt_or_api_key),
):
    """Reenvia ciencia para resumos na fila onde ciencia falhou.

    NAO chama SEFAZ DistDFe (evita 656). Apenas envia manifestacao
    (RecepcaoEvento) para as entradas pendentes na nfe_ciencia_queue.
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Busca certificado
    cert_result = sb.table("certificates").select("*").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", body.cnpj).eq("is_active", True).execute()

    if not cert_result.data:
        raise HTTPException(status_code=404, detail="CNPJ nao encontrado")

    cert = cert_result.data[0]

    # Tenant data
    tenant_res = sb.table("tenants").select(
        "id, sefaz_ambiente"
    ).eq("id", tenant_id).single().execute()

    ambiente = tenant_res.data.get("sefaz_ambiente", "2") if tenant_res.data else "2"

    pfx_password = _get_pfx_password(cert["id"], tenant_id)
    if not pfx_password:
        raise HTTPException(status_code=400, detail="Senha do certificado nao encontrada")

    pfx_encrypted, pfx_iv = _normalize_pfx_blob(
        cert["pfx_encrypted"], cert["pfx_iv"]
    )

    # Busca entradas na fila onde ciencia NAO foi enviada
    queue_result = sb.table("nfe_ciencia_queue").select("*").eq(
        "tenant_id", tenant_id,
    ).eq("cnpj", body.cnpj).eq(
        "ciencia_enviada", False,
    ).execute()

    if not queue_result.data:
        return NfeRetryCienciaResponse(
            pending_in_queue=0,
            results=[{"status": "empty", "detail": "Nenhuma entrada pendente na fila de ciencia"}],
        )

    entries = queue_result.data
    results = []
    ciencia_sent = 0
    ciencia_failed = 0

    for entry in entries:
        # Filtro: se CNPJ na chave é o nosso, somos emitente — descartar
        chave = entry["chave_acesso"]
        cnpj_emitente = chave[6:20] if len(chave) >= 20 else ""
        if cnpj_emitente == body.cnpj:
            sb.table("nfe_ciencia_queue").update({
                "ciencia_enviada": True,
                "ciencia_enviada_at": datetime.now(timezone.utc).isoformat(),
                "ciencia_cstat": "575",
                "xml_fetched": True,
                "xml_fetched_at": datetime.now(timezone.utc).isoformat(),
                "ultimo_erro": "descartado: emitente=nosso CNPJ, ciencia nao aplicavel",
            }).eq("id", entry["id"]).execute()
            ciencia_failed += 1
            results.append({
                "chave": chave,
                "status": "discarded",
                "cstat": "575",
                "xmotivo": "NF-e emitida pelo proprio CNPJ",
            })
            continue

        try:
            manif_result = manifestacao_service.enviar_evento(
                chave_acesso=entry["chave_acesso"],
                cnpj=body.cnpj,
                tipo_evento="210210",
                pfx_encrypted=pfx_encrypted,
                pfx_iv=pfx_iv,
                tenant_id=tenant_id,
                pfx_password=pfx_password,
                ambiente=ambiente,
            )

            # cStats de rejeição permanente — descartar da fila
            _DISCARD_CSTATS = {"575", "596"}

            # PRIMEIRO atualiza a queue, DEPOIS faz audit (audit pode falhar por constraint)
            if manif_result.success:
                sb.table("nfe_ciencia_queue").update({
                    "ciencia_enviada": True,
                    "ciencia_enviada_at": datetime.now(timezone.utc).isoformat(),
                    "ciencia_cstat": manif_result.cstat,
                    "ultimo_erro": None,
                }).eq("id", entry["id"]).execute()

                ciencia_sent += 1
                results.append({
                    "chave": entry["chave_acesso"],
                    "status": "ciencia_ok",
                    "cstat": manif_result.cstat,
                    "xmotivo": manif_result.xmotivo,
                })
            elif manif_result.cstat in _DISCARD_CSTATS:
                # Rejeição permanente — marcar como descartado
                sb.table("nfe_ciencia_queue").update({
                    "ciencia_enviada": True,
                    "ciencia_enviada_at": datetime.now(timezone.utc).isoformat(),
                    "ciencia_cstat": manif_result.cstat,
                    "xml_fetched": True,
                    "xml_fetched_at": datetime.now(timezone.utc).isoformat(),
                    "ultimo_erro": f"descartado: cstat={manif_result.cstat} {manif_result.xmotivo}",
                }).eq("id", entry["id"]).execute()

                ciencia_failed += 1
                results.append({
                    "chave": entry["chave_acesso"],
                    "status": "discarded",
                    "cstat": manif_result.cstat,
                    "xmotivo": manif_result.xmotivo,
                })
            else:
                sb.table("nfe_ciencia_queue").update({
                    "ciencia_cstat": manif_result.cstat,
                    "ultimo_erro": f"ciencia falhou: cstat={manif_result.cstat} {manif_result.xmotivo}",
                }).eq("id", entry["id"]).execute()

                ciencia_failed += 1
                results.append({
                    "chave": entry["chave_acesso"],
                    "status": "ciencia_failed",
                    "cstat": manif_result.cstat,
                    "xmotivo": manif_result.xmotivo,
                })
        except Exception as exc:
            err_msg = str(exc) or repr(exc)
            ciencia_failed += 1
            results.append({
                "chave": entry["chave_acesso"],
                "status": "error",
                "detail": f"{type(exc).__name__}: {err_msg}",
            })

        # Audit (best-effort — não aborta se falhar)
        try:
            sb.table("manifestacao_events").insert({
                "tenant_id": tenant_id,
                "document_id": None,
                "chave_acesso": entry["chave_acesso"],
                "tipo_evento": "210210",
                "cstat": manif_result.cstat if 'manif_result' in dir() else "999",
                "xmotivo": manif_result.xmotivo if 'manif_result' in dir() else "",
                "protocolo": manif_result.protocolo if 'manif_result' in dir() else None,
                "latency_ms": manif_result.latency_ms if 'manif_result' in dir() else 0,
                "source": "dashboard",
            }).execute()
        except Exception:
            pass  # Audit failure não deve bloquear o fluxo

        time.sleep(0.5)

    return NfeRetryCienciaResponse(
        pending_in_queue=len(entries),
        ciencia_sent=ciencia_sent,
        ciencia_failed=ciencia_failed,
        results=results,
    )


@router.post("/polling/nfe-reset-fila")
async def nfe_reset_fila(
    body: NfeCnpjRequest,
    auth: dict = Depends(verify_jwt_or_api_key),
):
    """Limpa a fila de ciência para reprocessar.

    NÃO reseta o cursor NSU — a SEFAZ rejeita permanentemente (656)
    qualquer consulta com NSU inferior ao último retornado.
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Deleta entries da fila
    deleted = sb.table("nfe_ciencia_queue").delete().eq(
        "tenant_id", tenant_id
    ).eq("cnpj", body.cnpj).execute()
    deleted_count = len(deleted.data) if deleted.data else 0

    return {
        "status": "ok",
        "deleted_from_queue": deleted_count,
        "message": f"Fila limpa ({deleted_count} entries). Cursor NSU mantido.",
    }


@router.post("/polling/nfe-xml-completo", response_model=NfeXmlCompletoResponse)
async def nfe_xml_completo(
    body: NfeCnpjRequest,
    auth: dict = Depends(verify_jwt_or_api_key),
):
    """Etapa 2 manual: busca XMLs completos para resumos ja com ciencia enviada.

    Processa apenas as entradas na nfe_ciencia_queue deste CNPJ onde
    ciencia_enviada=true e xml_fetched=false.
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Busca certificado
    cert_result = sb.table("certificates").select("*").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", body.cnpj).eq("is_active", True).execute()

    if not cert_result.data:
        raise HTTPException(status_code=404, detail="CNPJ nao encontrado ou certificado inativo")

    cert = cert_result.data[0]

    # Busca tenant data
    tenant_res = sb.table("tenants").select(
        "id, sefaz_ambiente"
    ).eq("id", tenant_id).single().execute()

    if not tenant_res.data:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")

    ambiente = tenant_res.data.get("sefaz_ambiente", "2")

    pfx_password = _get_pfx_password(cert["id"], tenant_id)
    if not pfx_password:
        raise HTTPException(status_code=400, detail="Senha do certificado nao encontrada")

    pfx_encrypted, pfx_iv = _normalize_pfx_blob(
        cert["pfx_encrypted"], cert["pfx_iv"]
    )

    # Fetch pending queue entries for this CNPJ
    queue_result = sb.table("nfe_ciencia_queue").select("*").eq(
        "tenant_id", tenant_id,
    ).eq(
        "cnpj", body.cnpj,
    ).eq(
        "ciencia_enviada", True,
    ).eq(
        "xml_fetched", False,
    ).execute()

    if not queue_result.data:
        return NfeXmlCompletoResponse(
            xml_found=0, saved=0, still_pending=0,
            results=[{
                "status": "empty",
                "detail": "Nenhum resumo com ciencia processada aguardando XML. Execute a Etapa 1 primeiro.",
            }],
        )

    entries = queue_result.data

    results = []
    saved = 0
    still_pending = 0

    # Busca XML completo por chave (consChNFe) — sem depender do cursor NSU
    for entry in entries:
        chave = entry["chave_acesso"]

        try:
            response = sefaz_client.consultar_por_chave(
                cnpj=body.cnpj,
                chave_acesso=chave,
                pfx_encrypted=pfx_encrypted,
                pfx_iv=pfx_iv,
                tenant_id=tenant_id,
                pfx_password=pfx_password,
                ambiente=ambiente,
            )
        except Exception as exc:
            logger.error(
                "nfe-xml-completo: consChNFe failed chave=%s: %s",
                chave[:20], exc,
            )
            still_pending += 1
            sb.table("nfe_ciencia_queue").update({
                "tentativas": entry.get("tentativas", 0) + 1,
                "ultimo_erro": f"consChNFe error: {type(exc).__name__}: {exc}",
            }).eq("id", entry["id"]).execute()
            results.append({
                "chave": chave,
                "status": "error",
                "detail": f"{type(exc).__name__}: {exc}",
            })
            time.sleep(1)
            continue

        # Procura procNFe (XML completo, não resumo) na resposta
        full_doc = None
        for doc in response.documents:
            if not doc.schema.startswith("res"):
                full_doc = doc
                break

        if full_doc:
            row = _build_document_row(
                tenant_id=tenant_id,
                cnpj=body.cnpj,
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

                # Verifica se doc já existe (pra diferenciar novo vs atualizado)
                existing = sb.table("documents").select("id", count="exact", head=True).eq(
                    "tenant_id", tenant_id
                ).eq("chave_acesso", chave).execute()
                is_new = (existing.count or 0) == 0

                sb.table("documents").upsert(
                    row, on_conflict="tenant_id,chave_acesso"
                ).execute()

                sb.table("nfe_ciencia_queue").update({
                    "xml_fetched": True,
                    "xml_fetched_at": now.isoformat(),
                }).eq("id", entry["id"]).execute()

                saved += 1
                results.append({
                    "chave": chave,
                    "nsu": full_doc.nsu,
                    "status": "saved" if is_new else "updated",
                })
            else:
                sb.table("nfe_ciencia_queue").update({
                    "xml_fetched": True,
                    "xml_fetched_at": datetime.now(timezone.utc).isoformat(),
                    "ultimo_erro": "XML era evento SEFAZ, nao documento fiscal",
                }).eq("id", entry["id"]).execute()
                results.append({
                    "chave": chave,
                    "status": "skipped",
                    "detail": "Evento SEFAZ, nao documento fiscal",
                })
        else:
            still_pending += 1
            new_tentativas = entry.get("tentativas", 0) + 1
            sb.table("nfe_ciencia_queue").update({
                "tentativas": new_tentativas,
                "ultimo_erro": f"procNFe nao retornado (cstat={response.cstat}: {response.xmotivo})",
            }).eq("id", entry["id"]).execute()
            results.append({
                "chave": chave,
                "status": "pending",
                "tentativas": new_tentativas,
                "detail": f"SEFAZ cstat={response.cstat}: {response.xmotivo}",
            })

        time.sleep(1)  # Rate limit entre chamadas

    # Log
    sb.table("polling_log").insert({
        "tenant_id": tenant_id,
        "cnpj": body.cnpj,
        "tipo": "nfe",
        "triggered_by": "nfe-xml-completo-manual",
        "status": "success",
        "docs_found": saved,
    }).execute()

    return NfeXmlCompletoResponse(
        xml_found=saved + still_pending,
        saved=saved,
        still_pending=still_pending,
        results=results,
    )


@router.get("/logs/stream")
async def stream_logs(auth: dict = Depends(verify_jwt_with_trial)):
    """Server-Sent Events em tempo real dos eventos de polling."""
    tenant_id = auth["tenant_id"]

    async def event_generator() -> AsyncGenerator[str, None]:
        sb = get_supabase_client()
        last_id = None

        while True:
            query = sb.table("polling_log").select("*").eq(
                "tenant_id", tenant_id
            ).order("created_at", desc=True).limit(10)

            if last_id:
                query = query.gt("id", last_id)

            result = query.execute()

            for log in reversed(result.data):
                event_data = json.dumps({
                    "id": log["id"],
                    "cnpj": log.get("cnpj"),
                    "tipo": log.get("tipo"),
                    "status": log.get("status"),
                    "docs_found": log.get("docs_found", 0),
                    "latency_ms": log.get("latency_ms"),
                    "error": log.get("error_message"),
                    "timestamp": log.get("created_at"),
                })
                yield f"data: {event_data}\n\n"
                last_id = log["id"]

            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
