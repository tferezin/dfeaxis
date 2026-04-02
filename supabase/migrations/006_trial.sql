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
