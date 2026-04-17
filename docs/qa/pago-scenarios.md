# Plano Pago + Overage — Cenários E2E P01-P06

Mapeamento dos cenários E2E que o agente da Fase 3.2 vai implementar em `backend/tests/scenarios/pago/`. Baseado em `docs/qa-scenarios.md` seção 9 (FINANCEIRO / BILLING / STRIPE).

Cobre o ciclo completo de um cliente pagante: checkout inicial → ativação → renovação mensal → upgrade → overage (estouro de limite) → portal de billing.

Todos os cenários usam os fakes existentes (`fakes/stripe_fake.py`, `fakes/sap_client.py`) e as fixtures de `conftest.py`.

## P01 — Checkout session criada com plano válido

- **Origem**: 9.2
- **Setup**: tenant em trial, autenticado via JWT
- **Ação**: POST `/api/v1/billing/checkout` com `price_id` do Starter
- **Asserts**: 200, response contém `checkout_url` válido do Stripe (formato `https://checkout.stripe.com/...`), `fake_stripe` registrou criação de Session com `mode=subscription`, `customer_email=tenant.email`, `success_url` e `cancel_url` apontando pro domínio do app
- **Bug que pega**: rota não passando metadados corretos pra Stripe (tenant_id, price_id errado), checkout quebrado por env var faltando

## P02 — Webhook `checkout.session.completed` ativa subscription

- **Origem**: 9.4 + 9.5
- **Setup**: tenant em trial, `fake_stripe` preparado com Session pendente
- **Ação**: POST `/api/v1/billing/webhook` payload `checkout.session.completed` assinado
- **Asserts**: 200, tenant pós-evento tem `subscription_status='active'`, `trial_active=false`, `stripe_customer_id` populado, `stripe_subscription_id` populado, `plan_id` correto (starter/business/enterprise), `docs_included_mes` setado conforme plano, `/polling/trigger` retorna 200
- **Bug que pega**: webhook não persistindo plano, não liberando tenant, não setando limites mensais

## P03 — Renewal mensal reseta contador de docs

- **Origem**: 9.7
- **Setup**: tenant active, `docs_consumidos_mes=2800` (perto do limite Starter 3000), `billing_period_end < now`
- **Ação**: POST `/api/v1/billing/webhook` payload `invoice.paid` (renewal)
- **Asserts**: 200, tenant pós-evento tem `docs_consumidos_mes=0`, `billing_period_end` avançou pra +30d, `subscription_status` continua `active`, próximo `/polling/trigger` retorna 200
- **Bug que pega**: renewal não zerando contador (cliente ficaria bloqueado indevidamente no mês 2), `billing_period_end` não avançando

## P04 — Upgrade de plano atualiza limites

- **Origem**: 9.10
- **Setup**: tenant no plano Starter (`docs_included_mes=3000`, `max_cnpjs=1`)
- **Ação**: POST `/api/v1/billing/webhook` payload `customer.subscription.updated` trocando pra Business
- **Asserts**: 200, tenant pós-evento tem `plan_id='business'`, `docs_included_mes=20000`, `max_cnpjs=5` (ou valor real do plano Business conforme `config`), `subscription_status='active'`
- **Bug que pega**: upgrade webhook não propagando novos limites (cliente pagaria mais mas ficaria com limites do plano antigo)

## P05 — Overage: estouro do cap mensal é medido e registrado

- **Origem**: 9.11
- **Setup**: tenant active Starter, `docs_consumidos_mes=3001` (1 doc acima do limite 3000)
- **Ação**: inspecionar estado via `monthly_overage_job` (chamada direta da função que calcula overage) OU via endpoint interno se existir
- **Asserts**: função retorna `overage_docs=1`, `overage_cost` calculado conforme precificação (ex: R$0,10/doc extra), registro criado em tabela `monthly_overages` ou campo `current_month_overage` do tenant
- **Bug que pega**: overage não sendo calculado/registrado (cliente usa mais do que paga sem cobrança extra)

## P06 — Billing portal session criada

- **Origem**: 9.6
- **Setup**: tenant active com `stripe_customer_id`
- **Ação**: POST `/api/v1/billing/portal`
- **Asserts**: 200, response contém `portal_url` válido (`https://billing.stripe.com/...`), `fake_stripe` registrou criação de billingPortal.Session com `customer=tenant.stripe_customer_id` e `return_url` apontando pro app
- **Bug que pega**: portal quebrado pra cliente cancelar/trocar cartão/upgradeable (impacto alto em retenção)

---

## Notas de implementação

- Os webhooks Stripe são assinados — use o helper do `fake_stripe` que gera assinatura válida com o secret de teste, ou `app.dependency_overrides` do verificador de assinatura se necessário.
- Para asserts de estado pós-webhook, leia o tenant via REST Supabase direto (mesmo padrão de `test_trial_e2e.py`).
- Endpoints reais: `/api/v1/billing/checkout`, `/api/v1/billing/webhook`, `/api/v1/billing/portal` (prefixo `/api/v1` vem de `main.py`, path de `routers/billing.py`).
- P05 pode não ter endpoint HTTP — se o cálculo de overage roda só em job scheduled, chame a função Python diretamente (`monthly_overage_job`) com mocks no Supabase.
