-- Add ambiente column to tenants (per-tenant SEFAZ environment)
ALTER TABLE tenants
  ADD COLUMN sefaz_ambiente TEXT DEFAULT '2'
    CHECK (sefaz_ambiente IN ('1', '2'));

COMMENT ON COLUMN tenants.sefaz_ambiente IS
  '1 = Produção, 2 = Homologação. Default homologação for safety.';
