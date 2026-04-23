-- ============================================================
-- Migration 023: past_due_since em tenants (dunning 5 dias)
-- ============================================================
--
-- Quando Stripe manda invoice.payment_failed, a gente stampa aqui a data
-- da PRIMEIRA falha do ciclo. Usado pra:
-- 1. Calcular days_remaining no alerta payment_overdue (GET /alerts)
-- 2. Bloquear acesso quando passar de 5 dias (middleware)
--
-- Regra 5+5: cliente paga dia 5 -> se falha, tem ate dia 10 pra
-- regularizar (5 dias de tolerancia). Dia 11 = bloqueio.
--
-- Limpa (NULL) quando invoice.paid chega com sucesso — cliente saiu
-- do dunning.
-- ============================================================

ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS past_due_since TIMESTAMPTZ;

COMMENT ON COLUMN tenants.past_due_since IS
  'Timestamp da primeira falha de pagamento no ciclo atual. NULL quando '
  'nao esta em dunning. Usado pra calcular o countdown de bloqueio '
  '(5 dias apos essa data). Resetado quando invoice.paid chega.';
