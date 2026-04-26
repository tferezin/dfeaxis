-- ============================================================================
-- 024_lock_tenant_sensitive_fields.sql
-- ============================================================================
-- Bloqueia bypass de trial / billing / prod-access via PATCH direto na API
-- PostgREST. A policy original `tenant_update` (001_initial.sql:26-27) so
-- valida `USING (user_id = auth.uid())` — sem WITH CHECK, sem coluna-allowlist
-- — entao um cliente autenticado consegue fazer:
--
--   PATCH /rest/v1/tenants?id=eq.<own_id>
--     { "subscription_status":"active",
--       "trial_blocked_at": null,
--       "docs_consumidos_mes": 0,
--       "docs_included_mes": 999999,
--       "sefaz_ambiente": "1",
--       "prod_access_approved": true,
--       "trial_cap": 999999 }
--
-- ...e libera trial pra sempre + entra em prod sem aprovacao + zera contador
-- de overage. Bloqueador de seguranca pre-launch.
--
-- IMPLEMENTACAO: TRIGGER BEFORE UPDATE que compara OLD vs NEW e raise se
-- alguma coluna sensivel mudou. service_role bypassa (backend continua
-- escrevendo via supabase admin client). RLS da policy continua valendo
-- pra restringir QUAIS rows o cliente acessa — o trigger restringe QUAIS
-- COLUNAS pode mudar.
--
-- ATENCAO: aplicar manualmente no Supabase SQL Editor. Nao depende de codigo
-- backend — eh mudanca exclusiva de banco. Idempotente: usa CREATE OR REPLACE
-- + DROP TRIGGER IF EXISTS.
-- ============================================================================

