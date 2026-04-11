"""Scheduler APScheduler para polling automático na SEFAZ."""

import base64
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from db.supabase import get_supabase_client
from middleware.lgpd import mask_cnpj
from services.cert_manager import decrypt_password
from services.manifestacao import manifestacao_service
from services.sefaz_client import sefaz_client
from services.nfse_client import nfse_client
from services.nsu_controller import nsu_controller

logger = logging.getLogger(__name__)

TIPOS = ["nfe", "cte", "mdfe", "nfse"]


def polling_job():
    """Job executado a cada 15 min: consulta SEFAZ para todos os certificados ativos."""
    sb = get_supabase_client()

    # Busca todos os certificados ativos com polling automático
    result = sb.table("certificates").select(
        "id, tenant_id, cnpj, pfx_encrypted, pfx_iv, "
        "last_nsu_nfe, last_nsu_cte, last_nsu_mdfe, last_nsu_nfse"
    ).eq("is_active", True).execute()

    if not result.data:
        logger.debug("Nenhum certificado ativo para polling")
        return

    # Cache tenants por id para não refazer query várias vezes por run
    blocked_in_run: set[str] = set()

    for cert in result.data:
        tenant_id = cert["tenant_id"]
        if tenant_id in blocked_in_run:
            continue

        tenant = sb.table("tenants").select(
            "id, polling_mode, manifestacao_mode, credits, sefaz_ambiente, "
            "subscription_status, docs_consumidos_trial, trial_cap, "
            "trial_blocked_at, trial_blocked_reason"
        ).eq("id", tenant_id).single().execute()

        if not tenant.data:
            continue

        tenant_data = tenant.data

        # Skip tenants expirados/cancelados/bloqueados
        status = tenant_data.get("subscription_status")
        if status in ("expired", "cancelled"):
            logger.info(f"Tenant {tenant_id} status={status}, pulando polling")
            blocked_in_run.add(tenant_id)
            continue
        if tenant_data.get("trial_blocked_at"):
            logger.info(
                f"Tenant {tenant_id} trial bloqueado "
                f"(reason={tenant_data.get('trial_blocked_reason')}), pulando polling"
            )
            blocked_in_run.add(tenant_id)
            continue

        if tenant_data.get("polling_mode") != "auto":
            continue

        if tenant_data.get("credits", 0) <= 0:
            logger.info(
                f"Tenant {tenant_id} sem créditos, pulando polling"
            )
            continue

        for tipo in TIPOS:
            _poll_single(cert, tipo, tenant_data)
            # Se o trial foi bloqueado durante o processamento, aborta
            # o restante dos tipos para este tenant neste run.
            if tenant_id in blocked_in_run:
                break
            # Re-lê flag de bloqueio do cache local (atualizada por _poll_single)
            if tenant_data.get("_trial_blocked_now"):
                blocked_in_run.add(tenant_id)
                break


