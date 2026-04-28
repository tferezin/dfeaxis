-- ============================================================
-- 026 — chat_stats: troca pra security_invoker
-- ============================================================
-- Motivacao:
--   Supabase Advisor (CRITICAL): "View public.chat_stats is defined
--   with the SECURITY DEFINER property". Views criadas por role admin
--   bypassam RLS por default — qualquer auth user que conseguir SELECT
--   na view ve dados de TODOS tenants.
--
-- Fix:
--   CREATE OR REPLACE VIEW ... WITH (security_invoker = on) — Postgres
--   15+ aplica RLS no contexto do role que esta consultando, nao do
--   creator. Isso mantém compatibilidade com chat_conversations RLS
--   (admin-only por design — view so retorna stats agregados, e o
--   admin policy ja existe na tabela base).
--
-- Idempotente: CREATE OR REPLACE substitui a definicao existente.

CREATE OR REPLACE VIEW chat_stats
WITH (security_invoker = on) AS
SELECT
  context,
  DATE(created_at) AS day,
  COUNT(DISTINCT id) AS conversations,
  COUNT(DISTINCT tenant_id) FILTER (WHERE tenant_id IS NOT NULL) AS unique_tenants,
  COUNT(DISTINCT session_id) FILTER (WHERE session_id IS NOT NULL) AS unique_sessions,
  SUM(CASE WHEN escalated_to_human THEN 1 ELSE 0 END) AS escalated
FROM chat_conversations
GROUP BY context, DATE(created_at)
ORDER BY day DESC;

COMMENT ON VIEW chat_stats IS
  'Métricas agregadas por dia e contexto. Uso no admin dashboard. SECURITY INVOKER (RLS aplicado no contexto do auth user).';
