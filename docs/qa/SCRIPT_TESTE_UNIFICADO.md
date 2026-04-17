# Script de Teste Unificado — DFeAxis

**Versão**: 1.0 (2026-04-16)
**Execução**: 5 agentes em paralelo, mesmo script, dados diferentes
**Duração estimada**: 40 minutos por agente

Cada agente simula um cliente completo (signup → trial → captura → manifestação → pagamento → uso pago → inadimplência → regularização → cancelamento).

---

## FASE 0 — SETUP (cada agente cria seu próprio tenant)

```
0.1  Criar auth user via Supabase Admin API (email: qa-agentN-<ts>@test.dfeaxis.com.br)
0.2  Criar tenant com prefixo qa- (CNPJ sintético 99*)
0.3  Criar certificado fake (pfx_encrypted deadbeef)
0.4  Criar API key → guardar raw_key pra testes SAP
0.5  Verificar: tenant.subscription_status == "trial"
0.6  Verificar: tenant.trial_active == true
0.7  Verificar: tenant.trial_cap == 500
0.8  Verificar: tenant.docs_consumidos_trial == 0
```

---

## FASE 1 — ENDPOINTS PÚBLICOS (sem auth)

```
1.1  GET /health → 200, body contém "status": "ok"
1.2  GET /api/v1/sefaz/status → 200, lista de endpoints SEFAZ
1.3  GET /api/v1/billing/plans → 200, array com 3 planos (starter, business, enterprise)
1.4  Verificar plano starter: monthly_amount_cents == 29000, docs_included == 3000
1.5  Verificar plano business: monthly_amount_cents == 69000, docs_included == 8000
1.6  Verificar plano enterprise: monthly_amount_cents == 149000, docs_included == 20000
1.7  Verificar yearly é -20% do monthly pra cada plano
1.8  GET /sap-drc/health → 200
1.9  POST /api/v1/chat/landing com mensagem "Olá" → 200, body tem "content"
```

---

## FASE 2 — AUTH E SEGURANÇA

```
2.1   GET /api/v1/documentos sem header → 401 API_KEY_MISSING
2.2   GET /api/v1/documentos com X-API-Key inválida → 401 API_KEY_INVALID
2.3   POST /api/v1/polling/trigger sem header → 401 AUTH_MISSING
2.4   GET /api/v1/tenants/me sem Bearer → 401 TOKEN_MISSING
2.5   GET /api/v1/tenants/me com Bearer inválido → 401 TOKEN_INVALID
2.6   POST /sap-drc/v1/retrieveInboundInvoices sem X-API-Key → 401
2.7   Rate limit: disparar 70 requests GET /api/v1/documentos em < 60s → 429
```

---

## FASE 3 — TRIAL LIFECYCLE

```
3.1   GET /api/v1/tenants/trial-status → trial_active=true, days_remaining > 0
3.2   GET /api/v1/tenants/me → subscription_status="trial", trial_cap=500
3.3   POST /api/v1/polling/trigger com CNPJ do cert → 200 (SEFAZ fake retorna docs)
3.4   Verificar: documents criados no banco com tenant_id correto
3.5   Verificar: NSU salvo em nsu_state (zero-padded 15 chars)
3.6   Verificar: polling_log registrado com status=success

--- Trial cap enforcement ---
3.7   Setar docs_consumidos_trial=499 via service role
3.8   Seed 10 docs na SEFAZ fake
3.9   POST /api/v1/polling/trigger → deve retornar (max 1 doc, depois parar)
3.10  Verificar: count(documents) == trial_cap (500)
3.11  Próximo POST /api/v1/polling/trigger → resultado "blocked", docs_found=0
3.12  SEFAZ fake NÃO deve ter recebido chamada no 3.11

--- Trial tempo expirado ---
3.13  Setar trial_expires_at = now - 1h via service role
3.14  POST /api/v1/polling/trigger → 402, code=TRIAL_EXPIRED
3.15  GET /api/v1/documentos → 402 (trial gate via API key)
3.16  POST /api/v1/documentos/{chave}/confirmar → 402

--- Paths isentos do trial gate ---
3.17  GET /api/v1/tenants/me → 200 (isento)
3.18  GET /api/v1/tenants/trial-status → 200 (isento)
3.19  GET /api/v1/billing/plans → 200 (público)
```

