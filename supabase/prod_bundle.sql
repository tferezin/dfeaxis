-- ================================================================
-- DFeAxis PRODUCTION — Consolidated migrations 001 → 011
-- Gerado em: Sun Apr 12 18:29:51 -03 2026
-- Cole este arquivo inteiro no SQL Editor do Supabase e execute.
-- ================================================================


-- ================================================================
-- 001_initial.sql
-- ================================================================
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


-- ================================================================
-- 002_manifestacao.sql
-- ================================================================
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


-- ================================================================
-- 003_security_hardening.sql
-- ================================================================
-- DFeAxis: Security Hardening
-- Atomic credit operations, audit trail, CNPJ validation, schema fixes

-- ============================================================
-- 1. Atomic credit debit/credit function (prevents race conditions)
-- ============================================================
CREATE OR REPLACE FUNCTION debit_credits(
  p_tenant_id UUID,
  p_amount INTEGER,
  p_description TEXT,
  p_reference_id TEXT DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
  v_current_credits INTEGER;
  v_new_credits INTEGER;
BEGIN
  -- Lock the row to prevent concurrent modifications
  SELECT credits INTO v_current_credits
  FROM tenants
  WHERE id = p_tenant_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Tenant % not found', p_tenant_id;
  END IF;

  -- For debits (negative amount), check sufficient credits
  IF p_amount < 0 AND v_current_credits < abs(p_amount) THEN
    RAISE EXCEPTION 'Insufficient credits: have %, need %',
      v_current_credits, abs(p_amount);
  END IF;

  v_new_credits := v_current_credits + p_amount;

  -- Update credits
  UPDATE tenants
  SET credits = v_new_credits
  WHERE id = p_tenant_id;

  -- Insert transaction record
  INSERT INTO credit_transactions (tenant_id, amount, description, reference_id)
  VALUES (p_tenant_id, p_amount, p_description, p_reference_id);

  RETURN v_new_credits;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 2. Audit trail table
-- ============================================================
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id),
  user_id UUID,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  details JSONB,
  ip_address TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "audit_isolation" ON audit_log
  USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

CREATE INDEX idx_audit_log_tenant_created ON audit_log(tenant_id, created_at DESC);
CREATE INDEX idx_audit_log_action_created ON audit_log(action, created_at DESC);

-- ============================================================
-- 3. CNPJ validation function (mod 11 checksum)
-- ============================================================
CREATE OR REPLACE FUNCTION validate_cnpj(cnpj TEXT) RETURNS BOOLEAN AS $$
DECLARE
  digits INTEGER[];
  weights_1 INTEGER[] := ARRAY[5,4,3,2,9,8,7,6,5,4,3,2];
  weights_2 INTEGER[] := ARRAY[6,5,4,3,2,9,8,7,6,5,4,3,2];
  sum_val INTEGER;
  remainder INTEGER;
  d1 INTEGER;
  d2 INTEGER;
  clean_cnpj TEXT;
  i INTEGER;
BEGIN
  -- Strip non-digits
  clean_cnpj := regexp_replace(cnpj, '[^0-9]', '', 'g');

  -- Must be exactly 14 digits
  IF length(clean_cnpj) != 14 THEN
    RETURN FALSE;
  END IF;

  -- Reject all-same-digit CNPJs (e.g., 00000000000000, 11111111111111)
  IF clean_cnpj ~ '^(.)\1{13}$' THEN
    RETURN FALSE;
  END IF;

  -- Extract digits into array
  FOR i IN 1..14 LOOP
    digits[i] := substring(clean_cnpj FROM i FOR 1)::INTEGER;
  END LOOP;

  -- First check digit (position 13)
  sum_val := 0;
  FOR i IN 1..12 LOOP
    sum_val := sum_val + digits[i] * weights_1[i];
  END LOOP;
  remainder := sum_val % 11;
  d1 := CASE WHEN remainder < 2 THEN 0 ELSE 11 - remainder END;

  IF digits[13] != d1 THEN
    RETURN FALSE;
  END IF;

  -- Second check digit (position 14)
  sum_val := 0;
  FOR i IN 1..13 LOOP
    sum_val := sum_val + digits[i] * weights_2[i];
  END LOOP;
  remainder := sum_val % 11;
  d2 := CASE WHEN remainder < 2 THEN 0 ELSE 11 - remainder END;

  IF digits[14] != d2 THEN
    RETURN FALSE;
  END IF;

  RETURN TRUE;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Add CNPJ validation constraints
