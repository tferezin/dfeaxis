# Plano Mestre de Testes e Validação — DFeAxis

**Data**: 2026-04-16  
**Branch**: `integration/pre-campanha`  
**Status**: Estruturado, pronto para execução

---

## Legenda

- ✅ Testado e passando (42 testes E2E confirmados 2026-04-16)
- 🔨 Existe no código, precisa de teste E2E
- ❌ Não implementado / não existe ainda
- ⚠️ Implementação parcial, precisa de ajuste

---

## BLOCO 1 — CAPTURA DE DOCUMENTOS (Core do produto)

### 1.1 Trial permite 500 documentos
| # | Cenário | Status |
|---|---------|--------|
| 1.1.1 | Tenant trial recém-criado tem `trial_cap=500` e `docs_consumidos_trial=0` | ✅ T01, T02 |
| 1.1.2 | Trial baixa documentos até atingir 500 (simulado com SEFAZ fake) | ⚠️ T06 testa parcialmente (499→500 com bloqueio), mas NÃO simula download real de 500 docs |
| 1.1.3 | Após 500 docs, polling retorna 402 TRIAL_EXPIRED com code=cap | ✅ T05 |
| 1.1.4 | Após 10 dias, polling retorna 402 TRIAL_EXPIRED com code=time | ✅ T04 |
| 1.1.5 | SEFAZ **nunca é chamada** quando trial está bloqueado | ✅ T04, T05 |

### 1.2 Chamadas SEFAZ em lotes de 50 (NSU pagination)
| # | Cenário | Status |
|---|---------|--------|
| 1.2.1 | `polling_job._poll_single_detailed` faz loop até `ult_nsu == max_nsu` | 🔨 Código existe em `scheduler/polling_job.py`, precisa teste E2E com SEFAZ fake retornando múltiplos lotes |
| 1.2.2 | Cada chamada SEFAZ retorna no máximo 50 docs (spec DistDFe) | 🔨 Precisa fake que simula paginação (lote 1: 50 docs + ult_nsu<max_nsu, lote 2: 30 docs + ult_nsu==max_nsu) |
| 1.2.3 | Baixa até atingir 500 no trial (loop para quando `count(documents) >= trial_cap`) | 🔨 Precisa validar se `nsu_controller` corta no cap |
| 1.2.4 | NSU é salvo corretamente (zero-padded 15 chars) após cada lote | 🔨 Código tem `.zfill(15)`, precisa teste |

### 1.3 SEFAZ Fake — simulação completa de chamadas e retornos
| # | Cenário | Status |
|---|---------|--------|
| 1.3.1 | `FakeSefazClient.seed_documents()` gera docs com XML válido | ✅ Fixture smoke |
| 1.3.2 | Fake simula `cstat=137` (nenhum doc novo) | 🔨 Precisa cenário |
| 1.3.3 | Fake simula `cstat=138` (docs encontrados) com paginação NSU | ❌ Fake atual não pagina |
| 1.3.4 | Fake simula erro SEFAZ (timeout, 500, cert inválido) | ❌ Precisa cenários de circuit breaker |
| 1.3.5 | Fake simula tipos mistos (NFe + CTe + MDFe no mesmo retorno) | ❌ |

### 1.4 SAP Fake — simulação de chamadas e retornos
| # | Cenário | Status |
|---|---------|--------|
| 1.4.1 | `TestSAPClient` faz GET /documentos e recebe lista com XML b64 | ✅ Fixture smoke (sap_client health) |
| 1.4.2 | SAP confirma documento via POST /documentos/{chave}/confirmar | 🔨 Endpoint existe, precisa teste E2E |
| 1.4.3 | Após confirmação, XML é removido (zero-retention) | 🔨 Precisa validar no banco |
| 1.4.4 | SAP tenta buscar doc já confirmado → retorna vazio | 🔨 |
| 1.4.5 | SAP com API key inválida → 401 | 🔨 |
| 1.4.6 | SAP de tenant bloqueado (trial expirado / fatura vencida) → 402 | 🔨 |

---

## BLOCO 2 — MANIFESTAÇÃO

### 2.1 Manifestação via SAP (API)
| # | Cenário | Status |
|---|---------|--------|
| 2.1.1 | POST /api/v1/manifestacao com tipo=210200 (Confirmação) → SEFAZ fake retorna sucesso | 🔨 Endpoint existe, precisa teste |
| 2.1.2 | POST /api/v1/manifestacao com tipo=210220 (Desconhecimento) → sucesso | 🔨 |
| 2.1.3 | POST /api/v1/manifestacao com tipo=210240 (Não Realizada) + justificativa | 🔨 |
| 2.1.4 | Manifesto batch (até 50 chaves) → processa todas | 🔨 |
| 2.1.5 | Manifesto de chave inexistente → erro adequado | 🔨 |
| 2.1.6 | Evento de manifestação gravado em `manifestacao_events` com source=api | 🔨 |

