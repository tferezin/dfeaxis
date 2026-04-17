# Auditoria Consolidada — DFeAxis SaaS
**Data**: 2026-04-16 | **Branch**: integration/pre-campanha
**Método**: 5 agentes especializados, leitura linha por linha de todo o código

---

## RESUMO EXECUTIVO

| Agente | Escopo | CRITICAL | HIGH | MEDIUM | LOW |
|--------|--------|----------|------|--------|-----|
| Backend | 41 arquivos Python | 0 | 4 | 16 | 17 |
| Frontend | 30+ arquivos TSX/TS + landing | 0 | 2 | 11 | 20+ |
| Database | 16 migrations + schema | 0 | 3 | 5 | 8 |
| Landing/SEO | Landing + concorrentes + keywords | 6 P0 items | 2 | 4 | 5 |
| Segurança | OWASP + infra + credenciais | 1 | 4 | 8 | 4 |
| **TOTAL** | | **1 CRITICAL** | **15 HIGH** | **44 MEDIUM** | **54+ LOW** |

---

## 1 CRITICAL — RESOLVER IMEDIATAMENTE

| # | Issue | Arquivo |
|---|-------|---------|
| **C1** | **Supabase service_role key commitada no git** — concede acesso admin total ao banco. Rotacionar a key no Supabase dashboard AGORA. | `frontend/tests/e2e/helpers/fixtures.ts:13` |

---

## TOP 15 HIGH — RESOLVER ANTES DO GO-LIVE

### Segurança
| # | Issue | Arquivo |
|---|-------|---------|
| H1 | Rate limiting in-memory — ineficaz em multi-instância, memory leak | `middleware/security.py` |
| H2 | Sem `--proxy-headers` no uvicorn — IP do client é sempre o proxy | `railway.json` |
| H3 | `xml.etree.ElementTree` no SAP DRC — vulnerável a billion laughs DoS | `routers/sap_drc.py:58` |
| H4 | Criptografia v1 usa salt hardcoded — dados legados são mais fracos | `services/cert_manager.py` |

### Backend
| # | Issue | Arquivo |
|---|-------|---------|
| H5 | Retroativa bloqueia Starter — contradiz decisão "todos têm 90 dias" | `routers/documents.py:240` |
| H6 | Counter increment duplicado 3x — DRY violation, risco de divergência | `documents.py`, `sap_drc.py` (2x) |
| H7 | Legacy credit debit em `_poll_single` — conflita com modelo Stripe | `polling_job.py:614` |
| H8 | Legacy credit debit em `_poll_nfse` — mesmo problema | `polling_job.py:762` |

### Database
| # | Issue | Arquivo |
|---|-------|---------|
| H9 | `prod_bundle.sql` faltando migrations 012-016 | `supabase/prod_bundle.sql` |
| H10 | Índice ausente em `tenants.user_id` — toda request faz seq scan | Schema |
| H11 | `debit_credits` com valor positivo inflaciona créditos | `polling_job.py:416` |

### Landing/Campanha
| # | Issue | Arquivo |
|---|-------|---------|
| H12 | "Demonstração" no footer + credenciais de teste expostas | `landing.html:822,849` |
| H13 | Zero analytics na landing (GTM-XXXXXXX placeholder) | `landing.html:27` |
| H14 | Pricing mismatch: Business 10k vs 8k, Enterprise 30k vs 20k | `landing.html` vs `stripe_plans.json` |
| H15 | Landing 480KB — dashboard code morto embarcado | `landing.html:835-1558` |

---

## PRICING MISMATCHES (resolver antes de qualquer campanha)

| Campo | Landing Page | stripe_plans.json | llms.txt | Comparison Table |
|-------|-------------|-------------------|----------|-----------------|
| Business docs | **10,000** | **8,000** | 8,000 | 10,000 |
| Enterprise docs | **30,000** | **20,000** | 20,000 | 30,000 |
| Enterprise CNPJs | **Até 20** (tabela) | **50** | 50 | **20** |
| Manifestação Starter | **Não disponível** (tabela) | Disponível | "Todos os planos" | **Não** |
| Retroativa Starter | **30 dias** (tabela) | — | "90 dias todos" | **30d** |

