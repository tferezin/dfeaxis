"""FakeManifestacaoService — substitui services.manifestacao.manifestacao_service em testes.

Sempre retorna sucesso sem chamar SEFAZ real. Mantém log de chamadas
pra assertions nos testes E2E.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ManifestacaoResponse:
    """Espelho de services.manifestacao.ManifestacaoResponse."""
    cstat: str
    xmotivo: str
    protocolo: Optional[str]
    latency_ms: int
    success: bool


class FakeManifestacaoService:
    """Fake in-memory do ManifestacaoService — compatível por duck-typing."""

    def __init__(self) -> None:
        self._call_log: list[dict] = []
        self._errors: dict[str, dict] = {}  # chave -> error override
        self.ambiente: str = "2"

    def enviar_evento(
        self,
        chave_acesso: str,
        cnpj: str,
        tipo_evento: str,
        pfx_encrypted: Any = None,
        pfx_iv: Any = None,
        tenant_id: str = "",
        pfx_password: str = "",
        justificativa: str = "",
        ambiente: str | None = None,
    ) -> ManifestacaoResponse:
        """Simula envio de manifestação. Retorna sucesso por padrão."""
        self._call_log.append({
            "chave_acesso": chave_acesso,
            "cnpj": cnpj,
            "tipo_evento": tipo_evento,
            "justificativa": justificativa,
            "tenant_id": tenant_id,
            "ambiente": ambiente or self.ambiente,
        })

        # Erro forçado pra chave específica
        if chave_acesso in self._errors:
            err = self._errors.pop(chave_acesso)
            return ManifestacaoResponse(
                cstat=err.get("cstat", "999"),
                xmotivo=err.get("xmotivo", "Erro simulado"),
                protocolo=None,
                latency_ms=10,
                success=False,
            )

        # Simula cStat 135 (evento registrado) — sucesso padrão
        return ManifestacaoResponse(
            cstat="135",
            xmotivo="Evento registrado e vinculado a NF-e",
            protocolo=f"135{chave_acesso[:10]}000001",
            latency_ms=50,
            success=True,
        )

    def force_error(self, chave_acesso: str, cstat: str = "999", xmotivo: str = "Erro simulado") -> None:
        """Próxima chamada pra essa chave retorna erro."""
        self._errors[chave_acesso] = {"cstat": cstat, "xmotivo": xmotivo}

    def get_calls(self, tipo_evento: str | None = None) -> list[dict]:
        """Retorna log de chamadas, filtrando opcionalmente por tipo."""
        if tipo_evento:
            return [c for c in self._call_log if c["tipo_evento"] == tipo_evento]
        return list(self._call_log)

    def clear(self) -> None:
        self._call_log.clear()
        self._errors.clear()
