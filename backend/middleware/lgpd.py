"""LGPD compliance: data masking, audit logging, and response sanitization."""

import json
import logging
import re
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data masking utilities
# ---------------------------------------------------------------------------

def mask_cnpj(cnpj: str) -> str:
    """Mask CNPJ for safe logging.

    Formatted:   01.786.983/0003-68 -> XX.XXX.XXX/0003-XX
    Unformatted: 01786983000368     -> XXXXXXXX0003XX
    """
    # Strip formatting
    digits = re.sub(r"[.\-/]", "", cnpj.strip())
    if len(digits) != 14:
        return "CNPJ_INVALID"
    # Keep only filial (positions 8-11), mask the rest
    masked = "X" * 8 + digits[8:12] + "X" * 2
    # If the original was formatted, return formatted
    if "/" in cnpj or "." in cnpj:
        return f"XX.XXX.XXX/{digits[8:12]}-XX"
    return masked


def mask_email(email: str) -> str:
    """Mask email for safe logging.

    user@domain.com -> u***@domain.com
    """
    if "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


def mask_chave(chave: str) -> str:
    """Mask chave de acesso for safe logging.

    44 digits -> first 8 + ... + last 4
    """
    digits = chave.strip()
    if len(digits) < 12:
        return "***"
    return f"{digits[:8]}...{digits[-4:]}"


# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------

