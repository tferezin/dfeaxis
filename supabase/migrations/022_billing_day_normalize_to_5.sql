-- ============================================================
-- Migration 022: normalizar billing_day = 5 pra todos os tenants
-- ============================================================
--
-- Decisao 23/Abril: billing_day fica fixo em 5 pra todo mundo (o
-- monthly_overage_job roda apenas dia 5). Tenants antigos com
-- billing_day=10 ou 15 (migration 010) nunca seriam cobrados de novo,
-- risco de receita perdida silenciosa.
--
-- Normaliza todos os tenants ativos/past_due pra billing_day=5. Tenants
-- cancelados/expirados ficam como estao (nao afeta cobranca futura).
--
-- No futuro, se quisermos reintroduzir 10/15 como opcoes do cliente:
-- 1. Ajustar monthly_overage_job pra rodar diariamente nos dias 5/10/15
-- 2. Liberar a UI de configuracoes pra cliente escolher
-- 3. Remover o forcing em backend/services/billing/checkout.py
-- ============================================================

UPDATE tenants
SET billing_day = 5
WHERE billing_day IS DISTINCT FROM 5
  AND subscription_status IN ('active', 'past_due');

COMMENT ON COLUMN tenants.billing_day IS
  'Dia do mes em que a cobranca e processada. Por convencao atual '
  'sempre = 5 (padronizacao 23/Abril/2026). CHECK da migration 010 '
  'ainda permite 5/10/15 pra suportar evolucao futura, mas no '
  'backend o checkout forca 5 via DEFAULT_BILLING_DAY.';
