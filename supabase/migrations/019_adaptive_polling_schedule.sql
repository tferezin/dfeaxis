-- Migration 019: Adaptive scheduler state for DistDFe SEFAZ (NT 2014.002)
--
-- Persiste "quando chamar SEFAZ de novo" por (certificate, tipo, ambiente).
-- Substitui o circuit_breaker in-memory (que reseta a cada deploy) por estado
-- durável no Postgres. Base do scheduler adaptativo padrão Sankhya:
-- wake-up 15min + backoff 61min após cStat 137 + drain pós-138.
--
-- Feature flag por tenant (adaptive_polling_enabled, default false) permite
-- rollout gradual — nenhum tenant vira adaptativo automaticamente.

-- ============================================================
-- 1) Tabela de estado adaptativo
-- ============================================================

CREATE TABLE IF NOT EXISTS dist_dfe_schedule_state (
  certificate_id UUID NOT NULL REFERENCES certificates(id) ON DELETE CASCADE,
  tipo           TEXT NOT NULL CHECK (tipo IN ('nfe','cte','mdfe')),
  ambiente       TEXT NOT NULL CHECK (ambiente IN ('1','2')),

  -- Estado do último ciclo SEFAZ
  ultimo_cstat        TEXT,
  ultimo_xmotivo      TEXT,
  ultimo_chamada_em   TIMESTAMPTZ,
  ultimo_latency_ms   INTEGER,

  -- NSU snapshot (redundante com nsu_state — facilita debug sem join)
  ult_nsu_atual       TEXT,
  max_nsu_atual       TEXT,

  -- Agenda adaptativa: worker só chama SEFAZ se now() >= este valor
  proxima_chamada_elegivel_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Mutex visível (complementa pg_advisory_lock, que é invisível)
  locked_until        TIMESTAMPTZ,
  locked_by           TEXT,

  -- Telemetria do drain loop (para monitoramento)
  ultimo_drain_iteracoes INTEGER DEFAULT 0,
  ultimo_drain_docs      INTEGER DEFAULT 0,

  -- Kill switch por cert — auto-quarantine após erros consecutivos
  enabled             BOOLEAN NOT NULL DEFAULT TRUE,
  disabled_reason     TEXT,

  -- Contadores de saúde
  consecutive_137     INTEGER DEFAULT 0,
  consecutive_errors  INTEGER DEFAULT 0,

  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW(),

  PRIMARY KEY (certificate_id, tipo, ambiente)
);

COMMENT ON TABLE dist_dfe_schedule_state IS
  'Estado adaptativo do scheduler DistDFe por (cert, tipo, ambiente). '
  'NT 2014.002: após cStat 137/656 aguardar 1h antes de nova consulta.';

COMMENT ON COLUMN dist_dfe_schedule_state.proxima_chamada_elegivel_em IS
  'Worker só chama SEFAZ se now() >= este valor. Gerenciado pelo scheduler.';

COMMENT ON COLUMN dist_dfe_schedule_state.locked_until IS
  'Lease-based mutex visível. Backup ao pg_advisory_lock (que só aparece em pg_locks).';

COMMENT ON COLUMN dist_dfe_schedule_state.enabled IS
  'Kill switch por cert. Setado false pelo scheduler após 5 erros consecutivos (auto-quarantine).';

CREATE INDEX IF NOT EXISTS idx_dist_dfe_sched_elegivel
  ON dist_dfe_schedule_state (proxima_chamada_elegivel_em)
  WHERE enabled = TRUE;

CREATE INDEX IF NOT EXISTS idx_dist_dfe_sched_cert
  ON dist_dfe_schedule_state (certificate_id);

-- Reusa a trigger function de nsu_state (migration 007)
CREATE TRIGGER trg_dist_dfe_sched_updated_at
  BEFORE UPDATE ON dist_dfe_schedule_state
  FOR EACH ROW EXECUTE FUNCTION update_nsu_state_updated_at();

-- RLS — tenant só vê seus próprios certificados
ALTER TABLE dist_dfe_schedule_state ENABLE ROW LEVEL SECURITY;

CREATE POLICY dist_dfe_sched_isolation ON dist_dfe_schedule_state
  FOR ALL
  USING (
    certificate_id IN (
      SELECT id FROM certificates WHERE tenant_id IN (
        SELECT id FROM tenants WHERE user_id = auth.uid()
      )
    )
  );

-- ============================================================
-- 2) Feature flag por tenant (opt-in para rollout gradual)
-- ============================================================

ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS adaptive_polling_enabled BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN tenants.adaptive_polling_enabled IS
  'Feature flag: scheduler adaptativo DistDFe (NT 2014.002). Default false — opt-in.';

-- ============================================================
-- 3) Backfill — cria linha inicial para cada cert ativo
-- ============================================================

INSERT INTO dist_dfe_schedule_state (certificate_id, tipo, ambiente, proxima_chamada_elegivel_em)
SELECT c.id, 'nfe', COALESCE(t.sefaz_ambiente, '2'), NOW()
FROM certificates c
JOIN tenants t ON t.id = c.tenant_id
WHERE c.is_active = TRUE
ON CONFLICT DO NOTHING;
