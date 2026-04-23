# Google Ads — Campanha V1 (Medir antes de escalar)

Estratégia **conservadora** pra primeiro mês. Objetivo: não gastar muito, coletar sinais, validar se a landing converte, e só depois escalar.

**Budget sugerido**: R$ 30/dia × 30 dias = **R$ 900/mês total** (R$15/dia por campanha × 2 campanhas).

---

## Pré-requisitos (fazer ANTES de criar campanha)

- [ ] GA4 instalado e recebendo eventos (validar no DebugView)
- [ ] Conversões configuradas no Google Ads (ver `docs/tracking-setup.md` seção 4)
- [ ] GA4 **linkado** ao Google Ads (Ads → Tools → Linked accounts → Google Analytics)
- [ ] Conversion action `DFeAxis Signup` criada e importada do GA4 ou via gtag
- [ ] **Enhanced conversions** ligado (para melhor atribuição pós-iOS14)
- [ ] Landing com Core Web Vitals no verde (LCP <2.5s, FID <100ms, CLS <0.1)

---

## Estrutura de conta

```
Account: DFeAxis
│
├── Campaign 1: BRAND (defensiva, sempre ligada)
│   ├── Ad group 1.1: dfeaxis
│   └── Budget: R$ 5/dia  (brand é barato, CPC ~R$0.30)
│
├── Campaign 2: NON-BRAND PROBLEM-AWARE
│   ├── Ad group 2.1: sap_grc_descontinuado
│   ├── Ad group 2.2: captura_nfe_automatica
│   ├── Ad group 2.3: erp_integracao_sefaz
│   └── Budget: R$ 15/dia
│
└── Campaign 3: COMPETITOR (opcional, semana 3+)
    ├── Ad group 3.1: alternativas
    └── Budget: R$ 10/dia
```

---

## Campaign 1 — BRAND

**Tipo**: Search  
**Budget**: R$ 5/dia  
**Bidding**: Maximize clicks (fase inicial, <30 conversões) → depois mudar pra **Maximize conversions**  
**Locations**: Brasil (todas as regiões, mas exclui cidades <50k habitantes)  
**Languages**: Português  
**Networks**: ❌ Desligar Display Network, ❌ Desligar Search Partners  

### Keywords (match type)
```
[dfeaxis]
"dfeaxis"
+dfeaxis +fiscal
+dfeaxis +nfe
```

### Negative keywords
```
-gratis -free -crack -tutorial -cursos -vagas -salario -emprego -reclame
```

### Ads (2 ads por ad group — RSA com 15 headlines + 4 descriptions)

**Headlines (15)**:
1. DFeAxis — Captura Fiscal Automática
2. NF-e, CT-e, CT-e OS, MDF-e e NFS-e
3. API REST para SAP, TOTVS, Oracle
4. 10 Dias Grátis, Sem Cartão
5. Zero Armazenamento de XMLs
6. Captura Direto na SEFAZ
7. Integração Nativa SAP DRC
8. Teste Sem Compromisso
9. Plataforma 100% Brasileira
10. Suporte a SAP DRC Cloud
11. Alternativa ao SAP GRC NFe
12. Multi-ERP por API REST
13. Preço a partir de R$ 290/mês
14. Trial de 500 Documentos
15. Conformidade SEFAZ Homolog

**Descriptions (4)**:
1. Captura automática de NF-e, CT-e, CT-e OS, MDF-e e NFS-e na SEFAZ. Entrega via API REST no seu ERP. Zero armazenamento.
2. Integração nativa com SAP DRC via RFC Destination. Compatível com TOTVS, Oracle, Senior, Sankhya e qualquer ERP.
3. Trial 10 dias grátis, sem cartão. 500 documentos inclusos no teste. Planos a partir de R$ 290/mês.
4. Feito pra resolver a lacuna do SAP GRC NFe descontinuado. Comece hoje e capture em produção em horas.

### Extensions
- [ ] Sitelinks: Planos, FAQ, Como funciona, Signup
- [ ] Callouts: "Trial 10 dias", "Sem cartão", "Multi-ERP", "SAP DRC nativo", "Zero storage", "API REST"
- [ ] Structured snippets (types): "NF-e", "CT-e", "MDF-e", "NFS-e"
- [ ] Call extension (se tiver telefone comercial)

---

## Campaign 2 — NON-BRAND PROBLEM-AWARE

**Tipo**: Search  
**Budget**: R$ 15/dia  
**Bidding**: Maximize clicks (primeiras 2 semanas) → depois **Target CPA R$50**  
**Locations**: Brasil (cidades >100k hab — corta tráfego ruim)  
**Networks**: ❌ Desligar Display Network, ❌ Desligar Search Partners  
**Audiences**: Observation (não exclusivo) — "IT decision makers", "Finance & Accounting"

