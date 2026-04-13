"""Chat service — Anthropic Claude Haiku 4.5 para bot landing + dashboard.

Carrega system prompts de /backend/prompts/{landing_bot.md, dashboard_bot.md}.
Suporta prompt caching (ephemeral) para reduzir custo do system prompt estático.

Também expõe um classificador silencioso de escalação: a partir do 4º turno
do usuário, o backend chama classify_escalation() com a conversa inteira e
decide se deve disparar email pro time. Nunca é visível pro usuário.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# Modelo fixo — Haiku 4.5 é o ponto doce preço/qualidade
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Limites de segurança
MAX_CONTEXT_MESSAGES = 30  # histórico máximo que vai pro modelo
MAX_OUTPUT_TOKENS = 1024
TEMPERATURE = 0.3

# Classificação silenciosa: só roda a partir do Nº turno + frequência
ESCALATION_THRESHOLD_USER_TURNS = 4  # começa a classificar no 4º turno do user
ESCALATION_CHECK_FREQUENCY = 2  # depois do threshold, classifica a cada 2 turnos

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass
class ChatResponse:
    """Resposta de uma chamada ao modelo."""
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str


@dataclass
class EscalationClassification:
    """Resultado do classificador silencioso de escalação."""
    should_escalate: bool
    severity: str  # 'low' | 'medium' | 'high'
    reason: str
    extracted_contact: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0


def should_classify_for_escalation(user_turn_count: int, already_escalated: bool) -> bool:
    """Decide se é o momento de rodar a classificação silenciosa.

    Regras:
    - Se já escalou, NUNCA classifica de novo (idempotência)
    - Abaixo do threshold, não classifica (80% das conversas são curtas)
    - No threshold exato, classifica (primeira análise)
    - Após o threshold, classifica a cada N turnos (frequência reduzida)
    """
    if already_escalated:
        return False
    if user_turn_count < ESCALATION_THRESHOLD_USER_TURNS:
        return False
    # No threshold exato (4º turno), sempre classifica
    if user_turn_count == ESCALATION_THRESHOLD_USER_TURNS:
        return True
    # Depois do threshold, classifica a cada N turnos (4, 6, 8, 10...)
    turns_after_threshold = user_turn_count - ESCALATION_THRESHOLD_USER_TURNS
    return turns_after_threshold % ESCALATION_CHECK_FREQUENCY == 0


def _load_prompt(name: str) -> str:
    """Carrega system prompt do disco. Lança se não achar."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt não encontrado: {path}")
    return path.read_text(encoding="utf-8")


# Cache em memória — prompts só mudam em deploy
_prompt_cache: dict[str, str] = {}


def get_system_prompt(context: Literal["landing", "dashboard"]) -> str:
    """Retorna o system prompt apropriado ao contexto."""
    key = f"{context}_bot"
    if key not in _prompt_cache:
        _prompt_cache[key] = _load_prompt(key)
    return _prompt_cache[key]


def render_user_context(user_ctx: dict) -> str:
    """Renderiza o bloco de contexto dinâmico do usuário (dashboard bot).

    Converte dict de placeholders em texto formatado que vai concatenado
    ao final do system prompt na seção `Contexto do usuário`.
    """
    if not user_ctx:
        return ""

    lines = ["", "## CONTEXTO DINÂMICO DO USUÁRIO (sessão atual)", ""]
    for key, value in user_ctx.items():
        if value is None or value == "":
            continue
        lines.append(f"- **{key}**: {value}")
    return "\n".join(lines)


def _get_anthropic_client():
    """Lazy import do SDK Anthropic."""
    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Anthropic SDK não instalado. Rode: pip install anthropic"
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada no ambiente")

    return anthropic.Anthropic(api_key=api_key)