---

## FASE 4 — CAPTURA SEFAZ (fluxo completo com fake)

```
4.1   Restaurar trial ativo (trial_expires_at = now + 10d, blocked_at = null)
4.2   Seed 150 docs NFe na SEFAZ fake (3 batches de 50)
4.3   POST /api/v1/polling/trigger tipos=["nfe"] → 200
4.4   Verificar: docs_found >= 100 (múltiplos batches executados)
4.5   Verificar: NSU avançou corretamente (último NSU do batch final)
4.6   Verificar: nenhum evento SEFAZ (procEventoNFe) salvo como document
4.7   Verificar: documentos resumo (resNFe) tem manifestacao_status="pendente"
4.8   Verificar: documentos completos (procNFe) tem manifestacao_status="nao_aplicavel" ou null

--- Auto-ciência ---
4.9   Setar tenant.manifestacao_mode = "auto_ciencia"
4.10  Seed 5 docs NFe resumo na SEFAZ fake
4.11  POST /api/v1/polling/trigger tipos=["nfe"] → 200
4.12  Verificar: manifestacao_events com tipo_evento=210210, source=auto_capture
4.13  Verificar: documents atualizados com manifestacao_status="ciencia"
4.14  Verificar: manifestacao_deadline setado (now + 180 dias)

--- Multi-tipo ---
4.15  Seed docs CTe + MDFe na SEFAZ fake
4.16  POST /api/v1/polling/trigger tipos=["nfe","cte","mdfe"] → 200
4.17  Verificar: results array com 3 entries, um por tipo
4.18  Verificar: CTe e MDFe tem manifestacao_status="nao_aplicavel"

--- Erros SEFAZ ---
4.19  Forçar erro na SEFAZ fake (cstat=999)
4.20  POST /api/v1/polling/trigger → resultado com status=error
4.21  Verificar: polling_log com status=error, error_message preenchida
4.22  Circuit breaker: 3 erros seguidos → próxima chamada retorna "circuit open"

--- XML Parser ---
4.23  Verificar: metadata extraída corretamente (cnpj_emitente, razao_social, valor_total)
4.24  Verificar: DocumentMetadata.parse_errors vazio pra docs válidos
```

---

## FASE 5 — SAP DRC (integração completa)

```
--- Pull flow ---
5.1   POST /sap-drc/v1/retrieveInboundInvoices com [cnpj] → lista de NotaFiscalFragments
5.2   Verificar: fragments contêm uuid, accessKey, docType, xmlBase64
5.3   GET /sap-drc/v1/downloadOfficialDocument?uuid=<id> → XML completo em base64
5.4   Verificar: XML decodificado é válido e contém dados do documento
5.5   DELETE /sap-drc/v1/deleteOfficialDocument?uuid=<id> → 200
5.6   Verificar: documento marcado como delivered no banco
5.7   Verificar: docs_consumidos_trial incrementado (ou docs_consumidos_mes)

--- Push flow ---
5.8   POST /sap-drc/v1/receiveOfficialDocument com XML válido → 201
5.9   POST /sap-drc/v1/retrieveInboundInvoices → doc pushado aparece na lista
5.10  POST /sap-drc/v1/receiveOfficialDocument com mesmo XML → 409 (duplicado)
5.11  POST /sap-drc/v1/receiveOfficialDocument com XML malformado → 400

--- Batch delete ---
5.12  DELETE /sap-drc/v1/deleteInboundInvoices com [uuid1, uuid2, uuid3] → 200
5.13  Verificar: todos 3 marcados delivered
5.14  Verificar: counter incrementado por 3

--- Idempotência ---
5.15  DELETE /sap-drc/v1/deleteOfficialDocument com uuid já delivered → 204 (no-op)
5.16  Verificar: counter NÃO incrementado novamente

--- Bloqueio por inadimplência ---
5.17  Setar subscription_status=past_due, current_period_end=now-1h
5.18  POST /sap-drc/v1/retrieveInboundInvoices → 402 PAYMENT_OVERDUE
5.19  Verificar: body contém code/error_code parseable por SAP ABAP
```

---

## FASE 6 — MANIFESTAÇÃO

