"""Endpoints de polling manual e logs."""

import asyncio
import base64
import json
import subprocess
import os
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from db.supabase import get_supabase_client
from middleware.security import verify_api_key, verify_jwt_token, verify_jwt_with_trial
from models.schemas import PollingTriggerRequest, PollingTriggerResponse, PollingTipoResult
from scheduler.polling_job import _poll_single_detailed

router = APIRouter()


class TestCaptureRequest(BaseModel):
    pfx_base64: str
    password: str
    cnpj: str
    tipos: list[str] = ["nfe", "cte", "mdfe"]


@router.post("/test-capture")
async def test_capture(body: TestCaptureRequest):
    """Teste direto de captura na SEFAZ — sem banco de dados.

    Recebe o certificado .pfx em base64, a senha e o CNPJ.
    Consulta a SEFAZ homologação e retorna o resultado.
    """
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "scripts",
        "test_sefaz.py",
    )

    if not os.path.exists(script_path):
        raise HTTPException(status_code=500, detail="Script de teste não encontrado")

    tipos_str = ",".join(body.tipos)

    try:
        result = subprocess.run(
            [
                "python3", script_path,
                body.pfx_base64,
                body.password,
                body.cnpj,
                tipos_str,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Erro desconhecido"
            return {"error": error_msg}

        return json.loads(result.stdout.strip())

    except subprocess.TimeoutExpired:
        return {"error": "Timeout: a SEFAZ não respondeu em 120 segundos"}
    except json.JSONDecodeError:
        return {"error": "Resposta inválida do script de teste"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/polling/trigger", response_model=PollingTriggerResponse)
async def trigger_polling(
    body: PollingTriggerRequest,
    auth: dict = Depends(verify_jwt_with_trial),
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
    results = []
    for tipo in body.tipos:
        if tipo not in ("nfe", "cte", "mdfe", "nfse"):
            continue
        result = _poll_single_detailed(cert, tipo, tenant.data)
        results.append(result)
        total_docs += result["docs_found"]

    return PollingTriggerResponse(
        status="completed",
        cnpj=body.cnpj,
        tipos=body.tipos,
        docs_found=total_docs,
        results=[PollingTipoResult(**r) for r in results],
    )


@router.get("/logs/stream")
async def stream_logs(auth: dict = Depends(verify_jwt_with_trial)):
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