def _poll_single_detailed(cert: dict, tipo: str, tenant_data: dict) -> dict:
    """Executa polling e retorna detalhes completos para a UI."""
    if tipo == "nfse":
        docs = _poll_nfse(cert, tenant_data)
        return {
            "tipo": tipo.upper(),
            "status": "success",
            "cstat": "138" if docs > 0 else "137",
            "xmotivo": "documento localizado." if docs > 0 else "Nenhum documento localizado",
            "docs_found": docs,
            "latency_ms": 0,
            "saved_to_db": docs > 0,
        }

    sb = get_supabase_client()
    tenant_id = cert["tenant_id"]
    cnpj = cert["cnpj"]
    ult_nsu = cert.get(f"last_nsu_{tipo}", "000000000000000")
    pfx_password = _get_pfx_password(cert["id"], tenant_id)

    if not pfx_password:
        return {
            "tipo": tipo.upper(), "status": "error", "cstat": "999",
            "xmotivo": "", "docs_found": 0, "latency_ms": 0,
            "error": "Senha do certificado não encontrada", "saved_to_db": False,
        }

    # pfx_encrypted comes from Supabase as hex string
    # v2 format stored as text: "v2:<hex>" — pass as-is to sefaz_client
    # Legacy BYTEA comes as "\x<hex>" — convert to bytes
    pfx_encrypted = cert["pfx_encrypted"]
    pfx_iv = cert["pfx_iv"]

    # If stored as text "v2:..." pass as string (sefaz_client handles it)
    # If stored as Supabase BYTEA "\x..." convert to bytes
    if isinstance(pfx_encrypted, str) and not pfx_encrypted.startswith("v2:"):
        # Legacy BYTEA hex from Supabase: "\x<hex>"
        clean = pfx_encrypted.replace("\\x", "").replace("\\\\x", "")
        # Check if it's actually v2 encoded as hex bytes
        try:
            decoded = bytes.fromhex(clean)
            decoded_str = decoded.decode("ascii", errors="ignore")
            if decoded_str.startswith("v2:"):
                pfx_encrypted = decoded_str
            else:
                pfx_encrypted = decoded
        except (ValueError, UnicodeDecodeError):
            pfx_encrypted = clean

    if pfx_iv and isinstance(pfx_iv, str):
        pfx_iv = bytes.fromhex(pfx_iv.replace("\\x", "").replace("\\\\x", ""))

    ambiente = tenant_data.get("sefaz_ambiente", "2")

    try:
        response = sefaz_client.consultar_distribuicao(
            cnpj=cnpj, tipo=tipo, ult_nsu=ult_nsu,
            pfx_encrypted=pfx_encrypted, pfx_iv=pfx_iv,
            tenant_id=tenant_id, pfx_password=pfx_password,
            ambiente=ambiente,
        )

        docs_found = len(response.documents)
        saved = False

        # Log
        sb.table("polling_log").insert({
            "tenant_id": tenant_id, "cnpj": cnpj, "tipo": tipo,
            "triggered_by": "manual",
            "status": "success" if response.cstat in ("137", "138") else "error",
            "docs_found": docs_found, "ult_nsu": response.ult_nsu,
            "latency_ms": response.latency_ms,
            "error_message": response.xmotivo if response.cstat not in ("137", "138") else None,
        }).execute()

        if docs_found > 0:
            # Debit credits (non-blocking — save docs even if credits fail)
            try:
                sb.rpc("debit_credits", {
                    "p_tenant_id": tenant_id,
                    "p_amount": -docs_found,
                    "p_description": f"Captura manual {tipo.upper()} CNPJ {mask_cnpj(cnpj)}: {docs_found} docs",
                }).execute()
            except Exception as credit_err:
                logger.warning(f"Credits debit skipped (non-blocking): {credit_err}")

            # Save documents
            for doc in response.documents:
                is_resumo = doc.schema.startswith("res")
                is_nfe = tipo == "nfe"
                if is_resumo and is_nfe:
                    manif_status = "pendente"
                    doc_status = "pending_manifestacao"
                elif is_resumo:
                    manif_status = "nao_aplicavel"
                    doc_status = "available"
                else:
                    manif_status = "nao_aplicavel" if not is_nfe else None
                    doc_status = "available"

                sb.table("documents").upsert({
                    "tenant_id": tenant_id, "cnpj": cnpj,
                    "tipo": doc.tipo, "chave_acesso": doc.chave,
                    "nsu": doc.nsu,
                    "xml_content": doc.xml_content if not is_resumo else None,
                    "status": doc_status, "is_resumo": is_resumo,
                    "manifestacao_status": manif_status,
                }, on_conflict="tenant_id,chave_acesso").execute()

            saved = True
            nsu_controller.update_last_nsu(cert["id"], tipo, response.ult_nsu)

        return {
            "tipo": tipo.upper(), "status": "success", "cstat": response.cstat,
            "xmotivo": response.xmotivo, "docs_found": docs_found,
            "latency_ms": response.latency_ms, "saved_to_db": saved,
        }

    except Exception as e:
        import traceback
        logger.error(f"Erro polling {mask_cnpj(cnpj)}/{tipo}: {e}\n{traceback.format_exc()}")
        sb.table("polling_log").insert({
            "tenant_id": tenant_id, "cnpj": cnpj, "tipo": tipo,
            "triggered_by": "manual", "status": "error",
            "error_message": str(e),
        }).execute()
        return {
            "tipo": tipo.upper(), "status": "error", "cstat": "999",
            "xmotivo": "", "docs_found": 0, "latency_ms": 0,
            "error": str(e), "saved_to_db": False,
        }


