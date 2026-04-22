-- DFeAxis: Chat leads (landing page lead capture)
-- Coleta email/nome/empresa/telefone antes do chat da landing começar,
-- pra alimentar funil de prospecção. Bloqueia domínios públicos (gmail etc).

CREATE TABLE chat_leads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Conversa associada (criada no mesmo POST que grava o lead)
  conversation_id UUID REFERENCES chat_conversations(id) ON DELETE CASCADE,

  -- Dados do lead
  email TEXT NOT NULL,
  email_domain TEXT NOT NULL,  -- Extraído de email (lower), pra agregação
  nome TEXT NOT NULL,
  empresa TEXT NOT NULL,
  telefone TEXT,
  cargo TEXT,  -- Opcional

  -- Contexto anônimo
  session_id TEXT,
  ip_hash TEXT,
  user_agent TEXT,
  page_url TEXT,

  -- Atribuição (UTM + click IDs capturados no localStorage do browser)
  utm_data JSONB DEFAULT '{}'::jsonb,

  -- Flag informativo: se o domínio bater com lista de email público conhecido
  -- (mesmo que o endpoint bloqueie antes, guardamos o flag pra referência)
  is_public_domain BOOLEAN DEFAULT false,

  created_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE chat_leads IS
  'Leads coletados no início do chat da landing (anônimo). Bloqueia emails públicos no endpoint.';

CREATE INDEX idx_chat_leads_created ON chat_leads(created_at DESC);
CREATE INDEX idx_chat_leads_email ON chat_leads(lower(email));
CREATE INDEX idx_chat_leads_domain ON chat_leads(email_domain);
CREATE INDEX idx_chat_leads_conversation ON chat_leads(conversation_id)
  WHERE conversation_id IS NOT NULL;

-- RLS: só service_role acessa. Endpoint é anônimo (sem auth.uid())
-- então não faz sentido permitir SELECT via anon.
ALTER TABLE chat_leads ENABLE ROW LEVEL SECURITY;

-- Admin futura (quando tiver tela de leads no /admin) vai ler via service_role.
-- Nenhuma policy permissiva pra anon/authenticated.
