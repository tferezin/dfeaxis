"""Chat service — Anthropic Claude Haiku 4.5 para bot landing + dashboard.

Carrega system prompts de /backend/prompts/{landing_bot.md, dashboard_bot.md}.
Suporta prompt caching (ephemeral) para reduzir custo do system prompt estático.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# Modelo fixo — Haiku 4.5 é o ponto doce preço/qualidade
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Limites de segurança
MAX_CONTEXT_MESSAGES = 30  # histórico máximo que vai pro modelo
MAX_OUTPUT_TOKENS = 1024
TEMPERATURE = 0.3

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass
class ChatResponse:
    """Resposta de uma chamada ao modelo."""
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str


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
