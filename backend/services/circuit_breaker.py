"""Circuit breaker por CNPJ + tipo de documento.

Protege contra erro 656 SEFAZ ("consumo indevido").
"""

import time
from enum import Enum
from dataclasses import dataclass, field


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitEntry:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    success_count_half_open: int = 0


class CircuitBreaker:
    """Circuit breaker em memória. Cada chave = '{cnpj}_{tipo}'."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout_s: int = 60,
        half_open_success_threshold: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.half_open_success_threshold = half_open_success_threshold
        self._circuits: dict[str, CircuitEntry] = {}

    def _key(self, cnpj: str, tipo: str) -> str:
        return f"{cnpj}_{tipo}"

    def _get(self, cnpj: str, tipo: str) -> CircuitEntry:
        key = self._key(cnpj, tipo)
        if key not in self._circuits:
            self._circuits[key] = CircuitEntry()
        return self._circuits[key]

    def can_execute(self, cnpj: str, tipo: str) -> bool:
        """Retorna True se o circuito permite uma chamada."""
        entry = self._get(cnpj, tipo)

        if entry.state == CircuitState.CLOSED:
            return True

        if entry.state == CircuitState.OPEN:
            elapsed = time.time() - entry.last_failure_time
            if elapsed >= self.recovery_timeout_s:
                entry.state = CircuitState.HALF_OPEN
                entry.success_count_half_open = 0
                return True
            return False

        # HALF_OPEN: permite uma chamada de teste
        return True

    def record_success(self, cnpj: str, tipo: str) -> None:
        entry = self._get(cnpj, tipo)

        if entry.state == CircuitState.HALF_OPEN:
            entry.success_count_half_open += 1
            if entry.success_count_half_open >= self.half_open_success_threshold:
                entry.state = CircuitState.CLOSED
                entry.failure_count = 0
        else:
            entry.failure_count = 0

    def record_failure(self, cnpj: str, tipo: str) -> None:
        entry = self._get(cnpj, tipo)
        entry.failure_count += 1
        entry.last_failure_time = time.time()

        if entry.state == CircuitState.HALF_OPEN:
            entry.state = CircuitState.OPEN
        elif entry.failure_count >= self.failure_threshold:
            entry.state = CircuitState.OPEN

    def get_state(self, cnpj: str, tipo: str) -> CircuitState:
        return self._get(cnpj, tipo).state


# Instância global
circuit_breaker = CircuitBreaker()
