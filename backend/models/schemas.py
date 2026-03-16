"""Pydantic models para request/response."""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


# --- Documentos ---

class DocumentoOut(BaseModel):
    chave: str
    tipo: str
    nsu: str
    xml_b64: str
    fetched_at: datetime


class DocumentosResponse(BaseModel):
    cnpj: str
    documentos: list[DocumentoOut]
    ult_nsu: str
    total: int


class ConfirmarResponse(BaseModel):
    status: str = "discarded"


class RetroativoRequest(BaseModel):
    cnpj: str
    tipo: str = Field(pattern=r"^(nfe|cte|mdfe)$")
    data_inicio: date
    data_fim: date


class RetroativoResponse(BaseModel):
    job_id: str
    status: str = "processing"
    estimativa_s: int = 45


class RetroativoStatusResponse(BaseModel):
    job_id: str
    status: str
    docs_found: int = 0
    progress_pct: int = 0


# --- Certificados ---

class CertificateOut(BaseModel):
    id: str
    cnpj: str
    company_name: Optional[str]
    valid_from: Optional[date]
    valid_until: Optional[date]
    is_active: bool
    last_polling_at: Optional[datetime]
    polling_mode: Optional[str] = None


class CertificateUploadResponse(BaseModel):
    certificate_id: str
    cnpj: str
    valid_until: Optional[date]


# --- Polling ---

class PollingTriggerRequest(BaseModel):
    cnpj: str
    tipos: list[str] = Field(default=["nfe", "cte"])


class PollingTriggerResponse(BaseModel):
    status: str
    cnpj: str
    tipos: list[str]
    docs_found: int = 0


# --- Créditos ---

class CreditBalanceResponse(BaseModel):
    tenant_id: str
    credits: int


class CheckoutRequest(BaseModel):
    amount: int = Field(gt=0, description="Quantidade de créditos a comprar")


class CheckoutResponse(BaseModel):
    checkout_url: str
    preference_id: str


# --- SEFAZ Status ---

class SefazEndpointStatus(BaseModel):
    tipo: str
    ambiente: str
    status: str
    latency_ms: Optional[int] = None


class SefazStatusResponse(BaseModel):
    endpoints: list[SefazEndpointStatus]