def _poll_single(cert: dict, tipo: str, tenant_data: dict) -> int:
    """Executa polling de um único CNPJ/tipo. Retorna quantidade de docs encontrados."""
    # NFS-e usa ADN (REST) em vez de SEFAZ (SOAP)
    if tipo == "nfse":
        return _poll_nfse(cert, tenant_data)

    sb = get_supabase_client()
    tenant_id = cert["tenant_id"]
    cnpj = cert["cnpj"]
    ambiente = tenant_data.get("sefaz_ambiente", "2")

    # Cursor agora vem de nsu_state (por cert/tipo/ambiente)
    ult_nsu = nsu_controller.get_cursor(cert["id"], tipo, ambiente)

    pfx_password = _get_pfx_password(cert["id"], tenant_id)
    if not pfx_password:
        return 0

    # Supabase retorna BYTEA como string hex com prefixo \x
    pfx_encrypted = cert["pfx_encrypted"]
    pfx_iv = cert["pfx_iv"]
    if isinstance(pfx_encrypted, str):
        pfx_encrypted = bytes.fromhex(pfx_encrypted.replace("\\x", ""))
    if isinstance(pfx_iv, str):
        pfx_iv = bytes.fromhex(pfx_iv.replace("\\x", ""))

    try:
        response = sefaz_client.consultar_distribuicao(
            cnpj=cnpj,
            tipo=tipo,
            ult_nsu=ult_nsu,
            pfx_encrypted=pfx_encrypted,
            pfx_iv=pfx_iv,
            tenant_id=tenant_id,
            pfx_password=pfx_password,
            ambiente=ambiente,
        )

        docs_found = len(response.documents)

        # Log do polling
        sb.table("polling_log").insert({
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "tipo": tipo,
            "triggered_by": "scheduler",
            "status": "success" if response.cstat in ("137", "138") else "error",
            "docs_found": docs_found,
            "ult_nsu": response.ult_nsu,
            "latency_ms": response.latency_ms,
            "error_message": response.xmotivo if response.cstat not in ("137", "138") else None,
        }).execute()

        if docs_found == 0:
            # Nenhum doc: mesmo assim atualiza max_nsu/pendentes para visibilidade
            if response.max_nsu:
                nsu_controller.update_pending_count(
                    cert["id"], tipo, ambiente, response.max_nsu
                )
            return 0

        # --- Trial cap enforcement ---------------------------------------
        # Se tenant é trial, limita quantos docs podem ser persistidos nesta
        # rodada ao remaining = trial_cap - docs_consumidos_trial.
        is_trial = tenant_data.get("subscription_status") == "trial"
        docs_to_save = list(response.documents)
        # Ordena por NSU asc para garantir corte determinístico
        try:
            docs_to_save.sort(key=lambda d: int(d.nsu) if d.nsu else 0)
        except Exception:
            pass

        if is_trial:
            trial_cap = int(tenant_data.get("trial_cap") or 500)
            consumed = int(tenant_data.get("docs_consumidos_trial") or 0)
            remaining = max(trial_cap - consumed, 0)

            if remaining == 0:
                # Cap já atingido antes deste batch: não salva, não avança cursor,
                # apenas registra pendentes e marca tenant como bloqueado no run.
                logger.info(
                    f"Tenant {tenant_id} trial cap atingido — {docs_found} docs "
                    f"{tipo.upper()} não serão capturados (remaining=0)"
                )
                if response.max_nsu:
                    nsu_controller.update_pending_count(
                        cert["id"], tipo, ambiente, response.max_nsu
                    )
                tenant_data["_trial_blocked_now"] = True
                return 0

            if len(docs_to_save) > remaining:
                logger.info(
                    f"Tenant {tenant_id} trial cap: salvando apenas {remaining}/{len(docs_to_save)} "
                    f"docs {tipo.upper()} (consumed={consumed}, cap={trial_cap})"
                )
                docs_to_save = docs_to_save[:remaining]

        effective_count = len(docs_to_save)
        if effective_count == 0:
            return 0

        # Cursor efetivo = maior NSU realmente salvo (para cortes parciais)
        # Em batch completo, usamos response.ult_nsu retornado pela SEFAZ.
        full_batch_saved = effective_count == len(response.documents)
        if full_batch_saved:
            effective_cursor = response.ult_nsu
        else:
            try:
                effective_cursor = max(
                    docs_to_save,
                    key=lambda d: int(d.nsu) if d.nsu else 0,
                ).nsu or response.ult_nsu
            except Exception:
                effective_cursor = response.ult_nsu

        # Debit credits atomically via RPC (apenas pelos docs efetivamente salvos)
        try:
            result = sb.rpc("debit_credits", {
                "p_tenant_id": tenant_id,
                "p_amount": -effective_count,
                "p_description": f"Polling {tipo.upper()} CNPJ {mask_cnpj(cnpj)}: {effective_count} docs",
            }).execute()
        except Exception as credit_err:
            logger.warning(
                f"Tenant {tenant_id} insufficient credits for {effective_count} docs: {credit_err}"
            )
            return 0

        # Classifica e salva documentos
        # resNFe/resCTe = resumo (precisa manifestação para NF-e)
        # procNFe/procCTe/procMDFe = XML completo
        for doc in docs_to_save:
            is_resumo = doc.schema.startswith("res")
            is_nfe = tipo == "nfe"

            if is_resumo and is_nfe:
                manif_status = "pendente"
                doc_status = "pending_manifestacao"
            elif is_resumo:
                # CT-e/MDF-e resumos — não requer manifestação
                manif_status = "nao_aplicavel"
                doc_status = "available"
            else:
                # XML completo
                manif_status = "nao_aplicavel" if not is_nfe else None
                doc_status = "available"

            sb.table("documents").upsert({
                "tenant_id": tenant_id,
                "cnpj": cnpj,
                "tipo": doc.tipo,
                "chave_acesso": doc.chave,
                "nsu": doc.nsu,
                "xml_content": doc.xml_content if not is_resumo else None,
                "status": doc_status,
                "is_resumo": is_resumo,
                "manifestacao_status": manif_status,
            }, on_conflict="tenant_id,chave_acesso").execute()

        # Se modo auto_ciencia e há resumos NF-e, envia Ciência automaticamente
        if tipo == "nfe" and tenant_data.get("manifestacao_mode") == "auto_ciencia":
            _auto_ciencia(
                docs_to_save,
                cert, tenant_id, pfx_encrypted, pfx_iv, pfx_password,
                ambiente=ambiente,
            )

        # Atualiza cursor no nsu_state (por ambiente). max_nsu vem do response
        # e é o verdadeiro "topo" conhecido na SEFAZ — serve para calcular pendentes.
        max_nsu_eff = response.max_nsu or effective_cursor
        nsu_controller.update_cursor(
            cert["id"], tipo, ambiente, effective_cursor, max_nsu_eff
        )
        # Mantém coluna legada sincronizada (deprecada, mas ainda lida por outros fluxos)
        nsu_controller.update_last_nsu(cert["id"], tipo, effective_cursor)

        # Incrementa contador de trial e bloqueia se atingir cap
        if is_trial:
            try:
                rpc_res = sb.rpc("increment_trial_docs", {
                    "p_tenant_id": tenant_id,
                    "p_count": effective_count,
                }).execute()
                new_count = 0
                if rpc_res.data is not None:
                    # RPC pode retornar int ou [{"...": int}]
                    if isinstance(rpc_res.data, int):
                        new_count = rpc_res.data
                    elif isinstance(rpc_res.data, list) and rpc_res.data:
                        first = rpc_res.data[0]
                        if isinstance(first, dict):
                            new_count = int(next(iter(first.values()), 0) or 0)
                        else:
                            new_count = int(first or 0)
                trial_cap = int(tenant_data.get("trial_cap") or 500)
                tenant_data["docs_consumidos_trial"] = new_count
                if new_count >= trial_cap:
                    logger.info(
                        f"Tenant {tenant_id} atingiu trial_cap={trial_cap} "
                        f"(count={new_count}), bloqueando polling neste run"
                    )
                    tenant_data["_trial_blocked_now"] = True
            except Exception as inc_err:
                logger.warning(
                    f"increment_trial_docs falhou para {tenant_id}: {inc_err}"
                )

        # Detecta gaps
        received_nsus = [d.nsu for d in docs_to_save]
        gaps = nsu_controller.detect_gap(ult_nsu, received_nsus)
        if gaps:
            logger.warning(f"Gaps detectados para {mask_cnpj(cnpj)}/{tipo}: {len(gaps)} NSUs faltantes")

        return effective_count

    except Exception as e:
        logger.error(f"Erro no polling {mask_cnpj(cnpj)}/{tipo}: {e}")
        sb.table("polling_log").insert({
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "tipo": tipo,
            "triggered_by": "scheduler",
            "status": "error",
            "error_message": str(e),
        }).execute()
        return 0


