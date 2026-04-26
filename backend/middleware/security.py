"""Middleware de segurança: headers, rate limiting, autenticação API key, request ID."""

import hashlib
import hmac
import logging
import os
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from db.supabase import get_supabase_client

logger = logging.getLogger("dfeaxis.security")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Context var for request ID, accessible from anywhere in the request lifecycle
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


# --- Endpoint Rate Limit Classification ---

def get_endpoint_limit(path: str) -> int:
    """Return the per-minute rate limit for a given request path.

    Categories:
      - Auth endpoints (certificate upload, API key creation): 20/min
      - SEFAZ-facing endpoints (polling, manifestacao, retroativo): 30/min
      - Read endpoints (documents list, balance, certificates list, logs): 100/min
      - Webhooks: 50/min
    """
    # Webhooks
    if "/webhook" in path:
        return 50

    # Auth / certificate management (write operations)
    if "/certificates/upload" in path or "/api-keys" in path or "/tenants/register" in path:
        return 20

    # SEFAZ-facing endpoints
    if "/polling" in path or "/manifestacao" in path or "/retroativo" in path:
        return 30

    # Read endpoints (GET on documents, balance, certificates list, logs, sefaz status)
    if any(segment in path for segment in (
        "/documentos", "/credits/balance", "/certificates", "/logs", "/sefaz/status",
    )):
        return 100

    # Default
    return 60


# --- Security Headers Middleware ---

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response


# --- Request ID Middleware ---

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate a unique request ID for every request, expose it via header and context var."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request_id_ctx.set(rid)
        request.state.request_id = rid

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