-- 1. Funcao guardia. SECURITY DEFINER pra rodar com privilegios do owner
--    (necessario pra acessar auth.role() de forma confiavel). search_path
--    explicito previne hijack via search_path manipulation.
CREATE OR REPLACE FUNCTION protect_tenant_sensitive_fields()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  -- Backend (service_role) bypassa o trigger — webhooks Stripe, jobs de
  -- snapshot/overage, admin, RPC `debit_credits` etc precisam mexer nesses
  -- campos. Cliente JWT (`authenticated`) nao bypassa.
  IF auth.role() = 'service_role' THEN
    RETURN NEW;
  END IF;

  -- Owner tambem bypassa (migrations/manuten DBA). Em Supabase isso so
  -- vale via SQL Editor / connection direta — nao via PostgREST.
  IF auth.role() IN ('postgres', 'supabase_admin') THEN
    RETURN NEW;
  END IF;

  -- ---------------- Subscription / cobranca (Stripe) ----------------
  IF NEW.subscription_status IS DISTINCT FROM OLD.subscription_status THEN
    RAISE EXCEPTION 'subscription_status is read-only via REST (backend only)';
  END IF;
  IF NEW.stripe_customer_id IS DISTINCT FROM OLD.stripe_customer_id THEN
    RAISE EXCEPTION 'stripe_customer_id is read-only via REST (backend only)';
  END IF;
  IF NEW.stripe_subscription_id IS DISTINCT FROM OLD.stripe_subscription_id THEN
    RAISE EXCEPTION 'stripe_subscription_id is read-only via REST (backend only)';
  END IF;
  IF NEW.stripe_price_id IS DISTINCT FROM OLD.stripe_price_id THEN
    RAISE EXCEPTION 'stripe_price_id is read-only via REST (backend only)';
  END IF;
  IF NEW.current_period_end IS DISTINCT FROM OLD.current_period_end THEN
    RAISE EXCEPTION 'current_period_end is read-only via REST (backend only)';
  END IF;
  IF NEW.cancel_at_period_end IS DISTINCT FROM OLD.cancel_at_period_end THEN
    RAISE EXCEPTION 'cancel_at_period_end is read-only via REST (backend only)';
  END IF;
  IF NEW.past_due_since IS DISTINCT FROM OLD.past_due_since THEN
    RAISE EXCEPTION 'past_due_since is read-only via REST (backend only)';
  END IF;

  -- ---------------- Trial ----------------
  IF NEW.trial_active IS DISTINCT FROM OLD.trial_active THEN
    RAISE EXCEPTION 'trial_active is read-only via REST (backend only)';
  END IF;
  IF NEW.trial_blocked_at IS DISTINCT FROM OLD.trial_blocked_at THEN
    RAISE EXCEPTION 'trial_blocked_at is read-only via REST (backend only)';
  END IF;
  IF NEW.trial_blocked_reason IS DISTINCT FROM OLD.trial_blocked_reason THEN
    RAISE EXCEPTION 'trial_blocked_reason is read-only via REST (backend only)';
  END IF;
  IF NEW.trial_expires_at IS DISTINCT FROM OLD.trial_expires_at THEN
    RAISE EXCEPTION 'trial_expires_at is read-only via REST (backend only)';
  END IF;
  IF NEW.trial_cap IS DISTINCT FROM OLD.trial_cap THEN
    RAISE EXCEPTION 'trial_cap is read-only via REST (backend only)';
  END IF;
  IF NEW.docs_consumidos_trial IS DISTINCT FROM OLD.docs_consumidos_trial THEN
    RAISE EXCEPTION 'docs_consumidos_trial is read-only via REST (backend only)';
  END IF;

  -- ---------------- Consumo / contadores mensais ----------------
  IF NEW.docs_consumidos_mes IS DISTINCT FROM OLD.docs_consumidos_mes THEN
    RAISE EXCEPTION 'docs_consumidos_mes is read-only via REST (backend only)';
  END IF;
  IF NEW.docs_included_mes IS DISTINCT FROM OLD.docs_included_mes THEN
    RAISE EXCEPTION 'docs_included_mes is read-only via REST (backend only)';
  END IF;
  IF NEW.billing_day IS DISTINCT FROM OLD.billing_day THEN
    RAISE EXCEPTION 'billing_day is read-only via REST (backend only)';
  END IF;
  IF NEW.ciclo_mes_inicio IS DISTINCT FROM OLD.ciclo_mes_inicio THEN
    RAISE EXCEPTION 'ciclo_mes_inicio is read-only via REST (backend only)';
  END IF;

  -- ---------------- Plano / limites ----------------
  IF NEW.max_cnpjs IS DISTINCT FROM OLD.max_cnpjs THEN
    RAISE EXCEPTION 'max_cnpjs is read-only via REST (backend only)';
  END IF;
  IF NEW.plan IS DISTINCT FROM OLD.plan THEN
    RAISE EXCEPTION 'plan is read-only via REST (backend only)';
  END IF;

  -- ---------------- Ambiente SEFAZ ----------------
  -- sefaz_ambiente='1' (producao) so pode ser setado pelo backend apos
  -- aprovacao manual (admin). Cliente editar via REST viola gate de prod.
  IF NEW.sefaz_ambiente IS DISTINCT FROM OLD.sefaz_ambiente THEN
    RAISE EXCEPTION 'sefaz_ambiente is read-only via REST (backend only)';
  END IF;
  IF NEW.prod_access_approved IS DISTINCT FROM OLD.prod_access_approved THEN
    RAISE EXCEPTION 'prod_access_approved is read-only via REST (backend only)';
  END IF;
  -- prod_access_allowed e coluna gerada / view? Tratar so se existir:
  -- IF NEW.prod_access_allowed IS DISTINCT FROM OLD.prod_access_allowed THEN
  --   RAISE EXCEPTION 'prod_access_allowed is read-only via REST (backend only)';
  -- END IF;
  -- (descomente se a coluna existir; senao mantem comentado)

  -- ---------------- FK / PK ----------------
  IF NEW.id IS DISTINCT FROM OLD.id THEN
    RAISE EXCEPTION 'id (PK) cannot be changed';
  END IF;
  IF NEW.user_id IS DISTINCT FROM OLD.user_id THEN
    RAISE EXCEPTION 'user_id is read-only via REST (backend only)';
  END IF;

  -- ---------------- Credits legacy (defesa em profundidade) ----------------
  -- Coluna `credits` ainda existe (legado MercadoPago). Cliente nao deve
  -- conseguir setar. Backend usa RPC `debit_credits` (security definer).
  IF NEW.credits IS DISTINCT FROM OLD.credits THEN
    RAISE EXCEPTION 'credits is read-only via REST (backend RPC only)';
  END IF;

  RETURN NEW;
END;
$$;

COMMENT ON FUNCTION protect_tenant_sensitive_fields() IS
  'Trigger guard que impede clientes JWT (authenticated) de sobreescrever '
  'colunas sensiveis de tenants via PostgREST. Backend (service_role) '
  'bypassa. Veja 024_lock_tenant_sensitive_fields.sql.';

-- 2. Trigger BEFORE UPDATE — substitui qualquer trigger anterior
DROP TRIGGER IF EXISTS trg_protect_tenant_sensitive ON tenants;
CREATE TRIGGER trg_protect_tenant_sensitive
  BEFORE UPDATE ON tenants
  FOR EACH ROW
  EXECUTE FUNCTION protect_tenant_sensitive_fields();

-- 3. Sanity: a policy `tenant_update` original CONTINUA valendo pra restringir
--    QUAIS linhas o user pode tocar (user_id = auth.uid()). O trigger acrescenta
--    a camada de coluna-allowlist. Nao precisamos drop+recriar a policy — eh
--    mudanca aditiva.
--
--    Aceitos pra cliente JWT: company_name, email, phone, cnpj, polling_mode,
--    polling_interval_min, ga_client_id, billing_day_preference, configs UI.
--    (qualquer coluna NAO listada acima passa por NEW.* IS DISTINCT FROM
--    OLD.* sem RAISE — vai escrever normal).