def _poll_nfse(cert: dict, tenant_data: dict) -> int:
    """Executa polling de NFS-e via ADN (REST). Retorna quantidade de docs encontrados."""
    sb = get_supabase_client()
    tenant_id = cert["tenant_id"]
    cnpj = cert["cnpj"]
    ult_nsu = cert.get("last_nsu_nfse", "000000000000000")

    pfx_password = _get_pfx_password(cert["id"], tenant_id)
    if not pfx_password:
        return 0

    pfx_encrypted = cert["pfx_encrypted"]
    pfx_iv = cert["pfx_iv"]
    if isinstance(pfx_encrypted, str):
        pfx_encrypted = bytes.fromhex(pfx_encrypted.replace("\\x", ""))
    if isinstance(pfx_iv, str):
        pfx_iv = bytes.fromhex(pfx_iv.replace("\\x", ""))

    try:
        response = nfse_client.consultar_dps_distribuicao(
            cnpj=cnpj,
            ult_nsu=ult_nsu,
            pfx_encrypted=pfx_encrypted,
            pfx_iv=pfx_iv,
            tenant_id=tenant_id,
            pfx_password=pfx_password,
        )

        docs_found = len(response.documents)

        # Log do polling
        sb.table("polling_log").insert({
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "tipo": "nfse",
            "triggered_by": "scheduler",
            "status": "success" if response.success else "error",
            "docs_found": docs_found,
            "ult_nsu": response.ult_nsu,
            "latency_ms": response.latency_ms,
            "error_message": response.message if not response.success else None,
        }).execute()

        if docs_found == 0:
            return 0

        # Debit credits atomically via RPC
        try:
            sb.rpc("debit_credits", {
                "p_tenant_id": tenant_id,
                "p_amount": -docs_found,
                "p_description": f"Polling NFSE CNPJ {mask_cnpj(cnpj)}: {docs_found} docs",
            }).execute()
        except Exception as credit_err:
            logger.warning(
                f"Tenant {tenant_id} insufficient credits for {docs_found} NFS-e docs: {credit_err}"
            )
            return 0

        # Salva documentos
        for doc in response.documents:
            sb.table("documents").upsert({
                "tenant_id": tenant_id,
                "cnpj": cnpj,
                "tipo": "NFSE",
                "chave_acesso": doc.chave,
                "nsu": doc.nsu,
                "xml_content": doc.xml_content,
                "status": "available",
                "is_resumo": False,
                "manifestacao_status": "nao_aplicavel",
                "codigo_municipio": doc.codigo_municipio,
                "codigo_servico": doc.codigo_servico,
            }, on_conflict="tenant_id,chave_acesso").execute()

        # Atualiza ultimo NSU
        sb.table("certificates").update({
            "last_nsu_nfse": response.ult_nsu,
        }).eq("id", cert["id"]).execute()

        return docs_found

    except Exception as e:
        logger.error(f"Erro no polling NFS-e {mask_cnpj(cnpj)}: {e}")
        sb.table("polling_log").insert({
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "tipo": "nfse",
            "triggered_by": "scheduler",
            "status": "error",
            "error_message": str(e),
        }).execute()
        return 0