# --- Rate Limiting Middleware ---

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting em memória com limites por tipo de endpoint.

    Para produção multi-instância, usar Redis.
    """

    def __init__(self, app, window_seconds: int = 60):
        super().__init__(app)
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Rate limit baseado na API key ou IP
        api_key = request.headers.get("X-API-Key")
        client_id = api_key or (request.client.host if request.client else "unknown")

        now = time.time()
        window_start = now - self.window_seconds

        # Limpa requests antigos
        self.requests[client_id] = [
            t for t in self.requests[client_id] if t > window_start
        ]

        max_requests = get_endpoint_limit(request.url.path)

        if len(self.requests[client_id]) >= max_requests:
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_ip": client_ip,
                    "path": request.url.path,
                    "limit": max_requests,
                    "request_id": getattr(request.state, "request_id", ""),
                },
            )
            return JSONResponse(
                content={"detail": "Rate limit exceeded", "error_code": "RATE_LIMIT_EXCEEDED"},
                status_code=429,
                headers={"Retry-After": str(self.window_seconds)},
            )

        self.requests[client_id].append(now)
        return await call_next(request)


# --- Sanitized Error Response Helper ---

_ERROR_MESSAGES = {
    401: "Authentication required.",
    403: "Access denied.",
    404: "Resource not found.",
    500: "Internal server error.",
}


def _sanitized_error(status_code: int, error_code: str, detail: str | None = None) -> HTTPException:
    """Return an HTTPException with a safe, non-leaking message.

    Use `detail` only when it is an intentional, user-facing message (e.g. 'CNPJ not found').
    For unexpected errors, pass None and a generic message will be used.
    """
    safe_detail = detail if detail else _ERROR_MESSAGES.get(status_code, "An error occurred.")
    raise HTTPException(
        status_code=status_code,
        detail={"message": safe_detail, "error_code": error_code},
    )


# --- API Key Authentication ---

async def verify_api_key(request: Request, api_key: str = Security(api_key_header)) -> dict:
    """Valida API key e retorna dados do tenant.

    Uses timing-safe comparison for the key hash and logs failed attempts.
    """
    client_ip = request.client.host if request.client else "unknown"

    if not api_key:
        logger.info(
            "API key missing in request",
            extra={"client_ip": client_ip, "path": request.url.path},
        )
        raise HTTPException(
            status_code=401,
            detail={"message": "API key required", "error_code": "API_KEY_MISSING"},
        )

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    sb = get_supabase_client()

    result = sb.table("api_keys").select(
        "id, tenant_id, key_hash, is_active"
    ).eq("is_active", True).execute()

    # Use timing-safe comparison against all active keys
    matched_key = None
    for row in result.data:
        if hmac.compare_digest(row["key_hash"], key_hash):
            matched_key = row
            break

    if not matched_key:
        logger.warning(
            "Invalid API key attempt",
            extra={"client_ip": client_ip, "path": request.url.path},
        )
        raise HTTPException(
            status_code=401,
            detail={"message": "Invalid API key", "error_code": "API_KEY_INVALID"},
        )

    # Atualiza last_used_at
    sb.table("api_keys").update(
        {"last_used_at": "now()"}
    ).eq("id", matched_key["id"]).execute()

    return {"tenant_id": matched_key["tenant_id"], "api_key_id": matched_key["id"]}


# --- JWT Authentication (dashboard) ---

async def verify_jwt_token(request: Request) -> dict:
    """Valida JWT do Supabase Auth e retorna tenant_id.

    Catches specific exceptions and logs failures without exposing the token.
    """
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.info(
            "Missing or malformed Bearer token",
            extra={"client_ip": client_ip, "path": path},
        )
        raise HTTPException(
            status_code=401,
            detail={"message": "Bearer token required", "error_code": "TOKEN_MISSING"},
        )

    token = auth_header.split(" ", 1)[1]
    sb = get_supabase_client()

    try:
        user_response = sb.auth.get_user(token)
        user = user_response.user
        if not user:
            raise HTTPException(
                status_code=401,
                detail={"message": "Invalid token", "error_code": "TOKEN_INVALID"},
            )
    except HTTPException:
        raise
    except ConnectionError:
        logger.error(
            "Connection error while validating JWT",
            extra={"client_ip": client_ip, "path": path},
        )
        raise HTTPException(
            status_code=503,
            detail={"message": "Authentication service unavailable", "error_code": "AUTH_SERVICE_UNAVAILABLE"},
        )
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "JWT validation failed: %s",
            type(exc).__name__,
            extra={"client_ip": client_ip, "path": path},
        )
        raise HTTPException(
            status_code=401,
            detail={"message": "Invalid or expired token", "error_code": "TOKEN_INVALID"},
        )
    except Exception as exc:
        logger.warning(
            "Unexpected JWT validation error: %s",
            type(exc).__name__,
            extra={"client_ip": client_ip, "path": path},
        )
        raise HTTPException(
            status_code=401,
            detail={"message": "Invalid or expired token", "error_code": "TOKEN_INVALID"},
        )

    # Busca tenant_id do user
    result = sb.table("tenants").select("id").eq(
        "user_id", user.id
    ).execute()

    tenant_id = result.data[0]["id"] if result.data else None

    # If tenant_id is None and endpoint is NOT /tenants/register, deny access
    if tenant_id is None and "/tenants/register" not in path:
        logger.warning(
            "JWT valid but no tenant found for user, access denied",
            extra={"client_ip": client_ip, "path": path, "user_id": str(user.id)},
        )
        raise HTTPException(
            status_code=403,
            detail={"message": "No tenant associated with this account", "error_code": "TENANT_NOT_FOUND"},
        )

    return {"tenant_id": tenant_id, "user_id": user.id}


# --- Paths exempt from trial expiration check ---

_TRIAL_EXEMPT_PATHS = (
    "/tenants/me",
    "/tenants/settings",
    "/tenants/register",
    "/tenants/trial-status",
    "/credits/",
)


def _is_trial_exempt(path: str) -> bool:
    """Return True if the request path is exempt from trial checks."""
    return any(exempt in path for exempt in _TRIAL_EXEMPT_PATHS)


# --- Paths exempt from past_due (payment failure) block ---
#
# Quando um tenant esta past_due ha mais de 5 dias (regra 5+5), o middleware
# retorna 402 em endpoints protegidos. MAS existem paths que precisam ficar
# acessiveis pro cliente conseguir regularizar + manter compliance fiscal:
#
# 1. Billing (pagar): /billing/portal, /billing/checkout
# 2. Ver status: /alerts, /tenants/me
# 3. Compliance fiscal: GET documentos ja capturados, baixar XML
# 4. Suporte: /chat/
# 5. Read-only de historico: /manifestacao/historico, /manifestacao/pendentes,
#    /documentos/retroativo/{job_id} (status), /sefaz/status
#
# Endpoints de WRITE (captura nova, manifestacao nova, upload de cert) sao
# bloqueados normalmente — cliente so volta ao fluxo completo apos pagar.
_PAST_DUE_EXEMPT_PATHS = (
    "/billing/",       # portal, checkout — tudo de pagar
    "/alerts",
    "/tenants/me",
    "/tenants/settings",
    "/credits/",       # ver saldo
    "/chat/",          # suporte
    "/sefaz/status",   # health
    "/manifestacao/historico",
    "/manifestacao/pendentes",
)

# Metodos HTTP sempre liberados em past_due — read-only nunca bloqueia.
# Cliente bloqueado PRECISA conseguir baixar docs ja capturados (obrigacao
# fiscal/legal). Escrita (POST/PUT/DELETE/PATCH) sim e bloqueada.
_PAST_DUE_READ_ONLY_METHODS = ("GET", "HEAD", "OPTIONS")


def _is_past_due_exempt(request: Request) -> bool:
    """Libera request quando past_due. Regra:
    - GET/HEAD/OPTIONS: sempre libera (read-only nao bloqueia)
    - POST/PUT/DELETE/PATCH: so libera se path esta em _PAST_DUE_EXEMPT_PATHS
      (billing, chat, settings)
    """
    method = request.method.upper()
    if method in _PAST_DUE_READ_ONLY_METHODS:
        return True
    path = request.url.path
    return any(exempt in path for exempt in _PAST_DUE_EXEMPT_PATHS)


# Mensagem unificada pra trial bloqueado (cap OU tempo). Decisão de
# produto 2026-04-15: uma só mensagem em vez de 3 variantes — o cliente
# entende melhor e a call-to-action é a mesma (assinar um plano).
_TRIAL_BLOCKED_MESSAGE = (
    "Limite do período de teste atingido (500 documentos ou 10 dias). "
    "Assine um plano para continuar ativo em nossa plataforma."
)

_PAYMENT_OVERDUE_MESSAGE = (
    "Sua fatura está vencida. Regularize o pagamento para "
    "reativar o acesso às funcionalidades da plataforma."
)


async def verify_trial_active(request: Request, auth: dict) -> None:
    """Check if the tenant's trial is still active.

    Blocks access when any of:
    - subscription_status is 'expired' or 'cancelled'
    - trial_blocked_at is set (cap=500 docs confirmed OR time=10 days)
    - trial_expires_at is in the past (auto-marks expired)

    Raises 402 (Payment Required) with unified message. Called after
    verify_jwt_token for protected endpoints.
    """
    if _is_trial_exempt(request.url.path):
        return

    tenant_id = auth.get("tenant_id")
    if not tenant_id:
        return

    sb = get_supabase_client()
    result = sb.table("tenants").select(
        "subscription_status, trial_expires_at, trial_active, "
        "trial_blocked_at, trial_blocked_reason, current_period_end, "
        "past_due_since"
    ).eq("id", tenant_id).single().execute()

    if not result.data:
        return

    data = result.data
    status = data.get("subscription_status")

    # Hard block: subscription fully ended
    if status in ("expired", "cancelled"):
        raise HTTPException(
            status_code=402,
            detail={
                "message": _TRIAL_BLOCKED_MESSAGE,
                "code": "TRIAL_EXPIRED",
            },
        )

    # Past due: tolerancia de 5 dias apos past_due_since (regra 5+5).
    # Soft block granular: passada a tolerancia, bloqueia apenas endpoints
    # de ESCRITA (captura, manifestacao nova) e preserva read-only + billing
    # portal/checkout pra compliance fiscal e pagamento.
    if status == "past_due":
        now = datetime.now(timezone.utc)
        past_due_raw = data.get("past_due_since")

        if past_due_raw:
            past_due_dt = datetime.fromisoformat(
                past_due_raw.replace("Z", "+00:00")
            )
            # Usa timedelta direto pra comparar (precisao de microssegundos),
            # nao .days que trunca pra baixo. Antes: cliente que falhou as
            # 14:00 era bloqueado so as 14:00 do dia 11 em vez de no dia 10
            # as 14:00 (off-by-one de ate 24h).
            elapsed = now - past_due_dt
            if elapsed <= timedelta(days=5):
                # Dentro da tolerancia — libera tudo
                return
            # Passou dos 5 dias: soft block.
            # Libera read-only e endpoints de regularizacao (billing, chat).
            if _is_past_due_exempt(request):
                return
            raise HTTPException(
                status_code=402,
                detail={
                    "message": _PAYMENT_OVERDUE_MESSAGE,
                    "code": "PAYMENT_OVERDUE",
                    "days_since_failure": elapsed.days,
                },
            )

        # Fallback: past_due_since nao setado, usa current_period_end.
        # Mesmo soft-block aplica aqui — se cliente sem past_due_since
        # mas Stripe diz que esta past_due ha muito, bloqueia escrita.
        period_end = data.get("current_period_end")
        if period_end:
            period_dt = datetime.fromisoformat(
                period_end.replace("Z", "+00:00")
            )
            if now < period_dt:
                return
        if _is_past_due_exempt(request):
            return
        raise HTTPException(
            status_code=402,
            detail={
                "message": _PAYMENT_OVERDUE_MESSAGE,
                "code": "PAYMENT_OVERDUE",
            },
        )

    # Se não está em trial (ex: active), libera
    if status != "trial":
        return

    # Em trial: checa se foi bloqueado por cap (500 docs confirmados)
    # ou tempo (10 dias). Ambos setam trial_blocked_at via polling/confirmar
    # ou via email_job/middleware.
    if data.get("trial_blocked_at"):
        raise HTTPException(
            status_code=402,
            detail={
                "message": _TRIAL_BLOCKED_MESSAGE,
                "code": "TRIAL_EXPIRED",
            },
        )

    # Checa expiração por tempo (fallback se o email_job não rodou ainda)
    expires_at = data.get("trial_expires_at")
    if not expires_at:
        return

    expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)

    if now >= expires_dt:
        # Trial expirado — marca tenant como expired e bloqueia
        sb.table("tenants").update({
            "subscription_status": "expired",
            "trial_active": False,
            "trial_blocked_at": now.isoformat(),
            "trial_blocked_reason": "time",
        }).eq("id", tenant_id).execute()

        raise HTTPException(
            status_code=402,
            detail={
                "message": _TRIAL_BLOCKED_MESSAGE,
                "code": "TRIAL_EXPIRED",
            },
        )


async def verify_jwt_with_trial(request: Request) -> dict:
    """Combined dependency: JWT auth + trial expiration check.

    Use this instead of verify_jwt_token on endpoints that should be blocked
    when the trial has expired.
    """
    auth = await verify_jwt_token(request)
    await verify_trial_active(request, auth)
    return auth


async def verify_api_key_with_trial(
    request: Request, api_key: str = Security(api_key_header)
) -> dict:
    """Combined dependency: API key auth + trial/block check.

    Use instead of verify_api_key on endpoints where trial_blocked_at should
    return 402. Same unified message as verify_jwt_with_trial for consistency.
    Used by the SAP DRC compatibility layer so SAP systems hit the same
    enforcement gate as our native dashboard.
    """
    auth = await verify_api_key(request, api_key)
    await verify_trial_active(request, auth)
    return auth


async def verify_jwt_or_api_key(request: Request) -> dict:
    """Dual auth: accepts either JWT Bearer token or X-API-Key header.

    Checks Authorization header first; falls back to X-API-Key. Both paths
    run the trial/block enforcement gate so SAP DRC clients hitting with
    API keys still get 402 when the trial is over — same enforcement as
    the native dashboard. Raises 401 if neither header is provided.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return await verify_jwt_with_trial(request)

    api_key_val = request.headers.get("X-API-Key")
    if api_key_val:
        auth = await verify_api_key(request, api_key_val)
        await verify_trial_active(request, auth)
        return auth

    raise HTTPException(
        status_code=401,
        detail={"message": "Authentication required. Provide Authorization Bearer token or X-API-Key header.", "error_code": "AUTH_MISSING"},
    )