ALTER TABLE certificates
  ADD CONSTRAINT chk_certificates_cnpj CHECK (validate_cnpj(cnpj));

ALTER TABLE documents
  ADD CONSTRAINT chk_documents_cnpj CHECK (validate_cnpj(cnpj));

-- ============================================================
-- 4. NOT NULL constraints where missing
-- ============================================================
ALTER TABLE polling_log
  ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE credit_transactions
  ALTER COLUMN tenant_id SET NOT NULL;

-- ============================================================
-- 5. Add job_id column to polling_log (replaces error_message hack)
-- ============================================================
ALTER TABLE polling_log ADD COLUMN job_id TEXT;
CREATE INDEX idx_polling_log_job ON polling_log(job_id) WHERE job_id IS NOT NULL;


-- ================================================================
-- 004_nfse.sql
-- ================================================================
-- 004_nfse.sql
-- Adiciona suporte a NFS-e (Nota Fiscal de Servico Eletronica) via ADN
-- Reforma Tributaria vigente desde 01/2026

-- Coluna para rastrear ultimo NSU de NFS-e no ADN
ALTER TABLE certificates
    ADD COLUMN IF NOT EXISTS last_nsu_nfse TEXT NOT NULL DEFAULT '000000000000000';

-- Campos especificos de NFS-e na tabela documents
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS codigo_municipio TEXT,
    ADD COLUMN IF NOT EXISTS codigo_servico TEXT;

-- Indice para consultas NFS-e por municipio
CREATE INDEX IF NOT EXISTS idx_documents_nfse_municipio
    ON documents (tenant_id, tipo, codigo_municipio)
    WHERE tipo = 'NFSE';

-- Comentarios
COMMENT ON COLUMN certificates.last_nsu_nfse IS 'Ultimo NSU processado no Ambiente Nacional de NFS-e (ADN)';
COMMENT ON COLUMN documents.codigo_municipio IS 'Codigo IBGE do municipio (NFS-e)';
COMMENT ON COLUMN documents.codigo_servico IS 'Codigo do servico LC 116 (NFS-e)';


-- ================================================================
-- 005_ambiente_toggle.sql
-- ================================================================
-- Add ambiente column to tenants (per-tenant SEFAZ environment)
ALTER TABLE tenants
  ADD COLUMN sefaz_ambiente TEXT DEFAULT '2'
    CHECK (sefaz_ambiente IN ('1', '2'));

COMMENT ON COLUMN tenants.sefaz_ambiente IS
  '1 = Produção, 2 = Homologação. Default homologação for safety.';


-- ================================================================
-- 006_trial.sql
-- ================================================================
-- Trial system: 7-day free trial for new tenants
ALTER TABLE tenants
  ADD COLUMN trial_expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '7 days'),
  ADD COLUMN trial_active BOOLEAN DEFAULT true,
  ADD COLUMN subscription_status TEXT DEFAULT 'trial'
    CHECK (subscription_status IN ('trial', 'active', 'cancelled', 'expired'));

-- Set trial for existing tenants
UPDATE tenants
  SET trial_expires_at = NOW() + INTERVAL '7 days',
      trial_active = true,
      subscription_status = 'trial'
  WHERE trial_expires_at IS NULL;

COMMENT ON COLUMN tenants.trial_expires_at IS
  'When the 7-day free trial expires.';
COMMENT ON COLUMN tenants.trial_active IS
  'Whether the trial period is still active.';
COMMENT ON COLUMN tenants.subscription_status IS
  'trial | active | cancelled | expired';


