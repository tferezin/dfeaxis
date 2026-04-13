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
from routers import documents, certificates, polling, credits, api_keys, tenants, manifestacao, nfse, sap_drc, billing, chat
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


app = FastAPI(
    title="DFeAxis API",
    description="Captura automática de documentos fiscais recebidos da SEFAZ para SAP DRC",
    version="0.1.0",
    lifespan=lifespan,
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
app.include_router(chat.router, prefix="/api/v1", tags=["Chat Bot"])


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "dfeaxis",
        "tagline": "Captura automática de documentos fiscais recebidos da SEFAZ para SAP DRC",
    }
