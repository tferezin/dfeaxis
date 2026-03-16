"""Scheduler APScheduler para polling automático na SEFAZ."""

import base64
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from db.supabase import get_supabase_client
from services.cert_manager import decrypt_password
from services.manifestacao import manifestacao_service
from services.sefaz_client import sefaz_client
from services.nsu_controller import nsu_controller

logger = logging.getLogger(__name__)

TIPOS = ["nfe", "cte", "mdfe"]


def polling_job():
    """Job executado a cada 15 min: consulta SEFAZ para todos os certificados ativos."""
    sb = get_supabase_client()

    # Busca todos os certificados ativos com polling automático
    result = sb.table("certificates").select(
        "id, tenant_id, cnpj, pfx_encrypted, pfx_iv, "
        "last_nsu_nfe, last_nsu_cte, last_nsu_mdfe"
    ).eq("is_active", True).execute()

    if not result.data:
        logger.debug("Nenhum certificado ativo para polling")
        return

    # Busca tenants com polling_mode='auto' e créditos > 0
    for cert in result.data:
        tenant = sb.table("tenants").select(
            "id, polling_mode, manifestacao_mode, credits"
        ).eq("id", cert["tenant_id"]).single().execute()

        if not tenant.data:
            continue

        tenant_data = tenant.data
        if tenant_data.get("polling_mode") != "auto":
            continue

        if tenant_data.get("credits", 0) <= 0:
            logger.info(
                f"Tenant {cert['tenant_id']} sem créditos, pulando polling"
            )
            continue

        for tipo in TIPOS:
            _poll_single(cert, tipo, tenant_data)


def _poll_single(cert: dict, tipo: str, tenant_data: dict) -> int:
    """Executa polling de um único CNPJ/tipo. Retorna quantidade de docs encontrados."""
    sb = get_supabase_client()
    tenant_id = cert["tenant_id"]
    cnpj = cert["cnpj"]
    ult_nsu = cert.get(f"last_nsu_{tipo}", "000000000000000")

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
            return 0

        # Verifica créditos disponíveis
        credits = tenant_data.get("credits", 0)
        if credits < docs_found:
            logger.warning(
                f"Tenant {tenant_id} tem {credits} créditos mas encontrou {docs_found} docs"
            )
            docs_found = credits  # Processa apenas o que tem crédito

        # Classifica e salva documentos
        # resNFe/resCTe = resumo (precisa manifestação para NF-e)
        # procNFe/procCTe/procMDFe = XML completo
        for doc in response.documents[:docs_found]:
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
                response.documents[:docs_found],
                cert, tenant_id, pfx_encrypted, pfx_iv, pfx_password,
            )

        # Debita créditos
        sb.table("tenants").update({
            "credits": credits - docs_found
        }).eq("id", tenant_id).execute()

        sb.table("credit_transactions").insert({
            "tenant_id": tenant_id,
            "amount": -docs_found,
            "description": f"Polling {tipo.upper()} CNPJ {cnpj}: {docs_found} docs",
        }).execute()

        # Atualiza último NSU
        nsu_controller.update_last_nsu(cert["id"], tipo, response.ult_nsu)

        # Detecta gaps
        received_nsus = [d.nsu for d in response.documents]
        gaps = nsu_controller.detect_gap(ult_nsu, received_nsus)
        if gaps:
            logger.warning(f"Gaps detectados para {cnpj}/{tipo}: {len(gaps)} NSUs faltantes")

        return docs_found

    except Exception as e:
        logger.error(f"Erro no polling {cnpj}/{tipo}: {e}")
        sb.table("polling_log").insert({
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "tipo": tipo,
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
        ).eq("error_message", job_id).eq("triggered_by", "retroativo").execute()
        return

    cert = cert_result.data[0]
    tenant = sb.table("tenants").select("id, polling_mode, manifestacao_mode, credits").eq(
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
    }).eq("error_message", job_id).eq("triggered_by", "retroativo").execute()


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
    scheduler.start()
    logger.info("Scheduler iniciado: polling a cada 15 minutos")
    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler):
    """Para o scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler parado")