-- ================================================================
-- 007_trial_spec.sql
-- ================================================================
-- 007_trial_spec.sql
-- Trial spec final: 10 dias OU 500 docs, CNPJ único global,
-- NSU por ambiente, deleção de .pfx após 30 dias inatividade.
-- IMPORTANTE: a 006 nunca foi aplicada — esta migration aplica
-- tudo que estava na 006 + os deltas do trial spec novo.

-- =============================================
-- 1. Tabela tenants — colunas do trial
-- =============================================

-- Aplicar campos do trial (consolidando 006 que nunca rodou)
ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS trial_expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '10 days'),
  ADD COLUMN IF NOT EXISTS trial_active BOOLEAN DEFAULT true,
  ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'trial';

-- CHECK constraint do subscription_status (separado pra ser idempotente)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'tenants_subscription_status_check'
  ) THEN
    ALTER TABLE tenants ADD CONSTRAINT tenants_subscription_status_check
      CHECK (subscription_status IN ('trial', 'active', 'cancelled', 'expired'));
  END IF;
END $$;

-- Colunas do trial spec final
ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS phone TEXT,
  ADD COLUMN IF NOT EXISTS cnpj TEXT,
  ADD COLUMN IF NOT EXISTS docs_consumidos_trial INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS trial_cap INT DEFAULT 500,
  ADD COLUMN IF NOT EXISTS trial_blocked_reason TEXT,
  ADD COLUMN IF NOT EXISTS trial_blocked_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS pfx_inactive_since TIMESTAMPTZ;

-- CHECK do trial_blocked_reason
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'tenants_trial_blocked_reason_check'
  ) THEN
    ALTER TABLE tenants ADD CONSTRAINT tenants_trial_blocked_reason_check
      CHECK (trial_blocked_reason IS NULL OR trial_blocked_reason IN ('time', 'cap'));
  END IF;
END $$;

-- UNIQUE constraint global em CNPJ (defesa anti-abuse principal)
-- 1 CNPJ = 1 trial na vida
CREATE UNIQUE INDEX IF NOT EXISTS tenants_cnpj_unique
  ON tenants(cnpj)
  WHERE cnpj IS NOT NULL;

-- Tenants já existentes (admin) — marcar como active, não trial
UPDATE tenants
  SET trial_active = false,
      subscription_status = 'active'
  WHERE plan IN ('enterprise', 'business', 'starter')
    AND created_at < NOW() - INTERVAL '1 day'
    AND subscription_status IS NULL;

COMMENT ON COLUMN tenants.docs_consumidos_trial IS
  'Quantidade de docs já capturados durante o trial';
COMMENT ON COLUMN tenants.trial_cap IS
  'Limite de docs no trial (default 500)';
COMMENT ON COLUMN tenants.trial_blocked_reason IS
  'time = atingiu 10 dias, cap = atingiu 500 docs';
COMMENT ON COLUMN tenants.cnpj IS
  'CNPJ principal do tenant. UNIQUE global para anti-abuse de trial.';
COMMENT ON COLUMN tenants.pfx_inactive_since IS
  'Quando ficou inativo. .pfx é deletado após 30 dias desta data.';

-- =============================================
-- 2. Tabela nsu_state — cursores por ambiente
-- =============================================

CREATE TABLE IF NOT EXISTS nsu_state (
  certificate_id UUID NOT NULL REFERENCES certificates(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN ('nfe', 'cte', 'mdfe', 'nfse')),
  ambiente TEXT NOT NULL CHECK (ambiente IN ('1', '2')),
  last_nsu TEXT NOT NULL DEFAULT '000000000000000',
  max_nsu TEXT,
  pendentes INT DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (certificate_id, tipo, ambiente)
);

CREATE INDEX IF NOT EXISTS idx_nsu_state_cert ON nsu_state(certificate_id);

