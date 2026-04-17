-- DFeAxis: metadata extraído do XML de cada documento fiscal
--
-- Contexto: até agora a tabela `documents` só guardava `cnpj` = CNPJ do
-- CLIENTE (tenant) e `chave_acesso`, sem extrair quem emitiu o doc, qual
-- o valor, ou a data de emissão. Isso fazia com que a UI de "Documentos
-- Recentes" mostrasse o mesmo CNPJ do cliente em todas as linhas — sem
-- valor informativo — já que o cliente já sabe o próprio CNPJ.
--
-- Esta migração adiciona colunas pros 6 campos críticos que devem ser
-- extraídos do XML (quando disponível — resumos não têm xml_content
-- completo, então alguns campos ficam NULL pra eles).

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS cnpj_emitente TEXT,
  ADD COLUMN IF NOT EXISTS razao_social_emitente TEXT,
  ADD COLUMN IF NOT EXISTS cnpj_destinatario TEXT,
  ADD COLUMN IF NOT EXISTS numero_documento TEXT,
  ADD COLUMN IF NOT EXISTS data_emissao TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS valor_total NUMERIC(18, 2);

-- Índice para queries de fornecedor (dashboard "quanto gastei com o
-- fornecedor X este mês?")
CREATE INDEX IF NOT EXISTS idx_documents_cnpj_emitente
  ON documents (tenant_id, cnpj_emitente)
  WHERE cnpj_emitente IS NOT NULL;

-- Índice para queries de data de emissão (diferente de fetched_at)
CREATE INDEX IF NOT EXISTS idx_documents_data_emissao
  ON documents (tenant_id, data_emissao)
  WHERE data_emissao IS NOT NULL;

COMMENT ON COLUMN documents.cnpj_emitente IS 'CNPJ (14 dígitos) extraído de <emit><CNPJ> do XML. Quem EMITIU a nota (fornecedor, no caso de inbound). NULL pra resumos onde xml_content é null.';
COMMENT ON COLUMN documents.razao_social_emitente IS 'Razão social de <emit><xNome>. NULL pra resumos.';
COMMENT ON COLUMN documents.cnpj_destinatario IS 'CNPJ extraído de <dest><CNPJ>. Deve bater com o cnpj do tenant (o cliente). NULL pra MDFe (não tem destinatário único).';
COMMENT ON COLUMN documents.numero_documento IS 'Número humano do doc (nNF, nCT, nMDF). NULL pra resumos.';
COMMENT ON COLUMN documents.data_emissao IS 'Timestamp de <dhEmi>. Diferente de fetched_at (quando o DFeAxis capturou).';
COMMENT ON COLUMN documents.valor_total IS 'Valor total: vNF (NFe), vTPrest (CTe), vCarga (MDFe), ValorServicos (NFSe).';
