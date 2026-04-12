-- DFeAxis: Prazo de manifestação (180 dias SEFAZ)
-- Adiciona campo para controlar deadline de manifestação definitiva em NF-e.

ALTER TABLE documents
  ADD COLUMN manifestacao_deadline TIMESTAMPTZ;

COMMENT ON COLUMN documents.manifestacao_deadline IS
  'Prazo limite para manifestação definitiva (180 dias após ciência). '
  'Só se aplica a NF-e com is_resumo=true. NULL para CT-e/MDF-e/NFS-e.';

-- Índice para o job de alertas: NF-e com ciência mas sem manifesto definitivo
CREATE INDEX idx_documents_manif_deadline
  ON documents(tenant_id, manifestacao_deadline)
  WHERE manifestacao_status = 'ciencia'
    AND manifestacao_deadline IS NOT NULL;
