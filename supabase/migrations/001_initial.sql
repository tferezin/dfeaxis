-- DFeAxis: Schema inicial
-- Todas as tabelas com Row Level Security habilitado

-- 1. Tenants
CREATE TABLE tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  company_name TEXT NOT NULL,
  email TEXT NOT NULL,
  plan TEXT DEFAULT 'starter',
  credits INTEGER DEFAULT 0,
  polling_mode TEXT DEFAULT 'manual',
  polling_interval_min INTEGER DEFAULT 15,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tenant_isolation" ON tenants
  USING (user_id = auth.uid());

CREATE POLICY "tenant_insert" ON tenants
  FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY "tenant_update" ON tenants
  FOR UPDATE USING (user_id = auth.uid());

-- 2. Certificates
CREATE TABLE certificates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
  cnpj TEXT NOT NULL,
  company_name TEXT,
  pfx_encrypted BYTEA NOT NULL,
  pfx_iv BYTEA NOT NULL,
  pfx_password_encrypted TEXT,
  valid_from DATE,
  valid_until DATE,
  is_active BOOLEAN DEFAULT true,
  last_polling_at TIMESTAMPTZ,
  last_nsu_nfe TEXT DEFAULT '000000000000000',
  last_nsu_cte TEXT DEFAULT '000000000000000',
  last_nsu_mdfe TEXT DEFAULT '000000000000000',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(tenant_id, cnpj)
);

ALTER TABLE certificates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "cert_isolation" ON certificates
  USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

CREATE POLICY "cert_insert" ON certificates
  FOR INSERT WITH CHECK (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

CREATE POLICY "cert_update" ON certificates
  FOR UPDATE USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

CREATE POLICY "cert_delete" ON certificates
  FOR DELETE USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

-- 3. Documents
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
  cnpj TEXT NOT NULL,
  tipo TEXT NOT NULL,
  chave_acesso TEXT NOT NULL,
  nsu TEXT NOT NULL,
  xml_content TEXT,
  status TEXT DEFAULT 'available',
  fetched_at TIMESTAMPTZ DEFAULT NOW(),
  delivered_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '90 days',
  job_id TEXT,
  UNIQUE(tenant_id, chave_acesso)
);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "doc_isolation" ON documents
  USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

CREATE INDEX idx_documents_tenant_cnpj_tipo ON documents(tenant_id, cnpj, tipo);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_chave ON documents(chave_acesso);

-- 4. API Keys
CREATE TABLE api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
  key_hash TEXT NOT NULL UNIQUE,
  key_prefix TEXT NOT NULL,
  description TEXT,
  last_used_at TIMESTAMPTZ,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY "apikey_isolation" ON api_keys
  USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

CREATE POLICY "apikey_insert" ON api_keys
  FOR INSERT WITH CHECK (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

CREATE POLICY "apikey_delete" ON api_keys
  FOR DELETE USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

-- 5. Polling Log
CREATE TABLE polling_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id),
  cnpj TEXT,
  tipo TEXT,
  triggered_by TEXT,
  status TEXT,
  docs_found INTEGER DEFAULT 0,
  ult_nsu TEXT,
  latency_ms INTEGER,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE polling_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "log_isolation" ON polling_log
  USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

CREATE INDEX idx_polling_log_tenant ON polling_log(tenant_id, created_at DESC);

-- 6. Credit Transactions
CREATE TABLE credit_transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id),
  amount INTEGER NOT NULL,
  description TEXT,
  reference_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE credit_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "credit_isolation" ON credit_transactions
  USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

-- 7. Função para auto-update do updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tenants_updated_at
  BEFORE UPDATE ON tenants
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- 8. Função para limpar documentos expirados (rodar via pg_cron)
CREATE OR REPLACE FUNCTION cleanup_expired_documents()
RETURNS void AS $$
BEGIN
  DELETE FROM documents
  WHERE expires_at < NOW() AND status = 'delivered';

  UPDATE documents
  SET xml_content = NULL, status = 'expired'
  WHERE expires_at < NOW() AND status = 'available';
END;
$$ LANGUAGE plpgsql;
