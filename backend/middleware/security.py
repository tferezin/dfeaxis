"""Middleware de segurança: headers, rate limiting, autenticação API key, request ID."""

import hashlib
import hmac
import logging
import os
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from datetime import datetime, timezone

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


async def verify_trial_active(request: Request, auth: dict) -> None:
    """Check if the tenant's trial is still active.

    If the trial has expired, updates the tenant and raises 403.
    Called after verify_jwt_token for protected endpoints.
    """
    if _is_trial_exempt(request.url.path):
        return

    tenant_id = auth.get("tenant_id")
    if not tenant_id:
        return

    sb = get_supabase_client()
    result = sb.table("tenants").select(
        "subscription_status, trial_expires_at, trial_active"
    ).eq("id", tenant_id).single().execute()

    if not result.data:
        return

    data = result.data
    status = data.get("subscription_status")

    # Only check trial-related statuses
    if status not in ("trial",):
        if status == "expired":
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Período de teste expirado. Realize o pagamento para continuar usando o DFeAxis.",
                    "code": "TRIAL_EXPIRED",
                },
            )
        return

    expires_at = data.get("trial_expires_at")
    if not expires_at:
        return

    expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)

    if now >= expires_dt:
        # Trial expired — update tenant
        sb.table("tenants").update({
            "subscription_status": "expired",
            "trial_active": False,
        }).eq("id", tenant_id).execute()

        raise HTTPException(
            status_code=403,
            detail={
                "message": "Período de teste expirado. Realize o pagamento para continuar usando o DFeAxis.",
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


async def verify_jwt_or_api_key(request: Request) -> dict:
    """Dual auth: accepts either JWT Bearer token or X-API-Key header.

    Checks Authorization header first; falls back to X-API-Key.
    Raises 401 if neither is provided.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return await verify_jwt_with_trial(request)

    api_key_val = request.headers.get("X-API-Key")
    if api_key_val:
        return await verify_api_key(request, api_key_val)

    raise HTTPException(
        status_code=401,
        detail={"message": "Authentication required. Provide Authorization Bearer token or X-API-Key header.", "error_code": "AUTH_MISSING"},
    )
