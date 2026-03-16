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