-- Migrar dados existentes para nsu_state
-- Os cursores antigos em certificates vão para o ambiente atual do tenant
INSERT INTO nsu_state (certificate_id, tipo, ambiente, last_nsu)
SELECT c.id, 'nfe', COALESCE(t.sefaz_ambiente, '2'), c.last_nsu_nfe
FROM certificates c
JOIN tenants t ON c.tenant_id = t.id
WHERE c.last_nsu_nfe IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO nsu_state (certificate_id, tipo, ambiente, last_nsu)
SELECT c.id, 'cte', COALESCE(t.sefaz_ambiente, '2'), c.last_nsu_cte
FROM certificates c
JOIN tenants t ON c.tenant_id = t.id
WHERE c.last_nsu_cte IS NOT NULL
ON CONFLICT DO NOTHING;

INSERT INTO nsu_state (certificate_id, tipo, ambiente, last_nsu)
SELECT c.id, 'mdfe', COALESCE(t.sefaz_ambiente, '2'), c.last_nsu_mdfe
FROM certificates c
JOIN tenants t ON c.tenant_id = t.id
WHERE c.last_nsu_mdfe IS NOT NULL
ON CONFLICT DO NOTHING;

-- NFS-e — só se a coluna existir (migration 004)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='certificates' AND column_name='last_nsu_nfse'
  ) THEN
    INSERT INTO nsu_state (certificate_id, tipo, ambiente, last_nsu)
    SELECT c.id, 'nfse', COALESCE(t.sefaz_ambiente, '2'),
           COALESCE(c.last_nsu_nfse, '000000000000000')
    FROM certificates c
    JOIN tenants t ON c.tenant_id = t.id
    ON CONFLICT DO NOTHING;
  END IF;
END $$;

-- Trigger para atualizar updated_at
CREATE OR REPLACE FUNCTION update_nsu_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_nsu_state_updated_at ON nsu_state;
CREATE TRIGGER trg_nsu_state_updated_at
  BEFORE UPDATE ON nsu_state
  FOR EACH ROW EXECUTE FUNCTION update_nsu_state_updated_at();

-- RLS
ALTER TABLE nsu_state ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS nsu_state_isolation ON nsu_state;
CREATE POLICY nsu_state_isolation ON nsu_state
  FOR ALL
  USING (
    certificate_id IN (
      SELECT id FROM certificates WHERE tenant_id IN (
        SELECT id FROM tenants WHERE user_id = auth.uid()
      )
    )
  );

COMMENT ON TABLE nsu_state IS
  'Cursor NSU por (certificado, tipo, ambiente). Permite alternar hom/prod sem perder estado.';
COMMENT ON COLUMN nsu_state.max_nsu IS
  'Maior NSU disponível na SEFAZ na última leitura. pendentes = max_nsu - last_nsu.';

-- =============================================
-- 3. Função atomica de incremento de docs no trial
-- =============================================

CREATE OR REPLACE FUNCTION increment_trial_docs(
  p_tenant_id UUID,
  p_count INT
) RETURNS INT AS $$
DECLARE
  v_new_count INT;
  v_cap INT;
  v_status TEXT;
  v_blocked_at TIMESTAMPTZ;
BEGIN
  SELECT trial_cap, subscription_status, trial_blocked_at
    INTO v_cap, v_status, v_blocked_at
    FROM tenants
    WHERE id = p_tenant_id
    FOR UPDATE;

  -- Não incrementa se não está em trial
  IF v_status != 'trial' THEN
    RETURN 0;
  END IF;

  -- Não incrementa se trial já está bloqueado (defense in depth)
  IF v_blocked_at IS NOT NULL THEN
    RETURN 0;
  END IF;

  UPDATE tenants
    SET docs_consumidos_trial = LEAST(docs_consumidos_trial + p_count, v_cap)
    WHERE id = p_tenant_id
    RETURNING docs_consumidos_trial INTO v_new_count;

  -- Se atingiu o cap, marca como bloqueado
  IF v_new_count >= v_cap THEN
    UPDATE tenants
      SET trial_blocked_reason = 'cap',
          trial_blocked_at = NOW(),
          trial_active = false
      WHERE id = p_tenant_id AND trial_blocked_at IS NULL;
  END IF;

  RETURN v_new_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION increment_trial_docs IS
  'Incrementa docs_consumidos_trial atomicamente. Bloqueia o trial automaticamente ao atingir o cap.';


