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
