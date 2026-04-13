"""Chat/Bot endpoints — landing (anônimo) + dashboard (autenticado).

POST /api/v1/chat        → 1 turno de conversa
POST /api/v1/chat/escalate → marcar conversa como escalada pro time humano

Persiste conversas em chat_conversations + chat_messages pra auditoria,
analytics e futura tela admin.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from db.supabase import get_supabase_client
from middleware.security import verify_jwt_token
from services.chat_service import chat_completion

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class LandingChatRequest(BaseModel):
    """Bot landing — anônimo, sem auth."""
    messages: list[ChatMessageIn] = Field(..., min_length=1, max_length=30)
    session_id: Optional[str] = Field(None, max_length=64, description="ID local gerado no browser")
    page_url: Optional[str] = Field(None, max_length=500)
    conversation_id: Optional[str] = Field(None, description="UUID da conversa existente")


class DashboardChatRequest(BaseModel):
    """Bot dashboard — autenticado, com contexto do tenant."""
    messages: list[ChatMessageIn] = Field(..., min_length=1, max_length=30)
    conversation_id: Optional[str] = Field(None, description="UUID da conversa existente")
    current_page: Optional[str] = Field(None, max_length=200, description="Página onde o usuário está")


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    escalate_available: bool = True


class EscalateRequest(BaseModel):
    conversation_id: str
    reason: Optional[str] = Field(None, max_length=1000)
    contact_email: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_ip(ip: str) -> str:
    """Hash SHA256 do IP (privacidade — não guardamos IP real)."""
    return hashlib.sha256(ip.encode()).hexdigest()[:32]


def _get_client_ip(request: Request) -> str:
    """Extrai IP do request (considera proxies via X-Forwarded-For)."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _create_or_load_conversation(
    sb,
    context: Literal["landing", "dashboard"],
    conversation_id: Optional[str],
    tenant_id: Optional[str],
    user_id: Optional[str],
    session_id: Optional[str],
    ip_hash: Optional[str],
    user_agent: Optional[str],
    metadata: Optional[dict] = None,
) -> dict:
    """Cria nova conversa ou carrega existente. Retorna row da conversa."""
    if conversation_id:
        result = sb.table("chat_conversations").select("*").eq("id", conversation_id).execute()
        if result.data:
            conv = result.data[0]
            # Valida ownership: se dashboard, tenant_id deve bater
            if context == "dashboard" and conv.get("tenant_id") != tenant_id:
                raise HTTPException(status_code=403, detail="Conversation não pertence a este tenant")
            return conv

    # Cria nova
    payload = {
        "context": context,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "session_id": session_id,
        "ip_hash": ip_hash,
        "user_agent": (user_agent or "")[:500],
        "metadata": metadata or {},
    }
    result = sb.table("chat_conversations").insert(payload).execute()
    return result.data[0]


