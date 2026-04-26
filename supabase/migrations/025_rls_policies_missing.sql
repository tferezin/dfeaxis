-- A4: tabelas com RLS habilitada mas sem nenhuma policy.
--
-- Em Postgres, "RLS enabled + 0 policies" significa "deny all" pra
-- usuarios anon/authenticated, mas o backend usa service_role e ignora
-- RLS. Problema: se a chave anon vazasse e existisse algum endpoint
-- intermediario que rodasse SELECT direto, nao havia policy explicita
-- documentando o comportamento — risco de regressao no futuro quando
-- alguem mexer.
--
-- Esta migration adiciona policies de isolamento por tenant pras tabelas
-- que estavam sem (`nfe_ciencia_queue`) e documenta intencao de "deny all"
-- pra `chat_leads` (PII, so service_role).
--
-- APLICAR MANUALMENTE no Supabase SQL Editor (este projeto nao roda
-- migrations automaticamente em prod).

-- ---------------------------------------------------------------------------
-- nfe_ciencia_queue: tenant ve so as proprias entries via SELECT.
-- INSERT/UPDATE/DELETE so via service_role (worker do scheduler).
-- ---------------------------------------------------------------------------

CREATE POLICY ciencia_queue_isolation ON nfe_ciencia_queue
  FOR SELECT USING (
    tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid())
  );

CREATE POLICY ciencia_queue_insert ON nfe_ciencia_queue
  FOR INSERT WITH CHECK (
    tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid())
  );

-- Sem policy de UPDATE/DELETE: scheduler/worker roda como service_role e
-- bypassa RLS. Cliente final nao tem motivo pra mexer nesta tabela.

-- ---------------------------------------------------------------------------
-- chat_leads: PII (email, telefone, ip). Mantemos RLS ENABLE sem policy
-- pra deixar o "deny all" pra anon/authenticated explicito. Acesso via
-- backend service_role apenas (admin dashboard).
-- ---------------------------------------------------------------------------

COMMENT ON TABLE chat_leads IS
  'PII (LGPD): leads de landing. Acesso somente via service_role (backend). '
  'RLS habilitada sem policy = deny all pra anon/authenticated por design.';
