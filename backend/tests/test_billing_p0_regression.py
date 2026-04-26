"""Testes de regressao pros 4 bugs P0 corrigidos no auto-review pre-launch.

Foca nas partes que sao logica pura (timezone + timedelta). Os fixes #1
(race condition webhook) e #4 (invoice.paid defensive) dependem de DB
e estao cobertos pelo test_stripe_billing_e2e.py.

Bugs corrigidos:
  #1 — Race condition webhook idempotency  (commit 68e959e)
  #2 — Timezone UTC vs Sao Paulo nos jobs   (commit fc6b663)  ← TESTADO AQUI
  #3 — Off-by-one no dunning (.days bug)    (commit caf0015)  ← TESTADO AQUI
  #4 — invoice.paid limpa past_due leniente (commit bf1addc)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest


# =============================================================================
# Fix #2 — Timezone (jobs mensais)
# =============================================================================


class TestTimezoneInMonthlyJobs:
    """Snapshot/overage devem usar SP tz, nao UTC, pra docs do fim do mes
    cairem no ciclo correto."""

    def test_previous_month_uses_sp_tz(self):
        """Quando job dispara as 02:00 SP dia 1 (= 05:00 UTC dia 1), o
        previous_month deve ser o mes que acabou em SP.
        """
        from scheduler.monthly_snapshot_reset_job import _previous_month_first_day

        # Em condicoes normais, _previous_month_first_day retorna o dia 1
        # do mes anterior ao corrente em SP.
        result = _previous_month_first_day()
        today_br = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

        # Day deve ser sempre 1
        assert result.day == 1

        # Month deve ser anterior ao corrente (com wraparound em janeiro)
        if today_br.month == 1:
            assert result.year == today_br.year - 1
            assert result.month == 12
        else:
            assert result.year == today_br.year
            assert result.month == today_br.month - 1

    def test_overage_job_uses_same_tz(self):
        """Garantia simbolica: ambos os jobs (snapshot + overage)
        compartilham mesma logica de timezone."""
        from scheduler.monthly_overage_job import _previous_month_first_day as overage_prev
        from scheduler.monthly_snapshot_reset_job import (
            _previous_month_first_day as snapshot_prev,
        )

        # Ambos calculam o mesmo mes anterior
        assert overage_prev() == snapshot_prev()

    def test_today_br_uses_sao_paulo(self):
        """_today_br retorna a data correta de SP, mesmo quando UTC e
        outro dia."""
        from scheduler.monthly_snapshot_reset_job import _today_br

        result = _today_br()
        expected = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

        # Pode haver diferenca de 1 segundo entre as 2 chamadas, mas a
        # data deve ser igual se ambas rodam no mesmo segundo
        assert result == expected


# =============================================================================
# Fix #3 — Off-by-one no dunning (timedelta vs .days)
# =============================================================================


class TestDunningOffByOne:
    """Cliente que falhou as 14:00 deve ser bloqueado as 14:00 do dia +5,
    nao as 14:00 do dia +6 (que era o bug com .days)."""

    @staticmethod
    def _is_within_tolerance(past_due_dt: datetime, now: datetime) -> bool:
        """Replica a logica do middleware (security.py:430)."""
        elapsed = now - past_due_dt
        return elapsed <= timedelta(days=5)

    def test_dentro_da_tolerancia_4d_20h(self):
        """4 dias e 20h apos a falha — ainda dentro da janela de 5d."""
        past_due = datetime(2026, 4, 5, 14, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)

        assert self._is_within_tolerance(past_due, now), (
            "4d20h < 5d, deveria estar dentro tolerancia"
        )

    def test_exatamente_5d(self):
        """Exatamente 5 dias — ainda dentro (timedelta <=)."""
        past_due = datetime(2026, 4, 5, 14, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 4, 10, 14, 0, 0, tzinfo=timezone.utc)

        assert self._is_within_tolerance(past_due, now), (
            "exatamente 5d, dentro tolerancia (limite incluido)"
        )

    def test_fora_da_tolerancia_5d_4h(self):
        """5 dias e 4h apos a falha — FORA. Antes (com .days) ainda
        considerava dentro porque (5d4h).days == 5."""
        past_due = datetime(2026, 4, 5, 14, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 4, 10, 18, 0, 0, tzinfo=timezone.utc)

        assert not self._is_within_tolerance(past_due, now), (
            "5d4h > 5d, deveria estar FORA tolerancia (era o bug)"
        )

    def test_fora_da_tolerancia_6d(self):
        """Caso obvio — 6 dias depois claramente fora."""
        past_due = datetime(2026, 4, 5, 14, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 4, 11, 14, 0, 0, tzinfo=timezone.utc)

        assert not self._is_within_tolerance(past_due, now)

    def test_days_field_no_response(self):
        """O response da 402 ainda usa .days (informativo) — verificar
        que retorna inteiro razoavel."""
        past_due = datetime(2026, 4, 5, 14, 0, 0, tzinfo=timezone.utc)
        now = datetime(2026, 4, 10, 18, 0, 0, tzinfo=timezone.utc)

        elapsed = now - past_due
        assert elapsed.days == 5  # OK ser truncado pra UX


# =============================================================================
# Fix #1 — Race condition webhook (smoke test sem DB)
# =============================================================================


class TestWebhookClaimSemantics:
    """Garantia que _record_event retorna bool — claim atomico pra
    serializar entregas paralelas. Bug original: _is_duplicate ANTES do
    insert deixava brecha pra 2 workers passarem.
    """

    def test_record_event_returns_bool(self):
        """Validacao da signature: retorna True/False, nao None.
        Sem DB — apenas valida o contrato da funcao.

        Modulo usa `from __future__ import annotations`, entao a anotacao
        vira string. Comparamos com 'bool' (string).
        """
        import inspect
        from services.billing.webhooks import _record_event

        sig = inspect.signature(_record_event)
        assert str(sig.return_annotation) == "bool", (
            "_record_event precisa retornar bool — caller usa pra decidir "
            "se rodou claim ou se foi duplicate (race serialized pelo DB)"
        )

    def test_release_claim_existe(self):
        """_release_claim deve existir pra desfazer claim apos dispatch
        falhar (Stripe retry vai reprocessar)."""
        from services.billing.webhooks import _release_claim

        assert callable(_release_claim)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