### Ad group 2.1 — sap_grc_descontinuado
Alvo: empresas SAP que perderam automação.

**Keywords (exact + phrase)**:
```
[sap grc nfe descontinuado]
[alternativa sap grc nfe]
[migrar sap grc para drc]
[sap grc nfe end of life]
"sap grc nfe"
"sap drc nfe"
"sap grc descontinuado"
```

**Negative**:
```
-gratis -tutorial -curso -abap -vagas -treinamento
```

### Ad group 2.2 — captura_nfe_automatica
Alvo: empresas buscando automação genérica.

**Keywords**:
```
[captura automatica nfe]
[captura automatica nf-e fornecedor]
[download automatico nfe sefaz]
[automatizar download nfe]
"captura nfe sefaz"
"api nfe recebida"
```

**Negative**:
```
-emissor -emitir -emissao -gratis -gratuito -cancelada -cancelamento
-tutorial -curso -php -nodejs -python -biblioteca
```

### Ad group 2.3 — erp_integracao_sefaz
Alvo: operadores TOTVS/Oracle buscando integração.

**Keywords**:
```
[integracao totvs sefaz]
[integracao oracle erp nfe]
[api rest documentos fiscais]
[webhook nfe sefaz]
"integrar nfe no totvs"
"conectar oracle sefaz"
```

### Ads (RSA — usar mesmas headlines base da Campaign 1, mas com 4 novas pra dor)

**Headlines adicionais pra não-brand**:
- Perdeu Automação no DRC? Resolvemos
- API Pronta pra TOTVS e Oracle
- Capture NF-e Direto da SEFAZ
- Sem Middleware, Sem Storage

---

## Campaign 3 — COMPETITOR (só ligar após 2 semanas)

**Budget**: R$ 10/dia  
**Estratégia**: bid em nome de concorrentes; landing deve ter comparativo claro.

**Keywords**:
```
[espiaonfe alternativa]
[arquivei alternativa]
[nfeio preço]
[nuvem fiscal nfe recebida]
```

**Cuidados**:
- ⚠️ Google Ads permite bid em marca concorrente mas **não no texto do anúncio**.
- Headlines não podem mencionar "EspiaoNFe", "Arquivei" etc.
- Foco nas headlines na diferenciação: "Com API REST", "Nativo SAP DRC", "Zero storage".

---

## Monitoramento semanal (primeiros 30 dias)

### Métricas que importam
| Métrica | Target Semana 1 | Target Semana 4 | Onde olhar |
|---|---|---|---|
| CTR brand | >15% | >20% | Ads UI |
| CTR non-brand | >3% | >5% | Ads UI |
| Quality Score | ≥6 | ≥8 | Ads UI → Keywords |
| CPC médio brand | <R$1 | <R$0.60 | Ads UI |
| CPC médio non-brand | <R$3 | <R$2 | Ads UI |
| Bounce rate landing | <60% | <45% | GA4 Engagement |
| Avg session duration | >40s | >90s | GA4 |
| Signups (conversion) | ≥1 | ≥10 | GA4 + Ads |
| Cost per signup (CPA) | n/a (aprender) | <R$90 | Ads Conversions |

### Ações por sinal

| Sinal | Ação |
|---|---|
| CTR <2% em non-brand | Refazer headlines (+ dor explícita) |
| Quality Score <5 | Melhorar landing relevance OU pausar keyword |
| CPA >R$150 | Pausar ad group mais caro, redirecionar budget |
| Bounce >70% | Landing tem problema (CWV, promessa, primeiro fold) |
| Zero conversões em 2 semanas | Landing não converte — não adianta escalar budget |
| Conversões >30 e CPA estável | **Aí sim** escalar budget (+20% por semana) |

---

## Negative keyword list (shared, aplicar em todas campanhas)

```
-emprego -vaga -vagas -salario -salarios -curso -cursos -tutorial -aprender
-gratis -gratuito -free -crack -pirata -download
-reclame -reclamacao -golpe -fraude
-emissor -emitir -emissao -cancelamento -cancelada
-pessoal -pessoa fisica -mei (se não quisermos MEI)
-php -nodejs -python -java -biblioteca -github -npm -pip
-wikipedia -dicionario -significado
```

---

## Se tudo der errado (kill switch)

- **Gastou R$ 300 sem 1 conversão**: pausar tudo, focar em SEO orgânico + bot de landing por 2 semanas
- **CPA >R$200 consistente**: landing não converte o tráfego. Problema é UX, não budget.
- **Cliques altos mas bounce >80%**: desalinhamento entre anúncio e landing. Revisar headlines.

**Lembrete**: este é o mês-de-aprendizado. Objetivo não é lucro, é **dado**. Depois de 30 dias com dados reais, fazemos a V2 da campanha com decisões baseadas em números, não achismo.
