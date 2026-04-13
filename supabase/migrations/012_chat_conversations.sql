-- DFeAxis: Chat/Bot conversations
-- Guarda histórico de conversas do bot landing (anônimo) e dashboard (autenticado)

-- ============================================================
-- 1. Tabela de conversas
-- ============================================================
CREATE TABLE chat_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Contexto: 'landing' = prospect anônimo, 'dashboard' = tenant autenticado
  context TEXT NOT NULL CHECK (context IN ('landing', 'dashboard')),

  -- Identificação (opcional): só tenant_id se logado
  tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
  user_id UUID,  -- Supabase auth user_id quando logado

  -- Pra landing bot anônimo: session_id do browser (localStorage), IP hash
  session_id TEXT,
  ip_hash TEXT,  -- SHA256 do IP pra rate limit sem guardar IP real
  user_agent TEXT,

  -- Metadata
  metadata JSONB DEFAULT '{}'::jsonb,  -- qualquer extra: page_url, referrer, etc

  -- Status
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'closed', 'escalated')),
  escalated_to_human BOOLEAN DEFAULT false,
  escalated_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_message_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE chat_conversations IS
  'Conversas do bot de atendimento. Landing (anônimo) e Dashboard (autenticado).';

CREATE INDEX idx_chat_conv_tenant ON chat_conversations(tenant_id, created_at DESC)
  WHERE tenant_id IS NOT NULL;
CREATE INDEX idx_chat_conv_session ON chat_conversations(session_id, created_at DESC)
  WHERE session_id IS NOT NULL;
CREATE INDEX idx_chat_conv_context ON chat_conversations(context, created_at DESC);

-- ============================================================
-- 2. Tabela de mensagens
-- ============================================================
CREATE TABLE chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,

  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,

  -- Metadados da mensagem do assistant
  model TEXT,  -- ex: 'claude-haiku-4-5-20251001'
  input_tokens INTEGER,
  output_tokens INTEGER,
  latency_ms INTEGER,

  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chat_msg_conv ON chat_messages(conversation_id, created_at ASC);

COMMENT ON TABLE chat_messages IS
  'Mensagens individuais de cada conversa. Uma linha por turno (user + assistant).';

-- ============================================================
-- 3. RLS — Tenants vêem só suas conversas do dashboard
-- ============================================================
ALTER TABLE chat_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "chat_conv_tenant_read" ON chat_conversations
  FOR SELECT
  USING (
    -- Tenants veem suas próprias (dashboard)
    (context = 'dashboard' AND tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()))
    -- Landing conversations são visíveis só via service_role
  );

CREATE POLICY "chat_msg_tenant_read" ON chat_messages
  FOR SELECT
  USING (
    conversation_id IN (
      SELECT id FROM chat_conversations
      WHERE context = 'dashboard'
        AND tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid())
    )
  );

-- ============================================================
-- 4. View de métricas (pra admin dashboard futuro)
-- ============================================================
CREATE OR REPLACE VIEW chat_stats AS
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
  'Métricas agregadas por dia e contexto. Uso no admin dashboard.';