-- ================================================================
-- 008_stripe_billing.sql
-- ================================================================
-- 008_stripe_billing.sql
-- Stripe billing integration: subscriptions + overage + Customer Portal.
--
-- Architecture: Stripe is the source of truth. We mirror only the minimum
-- necessary state in our DB to gate access without round-tripping to Stripe
-- on every request. The webhook keeps state in sync.

-- =============================================
-- 1. tenants — Stripe linkage columns
-- =============================================

ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
  ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT,
  ADD COLUMN IF NOT EXISTS stripe_price_id TEXT,
  ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN DEFAULT false;

-- One Stripe customer per tenant — enforce uniqueness
CREATE UNIQUE INDEX IF NOT EXISTS tenants_stripe_customer_id_unique
  ON tenants(stripe_customer_id)
  WHERE stripe_customer_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS tenants_stripe_subscription_id_idx
  ON tenants(stripe_subscription_id)
  WHERE stripe_subscription_id IS NOT NULL;

COMMENT ON COLUMN tenants.stripe_customer_id IS
  'Stripe Customer ID (cus_...). Created lazily on first checkout.';
COMMENT ON COLUMN tenants.stripe_subscription_id IS
  'Active Stripe Subscription ID (sub_...).';
COMMENT ON COLUMN tenants.stripe_price_id IS
  'Stripe Price ID currently active (price_...). Identifies the plan tier.';
COMMENT ON COLUMN tenants.current_period_end IS
  'When the current billing period ends (used to gate access on past_due).';
COMMENT ON COLUMN tenants.cancel_at_period_end IS
  'True if the user requested cancel; access remains until current_period_end.';

-- =============================================
-- 2. billing_events — webhook idempotency log
-- =============================================

CREATE TABLE IF NOT EXISTS billing_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
  stripe_event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB,
  processed_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT billing_events_stripe_event_id_unique UNIQUE (stripe_event_id)
);

CREATE INDEX IF NOT EXISTS billing_events_tenant_id_idx
  ON billing_events(tenant_id);
CREATE INDEX IF NOT EXISTS billing_events_event_type_idx
  ON billing_events(event_type);
CREATE INDEX IF NOT EXISTS billing_events_processed_at_idx
  ON billing_events(processed_at DESC);

COMMENT ON TABLE billing_events IS
  'Audit log + idempotency guard for Stripe webhook events. UNIQUE on stripe_event_id ensures double-delivery does not double-process.';

-- =============================================
-- 3. RLS for billing_events
-- =============================================

ALTER TABLE billing_events ENABLE ROW LEVEL SECURITY;

-- Tenants can read their own billing events (for invoice history UI)
DROP POLICY IF EXISTS billing_events_tenant_read ON billing_events;
CREATE POLICY billing_events_tenant_read ON billing_events
  FOR SELECT
  USING (
    tenant_id IN (
      SELECT id FROM tenants WHERE user_id = auth.uid()
    )
  );

-- Only service role can write (webhook handler runs with service role)
-- (no INSERT/UPDATE/DELETE policy means only service_role can write)


-- ================================================================
-- 009_manifestacao_deadline.sql
-- ================================================================
-- DFeAxis: Prazo de manifestação (180 dias SEFAZ)
-- Adiciona campo para controlar deadline de manifestação definitiva em NF-e.

ALTER TABLE documents
  ADD COLUMN manifestacao_deadline TIMESTAMPTZ;

COMMENT ON COLUMN documents.manifestacao_deadline IS
  'Prazo limite para manifestação definitiva (180 dias após ciência). '
  'Só se aplica a NF-e com is_resumo=true. NULL para CT-e/MDF-e/NFS-e.';

