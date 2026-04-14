# DFeAxis — Cenários de QA end-to-end

Matriz completa de cenários que um cliente real vai experimentar. Cada linha descreve
uma **jornada fim-a-fim** (entrada → passos → retorno esperado → validação).

**Status**:
- 🟢 Coberto por teste automatizado (Playwright ou pytest)
- 🟡 Parcialmente coberto (alguns passos, não tudo)
- 🔴 NÃO coberto — precisa de teste novo
- ⚪ Requer QA manual (não dá pra automatizar: cert real, SEFAZ real, time travel)

**Última atualização**: 2026-04-14

---

## 1. CADASTRO & ONBOARDING

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 1.1 | Novo usuário acessa landing sem UTM | GET `/` | Landing renderiza, gtag dispara `page_view`, cookie `_ga` é setado | 🟢 | `ga-cookie-real-gtag.spec.ts` |
| 1.2 | Usuário vem de anúncio Google com UTM | GET `/?utm_source=google&utm_campaign=sap_drc&gclid=...` | UTMs gravados em localStorage, persistem até signup | 🟢 | `attribution-capture.spec.ts` |
| 1.3 | Usuário clica "Criar conta grátis" na landing | Click CTA → navega pra `/signup` | Form de signup renderiza com todos os campos (nome, telefone, email, senha) | 🟢 | `signup.spec.ts` |
| 1.4 | Usuário tenta submeter form vazio | Click "Criar conta" | Botão desabilitado enquanto campos inválidos | 🟢 | `signup.spec.ts` |
| 1.5 | Telefone com formato inválido | Digita "123" no telefone, blur | Botão fica desabilitado, mensagem de erro | 🟢 | `signup.spec.ts` |
| 1.6 | Máscara de telefone mobile (11 dígitos) | Digita "11987654321" | Formata pra "(11) 98765-4321" | 🟢 | `signup.spec.ts` |
| 1.7 | Máscara de telefone fixo (10 dígitos) | Digita "1133334444" | Formata pra "(11) 3333-4444" | 🟢 | `signup.spec.ts` |
| 1.8 | Form válido preenchido | Preenche tudo certo | Botão "Criar conta" habilita | 🟢 | `signup.spec.ts` |
| 1.9 | Submete signup válido, email confirmation enabled | Click Criar conta | Supabase cria user, dispara evento `sign_up` no GA4, mostra "Conta criada! Verifique seu e-mail" | 🟡 | manual — precisa Supabase real |
| 1.10 | Submete signup válido, sessão imediata | (Supabase sem email confirm) | Cria tenant no backend, redireciona pra `/dashboard`, envia `ga_client_id` + UTMs no body | 🟡 | `ga-client-id-capture.spec.ts` + `attribution-capture.spec.ts` (isoladamente) |
| 1.11 | Usuário tenta criar 2 tenants com mesmo CNPJ | POST /tenants com CNPJ duplicado | 409 Conflict — anti-abuse bloqueia | 🟢 | `trial-flow.spec.ts:176` |
| 1.12 | User clica email confirmation link, volta ao login | Click link no email | Supabase valida, cria sessão, redireciona pra /dashboard | ⚪ | manual — fluxo de email |
| 1.13 | Primeiro login após confirmação | /login com cred válida | Dashboard carrega, banner de trial countdown aparece | 🟢 | `trial-flow.spec.ts:44` |

## 2. DASHBOARD & NAVEGAÇÃO INICIAL

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 2.1 | Fresh trial, dashboard carrega pela primeira vez | GET /dashboard | Counter 0/500 docs, "10 dias restantes", cards de stats zerados | 🟢 | `trial-flow.spec.ts:53` |
| 2.2 | Dashboard mostra gráfico de volume | GET /dashboard | VolumeChart renderiza (ainda sem dados) | 🟡 | navegação coberta, conteúdo não |
| 2.3 | Dashboard mostra trial counter | GET /dashboard | `<TrialCounter />` renderiza com dias restantes correto | 🟢 | `trial-flow.spec.ts:47` |
| 2.4 | Dashboard lista "Documentos recentes" | GET /dashboard | Lista vazia ou com docs do tenant | 🟡 | coberto indiretamente (navegação) |
| 2.5 | Sidebar de navegação tem todos os links e renderizam sem crash | Navegar por todas as 13 rotas | Sem 404, sem redirect, zero console errors críticos | 🟢 | `dashboard-navigation.spec.ts` ✅ |
| 2.6 | Usuário acessa `/getting-started` | Click link sidebar | Página renderiza com 4 passos + API docs + código ABAP | 🟢 | `dashboard-navigation.spec.ts` (rota incluída na lista) |