def _auto_ciencia(
    documents: list,
    cert: dict,
    tenant_id: str,
    pfx_encrypted: bytes,
    pfx_iv: bytes,
    pfx_password: str,
    ambiente: str = "2",
) -> None:
    """Envia Ciência da Operação (210210) automaticamente para resumos NF-e."""
    sb = get_supabase_client()
    cnpj = cert["cnpj"]

    for doc in documents:
        if not doc.schema.startswith("res"):
            continue

        try:
            result = manifestacao_service.enviar_evento(
                chave_acesso=doc.chave,
                cnpj=cnpj,
                tipo_evento="210210",
                pfx_encrypted=pfx_encrypted,
                pfx_iv=pfx_iv,
                tenant_id=tenant_id,
                pfx_password=pfx_password,
                ambiente=ambiente,
            )

            if result.success:
                sb.table("documents").update({
                    "manifestacao_status": "ciencia",
                    "manifestacao_at": "now()",
                }).eq("tenant_id", tenant_id).eq(
                    "chave_acesso", doc.chave
                ).execute()

            # Registra evento de auditoria
            doc_row = sb.table("documents").select("id").eq(
                "tenant_id", tenant_id
            ).eq("chave_acesso", doc.chave).execute()

            doc_id = doc_row.data[0]["id"] if doc_row.data else None

            sb.table("manifestacao_events").insert({
                "tenant_id": tenant_id,
                "document_id": doc_id,
                "chave_acesso": doc.chave,
                "tipo_evento": "210210",
                "cstat": result.cstat,
                "xmotivo": result.xmotivo,
                "protocolo": result.protocolo,
                "latency_ms": result.latency_ms,
            }).execute()

            logger.info(
                f"Auto-ciência {doc.chave}: cstat={result.cstat} "
                f"{'OK' if result.success else 'FALHA'}"
            )

        except Exception as e:
            logger.error(f"Erro auto-ciência {doc.chave}: {e}")