-- Índice para o job de alertas: NF-e com ciência mas sem manifesto definitivo
CREATE INDEX idx_documents_manif_deadline
  ON documents(tenant_id, manifestacao_deadline)
  WHERE manifestacao_status = 'ciencia'
    AND manifestacao_deadline IS NOT NULL;


-- ================================================================
-- 010_monthly_billing.sql
-- ================================================================
-- DFeAxis: Billing mensal — contadores, billing_day, ciclo
-- Suporte a modelo pós-trial: base pré-pago + excedente pós-pago via InvoiceItem

-- ============================================================
-- 1. Colunas em tenants para controle de ciclo mensal
-- ============================================================
ALTER TABLE tenants
  ADD COLUMN docs_consumidos_mes INTEGER DEFAULT 0,
  ADD COLUMN docs_included_mes INTEGER DEFAULT 0,
  ADD COLUMN billing_day INTEGER DEFAULT 5
    CHECK (billing_day IN (5, 10, 15)),
  ADD COLUMN ciclo_mes_inicio DATE,
  ADD COLUMN max_cnpjs INTEGER DEFAULT 1;

COMMENT ON COLUMN tenants.docs_consumidos_mes IS
  'Contador de docs capturados no mês calendário atual. Reseta no dia 1.';

COMMENT ON COLUMN tenants.docs_included_mes IS
  'Franquia de docs incluídos no plano (3000/8000/20000). '
  'Pro-rata no primeiro mês parcial.';

COMMENT ON COLUMN tenants.billing_day IS
  'Dia do mês em que Stripe gera a fatura. Opções: 5, 10, 15.';

COMMENT ON COLUMN tenants.ciclo_mes_inicio IS
  'Data de início do ciclo mensal atual. Usado para pro-rata e reset.';

COMMENT ON COLUMN tenants.max_cnpjs IS
  'Limite de CNPJs ativos permitidos no plano. '
  'Starter 1, Business 5, Enterprise 50.';

-- ============================================================
-- 2. Função: incrementar contador mensal atomicamente
-- ============================================================
CREATE OR REPLACE FUNCTION increment_monthly_docs(
  p_tenant_id UUID,
  p_count INTEGER DEFAULT 1
) RETURNS INTEGER AS $$
DECLARE
  v_new_count INTEGER;
BEGIN
  UPDATE tenants
  SET docs_consumidos_mes = COALESCE(docs_consumidos_mes, 0) + p_count
  WHERE id = p_tenant_id
    AND subscription_status = 'active'
  RETURNING docs_consumidos_mes INTO v_new_count;

  RETURN COALESCE(v_new_count, 0);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION increment_monthly_docs IS
  'Incrementa docs_consumidos_mes atomicamente para tenants ativos. '
  'Retorna o novo valor. Não bloqueia ao atingir limite — excedente cobrado.';

-- ============================================================
-- 3. Função: reset mensal do contador + snapshot pro excedente
-- ============================================================
CREATE OR REPLACE FUNCTION reset_monthly_counter(
  p_tenant_id UUID
) RETURNS INTEGER AS $$
DECLARE
  v_consumed INTEGER;
  v_included INTEGER;
  v_excedente INTEGER;
BEGIN
  SELECT docs_consumidos_mes, docs_included_mes
  INTO v_consumed, v_included
  FROM tenants
  WHERE id = p_tenant_id;

  v_excedente := GREATEST(0, COALESCE(v_consumed, 0) - COALESCE(v_included, 0));

  UPDATE tenants
  SET docs_consumidos_mes = 0,
      ciclo_mes_inicio = CURRENT_DATE
  WHERE id = p_tenant_id;

  RETURN v_excedente;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION reset_monthly_counter IS
  'Reseta docs_consumidos_mes e retorna o excedente do ciclo que acabou. '
  'Chamado no dia 1 de cada mês pelo job manifestacao_alert_job ou equivalente.';

-- ============================================================
-- 4. Tabela de histórico de excedentes cobrados
-- ============================================================
CREATE TABLE monthly_overage_charges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
  ciclo_mes DATE NOT NULL,
  docs_consumidos INTEGER NOT NULL,
  docs_included INTEGER NOT NULL,
  excedente_docs INTEGER NOT NULL,
  excedente_cents INTEGER NOT NULL,
  stripe_invoice_item_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (tenant_id, ciclo_mes)
);