## 3. CERTIFICADO DIGITAL A1 (.pfx)

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 3.1 | Fresh user, zero certificados | GET /cadastros/certificados | Lista vazia, CTA "Fazer upload do primeiro" | 🟡 | rota coberta por `dashboard-navigation.spec.ts` |
| 3.2 | Upload de .pfx válido | POST /certificates/upload (file, cnpj, password) | 201 Created, CN extraído, valid_until populado, cert aparece na lista | 🔴 | — |
| 3.3 | Upload com senha errada | POST com password wrong | 400 Bad Request, toast de erro "senha inválida" | 🔴 | — |
| 3.4 | Upload de arquivo não-PFX | POST com .txt | 400 Bad Request, validation error | 🔴 | — |
| 3.5 | Upload com CNPJ não-batendo com CN do cert (anti-fraude) | POST com CNPJ "00.000.000/0000-00" pra cert de "12.345.678/0001-90" | 400 Bad Request, "CNPJ não confere com o certificado" | 🔴 | — |
| 3.6 | Upload de cert expirado | POST com .pfx que já expirou | Upload permitido mas warning "certificado expirado" | 🔴 | — |
| 3.7 | Upload com CNPJ já em uso globalmente (trial exclusivity) | POST com CNPJ que outro tenant já teve trial | 409 Conflict "1 CNPJ = 1 trial na vida" | ⚪ | manual — requer seed de conflito |
| 3.8 | Renovação de cert (upload segundo cert pro mesmo CNPJ) | POST + existing cert | Cert antigo desativado, novo vira ativo | 🔴 | — |
| 3.9 | Deleção de cert | DELETE /certificates/{id} | Confirmação modal → cert removido → polling futuro fica sem cert | 🔴 | — |

## 4. CAPTURA DE DOCUMENTOS (POLLING SEFAZ)

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 4.1 | Usuário sem cert tenta disparar captura | POST /polling/trigger | 400 "Nenhum certificado ativo pra este CNPJ" | 🔴 | — |
| 4.2 | Captura com cert válido, SEFAZ retorna 0 docs | POST /polling/trigger | 200 OK, `docs_found: 0`, mensagem "nenhum doc novo" | ⚪ | manual — requer SEFAZ real |
| 4.3 | Captura retorna N docs | POST /polling/trigger | 200 OK, docs inseridos em `documentos` table | ⚪ | manual — requer SEFAZ real |
| 4.4 | SEFAZ retorna erro 656 (rate limit) | POST /polling/trigger | Circuit breaker abre, 503, retry sugerido | ⚪ | manual OU mock |
| 4.5 | SEFAZ timeout (>30s) | POST /polling/trigger | Timeout gracioso, mensagem amigável, sem crash | ⚪ | mock |
| 4.6 | Trial cap atingido (500 docs) durante captura | POST /polling/trigger com docs_consumidos_trial=499 | Bloqueia captura quando passar 500, 402 Payment Required | 🟢 | `trial-flow.spec.ts:80` |
| 4.7 | Trial time expirado durante captura | POST /polling/trigger com trial_expires_at < now | 402 Payment Required | 🟢 | `trial-flow.spec.ts:111` |
| 4.8 | Dashboard mostra captura em progresso | Click "Captura" | Loader, polling async, resultado aparece | 🔴 | — |
| 4.9 | Polling automático (cron) dispara a cada X min | `backend/scheduler/polling_job.py` | Job roda, pega tenants com `polling_mode='auto'` | ⚪ | manual — requer scheduler running |

## 5. HISTÓRICO / CONSULTA DE DOCUMENTOS

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 5.1 | Usuário acessa `/historico/nfe` | GET /historico/nfe | Lista paginada de NF-e do tenant | 🔴 | — |
| 5.2 | Usuário acessa `/historico/cte` | GET /historico/cte | Lista de CT-e | 🔴 | — |
| 5.3 | Usuário acessa `/historico/mdfe` | GET /historico/mdfe | Lista de MDF-e | 🔴 | — |
| 5.4 | Usuário acessa `/historico/nfse` | GET /historico/nfse | Lista de NFS-e, com disclaimer ADN parcial | 🔴 | — |
| 5.5 | Busca por chave na lista | Filtra campo search | Lista filtra em tempo real | 🔴 | — |
| 5.6 | Abre XML de um doc | Click "Ver XML" | Modal abre com XML formatado | 🔴 | — |
| 5.7 | Paginação | Click "Próxima página" | Carrega próximas 50 linhas | 🔴 | — |