```
--- Ciência manual ---
6.1   POST /api/v1/manifestacao tipo_evento=210210, chave=<chave_nfe> → sucesso
6.2   Verificar: manifestacao_events com source=dashboard (se JWT) ou api (se API key)
6.3   Verificar: document.manifestacao_status=ciencia
6.4   Verificar: document.manifestacao_deadline setado

--- Confirmação ---
6.5   POST /api/v1/manifestacao tipo_evento=210200, chave=<chave> → sucesso
6.6   Verificar: document.manifestacao_status=confirmada
6.7   Verificar: manifestacao_deadline limpo (obrigação cumprida)

--- Desconhecimento ---
6.8   POST /api/v1/manifestacao tipo_evento=210220, chave=<outra_chave> → sucesso
6.9   Verificar: document.manifestacao_status=desconhecida

--- Não realizada + justificativa ---
6.10  POST /api/v1/manifestacao tipo_evento=210240, justificativa="Teste QA" → sucesso
6.11  POST /api/v1/manifestacao tipo_evento=210240, justificativa="" → 422 (min 15 chars)

--- Batch ---
6.12  POST /api/v1/manifestacao/batch com 3 chaves → resultado parcial
6.13  Verificar: response tem sucesso + erro contados corretamente

--- Consultas ---
6.14  GET /api/v1/manifestacao/pendentes → lista docs com manifestacao_status=pendente
6.15  GET /api/v1/manifestacao/historico → lista eventos com filtros
6.16  GET /api/v1/manifestacao/historico?tipo_evento=210200 → só confirmações

--- Duplicata ---
6.17  POST /api/v1/manifestacao tipo=210210 mesmo chave de novo → cStat 573 = sucesso
```

---

## FASE 7 — BILLING E PAGAMENTO

```
--- Checkout ---
7.1   POST /api/v1/billing/checkout com price_id=starter_monthly → 201 com session_id, url
7.2   Verificar: url começa com https://checkout.stripe
7.3   Verificar: Stripe session metadata contém tenant_id e billing_day

--- Webhook checkout.session.completed ---
7.4   Simular webhook checkout.session.completed via FakeStripe
7.5   Verificar: subscription_status=active
7.6   Verificar: trial_active=false, trial_blocked_at=null
7.7   Verificar: plan=starter, docs_included_mes=3000, max_cnpjs=1
7.8   Verificar: stripe_subscription_id e stripe_price_id setados

--- Webhook invoice.paid (renewal) ---
7.9   Setar docs_consumidos_mes=2800
7.10  Simular webhook invoice.paid
7.11  Verificar: docs_consumidos_mes=0 (Bug D fix)
7.12  Verificar: current_period_end avançado +30d

--- Webhook invoice.payment_failed ---
7.13  Simular webhook invoice.payment_failed (sub status=past_due)
7.14  Verificar: subscription_status=past_due
7.15  Com current_period_end no futuro → polling ainda funciona (grace period)
7.16  Com current_period_end no passado → polling retorna 402 PAYMENT_OVERDUE

--- Regularização ---
7.17  Simular webhook invoice.paid (sub volta a active)
7.18  Verificar: subscription_status=active, polling liberado

--- Upgrade ---
7.19  Simular webhook subscription.updated (starter→business)
7.20  Verificar: plan=business, docs_included_mes=8000, max_cnpjs=5

--- Cancelamento ---
7.21  Simular webhook subscription.deleted
7.22  Verificar: subscription_status=cancelled
7.23  POST /api/v1/polling/trigger → 402

--- Overage ---
7.24  Setar docs_consumidos_mes=3001 (1 acima do cap)
7.25  Chamar process_monthly_overage()
7.26  Verificar: monthly_overage_charges com excedente_docs=1
7.27  Verificar: Stripe InvoiceItem.create chamado com amount=12 (cents)
7.28  Verificar: docs_consumidos_mes resetado pra 0

--- Overage zero ---
7.29  Setar docs_consumidos_mes=100 (abaixo do cap)
7.30  Chamar process_monthly_overage()
7.31  Verificar: row com excedente_docs=0, sem InvoiceItem

--- Portal ---
7.32  POST /api/v1/billing/portal → 200 com url Stripe portal

--- Idempotência webhook ---
7.33  Enviar mesmo evento (mesmo event_id) duas vezes → segundo é "duplicate"
```

