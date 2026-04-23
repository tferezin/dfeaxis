"""Guards hardcoded contra uso indevido de certificados de terceiros
em ambiente SEFAZ de produção.

**Por que existe:** durante desenvolvimento, o tenant admin (LINKTI) usa
um certificado A1 de terceiro (BEIERSDORF) emprestado para testes contra
SEFAZ homologação. Se esse certificado alcançar SEFAZ produção, a
plataforma passa a consultar/manifestar NF-e em nome de CNPJ alheio —
gera consumo indevido, bloqueio fiscal e potencial auto de infração.

**Regra gravada em código:** a lista abaixo define CNPJs de certificados
e e-mails de contas que **NUNCA** podem interagir com SEFAZ produção.
Remover entradas daqui exige commit + revisão — defesa deliberadamente
rígida contra mudança impulsiva.

**Duas camadas de aplicação:**
1. Endpoint PATCH /tenants/settings recusa sefaz_ambiente='1' quando
   tenant tem cert bloqueado ou email admin. Retorna HTTP 403.
2. services/sefaz_client antes de cada chamada SOAP força ambiente='2'
   se detectar cert bloqueado — defesa em profundidade caso a camada 1
   seja burlada por SQL direto no banco.

Normalização: CNPJs são comparados sem máscara (só dígitos). E-mails
são case-insensitive.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# CNPJs de certificados A1 de TERCEIROS usados em dev/homologação.
# Subir um desses contra SEFAZ produção = consulta em nome alheio.
NEVER_PROD_CERT_CNPJS: frozenset[str] = frozenset({
    "01786983000368",  # BEIERSDORF INDÚSTRIA E COMÉRCIO LTDA (cert emprestado dev)
})


# E-mails de contas admin/dev da LINKTI. Protege mesmo se o cert
# bloqueado for removido e outro for cadastrado depois — a conta fica
# permanentemente vinculada a ambiente homolog.
NEVER_PROD_USER_EMAILS: frozenset[str] = frozenset({
    "ferezinth@hotmail.com",
})


def _normalize_cnpj(cnpj: str | None) -> str:
    if not cnpj:
        return ""
    return re.sub(r"\D", "", cnpj)


def should_block_prod(
    *,
    cert_cnpj: str | None = None,
    user_email: str | None = None,
) -> tuple[bool, str | None]:
    """Retorna (should_block, motivo_legível) se este contexto nunca pode
    alcançar SEFAZ produção.

    Uso típico:
        blocked, reason = should_block_prod(cert_cnpj=cert["cnpj"])
        if blocked: ...
    """
    cnpj_digits = _normalize_cnpj(cert_cnpj)
    if cnpj_digits and cnpj_digits in NEVER_PROD_CERT_CNPJS:
        return (
            True,
            f"Certificado CNPJ {cert_cnpj} está permanentemente bloqueado "
            f"para SEFAZ produção (cert de terceiro usado em dev).",
        )

    if user_email:
        email_lower = user_email.strip().lower()
        if email_lower in {e.lower() for e in NEVER_PROD_USER_EMAILS}:
            return (
                True,
                f"Conta {user_email} é admin/dev e está permanentemente "
                f"restrita a SEFAZ homologação.",
            )

    return False, None


def safe_ambiente(
    requested_ambiente: str,
    *,
    cert_cnpj: str | None = None,
    user_email: str | None = None,
) -> str:
    """Retorna ambiente SEFAZ seguro. Se o contexto está bloqueado para
    produção, força '2' (homolog) independente do que foi solicitado.

    Emite logger.error quando força — sinaliza que há bug em camada
    superior (endpoint deveria ter bloqueado antes).
    """
    if requested_ambiente != "1":
        return requested_ambiente

    blocked, reason = should_block_prod(
        cert_cnpj=cert_cnpj, user_email=user_email,
    )
    if blocked:
        logger.error(
            "admin_guards: AMBIENTE FORCADO PARA HOMOLOG cert_cnpj=%s email=%s motivo=%s",
            cert_cnpj, user_email, reason,
        )
        return "2"

    return requested_ambiente
