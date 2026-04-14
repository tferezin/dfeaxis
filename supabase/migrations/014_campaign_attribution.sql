-- DFeAxis: Campaign attribution tracking
-- Guarda os parâmetros UTM + click IDs capturados na primeira página visitada
-- pelo usuário (ou na última com UTM, last-touch). Usado para atribuir
-- conversões a canais/grupos/keywords específicos no dashboard interno,
-- sem depender exclusivamente do painel do Google Analytics.
--
-- Fontes dos valores:
--   - utm_source, utm_medium, utm_campaign, utm_term, utm_content: query
--     string das URLs dos anúncios (ex: ?utm_source=google&utm_medium=cpc&
--     utm_campaign=sap_drc)
--   - gclid: Google Click ID adicionado automaticamente pelo auto-tagging
--     do Google Ads (permite match exato com cliques no painel do Ads)
--   - fbclid: Facebook Click ID (futuro, se rodar Meta Ads)
--   - referrer: document.referrer no momento da captura (pra distinguir
--     tráfego orgânico, direto, redes sociais, etc.)
--   - landing_path: pathname da primeira página onde o usuário caiu
--     (ex: /, /signup?plan=starter, /#pricing)

ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS utm_source TEXT,
  ADD COLUMN IF NOT EXISTS utm_medium TEXT,
  ADD COLUMN IF NOT EXISTS utm_campaign TEXT,
  ADD COLUMN IF NOT EXISTS utm_term TEXT,
  ADD COLUMN IF NOT EXISTS utm_content TEXT,
  ADD COLUMN IF NOT EXISTS gclid TEXT,
  ADD COLUMN IF NOT EXISTS fbclid TEXT,
  ADD COLUMN IF NOT EXISTS referrer TEXT,
  ADD COLUMN IF NOT EXISTS landing_path TEXT;

-- Index nos campos mais consultados em relatórios de ROAS:
-- "quantos tenants vieram do grupo X?" e "quantos do canal google cpc?"
CREATE INDEX IF NOT EXISTS idx_tenants_utm_campaign
  ON tenants (utm_campaign) WHERE utm_campaign IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tenants_utm_source_medium
  ON tenants (utm_source, utm_medium) WHERE utm_source IS NOT NULL;

COMMENT ON COLUMN tenants.utm_source IS 'UTM source (google, meta, direct, organic) — last-touch na hora do signup';
COMMENT ON COLUMN tenants.utm_medium IS 'UTM medium (cpc, email, social, organic) — last-touch na hora do signup';
COMMENT ON COLUMN tenants.utm_campaign IS 'UTM campaign (nome do grupo de anúncios Google Ads)';
COMMENT ON COLUMN tenants.utm_term IS 'UTM term (keyword que disparou o clique, opcional)';
COMMENT ON COLUMN tenants.utm_content IS 'UTM content (variante de anúncio, opcional)';
COMMENT ON COLUMN tenants.gclid IS 'Google Click ID — permite join direto com relatórios do Google Ads';
COMMENT ON COLUMN tenants.fbclid IS 'Facebook Click ID — futuro, se rodar Meta Ads';
COMMENT ON COLUMN tenants.referrer IS 'document.referrer no momento da captura (first-touch)';
COMMENT ON COLUMN tenants.landing_path IS 'Path da primeira página visitada antes do signup';
