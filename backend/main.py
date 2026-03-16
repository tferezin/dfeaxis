"""DFeAxis - API principal FastAPI."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from middleware.security import SecurityHeadersMiddleware, RateLimitMiddleware
from routers import documents, certificates, polling, credits
from scheduler.polling_job import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: inicia e para o scheduler."""
    scheduler = start_scheduler()
    yield
    stop_scheduler(scheduler)


app = FastAPI(
    title="DFeAxis API",
    description="Distribuição automática de DF-e da SEFAZ para SAP DRC",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Middleware ---
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

if os.getenv("ENVIRONMENT") == "production":
    allowed_hosts = os.getenv("ALLOWED_HOSTS", "api.dfeaxis.com.br").split(",")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# --- Routers ---
app.include_router(documents.router, prefix="/api/v1", tags=["Documentos"])
app.include_router(certificates.router, prefix="/api/v1", tags=["Certificados"])
app.include_router(polling.router, prefix="/api/v1", tags=["Polling"])
app.include_router(credits.router, prefix="/api/v1", tags=["Créditos"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "dfeaxis"}
