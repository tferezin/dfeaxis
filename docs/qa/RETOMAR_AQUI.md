# 🔖 Retomar aqui — próxima sessão Claude Code

**Data do snapshot**: 2026-04-15 14:40 BRT
**Motivo**: ambiente travado por file watcher, sessão reiniciada pra limpar

---

## Contexto em 30 segundos

Você tava trabalhando na fase de correções pré-campanha Google Ads. 4 agentes rodaram em paralelo no mesmo working tree e causaram thrashing de arquivos. Os commits ficaram salvos mas o working tree ficou sujo. Qualquer operação git que escrevia em disco (checkout, reset, archive) travava por causa de algum file watcher órfão.

**Nenhum trabalho foi perdido.**

---

## Estado garantido do git (consulte com `git log --all --oneline`)

### Branches de trabalho (commitados e íntegros)

| Branch | HEAD | Conteúdo |
|---|---|---|
| `main` | `8013ca3` | Baseline estável, com ABRASF fix e outros merges prévios |
| `fix/trial-enforcement` | `d3efbcd` | Bloco 1 (trial cap 500) + Bloco 1.5 (SAP DRC enforcement) + fakes (sefaz/stripe/sap) + conftest |
| `fix/security-batch` | `98d6e58` | Delete /test-capture + ResponseSanitizer whitelist + anti-fraude cert + docs_url prod |
| `fix/polling-legacy-v2` | `f1bedc4` | _poll_single retroativa com _normalize_pfx_blob (cert v2 fix) |
| `fix/health-check` | `7526371` | /health checa deps Supabase+Stripe+Resend |

### Branch de integração (criado via git plumbing, zero conflitos)

| Branch | HEAD | Conteúdo |
|---|---|---|
| `integration/pre-campanha` | `a61b238` | Os 4 branches acima consolidados sequencialmente |

**Sequência dos 4 merges em `integration/pre-campanha`:**
```
a61b238 merge: fix/health-check (Fase 4.3)
bfa8495 merge: fix/polling-legacy-v2 (Fase 4.2)
0fb3b40 merge: fix/security-batch (Fase 4.1)
de28ed5 merge: fix/trial-enforcement (Bloco 1 + 1.5 + fakes + conftest)
```

**Garantia do git**: zero conflitos detectados nos 4 merges (`git merge-tree --write-tree` rodou limpo).

---

## O que JÁ foi validado verde

| Onde | O quê | Resultado |
|---|---|---|
| `fix/security-batch` (rodado nesta sessão) | `test_xml_parser.py` | 16/16 ✅ |
| `fix/security-batch` (rodado nesta sessão) | `test_lgpd_sanitizer.py` | Todos asserts ✅ |
| `fix/trial-enforcement` (reportado pelo agente 2.4) | `test_fixtures_smoke.py` | 5/5 ✅ |
| `fix/trial-enforcement` (reportado pelo agente 2.1) | `fakes/test_sefaz_fake.py` | 5/5 ✅ |
| `fix/trial-enforcement` (reportado pelo agente 2.2) | `fakes/test_stripe_fake.py` | 7/7 ✅ |
| `fix/trial-enforcement` (reportado pelo agente 2.3) | `fakes/test_sap_client.py` | 6/6 ✅ |
| `fix/health-check` (reportado pelo agente 4.3) | `test_health_check.py` | 5/5 ✅ |
| `fix/polling-legacy-v2` (reportado pelo agente 4.2) | `test_xml_parser.py` | 16/16 ✅ |

---

## O que NÃO foi validado (tarefa #1 da próxima sessão)

**Testes integrados rodando CONTRA o branch consolidado `integration/pre-campanha`**.

Teste unitário em cada branch separado ≠ garantia de funcionamento quando tudo se junta. Precisa rodar esta bateria **após checkout do branch consolidado**:

```bash
git checkout integration/pre-campanha
./backend/venv/bin/python backend/tests/test_xml_parser.py          # esperado 16/16
./backend/venv/bin/python backend/tests/test_lgpd_sanitizer.py      # esperado tudo verde
./backend/venv/bin/python backend/tests/fakes/test_sefaz_fake.py    # esperado 5/5
./backend/venv/bin/python backend/tests/fakes/test_stripe_fake.py   # esperado 7/7
./backend/venv/bin/python backend/tests/fakes/test_sap_client.py    # esperado 6/6
./backend/venv/bin/python backend/tests/test_health_check.py        # esperado 5/5
./backend/venv/bin/python -m pytest backend/tests/test_fixtures_smoke.py -v  # esperado 5/5, precisa SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY no .env
```

Frontend:
```bash
cd frontend
rm -rf .next
npx tsc --noEmit                                                    # esperado clean
npm run build                                                       # esperado clean
npx playwright test dashboard-competencia dashboard-navigation trial-flow  # esperado tudo passando
```

Se tudo passar: **a Fase 3 (35 cenários E2E) pode arrancar**.

---

## Próximos passos (após validação)

1. **Fase 3** — 35 cenários E2E usando os fakes (trial lifecycle, plano pago, manifestação, segurança, erros) — **execução sequencial**, 1 agente por arquivo de teste, NÃO em paralelo
2. **Fase 4.4** — `feat/manifestacao-xmldsig` (implementa assinatura digital — precisa cert A1 de homolog do Thiago)
3. **Fase 4.5** — `feat/billing-prorata-emails` (pro-rata no checkout + emails D-3 e D-0)
4. **Fase 4.6** — `feat/lgpd-export` (GET /lgpd/export)
5. **Fase 5** — Playwright visual specs (4 arquivos)
6. **Fase 6** — Auto-review cruzado (2 agentes paralelos — read-only, pode paralelizar)
7. **Fase 7** — já concluída, documento em `docs/marketing/campaign-strategic-analysis.md`

---

## Regras aprendidas (NÃO repetir erros)

1. **Nunca** rodar agentes concorrentes no mesmo working tree git. Se paralelismo for necessário, usar `git worktree add` em diretórios separados.
2. **Execução sequencial é a regra** pra Fase 3+. 3 agentes no mesmo trabalho (implementador + reviewer + test author), não 3 trabalhos diferentes.
3. **Git plumbing** (`merge-tree`, `commit-tree`, `update-ref`) funciona mesmo quando o working tree trava — bom conhecer pra emergências.
4. **Ambientes macOS com file watcher (Claude Code, VS Code)** podem bloquear operações de git se houver múltiplos processos writing no mesmo diretório.

---

## Primeira instrução pra próxima sessão

Quando abrir a nova sessão, fala simplesmente:

> "Lê `docs/qa/RETOMAR_AQUI.md` e segue as instruções."

O novo Claude Code vai:
1. Ler este arquivo
2. Ler `docs/qa/ORCHESTRATION_PLAN.md` (plano completo)
3. Fazer checkout do `integration/pre-campanha`
4. Rodar a bateria completa de testes
5. Reportar o resultado
6. Aguardar seu OK pra arrancar a Fase 3

Se a bateria passar, a gente arranca. Se falhar, identificamos o que a consolidação quebrou e consertamos.

---

## Memória salva pra próxima sessão

- **D8** confirmado: pro-rata da primeira fatura = dias restantes do mês corrente, mensal e anual
- **D9** confirmado: overage do plano anual é cobrado mensalmente (já documentado nos commits de 11/04, verificar em monthly_overage_job.py na Fase 4.5)
- **D11** confirmado: cert A1 de homologação SEFAZ existe na conta admin — usado no teste real do XMLDSig na Fase 4.4
- **D12** confirmado: LGPD export entra na Fase 4.6 (antes da campanha)