### 2.2 Manifestação manual (Dashboard)
| # | Cenário | Status |
|---|---------|--------|
| 2.2.1 | Menu "Manifestação" existe no sidebar do dashboard | ✅ Existe em `/historico/manifestacao` |
| 2.2.2 | Listar documentos pendentes de manifestação | 🔨 Página existe, precisa validar filtro |
| 2.2.3 | Filtrar apenas docs sem manifestação definitiva | 🔨 |
| 2.2.4 | Selecionar doc → enviar manifestação → SEFAZ retorna confirmação | 🔨 Precisa teste visual + E2E |
| 2.2.5 | Manifestação gravada com source=dashboard | 🔨 |

### 2.3 Ciência automática
| # | Cenário | Status |
|---|---------|--------|
| 2.3.1 | Captura de NFe gera ciência automática (210210) | 🔨 Código em `polling_job.py`, precisa teste |
| 2.3.2 | Ciência gravada com source=auto_capture | 🔨 |
| 2.3.3 | Docs sem ciência não ficam visíveis para manifestação definitiva | 🔨 |

### 2.4 Alertas de vencimento (180 dias)
| # | Cenário | Status |
|---|---------|--------|
| 2.4.1 | Job `manifestacao_alert_job` detecta docs com ciência mas sem manifestação definitiva | 🔨 Job existe em `scheduler/`, precisa teste |
| 2.4.2 | Email enviado quando doc está a X dias do vencimento 180d | 🔨 Template `manifestacao_expiring.html` existe |
| 2.4.3 | Não enviar alerta se doc já tem manifestação definitiva | 🔨 |

---

## BLOCO 3 — CONSULTA DE DOCUMENTOS

### 3.1 Dashboard — consulta com até 180 dias
| # | Cenário | Status |
|---|---------|--------|
| 3.1.1 | Menu "Histórico > NF-e" existe no dashboard | ✅ Existe |
| 3.1.2 | Menu "Histórico > CT-e" existe | ✅ |
| 3.1.3 | Menu "Histórico > MDF-e" existe | ✅ |
| 3.1.4 | Menu "Histórico > NFS-e" existe | ✅ |
| 3.1.5 | Filtros por período (até 180 dias) funcionam | 🔨 Precisa validar visual |
| 3.1.6 | Filtro por CNPJ emitente funciona | 🔨 |
| 3.1.7 | Filtro por status de manifestação funciona | 🔨 |
| 3.1.8 | Paginação com volumes grandes (>100 docs) | 🔨 |

---

## BLOCO 4 — TRIAL LIFECYCLE

### 4.1 Controle durante trial
| # | Cenário | Status |
|---|---------|--------|
| 4.1.1 | Signup cria trial com 10 dias + 500 docs | ✅ T01 |
| 4.1.2 | Counter de docs consumidos visível no dashboard | ✅ Componente `trial-counter.tsx` existe |
| 4.1.3 | Counter de dias restantes visível | ✅ Componente existe com `daysRemaining` |
| 4.1.4 | Bloqueio por cap (500 docs) bloqueia polling | ✅ T05 |
| 4.1.5 | Bloqueio por tempo (10 dias) bloqueia polling | ✅ T04 |
| 4.1.6 | Overlay de trial expirado aparece no dashboard | ✅ Componente `trial-expired-overlay.tsx` existe |
| 4.1.7 | Overlay mostra botão para comprar plano | 🔨 Precisa validar visual |

---

## BLOCO 5 — PAGAMENTO E BILLING

### 5.1 Fluxo de compra
| # | Cenário | Status |
|---|---------|--------|
| 5.1.1 | Botão "Comprar plano" existe no dashboard | ✅ Existe em `/financeiro/creditos` com `PricingTable` |
| 5.1.2 | Botão "Comprar plano" existe na tela de regularização (trial expired overlay) | 🔨 Precisa validar |
| 5.1.3 | Checkout cria Stripe Session com metadata correta | ✅ P01 |
| 5.1.4 | Webhook checkout.session.completed ativa subscription | ✅ P02 |
| 5.1.5 | Acesso liberado imediatamente após pagamento | ✅ T07, P02 |

### 5.2 Pro-rata no primeiro pagamento
| # | Cenário | Status |
|---|---------|--------|
| 5.2.1 | Mensal: cobra `base × (dias_restantes_mes / 30)` | ⚠️ Stripe faz pro-rata nativo com `billing_cycle_anchor`, mas precisa validar se está configurado |
| 5.2.2 | Anual: cobra `(base_mes × 11) + (base_mes × dias_restantes/30)` | ⚠️ Precisa verificar implementação |
| 5.2.3 | Skip se pro-rata < R$50 | ❌ Não implementado |

