-- DFeAxis: rastreamento de origem dos eventos de manifestação
-- Permite saber se um evento veio da ciência automática, do dashboard, ou da API.

ALTER TABLE manifestacao_events
  ADD COLUMN source TEXT DEFAULT 'api'
    CHECK (source IN ('auto_capture', 'dashboard', 'api')),
  ADD COLUMN user_id UUID,
  ADD COLUMN api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL;

COMMENT ON COLUMN manifestacao_events.source IS
  'Origem do evento: '
  'auto_capture = ciência automática durante polling, '
  'dashboard = usuário clicou no painel DFeAxis, '
  'api = chamada REST (SAP, ERP, etc).';

COMMENT ON COLUMN manifestacao_events.user_id IS
  'ID do usuário Supabase que acionou o evento (quando source=dashboard).';

COMMENT ON COLUMN manifestacao_events.api_key_id IS
  'ID da API key que acionou o evento (quando source=api).';

-- Índice para consultas de auditoria por origem
CREATE INDEX idx_manif_events_source ON manifestacao_events(tenant_id, source, created_at DESC);
