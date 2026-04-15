"""Scheduler APScheduler para polling automático na SEFAZ."""

import base64
import logging
import time
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from db.supabase import get_supabase_client
from middleware.lgpd import mask_cnpj
from services.cert_manager import decrypt_password
from services.manifestacao import manifestacao_service
from services.sefaz_client import sefaz_client
from services.nfse_client import nfse_client
from services.nsu_controller import nsu_controller
from services.xml_parser import (
    is_evento_xml,
    metadata_to_db_dict,
    parse_document_xml,
)

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


def _build_document_row(
    *,
    tenant_id: str,
    cnpj: str,
    doc,
    is_resumo: bool,
    doc_status: str,
    manif_status,
) -> dict | None:
    """Constrói o dict de upsert em `documents` incluindo metadata extraída do XML.

    Centraliza a lógica pra os 3 fluxos de polling (NFE/CTE/MDFE via
    _poll_single_detailed/_poll_single, e NFSE via _poll_nfse) usarem os
    mesmos campos — evita divergência.

    Retorna None se o XML for um EVENTO SEFAZ (procEventoNFe, procEventoCTe,
    etc.) em vez de documento fiscal. Eventos chegam pelo mesmo canal
    DistDFe que as notas mas não devem ser persistidos em `documents` —
    caller deve tratar None e pular o upsert.
    """
    xml_source = doc.xml_content if hasattr(doc, "xml_content") else None

    # Filtra eventos (manifestação, cancelamento, carta de correção) —
    # não são documentos fiscais, não devem ir pra `documents`.
    if xml_source and is_evento_xml(xml_source):
        logger.info(
            "polling: skip evento xml chave=%s tipo=%s — não é doc fiscal",
            getattr(doc, "chave", "?"), getattr(doc, "tipo", "?"),
        )
        return None

    row: dict = {
        "tenant_id": tenant_id,
        "cnpj": cnpj,
        "tipo": doc.tipo,
        "chave_acesso": doc.chave,
        "nsu": doc.nsu,
        "xml_content": doc.xml_content if not is_resumo else None,
        "status": doc_status,
        "is_resumo": is_resumo,
        "manifestacao_status": manif_status,
    }

    # Extrai metadata do XML (emit, dest, número, data, valor). Parser é
    # defensive — nunca levanta. Resumos têm xml_content=None e vão retornar
    # metadata quase vazia (só CNPJ emitente quando o resumo contém).
    if xml_source:
        try:
            meta = parse_document_xml(xml_source, doc.tipo)
            row.update(metadata_to_db_dict(meta))
        except Exception as exc:  # noqa: BLE001 — tracking nunca quebra polling
            logger.warning(
                "xml_parser falhou pra chave=%s tipo=%s: %s: %s",
                doc.chave, doc.tipo, type(exc).__name__, exc,
            )

    return row


def _normalize_pfx_blob(
    pfx_encrypted, pfx_iv
) -> tuple[object, bytes | None]:
    """Normaliza `pfx_encrypted` e `pfx_iv` vindos do banco para os formatos
    que `sefaz_client` / `nfse_client` esperam.

    Regras (suporta cert v1 legado + cert v2 atual):
      - Se `pfx_encrypted` já é string começando com "v2:", deixa como string.
      - Se é string no formato BYTEA ("\\x<hex>"), converte pra bytes; se os
        bytes resultantes decodificam para ASCII começando com "v2:",
        converte de volta pra string (o sefaz_client detecta pelo prefixo).
      - Se é raw hex string, tenta bytes.fromhex.
      - Se já é bytes, deixa como bytes.
      - `pfx_iv` segue mesma lógica mas é sempre bytes (ou None pra v2).

    Compartilhada entre `_poll_single_detailed` e `_poll_nfse` pra garantir
    que os dois fluxos tratam v1/v2 identicamente.
    """
    if isinstance(pfx_encrypted, str) and not pfx_encrypted.startswith("v2:"):
        clean = pfx_encrypted.replace("\\x", "").replace("\\\\x", "")
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
        pfx_iv = bytes.fromhex(
            pfx_iv.replace("\\x", "").replace("\\\\x", "")
        )

    return pfx_encrypted, pfx_iv


# Limites do loop interno SEFAZ dentro de um único POST /polling/trigger.
# Cada batch traz no máximo ~50 docs (limitação do protocolo SEFAZ
# NFeDistribuicaoDFe), então pra plano Business (8000 docs) o loop pode
# rodar ~160 iterações no pior caso. 300 é teto de segurança; 300s
# (5 min) é o timeout razoável pra o SAP esperar uma resposta.
_MAX_BATCHES_PER_TRIGGER = 300
_MAX_SECONDS_PER_TRIGGER = 300