### 5.3 Pagamento pendente — negativação
| # | Cenário | Status |
|---|---------|--------|
| 5.3.1 | `invoice.payment_failed` transiciona para `subscription_status=expired` | ✅ T08 |
| 5.3.2 | Polling bloqueado com 402 quando status=expired | ✅ T08 |
| 5.3.3 | Cliente consegue regularizar pagamento pendente | ✅ T09 (invoice.paid restaura acesso) |
| 5.3.4 | Billing Portal acessível para trocar cartão | ✅ P06 |
| 5.3.5 | Após regularização, acesso restaurado imediatamente | ✅ T09 |

### 5.4 Bloqueio por fatura vencida
| # | Cenário | Status |
|---|---------|--------|
| 5.4.1 | Fatura não paga → Stripe marca past_due → backend mapeia para expired | ✅ T08 |
| 5.4.2 | Captura de documentos bloqueada | ✅ T08 |
| 5.4.3 | Dashboard mostra aviso de pagamento pendente | 🔨 Precisa validar visual |
| 5.4.4 | Botão de regularização visível | 🔨 |

### 5.5 Excedente mensal (overage)
| # | Cenário | Status |
|---|---------|--------|
| 5.5.1 | Job `monthly_overage_job` calcula docs excedentes | ✅ P05 |
| 5.5.2 | InvoiceItem criado no Stripe com valor correto | ✅ P05 |
| 5.5.3 | **Mensal**: fatura = base plano + excedente mês anterior | 🔨 Precisa validar Stripe end-to-end |
| 5.5.4 | **Anual**: fatura = APENAS excedente (base já pago) | 🔨 Precisa validar |

### 5.6 Renewal mensal
| # | Cenário | Status |
|---|---------|--------|
| 5.6.1 | `invoice.paid` reseta `docs_consumidos_mes=0` | ✅ P03 (Bug D corrigido) |
| 5.6.2 | `current_period_end` avançado +30d | ✅ P03 |
| 5.6.3 | Limites atualizados após upgrade de plano | ✅ P04 |

### 5.7 Cancelamento
| # | Cenário | Status |
|---|---------|--------|
| 5.7.1 | `customer.subscription.deleted` → status=cancelled | ✅ T10 |
| 5.7.2 | Polling bloqueado após cancelamento | ✅ T10 |
| 5.7.3 | Acesso mantido até fim do ciclo pago | ⚠️ Stripe faz isso nativamente com `cancel_at_period_end`, mas precisa validar se usamos |

### 5.8 Após 30 dias sem pagamento — ação a definir
| # | Cenário | Status |
|---|---------|--------|
| 5.8.1 | **DECIDIDO (2026-04-16)**: Manter acesso à plataforma (dashboard visível) até o final do mês. Após o vencimento, bloquear funcionalidades do dash (captura, manifestação, consulta) mas manter login + aviso de "pagamento necessário para regularização". Dados NÃO são deletados. | ❌ Não implementado |
| 5.8.2 | Dashboard mostra banner/overlay de regularização (similar ao trial expired, mas com mensagem de fatura vencida) | ❌ |
| 5.8.3 | Botão de regularização leva ao Billing Portal do Stripe (trocar cartão / pagar fatura pendente) | ❌ |
| 5.8.4 | Após regularização (invoice.paid), acesso restaurado imediatamente | ✅ T09 já cobre esse cenário |

---

## BLOCO 6 — PLAN ENFORCEMENT (gaps conhecidos)

### 6.1 Limites por plano
| # | Cenário | Status |
|---|---------|--------|
| 6.1.1 | Limite de CNPJs por plano (Starter=1, Business=5, Enterprise=50) | ⚠️ Tabela de planos define, mas enforcement no backend pode ser parcial |
| 6.1.2 | Limite de API keys = número de CNPJs | ⚠️ |
| 6.1.3 | Tipos de documento por plano (Starter: NFe apenas? ou todos?) | ❌ Não enforced |
| 6.1.4 | Retroativa: todos têm 90 dias (decisão Thiago) | 🔨 Precisa validar |

---

## BLOCO 7 — AVISOS E NOTIFICAÇÕES

### 7.1 Emails transacionais
| # | Cenário | Status |
|---|---------|--------|
| 7.1.1 | Email "trial expirando" (X dias restantes) | 🔨 Template + job existem (`trial_nudge.html`, `email_jobs.py`) |
| 7.1.2 | Email "cap do trial atingido" | 🔨 Template existe (`trial_cap_warning.html`) |
| 7.1.3 | Email "trial expirado" | 🔨 Template existe (`trial_expired.html`) |
| 7.1.4 | Email "docs pendentes de manifestação vencendo" | 🔨 Template existe (`manifestacao_expiring.html`) |
| 7.1.5 | Resend API configurado e DKIM/SPF válidos | ❌ Precisa configurar |

