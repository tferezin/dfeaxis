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

    # MercadoPago
    mp_access_token: str = ""
    mp_webhook_secret: str = ""

    # Resend (transactional email)
    resend_api_key: str = ""
    resend_from_email: str = "DFeAxis <noreply@dfeaxis.com.br>"

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