ALTER TABLE monthly_overage_charges ENABLE ROW LEVEL SECURITY;

CREATE POLICY "overage_tenant_read" ON monthly_overage_charges
  FOR SELECT
  USING (tenant_id IN (SELECT id FROM tenants WHERE user_id = auth.uid()));

CREATE INDEX idx_overage_tenant_ciclo
  ON monthly_overage_charges(tenant_id, ciclo_mes DESC);

COMMENT ON TABLE monthly_overage_charges IS
  'Histórico de cobranças de excedente por ciclo mensal. '
  'Uma linha por (tenant, mês). Auditoria + idempotência do job mensal.';


-- ================================================================
-- 011_manifestacao_source.sql
-- ================================================================
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


-- ================================================================
-- 012_chat_conversations.sql
-- ================================================================
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


-- ================================================================
-- 013_ga4_tracking.sql
-- ================================================================
-- DFeAxis: GA4 Measurement Protocol tracking
-- Armazena o client_id do GA4 (cookie _ga) capturado no signup
-- para permitir que o webhook do Stripe dispare um evento `purchase`
-- server-side atribuido ao mesmo usuário que clicou no anúncio original.
--
-- Formato do client_id: "XXXXXXXX.YYYYYYYY" (2 números separados por ponto)
-- extraído do cookie _ga "GA1.1.XXXXXXXX.YYYYYYYY".

ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS ga_client_id TEXT;

COMMENT ON COLUMN tenants.ga_client_id IS
  'GA4 client_id from _ga cookie at signup. Used by Stripe webhook to fire purchase event via Measurement Protocol with correct ad attribution.';


-- ================================================================
-- 014_campaign_attribution.sql
-- ================================================================
-- DFeAxis: Campaign attribution tracking
-- Guarda os parâmetros UTM + click IDs capturados na primeira página visitada
-- pelo usuário (ou na última com UTM, last-touch). Usado para atribuir
-- conversões a canais/grupos/keywords específicos no dashboard interno,
-- sem depender exclusivamente do painel do Google Analytics.

ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS utm_source TEXT,
  ADD COLUMN IF NOT EXISTS utm_medium TEXT,
  ADD COLUMN IF NOT EXISTS utm_campaign TEXT,
  ADD COLUMN IF NOT EXISTS utm_term TEXT,
  ADD COLUMN IF NOT EXISTS utm_content TEXT,
  ADD COLUMN IF NOT EXISTS gclid TEXT,
  ADD COLUMN IF NOT EXISTS fbclid TEXT,
  ADD COLUMN IF NOT EXISTS referrer TEXT,
  ADD COLUMN IF NOT EXISTS landing_path TEXT;

-- Index nos campos mais consultados em relatórios de ROAS:
CREATE INDEX IF NOT EXISTS idx_tenants_utm_campaign
  ON tenants (utm_campaign) WHERE utm_campaign IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tenants_utm_source_medium
  ON tenants (utm_source, utm_medium) WHERE utm_source IS NOT NULL;

COMMENT ON COLUMN tenants.utm_source IS 'UTM source (google, meta, direct, organic) — last-touch na hora do signup';
COMMENT ON COLUMN tenants.utm_medium IS 'UTM medium (cpc, email, social, organic) — last-touch na hora do signup';
COMMENT ON COLUMN tenants.utm_campaign IS 'UTM campaign (nome do grupo de anúncios Google Ads)';
COMMENT ON COLUMN tenants.utm_term IS 'UTM term (keyword que disparou o clique, opcional)';
COMMENT ON COLUMN tenants.utm_content IS 'UTM content (variante de anúncio, opcional)';
COMMENT ON COLUMN tenants.gclid IS 'Google Click ID — permite join direto com relatórios do Google Ads';
COMMENT ON COLUMN tenants.fbclid IS 'Facebook Click ID — futuro, se rodar Meta Ads';
COMMENT ON COLUMN tenants.referrer IS 'document.referrer no momento da captura (first-touch)';
COMMENT ON COLUMN tenants.landing_path IS 'Path da primeira página visitada antes do signup';


