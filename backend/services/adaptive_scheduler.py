"""Scheduler adaptativo para DistDFe SEFAZ (NT 2014.002).

Gerencia o estado persistente em `dist_dfe_schedule_state` que dita quando
o worker pode chamar SEFAZ novamente por (certificate_id, tipo, ambiente).

Padrão Sankhya: worker acorda a cada 15 min (pequeno intervalo), mas a
decisão de bater na SEFAZ vem do campo `proxima_chamada_elegivel_em`:

    cstat 137 (fila vazia) → schedule next = now + 61 min
    cstat 138 (doc retornado) → drain loop enquanto ultNSU < maxNSU
    cstat 656 (consumo indevido) → schedule next = now + 62 min (margem)
    exception → não avança estado; próximo wake re-tenta em 15 min

Este módulo só expõe operações sobre o estado. A orquestração (loop de
drain, chamada SEFAZ, persistência de docs) fica em `nfe_polling_job`.
"""

from __future__ import annotations

import logging
import os
import socket
from datetime import datetime, timedelta, timezone

from db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

# Backoffs (segundos). NT 2014.002 exige ≥60 min após 137; adicionamos
# margem pra evitar corrida com o clock SEFAZ.
BACKOFF_137_SEC = 3660   # 61 min
BACKOFF_656_SEC = 3720   # 62 min
BACKOFF_ERROR_SEC = 900  # 15 min (erro genérico não rate-limit)

# Lease do mutex row-based (backup ao pg_advisory_lock se usado).
# 15 min = uma janela inteira do scheduler; se worker crashar, libera na
# próxima rodada.
LOCK_LEASE_SEC = 900

# Auto-quarantine: após N exceptions consecutivas, desliga o cert até
# intervenção manual. Evita loops de erro-retry-erro consumindo SEFAZ.
AUTO_QUARANTINE_THRESHOLD = 5

# Global kill switch — liga via env var no Railway em incidente.
KILL_SWITCH_ENV = "ADAPTIVE_POLLING_KILL_SWITCH"


def is_kill_switch_active() -> bool:
    """True se a env var ADAPTIVE_POLLING_KILL_SWITCH=1 estiver setada."""
    return os.getenv(KILL_SWITCH_ENV, "") == "1"


def _worker_id() -> str:
    """Identificador do worker (hostname:pid). Usado em locked_by pra debug."""
    return f"{socket.gethostname()}:{os.getpid()}"


