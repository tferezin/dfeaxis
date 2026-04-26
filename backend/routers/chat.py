"""Chat/Bot endpoints — landing (anônimo) + dashboard (autenticado).

POST /api/v1/chat        → 1 turno de conversa
POST /api/v1/chat/escalate → marcar conversa como escalada pro time humano

Persiste conversas em chat_conversations + chat_messages pra auditoria,
analytics e futura tela admin.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from db.supabase import get_supabase_client
from middleware.security import verify_jwt_token
from services.chat_service import (
    chat_completion,
    classify_escalation,
    should_classify_for_escalation,
)
from services.email_service import email_service

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


def _maybe_silent_escalate(
    conversation_id: str,
    context: Literal["landing", "dashboard"],
    messages_payload: list[dict],
) -> None:
    """Roda o classificador silencioso e escala se necessário.

    Executa em background — nunca bloqueia a resposta pro usuário.
    Falha silenciosa com log, nunca lança exceção pro caller.

    Regras:
    - Só roda a partir do 4º turno do usuário (threshold)
    - Depois do threshold, a cada 2 turnos (4, 6, 8...)
    - Idempotente: se já escalou, não classifica de novo
    - Usuário nunca vê nada (sem modificar a resposta do chat)
    """
    try:
        sb = get_supabase_client()

        # Recarrega conversa pra pegar estado atual de escalated_to_human
        conv_res = sb.table("chat_conversations").select("*").eq("id", conversation_id).execute()
        if not conv_res.data:
            return
        conv = conv_res.data[0]
        already_escalated = bool(conv.get("escalated_to_human", False))

        user_turn_count = sum(1 for m in messages_payload if m.get("role") == "user")

        if not should_classify_for_escalation(user_turn_count, already_escalated):
            return

        logger.info(
            "Running silent escalation classifier",
            extra={
                "conversation_id": conversation_id,
                "user_turn_count": user_turn_count,
                "context": context,
            },
        )

        classification = classify_escalation(messages=messages_payload, context=context)
        if classification is None:
            return

        # Registra tentativa de classificação no metadata (analytics)
        try:
            meta = conv.get("metadata") or {}
            classifications = list(meta.get("classifications") or [])
            classifications.append({
                "at": datetime.now(timezone.utc).isoformat(),
                "user_turn_count": user_turn_count,
                "should_escalate": classification.should_escalate,
                "severity": classification.severity,
                "reason": classification.reason[:200],
            })
            meta["classifications"] = classifications[-10:]  # guarda só últimas 10
            sb.table("chat_conversations").update({"metadata": meta}).eq("id", conversation_id).execute()
        except Exception as exc:
            logger.warning("failed to save classification metadata: %s", exc)

        if not classification.should_escalate:
            return

        # Escala: monta EscalateRequest sintético e envia email
        contact = classification.extracted_contact or {}
        synth_body = EscalateRequest(
            conversation_id=conversation_id,
            reason=f"[AUTO] {classification.reason}"[:1000],
            contact_email=(contact.get("email") or "")[:200] or None,
            contact_name=(contact.get("name") or "")[:200] or None,
        )

        # Atualiza DB ANTES do email pra garantir idempotência mesmo em race
        try:
            meta = conv.get("metadata") or {}
            sb.table("chat_conversations").update({
                "status": "escalated",
                "escalated_to_human": True,
                "escalated_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    **meta,
                    "escalation_source": "silent_classifier",
                    "escalation_severity": classification.severity,
                    "escalation_reason": classification.reason,
                    "extracted_contact": contact,
                },
            }).eq("id", conversation_id).execute()
        except Exception as exc:
            logger.error("failed to mark conversation as escalated: %s", exc)
            return

        # Recarrega conv com o estado atualizado pra passar pro email helper
        conv_fresh = sb.table("chat_conversations").select("*").eq("id", conversation_id).execute().data
        conv_to_use = conv_fresh[0] if conv_fresh else conv

        _send_escalation_email(sb, conv_to_use, synth_body)

        logger.info(
            "Silent escalation triggered",
            extra={
                "conversation_id": conversation_id,
                "severity": classification.severity,
                "user_turn_count": user_turn_count,
            },
        )
    except Exception as exc:
        logger.error("silent classifier background task failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Endpoint 1: Landing bot (anônimo)
# ---------------------------------------------------------------------------


@router.post("/chat/landing", response_model=ChatResponse)
async def chat_landing(body: LandingChatRequest, request: Request, background_tasks: BackgroundTasks):
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
        logger.error("chat_completion runtime error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Bot temporariamente indisponível: {type(exc).__name__}: {str(exc)[:200]}",
        )
    except FileNotFoundError as exc:
        logger.error("chat_completion prompt file missing: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Prompt file missing: {str(exc)[:200]}",
        )
    except Exception as exc:
        logger.exception("chat_completion unexpected error: %s", exc)
        # Retorna tipo da exceção no detail pra debug (sem expor stack trace completo)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar mensagem: {type(exc).__name__}: {str(exc)[:300]}",
        )

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

    # Classificação silenciosa em background (nunca bloqueia a resposta)
    full_messages = [m.model_dump() for m in body.messages] + [
        {"role": "assistant", "content": result.content}
    ]
    background_tasks.add_task(
        _maybe_silent_escalate,
        conversation_id,
        "landing",
        full_messages,
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
    background_tasks: BackgroundTasks,
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
        logger.error("chat_completion runtime error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Bot temporariamente indisponível: {type(exc).__name__}: {str(exc)[:200]}",
        )
    except FileNotFoundError as exc:
        logger.error("chat_completion prompt file missing: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Prompt file missing: {str(exc)[:200]}",
        )
    except Exception as exc:
        logger.exception("chat_completion unexpected error: %s", exc)
        # Retorna tipo da exceção no detail pra debug (sem expor stack trace completo)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar mensagem: {type(exc).__name__}: {str(exc)[:300]}",
        )

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

    # Classificação silenciosa em background (nunca bloqueia a resposta)
    full_messages = [m.model_dump() for m in body.messages] + [
        {"role": "assistant", "content": result.content}
    ]
    background_tasks.add_task(
        _maybe_silent_escalate,
        conversation_id,
        "dashboard",
        full_messages,
    )

    return ChatResponse(
        conversation_id=conversation_id,
        message=result.content,
        escalate_available=True,
    )


# ---------------------------------------------------------------------------
# Endpoint 3: Escalar conversa para time humano
# ---------------------------------------------------------------------------


def _format_friendly_datetime(iso_string: Optional[str]) -> str:
    if not iso_string:
        return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M UTC")
    except Exception:
        return iso_string


def _send_escalation_email(
    sb,
    conv: dict,
    body: "EscalateRequest",
) -> None:
    """Busca transcrição da conversa e envia e-mail pro time de suporte.

    Nunca lança exceção — falha silenciosa com log, pra não quebrar o
    endpoint de escalação mesmo se o Resend estiver offline.
    """
    support_email = os.environ.get("SUPPORT_EMAIL", "ferezaai@gmail.com")

    try:
        # Carrega todas as mensagens da conversa (ordem cronológica)
        msg_res = (
            sb.table("chat_messages")
            .select("role, content, created_at")
            .eq("conversation_id", conv["id"])
            .order("created_at", desc=False)
            .execute()
        )
        messages = []
        for row in msg_res.data or []:
            created_at = row.get("created_at", "")
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                created_short = dt.strftime("%d/%m %H:%M")
            except Exception:
                created_short = ""
            messages.append({
                "role": row.get("role"),
                "content": row.get("content", ""),
                "created_at_short": created_short,
            })

        tenant_company_name = ""
        tenant_plan = ""
        if conv.get("tenant_id"):
            try:
                t_res = (
                    sb.table("tenants")
                    .select("company_name, plan")
                    .eq("id", conv["tenant_id"])
                    .single()
                    .execute()
                )
                t = t_res.data or {}
                tenant_company_name = t.get("company_name") or ""
                tenant_plan = (t.get("plan") or "").capitalize()
            except Exception:
                pass

        email_service.send_chat_escalation(
            to_email=support_email,
            context=conv.get("context", "landing"),
            conversation_id=conv["id"],
            contact_name=body.contact_name or "",
            contact_email=body.contact_email or "",
            reason=body.reason or "(não informado)",
            messages=messages,
            tenant_company_name=tenant_company_name,
            tenant_plan=tenant_plan,
            created_at_friendly=_format_friendly_datetime(conv.get("created_at")),
        )
        logger.info(
            "Escalation email sent",
            extra={
                "conversation_id": conv["id"],
                "to": support_email,
                "messages_count": len(messages),
            },
        )
    except Exception as exc:
        logger.error(
            "Failed to send escalation email (non-fatal): %s",
            exc,
            extra={"conversation_id": conv["id"]},
        )


@router.post("/chat/escalate", status_code=202)
async def escalate_conversation(body: EscalateRequest):
    """Marca a conversa como escalada pro time humano + envia e-mail pro suporte.

    Não requer JWT/API key (a conversa pode ser anônima — landing), mas exige
    que a conversa tenha SIDO IDENTIFICADA antes:

    - Landing: precisa ter lead capture (linha em chat_leads associada).
    - Dashboard: tenant_id setado na conversa (criado via /chat/dashboard).

    A11: sem essa proteção, qualquer um podia disparar emails pra
    `SUPPORT_EMAIL` em loop, virando vetor de spam. A escalação é passo
    final, depois do bot ja ter conversado com um lead identificado.
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

    conv = conv_res.data[0]

    # A11: gate de identificacao. Conversa precisa ter origem identificavel
    # (lead capture na landing OU tenant logado no dashboard) — caso contrario
    # qualquer ator anonimo pode disparar email pro suporte em loop.
    ctx = conv.get("context")
    if ctx == "dashboard":
        if not conv.get("tenant_id"):
            raise HTTPException(
                status_code=401,
                detail="Conversa dashboard sem tenant — escalacao bloqueada",
            )
    else:
        # Landing (ou qualquer outro context anonimo): exige lead capturado.
        try:
            lead_res = sb.table("chat_leads").select("id").eq(
                "conversation_id", body.conversation_id
            ).limit(1).execute()
        except Exception as exc:
            logger.error("escalate lead lookup failed: %s", exc)
            raise HTTPException(status_code=500, detail="Erro ao validar conversa")
        if not (lead_res.data or []):
            raise HTTPException(
                status_code=401,
                detail=(
                    "Escalacao requer captura de lead antes. "
                    "Use /chat/landing/lead pra identificar."
                ),
            )

    # Idempotência: se já foi escalada, não reenvia email
    already_escalated = conv.get("escalated_to_human", False)

    sb.table("chat_conversations").update({
        "status": "escalated",
        "escalated_to_human": True,
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            **(conv.get("metadata") or {}),
            "escalation_reason": body.reason or "",
            "contact_email": body.contact_email or "",
            "contact_name": body.contact_name or "",
        },
    }).eq("id", body.conversation_id).execute()

    logger.info(
        "Conversation escalated",
        extra={
            "conversation_id": body.conversation_id,
            "reason": body.reason,
            "email": body.contact_email,
            "already_escalated": already_escalated,
        },
    )

    # Envia email pro time se for primeira escalação (evita spam em reenvios)
    if not already_escalated:
        _send_escalation_email(sb, conv, body)

    return {"status": "escalated", "conversation_id": body.conversation_id}


