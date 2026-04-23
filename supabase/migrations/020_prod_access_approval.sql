-- Migration 020: allowlist de tenants autorizados a operar em SEFAZ produção
--
-- Contexto: durante soft launch (primeiros clientes reais chegando via
-- campanha Ads), não queremos que qualquer cliente novo consiga virar
-- `sefaz_ambiente='1'` sem nossa aprovação. Isso protege de:
--   - cliente que sobe o pfx errado (ex: cert homolog) e tenta prod
--   - cliente que não passou pelo onboarding técnico conosco
--   - aumento descontrolado de chamadas SEFAZ antes de a gente validar
--     o comportamento do scheduler adaptativo em produção real
--
-- Modelo aplicado: **flag global + allowlist por tenant** (Opção B).
-- O endpoint PATCH /tenants/settings permite sefaz_ambiente='1' apenas
-- quando uma das duas condições é verdadeira:
--   1) env var PROD_ACCESS_ALLOWED='true' no Railway (liga pra todos)
--   2) tenants.prod_access_approved=true (libera tenant específico)
--
-- Quando amadurecer e quisermos liberar pra todos sem gestão manual,
-- basta setar PROD_ACCESS_ALLOWED=true no Railway (sem deploy).

ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS prod_access_approved BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN tenants.prod_access_approved IS
  'Allowlist: true = tenant liberado pra sefaz_ambiente=1 individualmente. '
  'Default false — override apenas via SQL explícito. '
  'Complementa env var PROD_ACCESS_ALLOWED (flag global).';

-- Não backfilla ninguém como true — durante soft launch, ninguém está
-- pré-aprovado. Quando o primeiro cliente real chegar e você validar
-- que tá tudo ok pra ele, roda:
--
--   UPDATE tenants SET prod_access_approved = true WHERE id = '<id>';
