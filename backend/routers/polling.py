"""Endpoints de polling manual e logs."""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from db.supabase import get_supabase_client
from middleware.security import verify_api_key, verify_jwt_token
from models.schemas import PollingTriggerRequest, PollingTriggerResponse
from scheduler.polling_job import _poll_single

router = APIRouter()


@router.post("/polling/trigger", response_model=PollingTriggerResponse)
async def trigger_polling(
    body: PollingTriggerRequest,
    auth: dict = Depends(verify_jwt_token),
):
    """Força polling manual imediato para um CNPJ (modo teste)."""
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]

    # Busca certificado
    cert_result = sb.table("certificates").select("*").eq(
        "tenant_id", tenant_id
    ).eq("cnpj", body.cnpj).eq("is_active", True).execute()

    if not cert_result.data:
        raise HTTPException(status_code=404, detail="CNPJ não encontrado")

    cert = cert_result.data[0]

    # Busca tenant data
    tenant = sb.table("tenants").select(
        "id, polling_mode, credits, sefaz_ambiente"
    ).eq("id", tenant_id).single().execute()

    total_docs = 0
    for tipo in body.tipos:
        if tipo not in ("nfe", "cte", "mdfe"):
            continue
        docs = _poll_single(cert, tipo, tenant.data)
        total_docs += docs

    return PollingTriggerResponse(
        status="completed",
        cnpj=body.cnpj,
        tipos=body.tipos,
        docs_found=total_docs,
    )


@router.get("/logs/stream")
async def stream_logs(auth: dict = Depends(verify_jwt_token)):
    """Server-Sent Events em tempo real dos eventos de polling."""
    tenant_id = auth["tenant_id"]

    async def event_generator() -> AsyncGenerator[str, None]:
        sb = get_supabase_client()
        last_id = None

        while True:
            query = sb.table("polling_log").select("*").eq(
                "tenant_id", tenant_id
            ).order("created_at", desc=True).limit(10)

            if last_id:
                query = query.gt("id", last_id)

            result = query.execute()

            for log in reversed(result.data):
                event_data = json.dumps({
                    "id": log["id"],
                    "cnpj": log.get("cnpj"),
                    "tipo": log.get("tipo"),
                    "status": log.get("status"),
                    "docs_found": log.get("docs_found", 0),
                    "latency_ms": log.get("latency_ms"),
                    "error": log.get("error_message"),
                    "timestamp": log.get("created_at"),
                })
                yield f"data: {event_data}\n\n"
                last_id = log["id"]

            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