---

## FASE 8 — CONSULTA DE DOCUMENTOS

```
8.1   GET /api/v1/documentos?cnpj=<cnpj>&tipo=nfe → lista com docs capturados
8.2   Verificar: cada doc tem chave, tipo, nsu, xml_b64, fetched_at
8.3   Verificar: docs com status=available retornam XML
8.4   Verificar: docs com is_resumo=true retornam sem XML (base64 vazio)

--- Confirmação e limpeza ---
8.5   POST /api/v1/documentos/{chave}/confirmar → status=discarded
8.6   Verificar: doc.status mudou pra delivered
8.7   Verificar: xml_content removido (zero-retention)
8.8   Verificar: docs_consumidos_trial incrementado

--- Confirmar doc já confirmado ---
8.9   POST /api/v1/documentos/{mesma_chave}/confirmar → idempotente (não double-count)

--- Retroativo ---
8.10  POST /api/v1/documentos/retroativo com cnpj, tipo=nfe, datas → 200 job_id
8.11  GET /api/v1/documentos/retroativo/{job_id} → status processing ou completed
```

---

## FASE 9 — CADASTROS

```
--- Certificados ---
9.1   POST /api/v1/certificates/upload com .pfx fake → 201 com certificate_id
9.2   GET /api/v1/certificates → lista contém o cert recém-criado
9.3   DELETE /api/v1/certificates/{id} → 204
9.4   GET /api/v1/certificates → lista vazia

--- API Keys ---
9.5   POST /api/v1/api-keys com description → 201 com raw_key
9.6   GET /api/v1/api-keys → lista contém a key
9.7   Testar a nova key: GET /api/v1/documentos com X-API-Key=<nova_key> → 200
9.8   DELETE /api/v1/api-keys/{id} → 204
9.9   Testar key revogada: GET /api/v1/documentos → 401

--- Tenant ---
9.10  GET /api/v1/tenants/me → dados completos do tenant
9.11  PATCH /api/v1/tenants/settings com sefaz_ambiente="2" → 200
```

---

## FASE 10 — LGPD E SEGURANÇA

```
10.1  Verificar: nenhuma resposta de API expõe CNPJ completo em logs (mask_cnpj)
10.2  Verificar: headers de segurança presentes (X-Content-Type-Options, X-Frame-Options, HSTS)
10.3  Verificar: request_id retornado em X-Request-ID
10.4  Verificar: PFX cleanup job marca certificados inativos há 30+ dias
```

---

## FASE 11 — CLEANUP

```
11.1  Deletar todos os documents do tenant qa-*
11.2  Deletar api_keys do tenant
11.3  Deletar certificates do tenant
11.4  Deletar billing_events do tenant
11.5  Deletar manifestacao_events do tenant
11.6  Deletar monthly_overage_charges do tenant
11.7  Deletar tenant
11.8  Deletar auth user
11.9  Verificar: nenhum resíduo no banco
```

---

## CRITÉRIOS DE APROVAÇÃO

- **PASS**: Cenário executou e resultado bateu com o esperado
- **FAIL**: Resultado divergiu do esperado (detalhar o que esperava vs o que recebeu)
- **SKIP**: Cenário não pode ser executado (ex: dependência de serviço externo)
- **WARN**: Cenário passou mas com comportamento suspeito

**Mínimo pra aprovar**: 95% PASS, 0 FAIL nos cenários de FASE 3-7 (core business)

---

## COMO CADA AGENTE DEVE EXECUTAR

1. Ler este script inteiro ANTES de começar
2. Criar o tenant de teste (FASE 0)
3. Executar FASES 1-10 em ordem
4. Registrar resultado de CADA cenário (PASS/FAIL/SKIP/WARN + detalhes se FAIL)
5. Executar FASE 11 (cleanup)
6. Produzir relatório final com contagem PASS/FAIL/SKIP/WARN
7. Listar TODO cenário FAIL com: número, descrição, esperado, obtido, stack trace se houver

Os 5 agentes rodam com dados diferentes (tenant qa-agent1, qa-agent2, etc.) mas o MESMO script. Isso garante que se um encontrar um bug de concorrência que os outros não encontraram, a gente pega.
