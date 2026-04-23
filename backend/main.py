"""DFeAxis - API principal FastAPI."""

import logging
import os
import sys
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from middleware.lgpd import ResponseSanitizerMiddleware
from middleware.security import (
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    request_id_ctx,
)
from routers import documents, certificates, polling, credits, api_keys, tenants, manifestacao, nfse, sap_drc, billing, chat, admin, alerts
from scheduler.polling_job import start_scheduler, stop_scheduler


# --- Structured JSON Logging ---

class JSONFormatter(logging.Formatter):
    """Emit structured JSON log lines. Never includes sensitive data."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_entry: dict = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Include request_id if available
        rid = request_id_ctx.get("")
        if rid:
            log_entry["request_id"] = rid

        # Merge extra fields (exclude internal LogRecord attributes)
        _internal = {
            "name", "msg", "args", "created", "relativeCreated", "exc_info",
            "exc_text", "stack_info", "lineno", "funcName", "pathname",
            "filename", "module", "thread", "threadName", "process",
            "processName", "levelname", "levelno", "message", "msecs",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in _internal and not key.startswith("_"):
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


_configure_logging()

logger = logging.getLogger("dfeaxis.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: inicia e para o scheduler."""
    logger.info("DFeAxis starting up")
    scheduler = start_scheduler()
    yield
    stop_scheduler(scheduler)
    logger.info("DFeAxis shut down")


# Em produção, desligamos Swagger/ReDoc/openapi.json para não expor o
# schema da API (rotas, auth, modelos) a scanners automatizados. Em
# dev/staging continuam abertos pra facilitar debug.
_IS_PRODUCTION = os.getenv("ENVIRONMENT") == "production"

app = FastAPI(
    title="DFeAxis API",
    description="Captura automática de documentos fiscais recebidos da SEFAZ para SAP DRC",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
)

# --- Middleware (order matters — outermost first) ---

# CORS — sanitise origins, use explicit methods and headers
raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
cors_origins = [o.strip().rstrip("/") for o in raw_origins if o.strip()]
# Always allow the Vercel frontend
if "https://frontend-henna-five-35.vercel.app" not in cors_origins:
    cors_origins.append("https://frontend-henna-five-35.vercel.app")
logger.info(f"CORS origins: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Response sanitizer (LGPD — masks CNPJs, emails, PEM data in responses)
app.add_middleware(ResponseSanitizerMiddleware)

# Rate limiting (per-endpoint limits applied inside middleware)
app.add_middleware(RateLimitMiddleware)

# Request ID (generates UUID, sets context var and response header)
app.add_middleware(RequestIDMiddleware)

# Trusted hosts (production only)
if os.getenv("ENVIRONMENT") == "production":
    allowed_hosts = os.getenv("ALLOWED_HOSTS", "api.dfeaxis.com.br").split(",")
    allowed_hosts = [h.strip() for h in allowed_hosts if h.strip()]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


# --- Request Logging Middleware ---

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log method, path, status_code, latency_ms, request_id.

    NEVER logs request body or authorization headers.
    """
    start = time.perf_counter()

    response = await call_next(request)

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    rid = getattr(request.state, "request_id", request_id_ctx.get(""))

    logger.info(
        "%s %s %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
        extra={
            "request_id": rid,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    return response


# --- Global Exception Handler ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a sanitized response.

    Never expose internal exception details to the client.
    """
    rid = getattr(request.state, "request_id", request_id_ctx.get(""))
    logger.error(
        "Unhandled exception: %s",
        type(exc).__name__,
        extra={"request_id": rid, "path": request.url.path},
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "message": "Internal server error",
                "error_code": "INTERNAL_ERROR",
                "request_id": rid,
            }
        },
    )


# --- Routers ---
app.include_router(documents.router, prefix="/api/v1", tags=["Documentos"])
app.include_router(certificates.router, prefix="/api/v1", tags=["Certificados"])
app.include_router(polling.router, prefix="/api/v1", tags=["Polling"])
app.include_router(credits.router, prefix="/api/v1", tags=["Créditos"])
app.include_router(api_keys.router, prefix="/api/v1", tags=["API Keys"])
app.include_router(tenants.router, prefix="/api/v1", tags=["Tenants"])
app.include_router(manifestacao.router, prefix="/api/v1", tags=["Manifestação"])
app.include_router(nfse.router, prefix="/api/v1", tags=["NFS-e"])
app.include_router(sap_drc.router, prefix="/sap-drc", tags=["SAP DRC Compatibility"])
app.include_router(billing.router, prefix="/api/v1", tags=["Billing"])
app.include_router(alerts.router, prefix="/api/v1", tags=["Alerts"])
app.include_router(chat.router, prefix="/api/v1", tags=["Chat Bot"])
app.include_router(admin.router, prefix="/api/v1", tags=["Admin"])


