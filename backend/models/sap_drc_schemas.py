"""Pydantic schemas for SAP DRC NFe Inbound Simple API compatibility layer.

Limites de tamanho explicitos defendem contra DoS por payload gigante:
- xml: 5MB (NFe tipica tem 5-50 KB; SAP envia em UTF-8 sem compressao)
- listas (cnpj, uuidList): max 100 itens por request
- strings curtas: max razoavel (CNPJ 14 + formatacao = 18, UUID 36, etc)
"""

from pydantic import BaseModel, Field


# Limite de XML cru — 5MB. NFe normal e ~10-50 KB, e nf rejeitado pela
# SEFAZ por exceder 500KB. Damos 100x de folga e cortamos antes de
# qualquer parsing.
_MAX_XML_BYTES = 5_000_000

# Listas: 100 itens / request e mais que suficiente (SAP DRC nem manda
# tanto assim por chamada na pratica). Bloqueia atacante mandar 1M de
# CNPJs e estourar memoria do parser.
_MAX_LIST_ITEMS = 100


class InboundInvoiceRetrieveRequest(BaseModel):
    cnpj: list[str] = Field(..., max_length=_MAX_LIST_ITEMS)


class NotaFiscalFragment(BaseModel):
    uuid: str = Field(..., max_length=64)
    accessKey: str = Field(..., max_length=64)
    companyCNPJ: str = Field(..., max_length=32)
    companyRegion: str = Field(default="", max_length=8)
    supplierCNPJ: str = Field(default="", max_length=32)
    supplierRegion: str = Field(default="", max_length=8)
    notaFiscalNumber: str = Field(default="", max_length=32)
    notaFiscalSeries: str = Field(default="", max_length=16)
    notaFiscalStatusCode: str = Field(default="100", max_length=16)
    notaFiscalStatusDescription: str = Field(
        default="Authorized", max_length=512
    )
    environmentType: str = Field(default="2", max_length=4)
    issueType: str = Field(default="", max_length=4)
    issueDate: str = Field(default="", max_length=32)
    processStatusCode: str = Field(default="F00", max_length=16)
    processStatusDescription: str = Field(
        default="Valid Signature, Document is Authorized at SEFAZ",
        max_length=512,
    )


class EventFragment(BaseModel):
    uuid: str = Field(..., max_length=64)
    accessKey: str = Field(..., max_length=64)
    eventType: str = Field(default="", max_length=16)
    eventSequence: str = Field(default="", max_length=8)
    eventDescription: str = Field(default="", max_length=512)
    eventStatusCode: str = Field(default="", max_length=16)
    eventStatusDescription: str = Field(default="", max_length=512)
    issueDate: str = Field(default="", max_length=32)
    processStatusCode: str = Field(default="", max_length=16)
    processStatusDescription: str = Field(default="", max_length=512)


class InboundInvoiceRetrieveResponse(BaseModel):
    eventFragmentList: list[EventFragment] = []
    notaFiscalFragmentList: list[NotaFiscalFragment] = []


class OfficialDocumentReceiveRequest(BaseModel):
    xml: str = Field(..., max_length=_MAX_XML_BYTES)


class InboundInvoiceDeleteRequest(BaseModel):
    uuidList: list[str] = Field(..., max_length=_MAX_LIST_ITEMS)
