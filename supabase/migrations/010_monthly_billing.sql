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
