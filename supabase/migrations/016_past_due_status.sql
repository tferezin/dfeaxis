-- 016: Add 'past_due' to subscription_status check constraint.
--
-- Distinguishes between trial expiration ('expired') and payment overdue
-- ('past_due'). Enables grace period logic: access remains until
-- current_period_end, then blocks with PAYMENT_OVERDUE.

DO $$
BEGIN
  -- Drop and recreate to add the new value
  ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_subscription_status_check;
  ALTER TABLE tenants ADD CONSTRAINT tenants_subscription_status_check
    CHECK (subscription_status IN ('trial', 'active', 'cancelled', 'expired', 'past_due'));
END $$;