# --- Health Check ---

import asyncio
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "down", "not_configured", "skipped"]
    latency_ms: Optional[int] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    service: str
    version: str
    dependencies: list[DependencyStatus]
    timestamp: str


async def _check_supabase() -> DependencyStatus:
    start = time.perf_counter()
    try:
        from db.supabase import get_supabase_client

        def _run() -> None:
            sb = get_supabase_client()
            sb.table("tenants").select("id").limit(1).execute()

        await asyncio.wait_for(asyncio.to_thread(_run), timeout=2.0)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DependencyStatus(name="supabase", status="ok", latency_ms=latency_ms)
    except asyncio.TimeoutError:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DependencyStatus(
            name="supabase",
            status="down",
            latency_ms=latency_ms,
            error="Timeout > 2s",
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DependencyStatus(
            name="supabase",
            status="down",
            latency_ms=latency_ms,
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )


async def _check_stripe() -> DependencyStatus:
    from config import settings

    if not settings.stripe_secret_key:
        return DependencyStatus(name="stripe", status="not_configured")

    start = time.perf_counter()
    try:
        from services.billing.stripe_client import get_stripe

        def _run() -> None:
            stripe = get_stripe()
            stripe.Balance.retrieve()

        await asyncio.wait_for(asyncio.to_thread(_run), timeout=2.0)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DependencyStatus(name="stripe", status="ok", latency_ms=latency_ms)
    except asyncio.TimeoutError:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DependencyStatus(
            name="stripe",
            status="down",
            latency_ms=latency_ms,
            error="Timeout > 2s",
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DependencyStatus(
            name="stripe",
            status="down",
            latency_ms=latency_ms,
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )


async def _check_resend() -> DependencyStatus:
    from config import settings

    if not settings.resend_api_key:
        return DependencyStatus(name="resend", status="not_configured")

    start = time.perf_counter()
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(
                "https://api.resend.com/domains",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
        latency_ms = int((time.perf_counter() - start) * 1000)
        if resp.status_code == 200:
            return DependencyStatus(
                name="resend", status="ok", latency_ms=latency_ms
            )
        if resp.status_code == 401:
            # Endpoint reachable but key invalid — infra up, config wrong.
            return DependencyStatus(
                name="resend",
                status="degraded",
                latency_ms=latency_ms,
                error="Invalid API key",
            )
        return DependencyStatus(
            name="resend",
            status="degraded",
            latency_ms=latency_ms,
            error=f"HTTP {resp.status_code}",
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DependencyStatus(
            name="resend",
            status="down",
            latency_ms=latency_ms,
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Checa dependências críticas reais (Supabase, Stripe, Resend).

    - 200 se tudo OK ou apenas deps não-críticas degradadas.
    - 503 se alguma dep crítica (Supabase) está down ou se o timeout geral
      de 5s for estourado.
    - SEFAZ é marcado `skipped` por design (evita consumo indevido).
    """
    deps: list[DependencyStatus]
    overall_timeout = False

    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                _check_supabase(),
                _check_stripe(),
                _check_resend(),
                return_exceptions=False,
            ),
            timeout=5.0,
        )
        deps = list(results)
    except asyncio.TimeoutError:
        overall_timeout = True
        deps = [
            DependencyStatus(
                name="health_check",
                status="down",
                error="Overall timeout > 5s",
            )
        ]

    # SEFAZ — skipped by design
    deps.append(
        DependencyStatus(
            name="sefaz",
            status="skipped",
            error="Checked on-demand to avoid consumo indevido",
        )
    )

    # Aggregation
    critical_deps = [d for d in deps if d.name in ("supabase",)]
    if overall_timeout or any(d.status == "down" for d in critical_deps):
        overall: Literal["ok", "degraded", "down"] = "down"
        status_code = 503
    elif any(
        d.status in ("down", "degraded")
        for d in deps
        if d.status != "skipped"
    ):
        overall = "degraded"
        status_code = 200  # LB não faz failover em dep não-crítica
    else:
        overall = "ok"
        status_code = 200

    body = HealthResponse(
        status=overall,
        service="dfeaxis",
        version="0.1.0",
        dependencies=deps,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    return JSONResponse(content=body.model_dump(), status_code=status_code)