---

## BLOCO 8 — CAMPANHA DE MARKETING

### 8.1 Pré-requisitos técnicos
| # | Item | Status |
|---|------|--------|
| 8.1.1 | Domínio `dfeaxis.com.br` apontado para Vercel | ⚠️ Registrado, DNS pendente |
| 8.1.2 | GA4 property configurada | ✅ Validado 2026-04-14 |
| 8.1.3 | GA4 sign_up event configurado como evento-chave | ✅ |
| 8.1.4 | GA4 purchase event configurado (server-side via Measurement Protocol) | ✅ Código pronto, smoke test 204 |
| 8.1.5 | Google Ads — conversão sign_up importada | ✅ |
| 8.1.6 | Google Ads — conversão purchase importada e associada | ⏰ Executar 2026-04-15+ |
| 8.1.7 | GTM container ID real | ❌ Placeholder `GTM-XXXXXXX` |
| 8.1.8 | Meta Pixel configurado | ❌ |
| 8.1.9 | Stripe em modo live (sk_live_) | ❌ |
| 8.1.10 | UTM tracking no signup | ✅ Campos utm_* na tabela tenants |

### 8.2 Análise da campanha (referência sessão anterior)
| # | Item | Status |
|---|------|--------|
| 8.2.1 | Estrutura de campanhas Google Ads (Search brand + non-brand + competitor) | 🔨 Análise feita, aguardando implementação |
| 8.2.2 | Keywords research | 🔨 |
| 8.2.3 | Landing page otimizada para conversão | 🔨 V3 existe, precisa audit final |
| 8.2.4 | Competitor analysis (EspiaoNFe, Arquivei, NFe.io) | 🔨 Parcial |

---

## BLOCO 9 — INFRAESTRUTURA E ADMIN

### 9.1 Dashboard administrativo
| # | Item | Status |
|---|------|--------|
| 9.1.1 | Painel admin DFeAxis (fora do tenant) | ❌ Não existe |
| 9.1.2 | Listar tenants ativos/inativos/trial | ❌ |
| 9.1.3 | Ver conversas escaladas do chat | ❌ |
| 9.1.4 | Ver MRR, churn, conversões | ❌ |
| 9.1.5 | Impersonar tenant para suporte | ❌ |

### 9.2 Produção
| # | Item | Status |
|---|------|--------|
| 9.2.1 | Stripe prod configurado (sk_live_, produtos live) | ❌ |
| 9.2.2 | Resend configurado (DKIM, SPF) | ❌ |
| 9.2.3 | ANTHROPIC_API_KEY no Railway | ⚠️ Precisa confirmar |
| 9.2.4 | CERT_MASTER_SECRET de produção (não o de dev) | ❌ |
| 9.2.5 | SEFAZ_AMBIENTE=1 (produção) para clientes reais | ❌ Mantém 2 (homologação) |

---

## RESUMO EXECUTIVO — PRIORIDADES

### Camada 1: Bloqueadores de go-live (fazer AGORA)
1. **Testes de captura completa** — SEFAZ fake com paginação NSU, 500 docs trial, lotes de 50
2. **Testes de manifestação E2E** — via API (SAP) e via dashboard
3. **Stripe em modo live** — criar produtos, testar cobrança real
4. **Domínio definitivo** — DNS para Vercel
5. **Decisão: ação após 30 dias de inadimplência**

### Camada 2: Necessários antes de escalar
6. **Plan enforcement real** — CNPJ limit, docs/mês, tipos por plano
7. **Pro-rata validado** — Stripe billing_cycle_anchor configurado
8. **Emails transacionais testados** — Resend + templates
9. **Admin dashboard mínimo** — listar tenants, ver receita

### Camada 3: Otimização para campanha
10. **GA4 purchase como evento-chave** — importar no Ads
11. **GTM container real** — substituir placeholder
12. **Meta Pixel + Conversions API** — funil completo
13. **Landing page audit** — Lighthouse, keywords, CTA

---

## TESTES JÁ VALIDADOS (42 testes, 2026-04-16)

| Suite | Qtd | Status |
|-------|-----|--------|
| test_fixtures_smoke | 5 | ✅ PASSED |
| T01-T10 trial lifecycle | 10 | ✅ PASSED |
| P01-P06 plano pago + overage | 6 | ✅ PASSED (P03 Bug D fix confirmado) |
| test_lgpd_sanitizer | 5 | ✅ PASSED |
| test_xml_parser | 16 | ✅ PASSED |
| **TOTAL** | **42** | **42 PASSED** |