def _poll_single_detailed(cert: dict, tipo: str, tenant_data: dict) -> dict:
    """Executa polling e retorna detalhes completos para a UI / SAP.

    Loop interno: faz múltiplas chamadas SEFAZ dentro de UM único
    /polling/trigger do cliente até acontecer um dos 4:

    1. A SEFAZ devolve `ultNSU == maxNSU` (fila esgotada, nada mais)
    2. A SEFAZ devolve 0 docs no batch (idem)
    3. Trial cap atingido (count na tabela documents bate em trial_cap)
    4. Timeout de _MAX_SECONDS_PER_TRIGGER ou _MAX_BATCHES_PER_TRIGGER

    Trial cap enforcement:
    - Se tenant em trial, limite = trial_cap - count(documents WHERE tenant_id=X)
    - Inclui tanto docs 'available' (fila) quanto 'delivered' (já confirmados)
    - Quando o limite bate, o batch atual é truncado e o loop para
    - Contador docs_consumidos_trial NÃO é tocado aqui — só avança em /confirmar

    Retorna totais agregados do loop (docs_found = soma de todos os batches).
    """
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
    pfx_password = _get_pfx_password(cert["id"], tenant_id)

    if not pfx_password:
        return {
            "tipo": tipo.upper(), "status": "error", "cstat": "999",
            "xmotivo": "", "docs_found": 0, "latency_ms": 0,
            "error": "Senha do certificado não encontrada", "saved_to_db": False,
        }

    # Normalização v1/v2 via helper compartilhado — suporta cert legado
    # (CBC com pfx_iv separado) e cert atual (GCM v2 com prefixo "v2:").
    pfx_encrypted, pfx_iv = _normalize_pfx_blob(
        cert["pfx_encrypted"], cert["pfx_iv"]
    )

    ambiente = tenant_data.get("sefaz_ambiente", "2")
    is_trial = tenant_data.get("subscription_status") == "trial"
    trial_cap = int(tenant_data.get("trial_cap") or 500)

    # Gate inicial: se já está bloqueado por cap ou tempo, não chama SEFAZ.
    # verify_trial_active no middleware já bloqueia a entrada, mas dupla
    # defesa aqui evita qualquer race entre requests concorrentes.
    if is_trial and tenant_data.get("trial_blocked_at"):
        return {
            "tipo": tipo.upper(), "status": "blocked", "cstat": "999",
            "xmotivo": "Trial bloqueado", "docs_found": 0, "latency_ms": 0,
            "error": "trial_blocked", "saved_to_db": False,
        }

    # Calcula remaining inicial pro trial via count na tabela documents.
    # Isto inclui todos os docs já capturados na vida do trial (tanto
    # 'available' quanto 'delivered') — o cap de captura é acumulado,
    # não reseta quando o SAP confirma.
    def _trial_remaining() -> int:
        if not is_trial:
            return -1  # sem limite (plano pago usa overage billing)
        count_res = sb.table("documents").select(
            "id", count="exact", head=True
        ).eq("tenant_id", tenant_id).execute()
        total_in_bank = count_res.count or 0
        return max(trial_cap - total_in_bank, 0)

    # Cursor inicial vem do nsu_state (por ambiente) — mais preciso que o
    # last_nsu legado no certificates. Cai no legado se nsu_state não tem
    # entrada ainda pra esse cert/tipo/ambiente.
    try:
        ult_nsu = nsu_controller.get_cursor(cert["id"], tipo, ambiente)
    except Exception:
        ult_nsu = cert.get(f"last_nsu_{tipo}", "000000000000000")

    start_time = time.time()
    total_docs_saved = 0
    total_latency_ms = 0
    last_cstat = "137"
    last_xmotivo = "Nenhum documento localizado"
    last_response_ult_nsu = ult_nsu
    last_response_max_nsu = ult_nsu

    try:
        for batch_idx in range(_MAX_BATCHES_PER_TRIGGER):
            # Timeout interno — não deixa o SAP esperando mais que 5min
            if time.time() - start_time > _MAX_SECONDS_PER_TRIGGER:
                logger.info(
                    "polling/trigger: timeout %ds atingido após %d batches, "
                    "tenant=%s cnpj=%s tipo=%s",
                    _MAX_SECONDS_PER_TRIGGER, batch_idx, tenant_id, mask_cnpj(cnpj), tipo,
                )
                break

            # Checa cap antes de bater na SEFAZ
            remaining = _trial_remaining()
            if is_trial and remaining == 0:
                logger.info(
                    "polling/trigger: trial cap=%d atingido (batch %d), parando loop",
                    trial_cap, batch_idx,
                )
                break

            # Chamada SEFAZ
            response = sefaz_client.consultar_distribuicao(
                cnpj=cnpj, tipo=tipo, ult_nsu=ult_nsu,
                pfx_encrypted=pfx_encrypted, pfx_iv=pfx_iv,
                tenant_id=tenant_id, pfx_password=pfx_password,
                ambiente=ambiente,
            )

            total_latency_ms += response.latency_ms
            last_cstat = response.cstat
            last_xmotivo = response.xmotivo
            last_response_ult_nsu = response.ult_nsu
            last_response_max_nsu = response.max_nsu

            batch_docs = list(response.documents)
            batch_size = len(batch_docs)

            # Ordena por NSU asc pra garantir corte determinístico quando trunca
            try:
                batch_docs.sort(key=lambda d: int(d.nsu) if d.nsu else 0)
            except Exception:
                pass

            # Aplica truncamento do trial no batch atual
            if is_trial and remaining > 0 and batch_size > remaining:
                batch_docs = batch_docs[:remaining]
                logger.info(
                    "polling/trigger: trial cap trunca batch %d em %d/%d docs",
                    batch_idx, remaining, batch_size,
                )

            # Salva os docs do batch truncado
            saved_in_batch = 0
            last_saved_nsu: str | None = None
            for doc in batch_docs:
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

                row = _build_document_row(
                    tenant_id=tenant_id,
                    cnpj=cnpj,
                    doc=doc,
                    is_resumo=is_resumo,
                    doc_status=doc_status,
                    manif_status=manif_status,
                )
                if row is None:
                    # Era evento SEFAZ (procEventoNFe/CTe/...), não doc fiscal
                    continue
                sb.table("documents").upsert(
                    row, on_conflict="tenant_id,chave_acesso"
                ).execute()
                saved_in_batch += 1
                last_saved_nsu = doc.nsu or last_saved_nsu

            total_docs_saved += saved_in_batch

            # Avança cursor NSU de acordo com o que foi efetivamente salvo:
            # - Se salvou o batch inteiro (não truncou), usa o ult_nsu da
            #   resposta SEFAZ (inclui também quaisquer eventos que pulamos)
            # - Se truncou por cap, avança só até o último NSU salvo
            full_batch = len(batch_docs) == batch_size
            if full_batch:
                effective_cursor = response.ult_nsu
            else:
                effective_cursor = last_saved_nsu or response.ult_nsu

            nsu_controller.update_cursor(
                cert["id"], tipo, ambiente, effective_cursor, response.max_nsu or effective_cursor
            )
            nsu_controller.update_last_nsu(cert["id"], tipo, effective_cursor)
            ult_nsu = effective_cursor

            # Condições de parada do loop:
            # 1. Batch truncado por cap → não adianta continuar, próxima
            #    chamada SEFAZ daria mais docs que a gente não pode salvar
            if not full_batch:
                break
            # 2. SEFAZ esgotou a fila (ultNSU == maxNSU ou 0 docs)
            if batch_size == 0 or response.ult_nsu >= response.max_nsu:
                break

        saved = total_docs_saved > 0

        # Log único agregando o resultado de todos os batches
        sb.table("polling_log").insert({
            "tenant_id": tenant_id, "cnpj": cnpj, "tipo": tipo,
            "triggered_by": "manual",
            "status": "success" if last_cstat in ("137", "138") else "error",
            "docs_found": total_docs_saved,
            "ult_nsu": last_response_ult_nsu,
            "latency_ms": total_latency_ms,
            "error_message": last_xmotivo if last_cstat not in ("137", "138") else None,
        }).execute()

        return {
            "tipo": tipo.upper(), "status": "success", "cstat": last_cstat,
            "xmotivo": last_xmotivo, "docs_found": total_docs_saved,
            "latency_ms": total_latency_ms, "saved_to_db": saved,
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
            "xmotivo": "", "docs_found": total_docs_saved, "latency_ms": total_latency_ms,
            "error": str(e), "saved_to_db": total_docs_saved > 0,
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
        # Limita quantos docs podem ser persistidos nesta rodada pelo total
        # de docs já salvos na vida do trial (available + delivered). NÃO
        # usa `docs_consumidos_trial` porque esse campo só avança quando
        # o SAP confirma via /confirmar — ver documents.py:confirmar_documento.
        # Se usássemos o contador, docs já salvos mas ainda não confirmados
        # não seriam contados e a retroativa poderia explodir (cada iteração
        # do loop re-calcularia remaining=500 e baixaria mais 500 sem limite).
        is_trial = tenant_data.get("subscription_status") == "trial"
        docs_to_save = list(response.documents)
        # Ordena por NSU asc para garantir corte determinístico
        try:
            docs_to_save.sort(key=lambda d: int(d.nsu) if d.nsu else 0)
        except Exception:
            pass

        if is_trial:
            trial_cap = int(tenant_data.get("trial_cap") or 500)
            count_res = sb.table("documents").select(
                "id", count="exact", head=True
            ).eq("tenant_id", tenant_id).execute()
            total_in_bank = count_res.count or 0
            remaining = max(trial_cap - total_in_bank, 0)

            if remaining == 0:
                # Cap já atingido antes deste batch: não salva, não avança cursor,
                # apenas registra pendentes e marca tenant como bloqueado no run.
                logger.info(
                    f"Tenant {tenant_id} trial cap atingido — {docs_found} docs "
                    f"{tipo.upper()} não serão capturados (total_in_bank={total_in_bank}, cap={trial_cap})"
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
                    f"docs {tipo.upper()} (total_in_bank={total_in_bank}, cap={trial_cap})"
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

            row = _build_document_row(
                tenant_id=tenant_id,
                cnpj=cnpj,
                doc=doc,
                is_resumo=is_resumo,
                doc_status=doc_status,
                manif_status=manif_status,
            )
            if row is None:
                # Evento SEFAZ (manifestação, cancelamento, etc.) — skip
                continue
            sb.table("documents").upsert(
                row, on_conflict="tenant_id,chave_acesso"
            ).execute()

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

        # Contadores (trial e plano pago) NÃO são incrementados aqui.
        # O modelo é: captura vai pra fila, mas o contador só avança quando
        # o SAP confirma recebimento via POST /documentos/{chave}/confirmar.
        # Motivo: cobrar pelo que foi capturado mas nunca consumido pelo
        # cliente é injusto. Ver routers/documents.py:confirmar_documento.
        #
        # O limite do trial (500 docs) continua sendo aplicado como limite
        # DE CAPTURA (quanto a gente salva na fila de uma vez) — vem de
        # docs_consumidos_trial + saved_not_delivered_yet. Isso é calculado
        # lá em cima via `remaining = trial_cap - consumed`.

        # Detecta gaps
        received_nsus = [d.nsu for d in docs_to_save]
        gaps = nsu_controller.detect_gap(ult_nsu, received_nsus)
        if gaps:
            logger.warning(f"Gaps detectados para {mask_cnpj(cnpj)}/{tipo}: {len(gaps)} NSUs faltantes")

        return effective_count

    except Exception as e:
        # Log sempre com type(e) — muitas exceptions (ex: cryptography
        # InvalidTag) têm str(e) vazio, resultando em logs inúteis tipo
        # "Erro no polling XXX: " sem mensagem.
        err_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        logger.exception(
            f"Erro no polling {mask_cnpj(cnpj)}/{tipo}: {err_msg}"
        )
        sb.table("polling_log").insert({
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "tipo": tipo,
            "triggered_by": "scheduler",
            "status": "error",
            "error_message": err_msg,
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

    # Normalização v1/v2 via helper compartilhado — sem esse fix o polling
    # automático de NFS-e falhava com InvalidTag porque o código legado
    # fazia `bytes.fromhex("76323a...")` e passava esses bytes como se
    # fossem blob v1, quebrando a decryption do cert v2.
    pfx_encrypted, pfx_iv = _normalize_pfx_blob(
        cert["pfx_encrypted"], cert["pfx_iv"]
    )

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

        # Salva documentos. NFSe precisa de 2 campos extra (codigo_municipio,
        # codigo_servico) que não estão no DocumentMetadata padrão — adicionamos
        # manualmente após o helper popular o resto.
        for doc in response.documents:
            # NfseDocument não tem .tipo, fingimos pra o helper funcionar
            class _NfseDocShim:
                def __init__(self, d):
                    self.tipo = "NFSE"
                    self.chave = d.chave
                    self.nsu = d.nsu
                    self.xml_content = d.xml_content

            row = _build_document_row(
                tenant_id=tenant_id,
                cnpj=cnpj,
                doc=_NfseDocShim(doc),
                is_resumo=False,
                doc_status="available",
                manif_status="nao_aplicavel",
            )
            if row is None:
                # NFSe não tem eventos no mesmo canal, mas defensivo
                continue
            row["codigo_municipio"] = doc.codigo_municipio
            row["codigo_servico"] = doc.codigo_servico
            sb.table("documents").upsert(
                row, on_conflict="tenant_id,chave_acesso"
            ).execute()

        # Atualiza ultimo NSU
        sb.table("certificates").update({
            "last_nsu_nfse": response.ult_nsu,
        }).eq("id", cert["id"]).execute()

        return docs_found

    except Exception as e:
        # Log com type(e) sempre — InvalidTag e outras exceptions da
        # cryptography têm str(e) vazio, resultava em logs tipo
        # "Erro no polling NFS-e XXX: " sem info útil.
        err_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        logger.exception(
            f"Erro no polling NFS-e {mask_cnpj(cnpj)}: {err_msg}"
        )
        sb.table("polling_log").insert({
            "tenant_id": tenant_id,
            "cnpj": cnpj,
            "tipo": "nfse",
            "triggered_by": "scheduler",
            "status": "error",
            "error_message": err_msg,
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
                now = datetime.now(timezone.utc)
                sb.table("documents").update({
                    "manifestacao_status": "ciencia",
                    "manifestacao_at": now.isoformat(),
                    "manifestacao_deadline": (now + timedelta(days=180)).isoformat(),
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
                "source": "auto_capture",
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
    """Inicia o scheduler APScheduler.

    IMPORTANTE (decisão 2026-04-12): o polling automático SEFAZ foi
    REMOVIDO do scheduler. A plataforma NUNCA consulta a SEFAZ sozinha.
    Toda captura agora é on-demand, acionada pelo ERP do cliente via
    POST /api/v1/polling/trigger. A função `polling_job()` acima
    continua existindo porque é usada pelo endpoint manual/trigger
    como biblioteca, mas não é mais registrada como job recorrente.

    Razões da decisão:
    - Evita consumo de recursos internos pra tenants inativos
    - Distribui carga SEFAZ naturalmente ao longo do dia
    - Cliente controla 100% da frequência (melhor pra ele)
    - Reduz risco de erro 656 (consumo indevido SEFAZ)
    - Simplifica arquitetura (sem lógica de "polling_mode auto vs manual")
    """
    scheduler = BackgroundScheduler()

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

    # Billing: cálculo mensal de excedente + InvoiceItem no Stripe
    # Roda dia 1 às 02:00 UTC. Usa cron ao invés de interval pra garantir a data.
    try:
        from scheduler.monthly_overage_job import process_monthly_overage

        scheduler.add_job(
            process_monthly_overage,
            "cron",
            day=1,
            hour=2,
            minute=0,
            id="monthly_overage",
            name="Billing: cobrança de excedente mensal",
            replace_existing=True,
        )
        logger.info("monthly_overage_job agendado: dia 1 às 02:00 UTC")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível agendar monthly_overage_job: %s", exc)

    # Manifestação: alerta de NF-e pendentes (1x/dia)
    try:
        from scheduler.manifestacao_alert_job import check_manifestacao_expiring

        scheduler.add_job(
            check_manifestacao_expiring,
            "interval",
            hours=24,
            id="manifestacao_alerts",
            name="Alerta NF-e pendentes de manifestação (D-10/D-5)",
            replace_existing=True,
        )
        logger.info("manifestacao_alert_job agendado: 1x/dia")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível agendar manifestacao_alert_job: %s", exc)

    # LGPD: cleanup de .pfx após 30 dias de inatividade (1x/dia)
    try:
        from scheduler.pfx_cleanup_job import cleanup_inactive_pfx

        scheduler.add_job(
            cleanup_inactive_pfx,
            "interval",
            hours=24,
            id="pfx_cleanup",
            name="LGPD: cleanup de .pfx após 30 dias inatividade",
            replace_existing=True,
        )
        logger.info("pfx_cleanup_job agendado: 1x/dia")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível agendar pfx_cleanup_job: %s", exc)

    scheduler.start()
    logger.info("Scheduler iniciado: SEM polling automático SEFAZ. Jobs ativos: trial_emails, monthly_overage, manifestacao_alerts, pfx_cleanup.")
    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler):
    """Para o scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler parado")
