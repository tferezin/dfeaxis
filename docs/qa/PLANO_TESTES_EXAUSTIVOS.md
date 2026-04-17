# Plano de Testes Exaustivos — 5 Agentes × 40 min

**Data**: 2026-04-16  
**Objetivo**: Validação completa pós-merge, simulando 5 "clientes" em paralelo

---

## Agente 1 — Captura SEFAZ (E2E Backend)

**Simula**: Cliente com certificado fazendo captura de documentos

**Testes**:
1. Polling trigger com SEFAZ fake retornando múltiplos lotes (paginação NSU)
2. Trial cap de 500 docs — baixa até o limite, verifica bloqueio
3. Trial bloqueado não chama SEFAZ (zero requests ao fake)
4. Auto-ciência disparada após captura de NFe resumos
5. Créditos debitados após captura (plano pago)
6. Circuit breaker — 3 falhas consecutivas → bloqueia → recupera
7. NSU zero-padded corretamente (15 chars)
8. Eventos SEFAZ (procEventoNFe) filtrados e não salvos como docs
9. Captura de NFe + CTe + MDFe no mesmo trigger
10. NFS-e via ADN (caminho separado)

**Como**: pytest com FakeSefazClient, FakeStripeClient, test_tenant fixture

---

## Agente 2 — SAP DRC (E2E Backend)

**Simula**: SAP chamando nossa API via API Key

**Testes**:
1. Pull flow: seed docs → retrieveInboundInvoices → downloadOfficialDocument → deleteOfficialDocument
2. Push flow: receiveOfficialDocument com XML válido → aparece no retrieve
3. Batch delete: 3 docs → deleteInboundInvoices → todos delivered, counter +3
4. Trial cap enforcement via SAP: tenant no cap-1 → delete 1 → trial blocked
5. Past_due subscription block: any SAP call → 402 PAYMENT_OVERDUE
6. API key inválida → 401
7. API key de tenant cancelado → 402
8. Double delete idempotent → segundo não incrementa counter
9. Push XML duplicado → 409
10. Push XML malformado → 400

**Como**: TestSAPClient contra app real com test_tenant fixture

---

## Agente 3 — Billing Lifecycle (E2E Backend)

**Simula**: Cliente do signup ao cancelamento passando por todos os estados

**Testes**:
1. Signup → trial ativo → counter zerado → 10 dias
2. Trial expira por tempo → 402 TRIAL_EXPIRED
3. Trial expira por cap → 402 TRIAL_EXPIRED
4. Checkout cria Stripe session → webhook ativa subscription
5. Invoice.paid reseta docs_consumidos_mes (Bug D)
6. Invoice.payment_failed → past_due → grace period funciona
7. Past_due + period_end passado → 402 PAYMENT_OVERDUE
8. Invoice.paid restaura acesso imediatamente
9. Subscription.updated (upgrade Starter→Business) → novos limites
10. Subscription.deleted → cancelled → polling bloqueado
11. Overage job calcula excedente corretamente
12. Overage job com 0 excedente → não cobra
13. Portal session criada → URL válida

**Como**: pytest com FakeStripeClient, test_tenant fixture

---

## Agente 4 — Manifestação (E2E Backend)

**Simula**: Cliente fazendo manifestação de documentos via API e dashboard

**Testes**:
1. Auto-ciência durante captura de NFe (210210)
2. Manifestação definitiva — confirmação (210200)
3. Manifestação definitiva — desconhecimento (210220)
4. Manifestação definitiva — não realizada (210240) com justificativa
5. Batch manifestação — 5 chaves, parcial (3 sucesso, 2 falha)
6. Listar pendentes — filtro por CNPJ
7. Histórico de manifestação — filtro por tipo de evento
8. Deadline 180 dias calculado corretamente
9. Alerta de manifestação expirando (job)
10. Ciência duplicada → cStat 573 tratado como sucesso

**Como**: pytest com FakeSefazClient, test_tenant fixture

---

## Agente 5 — Frontend Playwright (E2E Visual)

**Simula**: Usuário real no browser

**Testes**:
1. Login com credenciais válidas → dashboard carrega
2. Sidebar tem todos os 14 menus → navegação funcional
3. Trial counter mostra docs consumidos e dias restantes
4. Trial expired overlay aparece quando bloqueado
5. Payment overdue overlay aparece quando past_due + period_end passado
6. Página de certificados: upload .pfx → lista atualizada
7. Captura manual: trigger polling → resultado na tela
8. Histórico NF-e: lista docs, filtros funcionam
9. Manifestação: selecionar doc → enviar ciência → toast de sucesso
10. Financeiro: ver planos → clicar checkout → redirect Stripe
11. Billing Portal acessível
12. Responsivo: viewport mobile 375px → sidebar collapsa, overlay legível

**Como**: Playwright headless contra localhost (front + back)

---

## Execução

- Agentes 1-4 rodam em `/tmp/dfeaxis-work` com venv de `/tmp/dfeaxis-testenv`
- Agente 5 roda Playwright contra `localhost:3000` + `localhost:8000`
- Duração estimada: 30-45 min por agente
- Cada agente produz relatório com PASS/FAIL por cenário
- No final, consolido os 5 relatórios num resultado único

## Decisão pendente antes de rodar

O Agente 5 (Playwright) precisa que o frontend e backend estejam rodando localmente. Posso:
- (A) Tentar subir `next dev` e `uvicorn` em background
- (B) Rodar Playwright contra o deploy do Railway/Vercel (se existir)
- (C) Pular Playwright e fazer 5 agentes backend (mais seguro dado os problemas de environment)

**Recomendação**: Começar com agentes 1-4 (backend E2E, 100% controlável) enquanto você decide sobre o Playwright.