# ---------------------------------------------------------------------------
# Endpoint 3: Landing lead capture (pré-chat)
# ---------------------------------------------------------------------------

# Lista de domínios públicos conhecidos — email corporativo é exigido
# pra liberar o chat da landing. Lista conservadora: top provedores BR + global.
PUBLIC_EMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com",
    "hotmail.com", "hotmail.com.br", "outlook.com", "outlook.com.br",
    "live.com", "live.com.br", "msn.com",
    "yahoo.com", "yahoo.com.br", "ymail.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "aim.com",
    "uol.com.br", "bol.com.br", "terra.com.br", "ig.com.br", "r7.com",
    "zipmail.com.br", "globo.com",
    "proton.me", "protonmail.com", "pm.me",
    "mail.com", "gmx.com", "fastmail.com", "tutanota.com",
    "qq.com", "163.com", "126.com",
})


class LandingLeadRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=200)
    nome: str = Field(..., min_length=2, max_length=100)
    empresa: str = Field(..., min_length=2, max_length=120)
    telefone: Optional[str] = Field(None, max_length=40)
    cargo: Optional[str] = Field(None, max_length=80)
    session_id: Optional[str] = Field(None, max_length=64)
    page_url: Optional[str] = Field(None, max_length=500)
    utm_data: Optional[dict] = Field(None, description="UTMs/click IDs do localStorage")


