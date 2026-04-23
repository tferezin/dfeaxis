# Cenário E2E Integrado + Spots — Script Unificado

**Cada agente executa TUDO abaixo, 5 vezes com dados diferentes.**
**5 agentes × 5 variações = 25 execuções completas.**

---

## PARTE A — CENÁRIO E2E INTEGRADO (fluxo completo do cliente)

Um único teste sequencial que simula a vida inteira de um cliente no DFeAxis.

### Etapa 1: Signup e configuração inicial
```
A.1.1  Criar usuário no Supabase Auth
A.1.2  Registrar tenant (POST /tenants/register) com company_name, email, phone
A.1.3  Verificar: subscription_status=trial, trial_active=true, trial_cap=500, 10 dias
A.1.4  Cadastrar certificado A1 (POST /certificates/upload com .pfx fake)
A.1.5  Verificar: certificado aparece no GET /certificates
A.1.6  Criar API key (POST /api-keys)
A.1.7  Verificar: API key funcional (GET /documentos com X-API-Key retorna 200)
```

### Etapa 2: Primeira captura — Trial em homologação (SEFAZ_AMBIENTE=2)
```
A.2.1  SAP dispara gatilho: POST /polling/trigger via API key (tipos=nfe,cte)
A.2.2  SEFAZ fake retorna 75 docs (NFe resumos + CTe completos) em 2 batches
A.2.3  Verificar: 75 docs salvos no banco, NSU avançado, polling_log registrado
A.2.4  Verificar: NFe resumos têm manifestacao_status=pendente
A.2.5  Verificar: CTe têm manifestacao_status=nao_aplicavel
A.2.6  Auto-ciência disparada para os resumos NFe
A.2.7  Verificar: manifestacao_events com tipo=210210, source=auto_capture
A.2.8  Verificar: docs atualizados para manifestacao_status=ciencia, deadline=+180d
```

### Etapa 3: SAP consome documentos
```
A.3.1  SAP chama retrieveInboundInvoices → recebe lista de fragments
A.3.2  SAP chama downloadOfficialDocument para cada doc → recebe XML
A.3.3  SAP confirma: deleteOfficialDocument para 10 docs → status=delivered
A.3.4  Verificar: xml_content removido (zero-retention)
A.3.5  Verificar: docs_consumidos_trial incrementado
A.3.6  SAP tenta deletar os mesmos 10 de novo → idempotente, counter não sobe
```

### Etapa 4: Manifestação definitiva
```
A.4.1  Manifestar 3 docs como Confirmação (210200) via API key
A.4.2  Manifestar 2 docs como Desconhecimento (210220) via API key
A.4.3  Manifestar 1 doc como Não Realizada (210240) com justificativa
A.4.4  Verificar: manifestacao_events com 6 registros, sources corretos
A.4.5  Verificar: docs atualizados (confirmada/desconhecida/nao_realizada)
A.4.6  Verificar: manifestacao_deadline limpo nos manifestados
A.4.7  GET /manifestacao/historico → 6 eventos + os auto_capture anteriores
A.4.8  GET /manifestacao/pendentes → docs restantes que só têm ciência
```

### Etapa 5: Trial vai expirando — monitoramento
```
A.5.1  Consultar GET /tenants/trial-status → dias restantes, docs consumidos
A.5.2  Verificar: trial_counter mostra valor correto
A.5.3  Simular passagem de tempo: setar trial_expires_at = now - 1h
A.5.4  SAP tenta novo trigger → 402 TRIAL_EXPIRED
A.5.5  SAP tenta retrieveInboundInvoices → 402
A.5.6  GET /tenants/me → ainda funciona (path isento)
A.5.7  GET /billing/plans → ainda funciona (público)
```

### Etapa 6: Cliente paga — ativa plano Starter
```
A.6.1  POST /billing/checkout com price_id starter → session criada
A.6.2  Simular webhook checkout.session.completed
A.6.3  Verificar: subscription_status=active, plan=starter
A.6.4  Verificar: docs_included_mes=3000, max_cnpjs=1
A.6.5  Verificar: trial_active=false, trial_blocked_at=null
A.6.6  SAP dispara novo trigger → funciona (polling liberado)
```

### Etapa 7: Captura como cliente pago — "produção" (SEFAZ_AMBIENTE=1 fake)
```
A.7.1  Setar sefaz_ambiente=1 no tenant (simula mudança pra produção)
A.7.2  Seed 100 docs na SEFAZ fake (ambiente=1)
A.7.3  SAP dispara trigger → 100 docs capturados
A.7.4  Verificar: docs salvos com ambiente correto
A.7.5  Verificar: créditos debitados (plano pago)
A.7.6  SAP consome todos via SAP DRC → delivered
```

### Etapa 8: Consultas e histórico
```
A.8.1  GET /documentos?cnpj=X&tipo=nfe → lista docs
A.8.2  GET /documentos?cnpj=X&tipo=cte → lista CTe separado
A.8.3  GET /manifestacao/historico → todos os eventos
A.8.4  GET /manifestacao/historico?tipo_evento=210200 → só confirmações
A.8.5  GET /sefaz/status → status dos endpoints
A.8.6  GET /certificates → cert ativo com last_polling_at atualizado
```

### Etapa 9: Mês vira — overage
```
A.9.1  Setar docs_consumidos_mes=3050 (50 acima do cap starter=3000)
A.9.2  Rodar process_monthly_overage()
A.9.3  Verificar: monthly_overage_charges com excedente_docs=50
A.9.4  Verificar: InvoiceItem criado no Stripe com amount=600 (50×12 cents)
A.9.5  Simular invoice.paid (renewal) → docs_consumidos_mes resetado pra 0
```