def _get_pfx_password(cert_id: str, tenant_id: str) -> str | None:
    """Recupera e decifra a senha do .pfx do certificado."""
    sb = get_supabase_client()
    result = sb.table("certificates").select(
        "pfx_password_encrypted"
    ).eq("id", cert_id).execute()

    if result.data and result.data[0].get("pfx_password_encrypted"):
        return decrypt_password(result.data[0]["pfx_password_encrypted"], tenant_id)
    return None


def run_retroactive_job(
    tenant_id: str,
    cnpj: str,
    tipo: str,
    job_id: str,
) -> None:
    """Executa consulta retroativa: faz polling contínuo até esgotar NSUs."""
    sb = get_supabase_client()

    cert_result = sb.table("certificates").select("*").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", cnpj).eq("is_active", True).execute()

    if not cert_result.data:
        sb.table("polling_log").update(
            {"status": "error", "error_message": "Certificado não encontrado"}
        ).eq("job_id", job_id).eq("triggered_by", "retroativo").execute()
        return

    cert = cert_result.data[0]
    tenant = sb.table("tenants").select("id, polling_mode, manifestacao_mode, credits, sefaz_ambiente").eq(
        "id", tenant_id
    ).single().execute()

    if not tenant.data:
        return

    total_docs = 0
    # Loop até não ter mais documentos (cStat != 138)
    max_iterations = 50  # Safety limit
    for _ in range(max_iterations):
        docs = _poll_single(cert, tipo, tenant.data)
        total_docs += docs
        if docs == 0:
            break
        # Refresh cert data to get updated NSU
        cert_result = sb.table("certificates").select("*").eq(
            "id", cert["id"]
        ).execute()
        if cert_result.data:
            cert = cert_result.data[0]

    # Update job status
    sb.table("polling_log").update({
        "status": "success",
        "docs_found": total_docs,
    }).eq("job_id", job_id).eq("triggered_by", "retroativo").execute()


def start_scheduler() -> BackgroundScheduler:
    """Inicia o scheduler APScheduler."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        polling_job,
        "interval",
        minutes=15,
        id="sefaz_polling",
        name="SEFAZ DF-e Polling",
        replace_existing=True,
    )

    # Transactional trial emails — imported lazily so the polling scheduler
    # still starts even if email deps are missing in a dev environment.
    try:
        from scheduler.email_jobs import check_trial_nudges, check_trial_expirations

        scheduler.add_job(
            check_trial_nudges,
            "interval",
            hours=6,
            id="trial_email_nudges",
            name="Trial nudge emails (D-5/D-2/D-1 + 80% cap)",
            replace_existing=True,
        )
        scheduler.add_job(
            check_trial_expirations,
            "interval",
            hours=1,
            id="trial_email_expirations",
            name="Trial expired emails",
            replace_existing=True,
        )
        logger.info(
            "Trial email jobs agendados: nudges a cada 6h, expirations a cada 1h"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível agendar trial email jobs: %s", exc)

    scheduler.start()
    logger.info("Scheduler iniciado: polling a cada 15 minutos")
    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler):
    """Para o scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler parado")