## 6. MANIFESTAÇÃO DO DESTINATÁRIO

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 6.1 | Dar ciência em 1 doc | Click "Dar Ciência" | Modal confirma → POST /manifestacao (210210) → doc marcado como manifestado | 🟢 | `manifestacao.spec.ts:single` |
| 6.2 | Ciência em lote | Seleciona múltiplos → "Dar ciência em lote" | POST /manifestacao/batch → todos marcados | 🟢 | `manifestacao.spec.ts:109` |
| 6.3 | SEFAZ retorna erro na manifestação | Click ciência, SEFAZ fora | Toast de erro, doc continua pendente | 🔴 | `manifestacao.spec.ts:176` **FALHANDO** |
| 6.4 | Manifestação auto (polling job) | `manifestacao_mode='auto_ciencia'` | Docs novos disparam ciência automaticamente | ⚪ | manual — requer job running |
| 6.5 | Histórico de manifestação | GET /manifestacao/historico | Lista de eventos enviados com filtro por data | 🔴 | — |
| 6.6 | Pendentes de manifestação | GET /manifestacao/pendentes | Lista de docs sem evento ainda | 🔴 | — |

## 7. API KEYS (integração externa)

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 7.1 | Usuário cria primeira API key | POST /api-keys com descrição | 201 Created, key `dfa_XXXXXX` mostrada UMA vez | 🔴 | — |
| 7.2 | Lista API keys existentes | GET /api-keys | Lista com prefix visível, chave hash não | 🔴 | — |
| 7.3 | Revogar API key | DELETE /api-keys/{id} | Confirmação → key invalidada | 🔴 | — |
| 7.4 | Consulta via API key válida | GET /documentos com header `X-API-Key` | 200 OK, docs retornados | 🔴 | — |
| 7.5 | Consulta via API key revogada | GET /documentos com key revogada | 401 Unauthorized | 🔴 | — |
| 7.6 | Cross-tenant leak attempt | API key tenant A tenta acessar CNPJ tenant B | 403 Forbidden (RLS) | 🔴 | — |
| 7.7 | Rate limit em criação de API keys | POST /api-keys 21x em 1 min | 429 Too Many Requests (limite 20/min) | 🔴 | — |

## 8. CONFIGURAÇÕES / SETTINGS

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 8.1 | Trocar polling_mode de manual pra auto | PATCH /tenants/settings `{polling_mode: "auto"}` | 200 OK, scheduler começa a rodar | 🔴 | — |
| 8.2 | Trocar manifestacao_mode | PATCH /tenants/settings `{manifestacao_mode: "auto_ciencia"}` | 200 OK, próximos docs são manifestados automaticamente | 🔴 | — |
| 8.3 | Trocar ambiente homolog → produção | PATCH com `sefaz_ambiente: "1"` | 200 OK, warning "cert produção necessário" | 🔴 | — |
| 8.4 | Notificações por email | Toggle on/off | Settings salvas, emails disparam conforme config | 🔴 | — |