### Etapa 10: Inadimplência
```
A.10.1  Simular invoice.payment_failed → subscription_status=past_due
A.10.2  current_period_end no futuro → SAP trigger ainda funciona (grace period)
A.10.3  Setar current_period_end no passado → SAP trigger retorna 402 PAYMENT_OVERDUE
A.10.4  Verificar: body da 402 tem code=PAYMENT_OVERDUE parseable
A.10.5  GET /tenants/me → funciona (isento)
A.10.6  POST /billing/portal → funciona (isento, pra regularizar)
```

### Etapa 11: Regularização
```
A.11.1  Simular invoice.paid → subscription_status volta a active
A.11.2  SAP trigger → funciona imediatamente
A.11.3  Verificar: docs_consumidos_mes=0
```

### Etapa 12: Upgrade
```
A.12.1  Simular subscription.updated (starter → business)
A.12.2  Verificar: plan=business, docs_included_mes=8000, max_cnpjs=5
A.12.3  SAP trigger → funciona com novos limites
```

### Etapa 13: Cancelamento
```
A.13.1  Simular subscription.deleted
A.13.2  Verificar: subscription_status=cancelled
A.13.3  SAP trigger → 402
A.13.4  GET /tenants/me → ainda funciona
A.13.5  GET /billing/plans → ainda funciona (pode reativar)
```

### Etapa 14: Cleanup
```
A.14.1  Deletar todos os dados do tenant (docs, events, keys, certs, tenant, auth user)
A.14.2  Verificar: nenhum resíduo no banco
```

---

## PARTE B — CENÁRIOS SPOT (funcionalidades isoladas)

Cada cenário é independente, não faz parte do fluxo E2E.

### B.1 — Segurança e Auth
```
B.1.1  Request sem nenhum header de auth → 401
B.1.2  API key inválida (5 variações: vazia, curta, longa, formato errado, revogada)
B.1.3  Bearer token inválido (5 variações)
B.1.4  Headers de segurança presentes (X-Content-Type-Options, X-Frame-Options, HSTS, X-Request-ID)
B.1.5  Request ID é único por request (5 requests → 5 IDs diferentes)
B.1.6  Mensagens de erro genéricas (sem stack traces, sem detalhes do banco)
```

### B.2 — Endpoints públicos
```
B.2.1  GET /health → 200
B.2.2  GET /sap-drc/health → 200
B.2.3  GET /billing/plans → 3 planos com preços corretos
B.2.4  Preço mensal Starter=29000, Business=69000, Enterprise=149000 cents
B.2.5  Yearly = monthly × 12 × 0.80 (desconto 20%)
```

### B.3 — Gestão de certificados
```
B.3.1  Upload certificado → 201 com certificate_id
B.3.2  Listar certificados → cert aparece
B.3.3  Deletar certificado → 204
B.3.4  Listar de novo → vazio
B.3.5  Upload com arquivo inválido → erro adequado
```

### B.4 — Gestão de API Keys
```
B.4.1  Criar API key → raw_key retornado
B.4.2  Listar keys → key aparece (sem expor hash)
B.4.3  Usar key pra acessar endpoint → 200
B.4.4  Revogar key → 204
B.4.5  Usar key revogada → 401
```

### B.5 — Consulta de tenant
```
B.5.1  GET /tenants/me → dados completos
B.5.2  GET /tenants/trial-status → campos de trial
B.5.3  PATCH /tenants/settings com sefaz_ambiente="2" → 200
B.5.4  PATCH /tenants/settings com polling_mode → 200
B.5.5  PATCH /tenants/settings com manifestacao_mode → 200
```

### B.6 — Billing Portal
```
B.6.1  POST /billing/portal → URL válida do Stripe
B.6.2  Portal acessível mesmo com trial bloqueado
```

### B.7 — Webhook idempotência
```
B.7.1  Enviar mesmo event_id duas vezes → segundo é "duplicate"
B.7.2  Evento de tipo não handled → "ignored" (mas registrado)
```

### B.8 — XML Parser (validação de metadata)
```
B.8.1  NFe completa → cnpj_emitente, razao_social, valor_total extraídos
B.8.2  CTe → cnpj_emitente extraído
B.8.3  MDFe → sem cnpj_destinatario (correto)
B.8.4  NFe resumo → só cnpj_emitente
B.8.5  XML malformado → DocumentMetadata com parse_errors, não levanta exceção
```

### B.9 — LGPD
```
B.9.1  Respostas de erro não expõem detalhes internos
B.9.2  CNPJ mascarado nos logs
B.9.3  Zero-retention: XML removido após confirmação
```

### B.10 — Erros SEFAZ e Circuit Breaker
```
B.10.1  SEFAZ retorna erro → polling_log registra
B.10.2  3 erros consecutivos → circuit breaker abre
B.10.3  Próxima chamada → "circuit open" sem chamar SEFAZ
B.10.4  Após timeout do breaker → circuito fecha, SEFAZ chamada novamente
```

---

## CONTAGEM TOTAL

- Parte A (E2E integrado): ~70 steps × 5 variações × 5 agentes = **1.750 execuções**
- Parte B (spots): ~40 cenários × 5 variações × 5 agentes = **1.000 execuções**
- **TOTAL: ~2.750 execuções de teste**