-- ================================================================
-- 015_document_metadata.sql
-- ================================================================
-- DFeAxis: metadata extraído do XML de cada documento fiscal

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS cnpj_emitente TEXT,
  ADD COLUMN IF NOT EXISTS razao_social_emitente TEXT,
  ADD COLUMN IF NOT EXISTS cnpj_destinatario TEXT,
  ADD COLUMN IF NOT EXISTS numero_documento TEXT,
  ADD COLUMN IF NOT EXISTS data_emissao TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS valor_total NUMERIC(18, 2);

CREATE INDEX IF NOT EXISTS idx_documents_cnpj_emitente
  ON documents (tenant_id, cnpj_emitente)
  WHERE cnpj_emitente IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_data_emissao
  ON documents (tenant_id, data_emissao)
  WHERE data_emissao IS NOT NULL;

COMMENT ON COLUMN documents.cnpj_emitente IS 'CNPJ (14 dígitos) extraído de <emit><CNPJ> do XML. Quem EMITIU a nota (fornecedor, no caso de inbound). NULL pra resumos onde xml_content é null.';
COMMENT ON COLUMN documents.razao_social_emitente IS 'Razão social de <emit><xNome>. NULL pra resumos.';
COMMENT ON COLUMN documents.cnpj_destinatario IS 'CNPJ extraído de <dest><CNPJ>. Deve bater com o cnpj do tenant (o cliente). NULL pra MDFe (não tem destinatário único).';
COMMENT ON COLUMN documents.numero_documento IS 'Número humano do doc (nNF, nCT, nMDF). NULL pra resumos.';
COMMENT ON COLUMN documents.data_emissao IS 'Timestamp de <dhEmi>. Diferente de fetched_at (quando o DFeAxis capturou).';
COMMENT ON COLUMN documents.valor_total IS 'Valor total: vNF (NFe), vTPrest (CTe), vCarga (MDFe), ValorServicos (NFSe).';


-- ================================================================
-- 016_past_due_status.sql
-- ================================================================
-- Add 'past_due' to subscription_status check constraint.

DO $$
BEGIN
  -- Drop and recreate to add the new value
  ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_subscription_status_check;
  ALTER TABLE tenants ADD CONSTRAINT tenants_subscription_status_check
    CHECK (subscription_status IN ('trial', 'active', 'cancelled', 'expired', 'past_due'));
END $$;

-- ================================================================
-- 017_nfe_ciencia_queue.sql
-- ================================================================
-- Queue for NFe resumos awaiting ciencia + XML fetch
CREATE TABLE IF NOT EXISTS nfe_ciencia_queue (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    certificate_id UUID NOT NULL REFERENCES certificates(id) ON DELETE CASCADE,
    cnpj TEXT NOT NULL,
    chave_acesso TEXT NOT NULL,
    nsu TEXT NOT NULL,
    -- Ciencia status
    ciencia_enviada BOOLEAN DEFAULT FALSE,
    ciencia_enviada_at TIMESTAMPTZ,
    ciencia_cstat TEXT,
    -- XML fetch status
    xml_fetched BOOLEAN DEFAULT FALSE,
    xml_fetched_at TIMESTAMPTZ,
    -- Control
    tentativas INTEGER DEFAULT 0,
    ultimo_erro TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    -- Unique per tenant+chave to avoid duplicates
    UNIQUE(tenant_id, chave_acesso)
);

CREATE INDEX IF NOT EXISTS idx_nfe_ciencia_queue_pending
    ON nfe_ciencia_queue(ciencia_enviada, xml_fetched)
    WHERE ciencia_enviada = FALSE OR xml_fetched = FALSE;

-- RLS
ALTER TABLE nfe_ciencia_queue ENABLE ROW LEVEL SECURITY;

