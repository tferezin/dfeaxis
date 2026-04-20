-- Queue for NFe resumos awaiting ciencia + XML fetch
CREATE TABLE IF NOT EXISTS nfe_ciencia_queue (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    certificate_id UUID NOT NULL REFERENCES certificates(id) ON DELETE CASCADE,
    cnpj TEXT NOT NULL,
    chave_acesso TEXT NOT NULL,
    nsu TEXT NOT NULL,
    -- Ciencia status
    ciencia_enviada BOOLEAN DEFAULT FALSE,
    ciencia_enviada_at TIMESTAMPTZ,
    ciencia_cstat TEXT,
    -- XML fetch status
    xml_fetched BOOLEAN DEFAULT FALSE,
    xml_fetched_at TIMESTAMPTZ,
    -- Control
    tentativas INTEGER DEFAULT 0,
    ultimo_erro TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    -- Unique per tenant+chave to avoid duplicates
    UNIQUE(tenant_id, chave_acesso)
);

CREATE INDEX idx_nfe_ciencia_queue_pending
    ON nfe_ciencia_queue(ciencia_enviada, xml_fetched)
    WHERE ciencia_enviada = FALSE OR xml_fetched = FALSE;

-- RLS
ALTER TABLE nfe_ciencia_queue ENABLE ROW LEVEL SECURITY;
