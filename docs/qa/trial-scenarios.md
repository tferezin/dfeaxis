# Trial Lifecycle — Cenários E2E T01-T10

Mapeamento dos cenários E2E que o agente da Fase 3.1 vai implementar em `backend/tests/scenarios/trial/`. Baseado em `docs/qa-scenarios.md` seção 11 (TRIAL TRANSITIONS) + 2 cenários de inicialização/recuperação que hoje não têm cobertura unitária.

Todos os cenários usam os fakes existentes: `fakes/sefaz_fake.py`, `fakes/stripe_fake.py`, `fakes/sap_client.py` e as fixtures de `conftest.py`.

## T01 — Signup cria trial em estado inicial correto

- **Origem**: extensão de 11.1 (sem equivalente isolado na doc)
- **Setup**: tenant recém-criado via fixture `tenant_test`
- **Ação**: inspecionar estado pós-signup
- **Asserts**: `trial_active=true`, `trial_expires_at ≈ now + 10d`, `docs_consumidos_trial=0`, `subscription_status` vazio/null, `sefaz_ambiente='2'` (homolog)
- **Bug que pega**: regressão no default do signup (trial sem prazo, ambiente prod por engano)

## T02 — Trial dia 1: acesso total + counter visível

- **Origem**: 11.1
- **Setup**: trial ativo, 0 docs consumidos
- **Ação**: GET `/dashboard` via TestSAPClient
- **Asserts**: 200, response contém counter de docs (`docs_consumidos_trial=0`, `docs_limite=500`, `dias_restantes≈10`)
- **Bug que pega**: dashboard bloqueando trial ativo por erro de guard

## T03 — Trial dia 10: banner urgente

- **Origem**: 11.2 (parcial na doc)
- **Setup**: trial ativo com `trial_expires_at = now + 1 dia`
- **Ação**: GET `/dashboard`
- **Asserts**: 200, response indica estado "última chance" (flag ou counter `dias_restantes=1`)
- **Bug que pega**: lógica de dias restantes errada na borda (off-by-one)

## T04 — Trial com tempo expirado bloqueia polling

- **Origem**: 11.3
- **Setup**: trial com `trial_expires_at < now`, `docs_consumidos_trial < 500`
- **Ação**: POST `/polling/trigger` via TestSAPClient
- **Asserts**: 402, SEFAZ fake NÃO foi chamado (zero calls registradas), response indica motivo "trial expirado"
- **Bug que pega**: polling ignorando expiração por tempo (capturaria pra trial vencido)

## T05 — Trial com cap atingido bloqueia polling

- **Origem**: 11.4
- **Setup**: trial ativo no prazo, `docs_consumidos_trial=500`
- **Ação**: POST `/polling/trigger`
- **Asserts**: 402, SEFAZ fake NÃO foi chamado, response indica motivo "cap atingido"
- **Bug que pega**: regressão no enforcement do cap de 500 docs

## T06 — Trial consome doc e incrementa counter

- **Origem**: extensão de 11.1/11.4 (fluxo feliz até o cap)
- **Setup**: trial ativo, `docs_consumidos_trial=499`, `fake_sefaz` seeded com 1 NFe
- **Ação**: POST `/polling/trigger`
- **Asserts**: 200, SEFAZ chamado 1x, `docs_consumidos_trial=500` após, próximo trigger retorna 402
- **Bug que pega**: counter não incrementando ou incrementando errado (double-count, race)

## T07 — Pagamento via webhook Stripe desbloqueia trial

- **Origem**: 11.5
- **Setup**: trial com cap atingido (502), `fake_stripe` com checkout session completed
- **Ação**: POST `/stripe/webhook` payload `checkout.session.completed`
- **Asserts**: 200, tenant pós-evento tem `trial_active=false`, `subscription_status='active'`, próximo `/polling/trigger` retorna 200
- **Bug que pega**: webhook não transicionando estado, usuário paga mas continua bloqueado

## T08 — Falha de pagamento transiciona active → past_due

- **Origem**: 11.6 (hoje 🔴 sem teste)
- **Setup**: tenant active (pós-pagamento), `fake_stripe` emite `invoice.payment_failed`
- **Ação**: POST `/stripe/webhook`
- **Asserts**: 200, tenant vira `subscription_status='past_due'`, `/polling/trigger` retorna 402 com motivo "assinatura vencida"
- **Bug que pega**: falha de cobrança não bloqueando acesso

## T09 — Past_due → active após retry bem-sucedido

- **Origem**: 11.7 (hoje 🔴 sem teste)
- **Setup**: tenant past_due
- **Ação**: webhook `invoice.paid`
- **Asserts**: 200, tenant volta pra `subscription_status='active'`, `/polling/trigger` 200
- **Bug que pega**: retry de cobrança não restaura acesso

## T10 — Cancelamento de assinatura bloqueia acesso

- **Origem**: 11.8 (hoje 🔴 sem teste)
- **Setup**: tenant active
- **Ação**: webhook `customer.subscription.deleted`
- **Asserts**: 200, tenant fica sem acesso (`trial_active=false` e `subscription_status='canceled'` ou equivalente), `/polling/trigger` retorna 402
- **Bug que pega**: cancelamento não revogando acesso
