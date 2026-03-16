"""Scheduler APScheduler para polling automático na SEFAZ."""

import base64
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from db.supabase import get_supabase_client
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
            "id, polling_mode, credits"
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

    # Nota: a senha do .pfx precisa ser armazenada de forma segura
    # Por ora, assumimos que está na config do tenant ou em vault
    # TODO: implementar armazenamento seguro da senha do .pfx
    pfx_password = _get_pfx_password(cert["id"])
    if not pfx_password:
        return 0

    try:
        response = sefaz_client.consultar_distribuicao(
            cnpj=cnpj,
            tipo=tipo,
            ult_nsu=ult_nsu,
            pfx_encrypted=cert["pfx_encrypted"],
            pfx_iv=cert["pfx_iv"],
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

        # Salva documentos no banco
        for doc in response.documents[:docs_found]:
            sb.table("documents").upsert({
                "tenant_id": tenant_id,
                "cnpj": cnpj,
                "tipo": doc.tipo,
                "chave_acesso": doc.chave,
                "nsu": doc.nsu,
                "xml_content": doc.xml_content,
                "status": "available",
            }, on_conflict="tenant_id,chave_acesso").execute()

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


def _get_pfx_password(cert_id: str) -> str | None:
    """Recupera a senha do .pfx do certificado.

    A senha é armazenada cifrada no banco.
    TODO: implementar vault ou campo dedicado.
    """
    sb = get_supabase_client()
    result = sb.table("certificates").select(
        "pfx_password_encrypted"
    ).eq("id", cert_id).execute()

    if result.data and result.data[0].get("pfx_password_encrypted"):
        # TODO: decifrar senha
        return result.data[0]["pfx_password_encrypted"]
    return None


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
