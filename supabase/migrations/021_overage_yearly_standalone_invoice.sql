-- ============================================================
-- Migration 021: separar cobrança de excedente de plano anual
-- ============================================================
--
-- Pro plano MENSAL o excedente continua como InvoiceItem pendurado que
-- entra na próxima fatura da subscription (30 dias depois). Ok.
--
-- Pro plano ANUAL isso não funciona — a próxima fatura da subscription
-- é daqui a 1 ano. Então passamos a criar uma Invoice AVULSA imediata
-- só pro excedente do mês anterior. Essa invoice tem um ID próprio
-- (stripe_invoice_id) além do InvoiceItem (stripe_invoice_item_id).
--
-- Campo stripe_invoice_id:
--   - NULL pra planos mensais (InvoiceItem pendura na sub)
--   - SET pra planos anuais (Invoice avulsa finalizada e cobrada)
--
-- Decisão D9: excedente é produto separado, cobrança mensal independente
-- do plano ser mensal ou anual.
-- ============================================================

ALTER TABLE monthly_overage_charges
  ADD COLUMN IF NOT EXISTS stripe_invoice_id TEXT;

COMMENT ON COLUMN monthly_overage_charges.stripe_invoice_id IS
  'Id da Invoice Stripe avulsa criada pra planos anuais. NULL pra planos '
  'mensais, onde o InvoiceItem fica pendurado e cai na próxima fatura do '
  'subscription (ciclo mensal).';
