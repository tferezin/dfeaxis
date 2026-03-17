"""Pydantic schemas for SAP DRC NFe Inbound Simple API compatibility layer."""

from pydantic import BaseModel


class InboundInvoiceRetrieveRequest(BaseModel):
    cnpj: list[str]


class NotaFiscalFragment(BaseModel):
    uuid: str
    accessKey: str
    companyCNPJ: str
    companyRegion: str = ""
    supplierCNPJ: str = ""
    supplierRegion: str = ""
    notaFiscalNumber: str = ""
    notaFiscalSeries: str = ""
    notaFiscalStatusCode: str = "100"
    notaFiscalStatusDescription: str = "Authorized"
    environmentType: str = "2"
    issueType: str = ""
    issueDate: str = ""
    processStatusCode: str = "F00"
    processStatusDescription: str = "Valid Signature, Document is Authorized at SEFAZ"


class EventFragment(BaseModel):
    uuid: str
    accessKey: str
    eventType: str = ""
    eventSequence: str = ""
    eventDescription: str = ""
    eventStatusCode: str = ""
    eventStatusDescription: str = ""
    issueDate: str = ""
    processStatusCode: str = ""
    processStatusDescription: str = ""


class InboundInvoiceRetrieveResponse(BaseModel):
    eventFragmentList: list[EventFragment] = []
    notaFiscalFragmentList: list[NotaFiscalFragment] = []


class OfficialDocumentReceiveRequest(BaseModel):
    xml: str


class InboundInvoiceDeleteRequest(BaseModel):
    uuidList: list[str]
