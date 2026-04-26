"""SAP DRC NFe Inbound Simple API compatibility layer.

Implements the same REST contract as SAP Document and Reporting Compliance
so that SAP systems can point to DFeAxis as a provider via BTP Destination.

Mounted at /sap-drc prefix in main.py.
"""

import logging
from lxml import etree
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from db.supabase import get_supabase_client
from middleware.security import verify_api_key_with_trial
from services.billing.consumption import increment_consumption
from models.sap_drc_schemas import (
    EventFragment,
    InboundInvoiceDeleteRequest,
    InboundInvoiceRetrieveRequest,
    InboundInvoiceRetrieveResponse,
    NotaFiscalFragment,
    OfficialDocumentReceiveRequest,
)

logger = logging.getLogger("dfeaxis.sap_drc")

router = APIRouter()

# NF-e XML namespaces
NFE_NS = "http://www.portalfiscal.inf.br/nfe"
NS = {"nfe": NFE_NS}


def _safe_xml_parser() -> etree.XMLParser:
    """Parser endurecido contra XXE / billion laughs / SSRF via DTD.

    - resolve_entities=False: bloqueia expansao de entidades (XXE classico
      e billion laughs). XMLs de NFe nao usam entidades customizadas.
    - no_network=True: bloqueia SYSTEM/PUBLIC com URL externa (DTD/entity
      external resolution faz o parser fazer GET pra URL atacante).
    - huge_tree=False: rejeita arvores absurdamente grandes que exigiriam
      muita memoria pra parsear (defesa em profundidade junto do max_length
      do schema Pydantic).
    - load_dtd=False: nao processa DTD declarado inline. NFe nao usa.

    Como sap_drc recebe XML de cliente (push model), nao podemos confiar.
    Aplicar este parser em TODA chamada etree.fromstring/parse no router.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        load_dtd=False,
    )

# UF code -> state abbreviation mapping (IBGE codes)
UF_CODE_MAP = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
    "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
    "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
    "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
    "52": "GO", "53": "DF",
}


def _find_text(root: etree._Element, xpath: str) -> str:
    """Find text at xpath with NF-e namespace, return empty string if missing."""
    el = root.find(xpath, NS)
    return el.text.strip() if el is not None and el.text else ""


def parse_nfe_xml(xml_str: str) -> dict:
    """Extract NF-e metadata from XML for SAP DRC NotaFiscalFragment.

    Handles both nfeProc (authorized envelope) and NFe (raw) root elements.
    Returns a dict with keys matching NotaFiscalFragment field names.
    """
    try:
        root = etree.fromstring(
            xml_str.encode("utf-8") if isinstance(xml_str, str) else xml_str,
            _safe_xml_parser(),
        )
    except etree.XMLSyntaxError:
        return {}

    # Strip namespace prefix for tag comparison
    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    # Navigate to the infNFe element depending on root structure
    if root_tag == "nfeProc":
        inf_nfe = root.find(".//nfe:NFe/nfe:infNFe", NS)
    elif root_tag == "NFe":
        inf_nfe = root.find(".//nfe:infNFe", NS)
    else:
        # Try without namespace (some XMLs may not use namespaces)
        inf_nfe = root.find(".//infNFe")

    if inf_nfe is None:
        return {}

    # Access key from infNFe Id attribute (format: "NFe" + 44 digits)
    ch_nfe = inf_nfe.get("Id", "")
    if ch_nfe.startswith("NFe"):
        ch_nfe = ch_nfe[3:]

    # ide - identification
    ide_prefix = "nfe:ide/"
    n_nf = _find_text(inf_nfe, f"{ide_prefix}nfe:nNF")
    serie = _find_text(inf_nfe, f"{ide_prefix}nfe:serie")
    tp_amb = _find_text(inf_nfe, f"{ide_prefix}nfe:tpAmb")
    tp_emis = _find_text(inf_nfe, f"{ide_prefix}nfe:tpEmis")
    dh_emi = _find_text(inf_nfe, f"{ide_prefix}nfe:dhEmi")
    c_uf = _find_text(inf_nfe, f"{ide_prefix}nfe:cUF")

    # Format issue date to YYYY-MM-DD
    issue_date = ""
    if dh_emi:
        try:
            # dhEmi can be "2024-01-15T10:30:00-03:00" or "2024-01-15"
            issue_date = dh_emi[:10]
        except (ValueError, IndexError):
            issue_date = dh_emi

    # emit - supplier (emitter)
    supplier_cnpj = _find_text(inf_nfe, "nfe:emit/nfe:CNPJ")
    supplier_uf = _find_text(inf_nfe, "nfe:emit/nfe:enderEmit/nfe:UF")

    # dest - company (receiver/destinatario)
    company_cnpj = _find_text(inf_nfe, "nfe:dest/nfe:CNPJ")
    company_uf = _find_text(inf_nfe, "nfe:dest/nfe:enderDest/nfe:UF")

    # Protocol info from protNFe (inside nfeProc)
    cstat = ""
    xmotivo = ""
    if root_tag == "nfeProc":
        prot = root.find(".//nfe:protNFe/nfe:infProt", NS)
        if prot is not None:
            cstat = _find_text(prot, "nfe:cStat")
            xmotivo = _find_text(prot, "nfe:xMotivo")

    # Derive region from UF code if UF string not available
    if not supplier_uf and c_uf:
        supplier_uf = UF_CODE_MAP.get(c_uf, "")
    # Also derive company region from access key (positions 0-1 = UF code)
    if not company_uf and len(ch_nfe) >= 2:
        company_uf = UF_CODE_MAP.get(ch_nfe[:2], "")

    return {
        "accessKey": ch_nfe,
        "companyCNPJ": company_cnpj,
        "companyRegion": company_uf,
        "supplierCNPJ": supplier_cnpj,
        "supplierRegion": supplier_uf,
        "notaFiscalNumber": n_nf,
        "notaFiscalSeries": serie,
        "notaFiscalStatusCode": cstat or "100",
        "notaFiscalStatusDescription": xmotivo or "Authorized",
        "environmentType": tp_amb or "2",
        "issueType": tp_emis or "",
        "issueDate": issue_date,
    }


def _extract_chave_from_xml(xml_str: str) -> str:
    """Extract the chave de acesso (access key) from an NF-e XML string."""
    try:
        root = etree.fromstring(
            xml_str.encode("utf-8") if isinstance(xml_str, str) else xml_str,
            _safe_xml_parser(),
        )
    except etree.XMLSyntaxError:
        return ""

    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    if root_tag == "nfeProc":
        inf_nfe = root.find(".//nfe:NFe/nfe:infNFe", NS)
    elif root_tag == "NFe":
        inf_nfe = root.find(".//nfe:infNFe", NS)
    else:
        inf_nfe = root.find(".//infNFe")

    if inf_nfe is None:
        return ""

    ch_nfe = inf_nfe.get("Id", "")
    if ch_nfe.startswith("NFe"):
        ch_nfe = ch_nfe[3:]
    return ch_nfe


def _extract_cnpj_dest_from_xml(xml_str: str) -> str:
    """Extract the CNPJ destinatario from an NF-e XML string."""
    try:
        root = etree.fromstring(
            xml_str.encode("utf-8") if isinstance(xml_str, str) else xml_str,
            _safe_xml_parser(),
        )
    except etree.XMLSyntaxError:
        return ""

    # Try with namespace
    el = root.find(".//nfe:NFe/nfe:infNFe/nfe:dest/nfe:CNPJ", NS)
    if el is None:
        el = root.find(".//nfe:infNFe/nfe:dest/nfe:CNPJ", NS)
    if el is None:
        el = root.find(".//infNFe/dest/CNPJ")
    return el.text.strip() if el is not None and el.text else ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health")
async def health():
    """Application health check (SAP DRC contract)."""
    return {"status": "ok"}


@router.post(
    "/v1/retrieveInboundInvoices",
    response_model=InboundInvoiceRetrieveResponse,
)
async def retrieve_inbound_invoices(
    body: InboundInvoiceRetrieveRequest,
    auth: dict = Depends(verify_api_key_with_trial),
):
    """Retrieve inbound NF-e documents for the given CNPJs.

    Returns NotaFiscalFragments and EventFragments in the SAP DRC format.
    Only documents with status='available' and XML content are returned.
    """
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    nota_fragments: list[NotaFiscalFragment] = []
    event_fragments: list[EventFragment] = []

    for cnpj in body.cnpj:
        # Fetch available documents for this CNPJ belonging to the tenant
        result = (
            sb.table("documents")
            .select("id, chave_acesso, xml_content, tipo, fetched_at")
            .eq("tenant_id", tenant_id)
            .eq("cnpj", cnpj)
            .eq("status", "available")
            .not_.is_("xml_content", "null")
            .execute()
        )

        for doc in result.data:
            xml_content = doc.get("xml_content", "")
            meta = parse_nfe_xml(xml_content) if xml_content else {}

            fragment = NotaFiscalFragment(
                uuid=doc["id"],
                accessKey=meta.get("accessKey", doc["chave_acesso"]),
                companyCNPJ=meta.get("companyCNPJ", cnpj),
                companyRegion=meta.get("companyRegion", ""),
                supplierCNPJ=meta.get("supplierCNPJ", ""),
                supplierRegion=meta.get("supplierRegion", ""),
                notaFiscalNumber=meta.get("notaFiscalNumber", ""),
                notaFiscalSeries=meta.get("notaFiscalSeries", ""),
                notaFiscalStatusCode=meta.get("notaFiscalStatusCode", "100"),
                notaFiscalStatusDescription=meta.get(
                    "notaFiscalStatusDescription", "Authorized"
                ),
                environmentType=meta.get("environmentType", "2"),
                issueType=meta.get("issueType", ""),
                issueDate=meta.get("issueDate", ""),
                processStatusCode="F00",
                processStatusDescription=(
                    "Valid Signature, Document is Authorized at SEFAZ"
                ),
            )
            nota_fragments.append(fragment)

    return InboundInvoiceRetrieveResponse(
        eventFragmentList=event_fragments,
        notaFiscalFragmentList=nota_fragments,
    )


@router.get("/v1/downloadOfficialDocument")
async def download_official_document(
    accessKey: str = Query(..., description="Chave de acesso (44 digits)"),
    eventSequence: str | None = Query(None),
    eventType: str | None = Query(None),
    auth: dict = Depends(verify_api_key_with_trial),
):
    """Download the XML file of an official document.

    Returns raw XML with Content-Type: application/xml.
    """
    if not accessKey or len(accessKey) < 44:
        raise HTTPException(status_code=400, detail="Invalid accessKey")

    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    result = (
        sb.table("documents")
        .select("xml_content")
        .eq("tenant_id", tenant_id)
        .eq("chave_acesso", accessKey)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")

    xml_content = result.data[0].get("xml_content")
    if not xml_content:
        raise HTTPException(status_code=404, detail="XML content not available")

    return Response(content=xml_content, media_type="application/xml")


@router.post("/v1/receiveOfficialDocument", status_code=202)
async def receive_official_document(
    body: OfficialDocumentReceiveRequest,
    auth: dict = Depends(verify_api_key_with_trial),
):
    """Receive an NF-e XML document (push model).

    Parses the XML, extracts metadata, and stores in the documents table.
    Returns 202 Accepted on success, 409 if the document already exists.
    """
    xml_str = body.xml
    if not xml_str or not xml_str.strip():
        raise HTTPException(status_code=400, detail="Empty XML content")

    # Extract key metadata
    chave = _extract_chave_from_xml(xml_str)
    if not chave:
        raise HTTPException(
            status_code=422, detail="Could not extract access key from XML"
        )

    cnpj_dest = _extract_cnpj_dest_from_xml(xml_str)
    if not cnpj_dest:
        raise HTTPException(
            status_code=422, detail="Could not extract destinatario CNPJ from XML"
        )

    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Check if document already exists for this tenant
    existing = (
        sb.table("documents")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("chave_acesso", chave)
        .execute()
    )

    if existing.data:
        raise HTTPException(status_code=409, detail="Document already exists")

    # Determine tipo from access key (position 20-21: model code)
    # 55 = NF-e, 57 = CT-e, 58 = MDF-e, 65 = NFC-e
    modelo = chave[20:22] if len(chave) >= 22 else "55"
    tipo_map = {"55": "NFE", "57": "CTE", "58": "MDFE", "65": "NFCE"}
    tipo = tipo_map.get(modelo, "NFE")

    # Insert document
    sb.table("documents").insert({
        "tenant_id": tenant_id,
        "cnpj": cnpj_dest,
        "tipo": tipo,
        "chave_acesso": chave,
        "nsu": "000000000000000",  # Push model has no NSU
        "xml_content": xml_str,
        "status": "available",
    }).execute()

    logger.info(
        "Received official document via SAP DRC push",
        extra={"chave": chave, "tipo": tipo, "tenant_id": tenant_id},
    )

    return {"message": "Document received successfully"}


@router.delete("/v1/deleteInboundInvoices", status_code=204)
async def delete_inbound_invoices(
    body: InboundInvoiceDeleteRequest,
    auth: dict = Depends(verify_api_key_with_trial),
):
    """Delete (confirm delivery of) inbound invoices by UUID list.

    Marks documents as 'delivered' and clears the XML content.
    This is equivalent to the confirmar endpoint in our native API and is
    the point where the trial/monthly counter advances (same racional do
    /documentos/{chave}/confirmar nativo).
    """
    if not body.uuidList:
        raise HTTPException(status_code=400, detail="No UUID informed")

    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Transição atômica available → delivered por UUID. O filtro
    # status=available garante idempotência: se o SAP chamar 2x com o mesmo
    # UUID, a segunda chamada não conta nada (result.data vazio).
    confirmed_count = 0
    for doc_uuid in body.uuidList:
        result = sb.table("documents").update({
            "status": "delivered",
            "xml_content": None,
            "delivered_at": datetime.now(timezone.utc).isoformat(),
        }).eq(
            "id", doc_uuid,
        ).eq(
            "tenant_id", tenant_id,
        ).eq(
            "status", "available",
        ).execute()

        if result.data:
            confirmed_count += 1

    # Incrementa contador de consumo apenas pelos docs que de fato
    # transicionaram. Graceful — contador nunca quebra a confirmação.
    if confirmed_count > 0:
        try:
            increment_consumption(tenant_id, count=confirmed_count)
        except Exception as exc:  # noqa: BLE001 — contador nunca quebra confirmação
            logger.warning(
                "falha ao incrementar contador de consumo (SAP DRC batch) para tenant %s: %s",
                tenant_id, exc,
            )

    return Response(status_code=204)


@router.delete("/v1/deleteOfficialDocument", status_code=204)
async def delete_official_document(
    accessKey: str = Query(..., description="Chave de acesso"),
    eventSequence: str | None = Query(None),
    eventType: str | None = Query(None),
    auth: dict = Depends(verify_api_key_with_trial),
):
    """Delete the XML of an official document by access key.

    Marks the document as 'delivered' and clears XML content. Avança o
    contador de consumo (trial ou mensal) exatamente como o endpoint
    nativo /documentos/{chave}/confirmar.
    """
    if not accessKey:
        raise HTTPException(status_code=400, detail="Invalid accessKey")

    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Filtro status=available garante idempotência: chamada repetida retorna
    # 404 em vez de contar 2x o mesmo documento.
    result = (
        sb.table("documents")
        .update({
            "status": "delivered",
            "xml_content": None,
            "delivered_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("tenant_id", tenant_id)
        .eq("chave_acesso", accessKey)
        .eq("status", "available")
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")

    # Incrementa contador de consumo. Graceful — contador nunca quebra
    # a confirmação em si.
    try:
        increment_consumption(tenant_id, count=1)
    except Exception as exc:  # noqa: BLE001 — contador nunca quebra confirmação
        logger.warning(
            "falha ao incrementar contador de consumo (SAP DRC single) para tenant %s chave %s: %s",
            tenant_id, accessKey, exc,
        )

    return Response(status_code=204)
