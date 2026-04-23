# Checklist: atualizar plano/preço

**Quando atualizar valores, quantidade de docs inclusos, criar plano novo ou descontinuar existente, mexer nos DOIS lados — Stripe e SaaS. Se esquecer um dos lados, o dashboard mostra valor errado ou cobrança sai fora do esperado.**

Source of truth técnica é o Stripe (o webhook propaga pro Supabase via `docs_included_mes`, `stripe_price_id`, etc.). Mas o SaaS precisa conhecer o catálogo por `stripe_plans.json` pra validar preços no checkout, mapear `price_id → docs_included` e calcular overage. Por isso **sempre os dois**.

---

## Passo a passo quando mudar um plano existente (ex: Business de 8000 → 10000 docs)

### 1. Stripe Dashboard

- [ ] Criar um **novo price** no produto correspondente (NÃO edite o price antigo — Stripe não permite alterar preço depois de criado; você cria um novo e desativa o antigo)
- [ ] Anotar o novo `price_id` (ex: `price_1TXYZ...`)
- [ ] Desativar o price antigo (archive) pra evitar novas assinaturas no valor velho
- [ ] Assinaturas ativas no price antigo **continuam rodando** — migrar manualmente se quiser padronizar

### 2. SaaS — arquivo `backend/data/stripe_plans.json`

- [ ] Atualizar `docs_included` do plano correspondente
- [ ] Atualizar `price_id` (mensal) e `price_id_yearly` (anual) pros novos IDs do Stripe
- [ ] Atualizar `monthly_amount_cents` e `yearly_amount_cents` se o preço mudou
- [ ] Atualizar `overage_cents_per_doc` se a regra de excedente mudou
- [ ] Commit + deploy

### 3. Landing / marketing

- [ ] `frontend/public/landing-v4.html` — tabela comparativa de planos (bloco pricing)
- [ ] `frontend/public/llms.txt` — descrição pra crawlers
- [ ] `backend/prompts/landing_bot.md` — chatbot de vendas conhece o catálogo
- [ ] `backend/prompts/dashboard_bot.md` — chatbot do dashboard também
- [ ] `docs/google-ads-campaign-v1.md` — textos de anúncio

### 4. Tenants que já estão no plano antigo

- [ ] Decidir política: migração automática (Stripe `subscription.update` em massa), grandfather no valor antigo, ou aviso de mudança com prazo
- [ ] Se for migração: atualizar via script um a um — NUNCA em loop sem pausa (rate limit Stripe)
- [ ] Se for grandfather: atualizar `stripe_plans.json` sem deletar os `price_id`s antigos; eles ficam referenciáveis pelos `stripe_price_id` salvos em `tenants`

### 5. Validação pós-deploy

- [ ] Criar tenant de teste (trial → checkout → pagamento)
- [ ] Conferir que `docs_included_mes` no Supabase bate com o novo valor
- [ ] Conferir que dashboard mostra o novo limite no card "Uso do mês"
- [ ] Conferir que `GET /api/v1/alerts` não dispara `high_usage` falso
- [ ] Se mudou overage: simular consumo > incluído e verificar job mensal (`scheduler/monthly_overage_job.py`)

---

## Se o dashboard mostrar "Sincronizando com Stripe..."

Sinaliza que `docs_included_mes` está 0 ou null no Supabase **mesmo com subscription ativa**. Causas mais comuns:

1. Webhook do Stripe não processou o `customer.subscription.created/updated` — checar logs de `backend/services/billing/webhooks.py`
2. Migration `010_monthly_billing.sql` não rodou em produção (o campo nem existe)
3. `price_id` do tenant não está no `stripe_plans.json` — o webhook não consegue mapear pro plano

**Fluxo de diagnóstico:**

```sql
-- 1. Ver o tenant
select id, email, plan, subscription_status, stripe_price_id,
       docs_included_mes, docs_consumidos_mes
from tenants where email = 'cliente@exemplo.com';

-- 2. Se stripe_price_id existe mas docs_included_mes=0:
--    confere stripe_plans.json — o price_id tá no catálogo?

-- 3. Se nada disso: recebeu o webhook?
select * from stripe_webhook_events
where tenant_id = '...' order by created_at desc limit 5;
```

**Resolução rápida (emergência):** atualizar manualmente no Supabase com o valor correto do plano. Mas isso é paliativo — o webhook precisa ser consertado pra próxima renovação não quebrar.

---

## Por que NÃO tem fallback de PLAN_DEFAULTS no frontend

Antes `use-monthly-usage.ts` tinha:
```ts
const PLAN_DEFAULTS = { starter: 3000, business: 8000, enterprise: 20000 }
```

Problema: se um dia você subir Business pra 10000 no Stripe mas esquecer do `stripe_plans.json` ou do webhook falhar, o dashboard continua mostrando 8000 — cliente consome até 10000 sem alerta, você cobra overage sobre limite errado, ele reclama, você tem que devolver. Erro silencioso é pior que erro visível.

Solução: sem fallback. Se não sincronizou, banner amarelo **"Sincronizando com Stripe..."** no topo do dashboard. Usuário (ou você via admin) percebe de cara e resolve.