class LandingLeadResponse(BaseModel):
    ok: bool
    conversation_id: str


@router.post("/chat/landing/lead", response_model=LandingLeadResponse)
async def chat_landing_lead(body: LandingLeadRequest, request: Request):
    """Captura lead antes do chat da landing começar.

    Bloqueia emails de domínios públicos (gmail/hotmail/etc) server-side.
    Cria uma chat_conversation vinculada ao lead pra que os próximos POST
    /chat/landing sejam associados à mesma conversa.
    """
    email_clean = body.email.strip().lower()
    if "@" not in email_clean:
        raise HTTPException(status_code=400, detail="E-mail inválido")
    local_part, _, domain = email_clean.partition("@")
    if not local_part or not domain or "." not in domain:
        raise HTTPException(status_code=400, detail="E-mail inválido")

    is_public = domain in PUBLIC_EMAIL_DOMAINS
    if is_public:
        raise HTTPException(
            status_code=422,
            detail="Use um e-mail corporativo. Não aceitamos domínios públicos (gmail, hotmail, outlook etc).",
        )

    sb = get_supabase_client()
    ip = _get_client_ip(request)
    ip_hash = _hash_ip(ip)
    ua = request.headers.get("user-agent", "")[:500]

    # Cria conversa com metadata do lead pra vincular próximas mensagens
    conv_metadata = {
        "lead_captured_at": datetime.now(timezone.utc).isoformat(),
        "lead_email": email_clean,
        "lead_nome": body.nome.strip(),
        "lead_empresa": body.empresa.strip(),
        "page_url": body.page_url,
    }
    try:
        conv_result = sb.table("chat_conversations").insert({
            "context": "landing",
            "session_id": body.session_id,
            "ip_hash": ip_hash,
            "user_agent": ua,
            "metadata": conv_metadata,
        }).execute()
        conversation_id = conv_result.data[0]["id"]
    except Exception as exc:
        logger.error("failed to create conversation for lead: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao iniciar conversa")

    # Insere lead
    try:
        sb.table("chat_leads").insert({
            "conversation_id": conversation_id,
            "email": email_clean,
            "email_domain": domain,
            "nome": body.nome.strip(),
            "empresa": body.empresa.strip(),
            "telefone": (body.telefone or "").strip() or None,
            "cargo": (body.cargo or "").strip() or None,
            "session_id": body.session_id,
            "ip_hash": ip_hash,
            "user_agent": ua,
            "page_url": body.page_url,
            "utm_data": body.utm_data or {},
            "is_public_domain": is_public,
        }).execute()
    except Exception as exc:
        logger.error("failed to insert chat lead: %s", exc)
        # Não derruba a conversa — o lead podia ser duplicado ou ter constraint.
        # Mesmo sem salvar o lead, a conversa existe e o chat pode seguir.

    logger.info(
        "Landing lead captured",
        extra={
            "conversation_id": conversation_id,
            "email_domain": domain,
            "empresa": body.empresa[:80],
        },
    )

    return {"ok": True, "conversation_id": conversation_id}