## 9. FINANCEIRO / BILLING / STRIPE

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 9.1 | Usuário acessa `/financeiro/creditos` no trial | GET /financeiro/creditos | Pricing table, 3 planos, botão "Assinar" em cada | 🔴 | — |
| 9.2 | Clica "Assinar" plano Starter | POST /billing/checkout `{price_id: starter}` | Redireciona pra Stripe checkout com session válida | 🟢 | `billing-checkout.spec.ts` |
| 9.3 | Paga com cartão 4242 no Stripe | Stripe UI | Stripe redireciona pra `/dashboard?checkout=success` | ⚪ | manual — Stripe checkout é externo |
| 9.4 | Webhook `checkout.session.completed` chega | Stripe POST /billing/webhook | Backend sincroniza subscription, libera tenant, dispara GA4 purchase | 🟢 | `test_ga4_mp.py:6` + `test_stripe_billing_e2e.py` |
| 9.5 | Subscription ativada → dashboard libera | Refresh /dashboard | Banner trial some, conta ativada, planos mostram "atual" | 🟢 | `trial-flow.spec.ts:144` |
| 9.6 | Usuário acessa `/billing/portal` | POST /billing/portal | Redireciona pra Stripe Customer Portal | 🔴 | — |
| 9.7 | Segundo mês de billing (renewal) | Stripe dispara `invoice.paid` | Tenant continua ativo, contador de docs do mês reseta | ⚪ | manual — requer time travel Stripe |
| 9.8 | Pagamento recorrente FALHA | Stripe dispara `invoice.payment_failed` | subscription_status → past_due → tenant bloqueado | ⚪ | manual — requer cartão que falha no sandbox |
| 9.9 | Usuário cancela subscription no portal | Portal UI → cancel | Stripe dispara `customer.subscription.deleted` → tenant volta pra trial (se ainda no período) ou bloqueia | 🔴 | — |
| 9.10 | Upgrade de plano (starter → business) | Portal UI → upgrade | Webhook `customer.subscription.updated` → max_cnpjs + docs_included atualizados | 🔴 | — |
| 9.11 | Usuário bate o docs_included do mês e cai em overage | Captura passa de 3000 | `docs_consumidos_mes > docs_included_mes` → overage billing via `monthly_overage_job.py` | ⚪ | manual — requer volume + time |

## 10. ZERO-RETENTION / LGPD

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 10.1 | Cliente consulta doc → confirma recebimento | POST /documentos/{chave}/confirmar | Doc marcado como confirmado, XML nullificado (mas metadata fica) | 🔴 | — |
| 10.2 | Doc não confirmado após X dias | Cleanup job | XML deletado por retenção | ⚪ | manual — requer scheduler |
| 10.3 | PFX inativo há 30 dias | `pfx_cleanup_job.py` | Cert marcado pra deleção, notificação enviada | 🟢 | `test_pfx_cleanup_e2e.py` |
| 10.4 | Audit log de acesso a doc | GET /documentos via API | Entry em `audit_log` com tenant_id, action, IP hash | 🔴 | — |

## 11. TRIAL TRANSITIONS (estados do funil)

| # | Cenário | Estado inicial | Trigger | Retorno | Status | Teste |
|---|---|---|---|---|---|---|
| 11.1 | Trial dia 1 | trial_active=true, docs=0 | GET /dashboard | Acesso total, counter visível | 🟢 | `trial-flow.spec.ts:44` |
| 11.2 | Trial dia 10 (último dia) | trial_active=true, 1 day left | GET /dashboard | Banner urgente "seu trial acaba hoje" | 🟡 | parcial, sem teste específico |
| 11.3 | Trial time expirado | trial_expires_at < now | POST /polling/trigger | 402, UI mostra overlay "trial expirado" | 🟢 | `trial-flow.spec.ts:111` |
| 11.4 | Trial cap atingido | docs_consumidos_trial=500 | POST /polling/trigger | 402, UI mostra overlay "500 docs atingidos" | 🟢 | `trial-flow.spec.ts:80` |
| 11.5 | Trial → active após pagamento | subscription_status: active | Webhook Stripe | trial_active=false, acesso restaurado | 🟢 | `trial-flow.spec.ts:144` |
| 11.6 | Active → past_due após falha | invoice.payment_failed | Stripe webhook | tenant bloqueado, UI "assinatura vencida" | 🔴 | — |
| 11.7 | Past_due → active após pagamento | invoice.paid | Stripe webhook | acesso restaurado | 🔴 | — |
| 11.8 | Cancelado (fim do período) | subscription.deleted | Stripe webhook | Volta pra trial (se ainda houver) ou acesso bloqueado | 🔴 | — |

## 12. ANALYTICS / TRACKING (o que a gente acabou de fazer)

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 12.1 | Cookie `_ga` setado pelo gtag real | GET `/signup` | Cookie format `GA1.1.X.Y` | 🟢 | `ga-cookie-real-gtag.spec.ts` |
| 12.2 | Helper `getGaClientId` extrai client_id | — | Format `X.Y` | 🟢 | `ga-client-id-capture.spec.ts` |
| 12.3 | Signup page envia ga_client_id no body | POST /tenants/register | Field presente ou null | 🟡 | covered por schema; UI test indireto |
| 12.4 | UTM captura completa | GET `/?utm_*=...` | localStorage com todos os campos | 🟢 | `attribution-capture.spec.ts` |
| 12.5 | UTM last-touch preserva em nav interna | Nav sem UTM | Atribuição anterior intacta | 🟢 | `attribution-capture.spec.ts` |
| 12.6 | UTM last-touch sobrescreve com novo | Nav com novo UTM | Substitui | 🟢 | `attribution-capture.spec.ts` |
| 12.7 | Tráfego direto (sem UTM) | GET `/signup` | localStorage vazio | 🟢 | `attribution-capture.spec.ts` |
| 12.8 | GA4 MP dispara purchase no webhook Stripe | `checkout.session.completed` | HTTP 204 do GA4, evento aparece em Tempo Real | 🟢 | `test_ga4_mp.py` + smoke test real |
| 12.9 | Google aceita payload do MP | Smoke test | HTTP 204 | 🟢 | `smoke_ga4_purchase.py` |