def _save_message(
    sb,
    conversation_id: str,
    role: Literal["user", "assistant"],
    content: str,
    model: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    latency_ms: Optional[int] = None,
) -> None:
    """Salva uma mensagem e atualiza last_message_at da conversa."""
    sb.table("chat_messages").insert({
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
    }).execute()
    sb.table("chat_conversations").update({
        "last_message_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", conversation_id).execute()


# ---------------------------------------------------------------------------
# Endpoint 1: Landing bot (anônimo)
# ---------------------------------------------------------------------------


@router.post("/chat/landing", response_model=ChatResponse)
async def chat_landing(body: LandingChatRequest, request: Request):
    """Bot comercial da landing page — anônimo, sem auth."""
    sb = get_supabase_client()

    ip = _get_client_ip(request)
    ip_hash = _hash_ip(ip)
    ua = request.headers.get("user-agent", "")

    # Cria/carrega conversa
    try:
        conv = _create_or_load_conversation(
            sb=sb,
            context="landing",
            conversation_id=body.conversation_id,
            tenant_id=None,
            user_id=None,
            session_id=body.session_id,
            ip_hash=ip_hash,
            user_agent=ua,
            metadata={"page_url": body.page_url} if body.page_url else None,
        )
    except Exception as exc:
        logger.error("failed to create landing conversation: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao iniciar conversa")

    conversation_id = conv["id"]

    # Salva mensagem do usuário (a última da lista é sempre o turno atual)
    last_user_msg = body.messages[-1]
    if last_user_msg.role != "user":
        raise HTTPException(status_code=400, detail="Última mensagem deve ser do usuário")

    _save_message(sb, conversation_id, "user", last_user_msg.content)

    # Chama o modelo
    try:
        result = chat_completion(
            context="landing",
            messages=[m.model_dump() for m in body.messages],
            user_context=None,
        )
    except RuntimeError as exc:
        logger.error("chat_completion failed: %s", exc)
        raise HTTPException(status_code=503, detail="Bot temporariamente indisponível")
    except Exception as exc:
        logger.exception("chat_completion unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao processar mensagem")

    # Salva resposta do assistant
    _save_message(
        sb,
        conversation_id,
        "assistant",
        result.content,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
    )

    return ChatResponse(
        conversation_id=conversation_id,
        message=result.content,
        escalate_available=True,
    )


# ---------------------------------------------------------------------------
# Endpoint 2: Dashboard bot (autenticado)
# ---------------------------------------------------------------------------


async def _build_user_context(sb, tenant_id: str, user_id: str, current_page: Optional[str]) -> dict:
    """Busca dados do tenant e monta o dict de contexto dinâmico pro prompt."""
    from datetime import datetime, timezone

    ctx: dict = {
        "mode": "user",
        "now_iso": datetime.now(timezone.utc).isoformat(),
        "current_page": current_page or "dashboard",
        "user_id": user_id,
        "tenant_id": tenant_id,
    }

    try:
        t_res = sb.table("tenants").select(
            "company_name, email, plan, subscription_status, "
            "trial_active, trial_expires_at, trial_cap, docs_consumidos_trial, "
            "docs_consumidos_mes, docs_included_mes, max_cnpjs, billing_day, "
            "sefaz_ambiente"
        ).eq("id", tenant_id).single().execute()
        t = t_res.data or {}
    except Exception:
        t = {}

    ctx["tenant_company_name"] = t.get("company_name") or ""
    ctx["user_email"] = t.get("email") or ""
    ctx["plan"] = (t.get("plan") or "starter").capitalize()
    ctx["subscription_status"] = t.get("subscription_status") or "trial"
    ctx["billing_day"] = t.get("billing_day") or 5
    ctx["sefaz_environment"] = "homologação" if str(t.get("sefaz_ambiente") or "2") == "2" else "produção"

    # Trial
    ctx["in_trial"] = t.get("subscription_status") == "trial"
    ctx["trial_cap"] = t.get("trial_cap") or 500
    ctx["docs_consumed_trial"] = t.get("docs_consumidos_trial") or 0
    if t.get("trial_expires_at"):
        try:
            exp = datetime.fromisoformat(t["trial_expires_at"].replace("Z", "+00:00"))
            delta = exp - datetime.now(timezone.utc)
            ctx["trial_days_remaining"] = max(0, delta.days)
        except Exception:
            ctx["trial_days_remaining"] = 0
    else:
        ctx["trial_days_remaining"] = 0

    # Uso mensal
    ctx["docs_consumed_month"] = t.get("docs_consumidos_mes") or 0
    ctx["docs_included_month"] = t.get("docs_included_mes") or 0
    overage_docs = max(0, ctx["docs_consumed_month"] - ctx["docs_included_month"])
    ctx["overage_forecast_docs"] = overage_docs

    # CNPJs
    ctx["max_cnpjs"] = t.get("max_cnpjs") or 1
    try:
        cnpj_res = sb.table("certificates").select("id", count="exact").eq(
            "tenant_id", tenant_id
        ).eq("is_active", True).execute()
        ctx["cnpj_count"] = cnpj_res.count or 0
        ctx["cert_count"] = cnpj_res.count or 0
    except Exception:
        ctx["cnpj_count"] = 0
        ctx["cert_count"] = 0

    # Manifestação pendente
    try:
        pend_res = sb.table("documents").select("id", count="exact").eq(
            "tenant_id", tenant_id
        ).eq("manifestacao_status", "ciencia").execute()
        ctx["pending_manifestation_count"] = pend_res.count or 0
    except Exception:
        ctx["pending_manifestation_count"] = 0

    return ctx


@router.post("/chat/dashboard", response_model=ChatResponse)
async def chat_dashboard(
    body: DashboardChatRequest,
    request: Request,
    auth: dict = Depends(verify_jwt_token),
):
    """Bot técnico do dashboard — autenticado, com contexto do tenant."""
    sb = get_supabase_client()
    tenant_id = auth["tenant_id"]
    user_id = auth.get("user_id")

    ua = request.headers.get("user-agent", "")

    # Monta contexto dinâmico do tenant
    user_ctx = await _build_user_context(sb, tenant_id, user_id, body.current_page)

    # Cria/carrega conversa
    try:
        conv = _create_or_load_conversation(
            sb=sb,
            context="dashboard",
            conversation_id=body.conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=None,
            ip_hash=None,
            user_agent=ua,
            metadata={"current_page": body.current_page} if body.current_page else None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("failed to create dashboard conversation: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao iniciar conversa")

    conversation_id = conv["id"]

    last_user_msg = body.messages[-1]
    if last_user_msg.role != "user":
        raise HTTPException(status_code=400, detail="Última mensagem deve ser do usuário")

    _save_message(sb, conversation_id, "user", last_user_msg.content)

    try:
        result = chat_completion(
            context="dashboard",
            messages=[m.model_dump() for m in body.messages],
            user_context=user_ctx,
        )
    except RuntimeError as exc:
        logger.error("chat_completion failed: %s", exc)
        raise HTTPException(status_code=503, detail="Bot temporariamente indisponível")
    except Exception as exc:
        logger.exception("chat_completion unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao processar mensagem")

    _save_message(
        sb,
        conversation_id,
        "assistant",
        result.content,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
    )

    return ChatResponse(
        conversation_id=conversation_id,
        message=result.content,
        escalate_available=True,
    )


# ---------------------------------------------------------------------------
# Endpoint 3: Escalar conversa para time humano
# ---------------------------------------------------------------------------


@router.post("/chat/escalate", status_code=202)
async def escalate_conversation(body: EscalateRequest):
    """Marca a conversa como escalada pro time humano.

    Não requer auth — qualquer um pode escalar a própria conversa (landing ou
    dashboard). O backend valida que a conversation_id é válida.
    """
    sb = get_supabase_client()

    try:
        conv_res = sb.table("chat_conversations").select("*").eq("id", body.conversation_id).execute()
        if not conv_res.data:
            raise HTTPException(status_code=404, detail="Conversation não encontrada")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("escalate lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao processar escalação")

    sb.table("chat_conversations").update({
        "status": "escalated",
        "escalated_to_human": True,
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            **(conv_res.data[0].get("metadata") or {}),
            "escalation_reason": body.reason or "",
            "contact_email": body.contact_email or "",
            "contact_name": body.contact_name or "",
        },
    }).eq("id", body.conversation_id).execute()

    # TODO: notificar time via Slack/email quando tiver endpoint configurado
    logger.info(
        "Conversation escalated",
        extra={
            "conversation_id": body.conversation_id,
            "reason": body.reason,
            "email": body.contact_email,
        },
    )

    return {"status": "escalated", "conversation_id": body.conversation_id}
