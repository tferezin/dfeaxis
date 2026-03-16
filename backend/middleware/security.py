"""Middleware de segurança: headers, rate limiting, autenticação API key."""

import hashlib
import os
import time
from collections import defaultdict

from fastapi import Request, HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from db.supabase import get_supabase_client

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


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


# --- Rate Limiting Middleware ---

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting simples em memória. Para produção multi-instância, usar Redis."""

    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Rate limit baseado na API key ou IP
        api_key = request.headers.get("X-API-Key")
        client_id = api_key or request.client.host if request.client else "unknown"

        now = time.time()
        window_start = now - self.window_seconds

        # Limpa requests antigos
        self.requests[client_id] = [
            t for t in self.requests[client_id] if t > window_start
        ]

        if len(self.requests[client_id]) >= self.max_requests:
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(self.window_seconds)},
            )

        self.requests[client_id].append(now)
        return await call_next(request)


# --- API Key Authentication ---

async def verify_api_key(api_key: str = Security(api_key_header)) -> dict:
    """Valida API key e retorna dados do tenant."""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    sb = get_supabase_client()

    result = sb.table("api_keys").select(
        "id, tenant_id, is_active"
    ).eq("key_hash", key_hash).eq("is_active", True).execute()

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid API key")

    key_data = result.data[0]

    # Atualiza last_used_at
    sb.table("api_keys").update(
        {"last_used_at": "now()"}
    ).eq("id", key_data["id"]).execute()

    return {"tenant_id": key_data["tenant_id"], "api_key_id": key_data["id"]}


# --- JWT Authentication (dashboard) ---

async def verify_jwt_token(request: Request) -> dict:
    """Valida JWT do Supabase Auth e retorna tenant_id."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = auth_header.split(" ", 1)[1]
    sb = get_supabase_client()

    try:
        user_response = sb.auth.get_user(token)
        user = user_response.user
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Busca tenant_id do user
    result = sb.table("tenants").select("id").eq(
        "user_id", user.id
    ).execute()

    tenant_id = result.data[0]["id"] if result.data else None
    return {"tenant_id": tenant_id, "user_id": user.id}