## 13. ADMIN / PRODUÇÃO (CRÍTICO pra GO-LIVE)

| # | Cenário | Passos | Retorno esperado | Status | Teste |
|---|---|---|---|---|---|
| 13.1 | Ambiente default = homologação (seguro) | Novo tenant | `sefaz_ambiente='2'` | 🟡 | schema confirma |
| 13.2 | Usuário troca pra produção | Settings → produção | Certificados revalidados, warning mostrado | 🔴 | — |
| 13.3 | Trocar pra prod com cert homolog | PATCH | Rejeitado ou warning | 🔴 | — |
| 13.4 | Monitor SEFAZ health | GET /sefaz/status | 200 OK com estado dos endpoints | 🔴 | — |
| 13.5 | Logs de captura acessíveis | GET /logs | Lista de eventos recentes | 🔴 | — |

---

## 📊 SUMÁRIO DE COBERTURA ATUAL

| Seção | Total | 🟢 | 🟡 | 🔴 | ⚪ |
|---|---|---|---|---|---|
| 1. Cadastro | 13 | 8 | 2 | 0 | 3 |
| 2. Dashboard | 6 | 3 | 1 | 2 | 0 |
| 3. Certificado | 9 | 0 | 0 | 8 | 1 |
| 4. Captura | 9 | 2 | 0 | 2 | 5 |
| 5. Histórico | 7 | 0 | 0 | 7 | 0 |
| 6. Manifestação | 6 | 2 | 0 | 3 | 1 |
| 7. API Keys | 7 | 0 | 0 | 7 | 0 |
| 8. Settings | 4 | 0 | 0 | 4 | 0 |
| 9. Billing | 11 | 3 | 0 | 4 | 4 |
| 10. LGPD | 4 | 1 | 0 | 2 | 1 |
| 11. Trial transitions | 8 | 4 | 1 | 3 | 0 |
| 12. Analytics | 9 | 8 | 1 | 0 | 0 |
| 13. Admin/Prod | 5 | 0 | 1 | 4 | 0 |
| **TOTAL** | **98** | **31** | **6** | **46** | **15** |

**Cobertura atual**: 32% (31/98) com teste verde automatizado, 6% parcial, **47% sem teste**, 15% só manual.

**Teste falhando (vermelho real)**: 1 — `manifestacao.spec.ts:176` — erro SEFAZ exibe toast

---

## 🎯 PRIORIZAÇÃO PRA GO-LIVE

### 🚨 Must-have antes de despausar campanha
1. **Corrigir `manifestacao.spec.ts:176`** (teste quebrado agora)
2. **Certificado**: upload válido/inválido/senha errada (3.2, 3.3, 3.4, 3.5) — é o primeiro passo do cliente após cadastro
3. **API Keys**: criar + revogar + consultar (7.1, 7.3, 7.4, 7.5) — é como a integração real funciona
4. **Histórico lista docs**: navegação básica funcionando (5.1, 5.2, 5.3, 5.4)
5. **Configurações**: troca polling mode + ambiente (8.1, 8.3)

### 🟡 Should-have logo após despausar
6. **Billing edge cases**: renewal, past_due, cancel (9.7, 9.8, 9.9)
7. **Trial transitions**: past_due → active (11.6, 11.7)
8. **Zero-retention**: confirmar doc + audit log (10.1, 10.4)
9. **Admin/Prod**: troca ambiente (13.2, 13.3)

### ⚪ QA manual (não tem como automatizar)
10. **SEFAZ real**: captura com cert real em homologação — você executa manualmente com um cert de teste
11. **Stripe time-travel**: virada de mês, falha de pagamento — você executa manualmente no dashboard do Stripe
12. **Polling job scheduler**: rodar em background e verificar logs