**DECISÃO NECESSÁRIA**: Qual é o correto? O backend (stripe_plans.json) é o que cobra. Se landing promete mais do que o backend entrega, cliente é overcharged.

---

## CONCORRENTES — POSICIONAMENTO

| | DFeAxis | EspiaoNFe | Qive/Arquivei |
|---|---------|-----------|---------------|
| **Preço (5 CNPJs)** | R$ 690/mês | R$ 106,90/mês | Custom (caro) |
| **SAP DRC nativo** | SIM (único) | Não | Parcial |
| **Zero-retention** | SIM | Não (11 anos) | Não |
| **NFS-e** | ADN apenas | Centenas de cidades | Nacional |
| **Blog/Conteúdo** | Zero | Ativo | Extensivo |

**Conclusão**: DFeAxis é 4-7x mais caro que EspiaoNFe. A diferenciação TEM que ser SAP DRC. Keywords "sap drc nfe" e "substituir sap grc" têm ZERO concorrência — oceano azul.

---

## KEYWORDS — OCEANO AZUL (prioridade máxima)

| Keyword | Competição | Relevância |
|---------|-----------|------------|
| "sap drc nfe inbound" | ZERO | Máxima |
| "substituir sap grc nfe por drc" | ZERO | Máxima |
| "automacao nfe sap sem pi" | ZERO | Máxima |
| "migrar grc para drc nfe" | ZERO | Máxima |
| "espiaonfe alternativa" | Muito baixa | Alta |
| "nfe fornecedor automatica" | Baixa | Alta |
| "manifestacao destinatario automatica" | Média | Alta |

---

## FEATURES — STATUS COMPLETO

| Status | Qtd | % |
|--------|-----|---|
| DONE (testado) | 34 | 51% |
| Existe, sem teste E2E | 14 | 21% |
| PARCIAL | 5 | 7% |
| NÃO CONSTRUÍDO | 10 | 15% |
| NÃO CONFIGURADO (infra) | 4 | 6% |

### Não construído:
1. Admin Dashboard
2. Plan enforcement (tipos doc, frequência polling)
3. FREE plan
4. Webhook push pra ERPs
5. Pro-rata skip < R$50
6. NFS-e prefeituras
7. 30d sem pagamento (overlay/banner)
8. Cookie consent banner (LGPD)
9. Páginas /privacidade e /termos (links mortos)
10. CI/CD pipeline

---

## INFRA — TODO LIST GO-LIVE

| # | Item | Status |
|---|------|--------|
| 1 | Rotacionar service_role key do Supabase | **P0** |
| 2 | Stripe live mode (sk_live_) | Pendente |
| 3 | Domínio DNS → Vercel | Pendente |
| 4 | CERT_MASTER_SECRET produção | Pendente |
| 5 | Resend DKIM/SPF | Pendente |
| 6 | ANTHROPIC_API_KEY no Railway | Confirmar |
| 7 | GA4 na landing.html | Pendente |
| 8 | Remover "Demonstração" e credenciais | Pendente |
| 9 | Alinhar pricing (landing vs json) | Pendente |
| 10 | Criar /termos e /privacidade reais | Pendente |
| 11 | Cookie consent banner | Pendente |
| 12 | --proxy-headers no uvicorn | Pendente |
| 13 | Índice tenants.user_id | Pendente |
| 14 | Atualizar prod_bundle.sql | Pendente |
| 15 | Railway health check | Pendente |
| 16 | Importar purchase no Google Ads | Pendente |

---

## TESTES — ESTADO ATUAL

| Camada | Testes | Resultado |
|--------|--------|-----------|
| Backend E2E (5 perfis) | 225 | 225 PASSED |
| Backend isolado | 347 | 346 PASSED, 1 skip |
| Playwright browser | 44 | 44 PASSED |
| **TOTAL** | **616** | **615 PASSED, 0 bugs** |
