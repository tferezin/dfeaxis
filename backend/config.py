import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str = ""

    # Security
    cert_master_secret: str = Field(min_length=32)
    jwt_secret: str = ""
    allowed_hosts: str = "localhost"
    cors_origins: str = "http://localhost:3000"

    # Resend (transactional email)
    resend_api_key: str = ""
    resend_from_email: str = "DFeAxis <noreply@dfeaxis.com.br>"

    # Stripe billing
    stripe_publishable_key: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_portal_return_url: str = "http://localhost:3000/dashboard"
    stripe_checkout_success_url: str = "http://localhost:3000/dashboard?checkout=success"
    stripe_checkout_cancel_url: str = "http://localhost:3000/financeiro/creditos"

    # Google Analytics 4 — Measurement Protocol (server-side events)
    # ID mantido em sync com frontend/src/app/layout.tsx e landing-v3.html.
    ga4_measurement_id: str = "G-XZTRG63C53"
    # Secret criado em GA4 Admin → Data Streams → Measurement Protocol API secrets.
    # Deixar vazio desliga o envio server-side (código loga warning e segue).
    ga4_api_secret: str = ""

    # SEFAZ
    sefaz_ambiente: str = "2"  # ALWAYS default to homologação

    # App
    environment: str = "development"
    api_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    log_level: str = "INFO"
    log_format: str = "json"

    # Rate limits
    rate_limit_default: int = 100
    rate_limit_auth: int = 20
    rate_limit_sefaz: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Convenience module-level singleton (backward compatible name)
settings = get_settings()
