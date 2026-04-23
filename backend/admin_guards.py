"""Guards hardcoded contra contas admin da LINKTI alcançarem SEFAZ produção.

**Por que existe:** a conta admin do DFeAxis (admin@dfeaxis.com.br,
tenant LINKTI) é usada para desenvolvimento contra SEFAZ homologação,
frequentemente com certificados A1 emprestados de terceiros. Se essa
conta virar `sefaz_ambiente='1'` por acidente, a plataforma passa a
consultar/manifestar NF-e em produção em nome de CNPJ alheio — gera
consumo indevido, bloqueio fiscal e potencial auto de infração.

**Regra gravada em código:** as listas abaixo definem contas que
**NUNCA** podem interagir com SEFAZ produção. Remover entradas daqui
exige commit + revisão — defesa deliberadamente rígida contra mudança
impulsiva via UI ou SQL direto.

**Bloqueio por identidade da CONTA, não por CNPJ do cert:** se um dia
a BEIERSDORF (cujo cert está nesta conta admin) virar cliente real,
ela cadastra conta própria via signup e opera em produção normalmente.
A proteção aqui é sobre **quem está usando**, não sobre **qual CNPJ**.

**Três camadas de aplicação:**
1. Endpoint PATCH /tenants/settings recusa sefaz_ambiente='1' quando
   user_id/tenant_id/email está na blacklist. Retorna HTTP 403.
2. services/sefaz_client e services/manifestacao antes de cada chamada
   SOAP forçam ambiente='2' se detectarem conta bloqueada — defesa em
   profundidade caso a camada 1 seja burlada por SQL direto.
3. Logger.error sempre que a camada 2 dispara — sinaliza que uma camada
   superior falhou e precisa investigar.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# UUIDs do auth.users das contas admin/dev — identificador primário,
# imutável mesmo se o email mudar. Fonte de verdade.
NEVER_PROD_USER_IDS: frozenset[str] = frozenset({
    "3e9c9d9b-9682-4713-8552-6e1abf3514bc",  # admin@dfeaxis.com.br
})


# UUIDs da tabela tenants — redundância defensiva. Se por algum motivo
# o user_id não for propagado mas o tenant_id sim, ainda bloqueia.
NEVER_PROD_TENANT_IDS: frozenset[str] = frozenset({
    "dfe11fdb-fa54-403e-b563-24aef3b7b406",  # tenant LINKTI / admin@dfeaxis.com.br
})


# E-mails admin — fallback caso UUIDs sejam recriados numa migração
# de ambiente (dev → staging → prod) e os IDs mudem. Case-insensitive.
NEVER_PROD_USER_EMAILS: frozenset[str] = frozenset({
    "admin@dfeaxis.com.br",
})


def should_block_prod(
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    user_email: str | None = None,
) -> tuple[bool, str | None]:
    """Retorna (should_block, motivo_legível) se este contexto é uma
    conta admin que nunca pode alcançar SEFAZ produção.

    Basta um dos três identificadores bater na blacklist — qualquer
    match bloqueia. Uso típico:

        blocked, reason = should_block_prod(
            user_id=auth["user_id"],
            tenant_id=auth["tenant_id"],
        )
        if blocked: raise HTTPException(403, reason)
    """
    if user_id and user_id in NEVER_PROD_USER_IDS:
        return (
            True,
            f"Conta admin (user_id={user_id[:8]}...) está permanentemente "
            f"restrita a SEFAZ homologação.",
        )

    if tenant_id and tenant_id in NEVER_PROD_TENANT_IDS:
        return (
            True,
            f"Tenant admin (tenant_id={tenant_id[:8]}...) está "
            f"permanentemente restrito a SEFAZ homologação.",
        )

    if user_email:
        email_lower = user_email.strip().lower()
        if email_lower in {e.lower() for e in NEVER_PROD_USER_EMAILS}:
            return (
                True,
                f"Conta {user_email} é admin e está permanentemente "
                f"restrita a SEFAZ homologação.",
            )

    return False, None


def safe_ambiente(
    requested_ambiente: str,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
    user_email: str | None = None,
) -> str:
    """Retorna ambiente SEFAZ seguro. Se o contexto é conta admin
    bloqueada, força '2' (homologação) independente do que foi pedido.

    Emite logger.error quando força — sinaliza que há bug em camada
    superior (endpoint deveria ter bloqueado antes de chegar aqui).
    """
    if requested_ambiente != "1":
        return requested_ambiente

    blocked, reason = should_block_prod(
        user_id=user_id,
        tenant_id=tenant_id,
        user_email=user_email,
    )
    if blocked:
        logger.error(
            "admin_guards: AMBIENTE FORCADO PARA HOMOLOG "
            "user_id=%s tenant_id=%s email=%s motivo=%s",
            user_id, tenant_id, user_email, reason,
        )
        return "2"

    return requested_ambiente
