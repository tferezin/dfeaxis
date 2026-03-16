-- 004_nfse.sql
-- Adiciona suporte a NFS-e (Nota Fiscal de Servico Eletronica) via ADN
-- Reforma Tributaria vigente desde 01/2026

-- Coluna para rastrear ultimo NSU de NFS-e no ADN
ALTER TABLE certificates
    ADD COLUMN IF NOT EXISTS last_nsu_nfse TEXT NOT NULL DEFAULT '000000000000000';

-- Campos especificos de NFS-e na tabela documents
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS codigo_municipio TEXT,
    ADD COLUMN IF NOT EXISTS codigo_servico TEXT;

-- Indice para consultas NFS-e por municipio
CREATE INDEX IF NOT EXISTS idx_documents_nfse_municipio
    ON documents (tenant_id, tipo, codigo_municipio)
    WHERE tipo = 'NFSE';

-- Comentarios
COMMENT ON COLUMN certificates.last_nsu_nfse IS 'Ultimo NSU processado no Ambiente Nacional de NFS-e (ADN)';
COMMENT ON COLUMN documents.codigo_municipio IS 'Codigo IBGE do municipio (NFS-e)';
COMMENT ON COLUMN documents.codigo_servico IS 'Codigo do servico LC 116 (NFS-e)';
