-- DFeAxis: Suporte a Manifestação do Destinatário
-- Adiciona campos para controlar o fluxo de manifestação NF-e

-- 1. Campo no tenant para modo de manifestação
ALTER TABLE tenants
  ADD COLUMN manifestacao_mode TEXT DEFAULT 'auto_ciencia'
    CHECK (manifestacao_mode IN ('auto_ciencia', 'manual', 'manual_only'));

COMMENT ON COLUMN tenants.manifestacao_mode IS
  'auto_ciencia (default): envia Ciência (210210) automaticamente ao detectar resumo. '
  'manual: legado, equivale a auto_ciencia (ciência é obrigatória SEFAZ). '
  'manual_only: desabilita ciência automática — cliente envia manualmente.';

-- 2. Novos campos na tabela documents para rastrear manifestação
ALTER TABLE documents
  ADD COLUMN manifestacao_status TEXT DEFAULT NULL
    CHECK (manifestacao_status IN (
      'pendente',          -- resumo recebido, aguardando manifestação
      'ciencia',           -- 210210 enviada
      'confirmada',        -- 210200 enviada
      'desconhecida',      -- 210220 enviada
      'nao_realizada',     -- 210240 enviada
      'nao_aplicavel'      -- CT-e/MDF-e (não requer manifestação)
    )),
  ADD COLUMN manifestacao_at TIMESTAMPTZ,
  ADD COLUMN is_resumo BOOLEAN DEFAULT false;

COMMENT ON COLUMN documents.manifestacao_status IS
  'Status da manifestação do destinatário para NF-e. '
  'NULL para docs que já vieram com XML completo.';

COMMENT ON COLUMN documents.is_resumo IS
  'true se o documento é apenas um resumo (resNFe), sem XML completo.';

-- 3. Tabela de eventos de manifestação (auditoria)
CREATE TABLE manifestacao_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  chave_acesso TEXT NOT NULL,
  tipo_evento TEXT NOT NULL
    CHECK (tipo_evento IN ('210210', '210200', '210220', '210240')),
  cstat TEXT,
  xmotivo TEXT,
  protocolo TEXT,
  latency_ms INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE manifestacao_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "manif_isolation" ON manifestacao_events
  USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

CREATE INDEX idx_manif_tenant_doc ON manifestacao_events(tenant_id, document_id);
CREATE INDEX idx_manif_chave ON manifestacao_events(chave_acesso);

-- 4. Índice para buscar documentos pendentes de manifestação
CREATE INDEX idx_documents_manifestacao ON documents(tenant_id, manifestacao_status)
  WHERE manifestacao_status = 'pendente';
