"""Pydantic models para request/response."""

import re
from datetime import date, datetime
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, Field


# --- Custom Validators ---

def _validate_cnpj(value: str) -> str:
    """Valida CNPJ com checksum mod 11.

    Aceita com ou sem formatacao (pontos, barra, hifen).
    Retorna apenas os 14 digitos.
    """
    # Strip formatting characters
    cleaned = re.sub(r"[.\-/]", "", str(value).strip())

    if not cleaned.isdigit() or len(cleaned) != 14:
        raise ValueError("CNPJ deve conter exatamente 14 digitos")

    # Rejeita CNPJs com todos os digitos iguais (ex: 00000000000000)
    if len(set(cleaned)) == 1:
        raise ValueError("CNPJ invalido")

    # Calcula primeiro digito verificador
    weights_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(int(cleaned[i]) * weights_1[i] for i in range(12))
    remainder = total % 11
    digit_1 = 0 if remainder < 2 else 11 - remainder

    if int(cleaned[12]) != digit_1:
        raise ValueError("CNPJ invalido: digito verificador incorreto")

    # Calcula segundo digito verificador
    weights_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(int(cleaned[i]) * weights_2[i] for i in range(13))
    remainder = total % 11
    digit_2 = 0 if remainder < 2 else 11 - remainder

    if int(cleaned[13]) != digit_2:
        raise ValueError("CNPJ invalido: digito verificador incorreto")

    return cleaned


def _validate_nsu(value: str) -> str:
    """Valida NSU: exatamente 15 digitos, zero-padded."""
    cleaned = str(value).strip()
    if not cleaned.isdigit():
        raise ValueError("NSU deve conter apenas digitos")
    if len(cleaned) > 15:
        raise ValueError("NSU deve ter no maximo 15 digitos")
    # Zero-pad to 15 digits
    return cleaned.zfill(15)


def _validate_chave_acesso(value: str) -> str:
    """Valida chave de acesso: exatamente 44 digitos."""
    cleaned = str(value).strip()
    if not cleaned.isdigit() or len(cleaned) != 44:
        raise ValueError("Chave de acesso deve conter exatamente 44 digitos")
    return cleaned


# --- Annotated Types ---

CnpjStr = Annotated[str, BeforeValidator(_validate_cnpj)]
NsuStr = Annotated[str, BeforeValidator(_validate_nsu)]
ChaveAcessoStr = Annotated[str, BeforeValidator(_validate_chave_acesso)]


# --- Documentos ---

class DocumentoOut(BaseModel):
    chave: str
    tipo: str
    nsu: str
    xml_b64: str
    fetched_at: datetime
    manifestacao_status: Optional[str] = None
    is_resumo: bool = False


class DocumentosResponse(BaseModel):
    cnpj: str
    documentos: list[DocumentoOut]
    ult_nsu: str
    total: int


class ConfirmarResponse(BaseModel):
    status: str = "discarded"


class RetroativoRequest(BaseModel):
    cnpj: CnpjStr
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
    api_key: Optional[str] = None
    api_key_id: Optional[str] = None


class TenantRegisterRequest(BaseModel):
    company_name: str
    email: str
    phone: Optional[str] = None
    # GA4 client_id do cookie _ga — capturado no signup do frontend
    # para permitir atribuição correta de conversões no Google Ads quando
    # o webhook do Stripe dispara o evento purchase via Measurement Protocol.
    # Formato esperado: "XXXXXXXX.YYYYYYYY" (≤ 24 chars na prática). Limite
    # generoso em 64 + regex restritivo para não aceitar lixo/strings gigantes.
    ga_client_id: Optional[str] = Field(
        default=None,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    # Campaign attribution (last-touch) — capturado do localStorage no signup
    # page. Vem dos query params do anúncio (utm_*) ou do auto-tagging do
    # Google Ads (gclid). Usado para relatórios internos de ROAS sem depender
    # exclusivamente do painel do GA4. Todos opcionais — signups orgânicos
    # chegam com todos null.
    utm_source: Optional[str] = Field(default=None, max_length=255)
    utm_medium: Optional[str] = Field(default=None, max_length=255)
    utm_campaign: Optional[str] = Field(default=None, max_length=255)
    utm_term: Optional[str] = Field(default=None, max_length=255)
    utm_content: Optional[str] = Field(default=None, max_length=255)
    gclid: Optional[str] = Field(default=None, max_length=512)
    fbclid: Optional[str] = Field(default=None, max_length=512)
    referrer: Optional[str] = Field(default=None, max_length=2048)
    landing_path: Optional[str] = Field(default=None, max_length=2048)


# --- Polling ---

class PollingTriggerRequest(BaseModel):
    cnpj: CnpjStr
    tipos: list[str] = Field(default=["nfe", "cte"])


class PollingTipoResult(BaseModel):
    tipo: str
    status: str
    cstat: str = ""
    xmotivo: str = ""
    docs_found: int = 0
    latency_ms: int = 0
    error: Optional[str] = None
    saved_to_db: bool = False

class PollingTriggerResponse(BaseModel):
    status: str
    cnpj: str
    tipos: list[str]
    docs_found: int = 0
    results: list[PollingTipoResult] = []


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

# --- Manifestação ---

class ManifestacaoRequest(BaseModel):
    chave_acesso: ChaveAcessoStr
    tipo_evento: str = Field(pattern=r"^(210210|210200|210220|210240)$")
    justificativa: str = Field(default="", max_length=255)


class ManifestacaoResponse(BaseModel):
    chave_acesso: str
    tipo_evento: str
    descricao: str
    cstat: str
    xmotivo: str
    protocolo: Optional[str] = None
    success: bool


class ManifestacaoBatchRequest(BaseModel):
    chaves: list[ChaveAcessoStr] = Field(min_length=1, max_length=50)
    tipo_evento: str = Field(pattern=r"^(210210|210200|210220|210240)$")
    justificativa: str = Field(default="", max_length=255)


class ManifestacaoBatchResponse(BaseModel):
    total: int
    sucesso: int
    erro: int
    resultados: list[ManifestacaoResponse]


class DocumentoPendenteOut(BaseModel):
    chave: str
    nsu: str
    cnpj_emitente: Optional[str] = None
    razao_social_emitente: Optional[str] = None
    valor: Optional[str] = None
    manifestacao_status: str
    fetched_at: datetime


# --- SEFAZ Status ---

class SefazEndpointStatus(BaseModel):
    tipo: str
    ambiente: str
    status: str
    latency_ms: Optional[int] = None


class SefazStatusResponse(BaseModel):
    endpoints: list[SefazEndpointStatus]


# --- NFS-e (Ambiente Nacional - ADN) ---

class NfseOut(BaseModel):
    chave: str
    nsu: str
    xml_content: str
    codigo_municipio: Optional[str] = None
    codigo_servico: Optional[str] = None
    data_emissao: Optional[str] = None
    valor_servico: Optional[str] = None


class NfseListResponse(BaseModel):
    cnpj: str
    documentos: list[NfseOut]
    total: int
    disclaimer: str = ""


class NfsePollingResponse(BaseModel):
    status: str
    cnpj: str
    docs_found: int = 0
    ult_nsu: str
    message: str
    disclaimer: str = ""
