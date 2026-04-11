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