def chat_completion(
    context: Literal["landing", "dashboard"],
    messages: list[dict],
    user_context: Optional[dict] = None,
) -> ChatResponse:
    """Executa uma chamada ao modelo Claude Haiku 4.5.

    Args:
        context: 'landing' (anônimo) ou 'dashboard' (autenticado)
        messages: histórico de mensagens no formato [{role, content}]
                  role ∈ {'user', 'assistant'}
        user_context: dict opcional de placeholders (só dashboard)
                      ex: {'plan': 'Business', 'docs_consumed_month': 1234, ...}

    Returns:
        ChatResponse com conteúdo, tokens e latência
    """
    client = _get_anthropic_client()

    # Carrega system prompt + concatena contexto dinâmico
    system_prompt = get_system_prompt(context)
    if user_context:
        system_prompt += "\n" + render_user_context(user_context)

    # Trunca histórico se passar do limite
    if len(messages) > MAX_CONTEXT_MESSAGES:
        messages = messages[-MAX_CONTEXT_MESSAGES:]

    # Valida formato
    sanitized = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role not in ("user", "assistant") or not content:
            continue
        sanitized.append({"role": role, "content": str(content)[:8000]})  # limite por msg

    if not sanitized:
        raise ValueError("messages vazio ou inválido")

    start = time.time()
    try:
        # Usa prompt caching pra reduzir custo — system prompt é estático
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=TEMPERATURE,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=sanitized,
        )
    except Exception as exc:
        logger.error("Anthropic call failed: %s", exc)
        raise

    latency_ms = int((time.time() - start) * 1000)

    # Extrai texto da resposta (Anthropic retorna lista de content blocks)
    text_parts = []
    for block in response.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)
    content = "\n".join(text_parts).strip()

    if not content:
        content = "Desculpa, não consegui gerar uma resposta agora. Pode reformular a pergunta?"

    usage = response.usage
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0

    return ChatResponse(
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        model=CLAUDE_MODEL,
    )


# ============================================================================
# Classificador silencioso de escalação
# ============================================================================


def _parse_classifier_json(raw: str) -> Optional[dict]:
    """Extrai JSON válido da resposta do classificador.

    Tolera: markdown fences, texto antes/depois, espaços extras.
    Retorna None se não encontrar JSON válido.
    """
    if not raw:
        return None

    # Remove fences markdown comuns
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    # Tenta parse direto
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fallback: extrai primeiro {} balanceado
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def classify_escalation(
    messages: list[dict],
    context: Literal["landing", "dashboard"],
) -> Optional[EscalationClassification]:
    """Analisa uma conversa completa e decide se deve escalar pro humano.

    Faz uma chamada extra ao Claude Haiku com o prompt classificador
    (prompts/escalation_classifier.md). Retorna o resultado estruturado
    ou None em caso de erro (nunca lança exceção pra não quebrar o chat).

    Args:
        messages: histórico completo da conversa no formato [{role, content}]
        context: 'landing' ou 'dashboard' (adiciona no prompt pra o classificador
                 saber as regras específicas)

    Returns:
        EscalationClassification com should_escalate/severity/reason/contact
        None se a chamada falhar ou o JSON não for parseável
    """
    try:
        system_prompt = _load_prompt("escalation_classifier")
    except FileNotFoundError:
        logger.error("escalation_classifier.md not found")
        return None

    try:
        client = _get_anthropic_client()
    except RuntimeError as exc:
        logger.warning("Classifier unavailable: %s", exc)
        return None

    # Monta histórico legível pro classificador (format string compacto)
    conversation_lines = [f"[Contexto: {context}]", ""]
    for msg in messages[-20:]:  # últimos 20 turnos são suficientes
        role_label = "usuário" if msg.get("role") == "user" else "bot"
        content = str(msg.get("content", ""))[:2000]  # trunca se muito longo
        conversation_lines.append(f"{role_label}: {content}")
    conversation_text = "\n".join(conversation_lines)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,  # JSON é pequeno, não precisa de muito
            temperature=0.0,  # determinístico
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Analise a conversa abaixo e retorne APENAS o JSON "
                        "de classificação, sem texto extra:\n\n"
                        + conversation_text
                    ),
                }
            ],
        )
    except Exception as exc:
        logger.warning("Classifier API call failed: %s", exc)
        return None

    text_parts = []
    for block in response.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)
    raw = "\n".join(text_parts).strip()

    data = _parse_classifier_json(raw)
    if not data:
        logger.warning("Classifier returned non-JSON: %s", raw[:200])
        return None

    usage = response.usage
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0

    # Normaliza campos
    should_escalate = bool(data.get("should_escalate", False))
    severity = data.get("severity", "low")
    if severity not in ("low", "medium", "high"):
        severity = "low"
    reason = str(data.get("reason", ""))[:500]
    extracted_contact = data.get("extracted_contact", {}) or {}
    if not isinstance(extracted_contact, dict):
        extracted_contact = {}

    return EscalationClassification(
        should_escalate=should_escalate,
        severity=severity,
        reason=reason,
        extracted_contact=extracted_contact,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
