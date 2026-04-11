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