def audit_log(
    tenant_id: str,
    user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Write an entry to the audit_log table.

    This function imports supabase lazily to avoid circular imports.
    """
    from db.supabase import get_supabase_client

    try:
        sb = get_supabase_client()
        # `details` e jsonb na tabela — supabase-py serializa o dict pra JSON.
        # Antes faziamos json.dumps aqui, o que gerava double-encode (string
        # JSON dentro de uma coluna jsonb). Corrigido em A6.
        row = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details if details else None,
            "ip_address": ip_address,
        }
        sb.table("audit_log").insert(row).execute()
    except Exception as exc:
        # Never let audit logging break the main flow
        logger.error(f"Failed to write audit log: {exc}")


# ---------------------------------------------------------------------------
# Regex patterns for sensitive data detection
# ---------------------------------------------------------------------------

# CNPJ: 14 consecutive digits (unformatted) or XX.XXX.XXX/XXXX-XX
_CNPJ_UNFORMATTED_RE = re.compile(r"\b(\d{14})\b")
_CNPJ_FORMATTED_RE = re.compile(
    r"\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b"
)

# Email
_EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b"
)

# PEM certificate data (BEGIN CERTIFICATE / BEGIN PRIVATE KEY blocks)
_PEM_RE = re.compile(
    r"-----BEGIN\s+(CERTIFICATE|PRIVATE\s+KEY|RSA\s+PRIVATE\s+KEY|ENCRYPTED\s+PRIVATE\s+KEY)-----"
    r"[\s\S]*?"
    r"-----END\s+\1-----",
    re.MULTILINE,
)


def _is_likely_cnpj(digits: str) -> bool:
    """Quick heuristic: check if 14-digit string could be a CNPJ.

    We avoid masking things like NSUs (15 digits), timestamps, and IDs.
    """
    if len(set(digits)) == 1:
        return False  # all same digit, not a real CNPJ
    return True


def sanitize_text(text: str) -> str:
    """Mask sensitive patterns found in a text string."""
    # Mask formatted CNPJs first (more specific pattern)
    text = _CNPJ_FORMATTED_RE.sub(
        lambda m: mask_cnpj(m.group(1)), text
    )

    # Mask unformatted 14-digit sequences that look like CNPJs
    def _replace_unformatted_cnpj(m: re.Match) -> str:
        digits = m.group(1)
        if _is_likely_cnpj(digits):
            return mask_cnpj(digits)
        return digits

    text = _CNPJ_UNFORMATTED_RE.sub(_replace_unformatted_cnpj, text)

    # Mask emails
    text = _EMAIL_RE.sub(lambda m: mask_email(m.group(1)), text)

    # Mask PEM certificate data
    text = _PEM_RE.sub("[CERTIFICATE_DATA_REDACTED]", text)

    return text


# ---------------------------------------------------------------------------
# Response sanitizer middleware
# ---------------------------------------------------------------------------

# Rotas onde o sanitizer NÃO roda — clientes legítimos (SAP DRC, dashboard)
# precisam do CNPJ real pra rotear documentos fiscais. Mascarar aqui quebra
# a integração core. Rotas admin/auth/tenants continuam sanitizadas pra não
# vazar PII em logs de erro / respostas de debug.
_SANITIZE_WHITELIST_PREFIXES = (
    "/api/v1/documentos",
    "/api/v1/certificates",
    "/api/v1/nfse",
    "/api/v1/manifestacao",
    "/sap-drc/",       # todo o layer SAP DRC compatibility
    "/api/v1/sefaz/",  # status endpoints SEFAZ
)


def _is_sanitize_whitelisted(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _SANITIZE_WHITELIST_PREFIXES)


# Item M11: cap de tamanho pra evitar DoS por buferizacao integral.
# Antes, qualquer response — mesmo de 100MB — era acumulada em memoria
# pra rodar o regex. Atacante autenticado podia disparar endpoint que
# retorna lote grande e estourar RAM da instancia.
_SANITIZER_MAX_BUFFER = 1_000_000  # 1MB e suficiente pra responses JSON de UI


class ResponseSanitizerMiddleware(BaseHTTPMiddleware):
    """Scans JSON response bodies and masks accidentally leaked sensitive data.

    Only processes application/json responses.  Skips streaming responses.
    Rotas de dados fiscais legítimos (ver _SANITIZE_WHITELIST_PREFIXES) são
    puladas — CNPJs de emitente/destinatário devem passar raw para o cliente.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        # Skip non-JSON or streaming responses
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response
        if isinstance(response, StreamingResponse):
            return response

        # Skip whitelisted routes (data that must be returned unmasked —
        # SAP DRC precisa do CNPJ real pra rotear documentos)
        if _is_sanitize_whitelisted(request.url.path):
            return response

        # Item M11: respostas grandes pulam sanitizacao pra prevenir DoS.
        # Content-Length pode nao estar setado em respostas chunked — nesse
        # caso buferiza com o cap em loop, e se estourar, retorna a resposta
        # completa sem sanitizar (preserva funcionalidade > completeza).
        content_length_str = response.headers.get("content-length")
        if content_length_str:
            try:
                if int(content_length_str) > _SANITIZER_MAX_BUFFER:
                    logger.warning(
                        "Response > %d bytes — skipping sanitization (path=%s)",
                        _SANITIZER_MAX_BUFFER, request.url.path,
                    )
                    return response
            except ValueError:
                pass

        # Read body com cap. Se estourar durante a leitura, drena o resto
        # e retorna sem sanitizar (garante que o cliente recebe a resposta
        # integra).
        body = b""
        oversized = False
        async for chunk in response.body_iterator:
            if isinstance(chunk, bytes):
                body += chunk
            else:
                body += chunk.encode("utf-8")
            if len(body) > _SANITIZER_MAX_BUFFER:
                oversized = True
                # Continua drenando pra nao deixar iterator pendente
                async for rest in response.body_iterator:
                    body += (
                        rest if isinstance(rest, bytes)
                        else rest.encode("utf-8")
                    )
                break

        if oversized:
            logger.warning(
                "Response excedeu cap durante leitura — sanitizacao skipped "
                "(path=%s size=%d)",
                request.url.path, len(body),
            )
            # Retorna response com body original; headers preservados.
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        try:
            text = body.decode("utf-8")
            sanitized = sanitize_text(text)
            body = sanitized.encode("utf-8")
        except (UnicodeDecodeError, Exception):
            pass  # leave body as-is if we can't process it

        # Rebuild response with sanitized body
        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