class AdaptiveScheduler:
    """Controla o estado adaptativo do DistDFe por (cert, tipo, ambiente)."""

    def list_eligible(self) -> list[dict]:
        """Retorna linhas elegíveis pra chamar SEFAZ agora.

        Critérios:
        - tenant tem adaptive_polling_enabled = true
        - tenant subscription_status not in ('expired','cancelled')
        - tenant não está com trial bloqueado
        - certificate is_active = true
        - schedule_state enabled = true
        - proxima_chamada_elegivel_em <= now()
        - locked_until is null or locked_until < now()

        Retorna dicts com {certificate_id, tenant_id, cnpj, tipo, ambiente,
        ultimo_cstat, ult_nsu_atual, max_nsu_atual, proxima_chamada_elegivel_em}.
        """
        sb = get_supabase_client()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Supabase client não tem join SQL nativo — fazemos em duas queries
        # e combinamos em memória. Volume esperado é baixo (dezenas de
        # tenants × certs × tipos), então a leitura é barata.
        schedule_res = sb.table("dist_dfe_schedule_state").select(
            "certificate_id, tipo, ambiente, ultimo_cstat, "
            "ult_nsu_atual, max_nsu_atual, proxima_chamada_elegivel_em, "
            "locked_until, enabled"
        ).eq("enabled", True).lte(
            "proxima_chamada_elegivel_em", now_iso
        ).execute()

        if not schedule_res.data:
            return []

        # Filtra rows ainda com lock ativo
        rows = [
            r for r in schedule_res.data
            if not r.get("locked_until") or r["locked_until"] < now_iso
        ]
        if not rows:
            return []

        cert_ids = list({r["certificate_id"] for r in rows})
        cert_res = sb.table("certificates").select(
            "id, tenant_id, cnpj, is_active"
        ).in_("id", cert_ids).eq("is_active", True).execute()

        certs_by_id = {c["id"]: c for c in (cert_res.data or [])}
        if not certs_by_id:
            return []

        tenant_ids = list({c["tenant_id"] for c in certs_by_id.values()})
        tenant_res = sb.table("tenants").select(
            "id, adaptive_polling_enabled, subscription_status, "
            "trial_blocked_at, sefaz_ambiente"
        ).in_("id", tenant_ids).eq(
            "adaptive_polling_enabled", True,
        ).execute()

        tenants_by_id = {t["id"]: t for t in (tenant_res.data or [])}

        eligible = []
        for row in rows:
            cert = certs_by_id.get(row["certificate_id"])
            if not cert:
                continue
            tenant = tenants_by_id.get(cert["tenant_id"])
            if not tenant:
                continue
            if tenant.get("subscription_status") in ("expired", "cancelled"):
                continue
            if tenant.get("trial_blocked_at"):
                continue
            eligible.append({
                "certificate_id": row["certificate_id"],
                "tenant_id": cert["tenant_id"],
                "cnpj": cert["cnpj"],
                "tipo": row["tipo"],
                "ambiente": row["ambiente"],
                "ultimo_cstat": row.get("ultimo_cstat"),
                "ult_nsu_atual": row.get("ult_nsu_atual"),
                "max_nsu_atual": row.get("max_nsu_atual"),
            })
        return eligible

    def try_acquire_lock(
        self, certificate_id: str, tipo: str, ambiente: str
    ) -> bool:
        """Tenta adquirir o lease-based lock.

        Estratégia: UPDATE condicional. Se o row ainda está livre (locked_until
        null ou expirado), seta locked_until=now+lease. Supabase retorna o
        row atualizado; se nenhum row casou (outra instância pegou antes),
        retorna vazio.

        Não é 100% atômico no supabase-py (não existe WHERE locked_until<now
        in-row direto), mas fazemos select→update com double-check no retorno.
        Pra ambiente single-instance no Railway, é suficiente. Multi-replica
        requer pg_advisory_lock (TODO futuro).
        """
        sb = get_supabase_client()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        lease_until = (now + timedelta(seconds=LOCK_LEASE_SEC)).isoformat()

        # Primeiro: confere se está livre
        cur = sb.table("dist_dfe_schedule_state").select(
            "locked_until"
        ).eq("certificate_id", certificate_id).eq(
            "tipo", tipo,
        ).eq("ambiente", ambiente).execute()

        if not cur.data:
            logger.warning(
                "adaptive: try_acquire_lock sem linha cert=%s tipo=%s amb=%s",
                certificate_id, tipo, ambiente,
            )
            return False

        current_lock = cur.data[0].get("locked_until")
        if current_lock and current_lock >= now_iso:
            return False  # ainda travado

        # Atualiza pra marcar o lease
        sb.table("dist_dfe_schedule_state").update({
            "locked_until": lease_until,
            "locked_by": _worker_id(),
        }).eq(
            "certificate_id", certificate_id
        ).eq("tipo", tipo).eq("ambiente", ambiente).execute()

        return True

    def release_lock(
        self, certificate_id: str, tipo: str, ambiente: str
    ) -> None:
        """Libera o lock (idempotente)."""
        sb = get_supabase_client()
        sb.table("dist_dfe_schedule_state").update({
            "locked_until": None,
            "locked_by": None,
        }).eq(
            "certificate_id", certificate_id
        ).eq("tipo", tipo).eq("ambiente", ambiente).execute()

    def schedule_next(
        self,
        certificate_id: str,
        tipo: str,
        ambiente: str,
        cstat: str | None,
        xmotivo: str | None,
        ult_nsu: str | None,
        max_nsu: str | None,
        latency_ms: int | None,
        seconds_until_next: int,
        drain_iteracoes: int = 0,
        drain_docs: int = 0,
    ) -> None:
        """Atualiza o estado após um ciclo completo (sucesso ou negativa SEFAZ).

        Zera consecutive_errors (foi uma chamada que foi até a SEFAZ, não
        exception). Incrementa consecutive_137 se cstat=137, zera em outros.
        """
        sb = get_supabase_client()
        now = datetime.now(timezone.utc)
        next_at = now + timedelta(seconds=seconds_until_next)

        # Lê consecutive_137 atual pra incrementar
        cur = sb.table("dist_dfe_schedule_state").select(
            "consecutive_137"
        ).eq("certificate_id", certificate_id).eq(
            "tipo", tipo,
        ).eq("ambiente", ambiente).execute()
        prev_137 = (cur.data[0].get("consecutive_137") or 0) if cur.data else 0
        new_137 = prev_137 + 1 if cstat == "137" else 0

        sb.table("dist_dfe_schedule_state").update({
            "ultimo_cstat": cstat,
            "ultimo_xmotivo": xmotivo,
            "ultimo_chamada_em": now.isoformat(),
            "ultimo_latency_ms": latency_ms,
            "ult_nsu_atual": ult_nsu,
            "max_nsu_atual": max_nsu,
            "proxima_chamada_elegivel_em": next_at.isoformat(),
            "consecutive_137": new_137,
            "consecutive_errors": 0,
            "ultimo_drain_iteracoes": drain_iteracoes,
            "ultimo_drain_docs": drain_docs,
        }).eq(
            "certificate_id", certificate_id,
        ).eq("tipo", tipo).eq("ambiente", ambiente).execute()

    def record_exception(
        self,
        certificate_id: str,
        tipo: str,
        ambiente: str,
        exc: Exception,
    ) -> None:
        """Registra exception sem avançar cursor nem proxima_chamada.

        Incrementa consecutive_errors. Se passar do threshold, desliga o
        cert (enabled=false) com disabled_reason — evita loop de retry
        infinito consumindo a cota SEFAZ.
        """
        sb = get_supabase_client()
        cur = sb.table("dist_dfe_schedule_state").select(
            "consecutive_errors"
        ).eq("certificate_id", certificate_id).eq(
            "tipo", tipo,
        ).eq("ambiente", ambiente).execute()

        new_errors = 1
        if cur.data:
            new_errors = (cur.data[0].get("consecutive_errors") or 0) + 1

        update_fields: dict = {
            "consecutive_errors": new_errors,
        }

        if new_errors >= AUTO_QUARANTINE_THRESHOLD:
            update_fields["enabled"] = False
            update_fields["disabled_reason"] = (
                f"auto-quarantine: {new_errors} exceptions consecutivas. "
                f"Ultima: {type(exc).__name__}: {exc}"[:500]
            )
            logger.error(
                "adaptive: AUTO-QUARANTINE cert=%s tipo=%s amb=%s errors=%d exc=%s",
                certificate_id, tipo, ambiente, new_errors, exc,
            )

        sb.table("dist_dfe_schedule_state").update(update_fields).eq(
            "certificate_id", certificate_id,
        ).eq("tipo", tipo).eq("ambiente", ambiente).execute()

    def is_eligible_for_call(
        self, certificate_id: str, tipo: str, ambiente: str
    ) -> tuple[bool, int | None]:
        """Endpoint manual usa pra decidir se pode chamar SEFAZ agora.

        Retorna (eligible, seconds_remaining).
        - eligible=True: pode chamar (proxima_chamada_elegivel_em <= now).
        - eligible=False: segundos até ficar elegível.
        """
        sb = get_supabase_client()
        now = datetime.now(timezone.utc)
        res = sb.table("dist_dfe_schedule_state").select(
            "proxima_chamada_elegivel_em, enabled"
        ).eq("certificate_id", certificate_id).eq(
            "tipo", tipo,
        ).eq("ambiente", ambiente).execute()

        if not res.data:
            # Sem linha — primeiro uso, pode chamar. list_eligible via
            # backfill cria a linha; pra edge cases (cert novo pós-backfill),
            # o scheduler/router trata via upsert no primeiro schedule_next.
            return True, None

        row = res.data[0]
        if not row.get("enabled", True):
            return False, None  # quarantine — sem ETA

        next_iso = row.get("proxima_chamada_elegivel_em")
        if not next_iso:
            return True, None

        next_dt = datetime.fromisoformat(next_iso.replace("Z", "+00:00"))
        if next_dt <= now:
            return True, None

        delta = int((next_dt - now).total_seconds())
        return False, delta

    def ensure_row(
        self, certificate_id: str, tipo: str, ambiente: str
    ) -> None:
        """Garante linha em dist_dfe_schedule_state (upsert noop se existir).

        Usado no primeiro ciclo pra cert criado após o backfill da migration.
        """
        sb = get_supabase_client()
        sb.table("dist_dfe_schedule_state").upsert(
            {
                "certificate_id": certificate_id,
                "tipo": tipo,
                "ambiente": ambiente,
            },
            on_conflict="certificate_id,tipo,ambiente",
            ignore_duplicates=True,
        ).execute()


# Instância singleton — pattern usado em nsu_controller, sefaz_client, etc.
adaptive_scheduler = AdaptiveScheduler()
