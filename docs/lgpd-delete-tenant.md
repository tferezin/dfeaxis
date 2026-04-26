# LGPD — Direito ao Esquecimento (exclusao de tenant)

**Lei 13.709/2018 (LGPD), Art. 18, VI** — Titular pode requerer "eliminacao
dos dados pessoais tratados com o consentimento do titular".

## Quando aplicar

- Solicitacao formal por e-mail ou ticket (DPO recebe via `dpo@dfeaxis.com.br`)
- Tenant **NAO** pode ter pendencias fiscais ativas (manifestacao em prazo legal,
  documentos em prazo de retencao). Pra esses casos a politica e **anonimizacao
  parcial** em vez de exclusao total — ver secao "Casos especiais" abaixo.
- Pagamentos abertos: encerrar fatura no Stripe ANTES de apagar (refund/cancel).

## Procedimento

### 1. Validar a solicitacao

- Confirmar identidade do titular (e-mail bate com `tenants.email`).
- Verificar se ha pendencias fiscais (consultar `manifestacao_pendentes` na DB).
- Solicitar tenant_id ao time de produto se nao for fornecido.

### 2. Cancelar Stripe (se aplicavel)

```bash
# Acessar dashboard Stripe -> Customers -> buscar por stripe_customer_id
# Cancelar subscription + gerar refund se houver fatura recente
```

### 3. Executar o script

```bash
cd backend
source venv/bin/activate
python scripts/delete_tenant_lgpd.py <tenant_id>
```

O script faz **dupla confirmacao** (precisa digitar `DELETE <tenant_id>`),
apaga em ordem de FK e gera relatorio JSON em `/tmp/lgpd_delete_<id>.json`.

### 4. Confirmar ao titular

Responder no mesmo canal da solicitacao com:
- Confirmacao da exclusao (data/hora UTC)
- Relatorio JSON gerado pelo script
- Aviso: dados apagados sao **irreversiveis** — backups expirat em 30 dias.

## Casos especiais — anonimizacao parcial

Se o tenant tem documentos em prazo de retencao fiscal (5 anos para fins
tributarios — Lei Complementar 105/2001), substituir exclusao por:

1. Apagar `tenants.email`, `tenants.phone`, `auth.users` (PII pura)
2. **Manter** `documents` (chave de acesso, XML, datas) — dado fiscal/contabil
3. Apagar `chat_*`, `audit_log`, `polling_log` (sem valor fiscal)
4. Anotar em `tenants.deletion_metadata` JSONB:
   ```json
   {"anonymized_at": "<iso>", "reason": "fiscal_retention", "operator": "<user>"}
   ```

## Backup e logs

- Backups Supabase tem retencao de 30 dias — apos isso, dados nao sao
  recuperaveis nem por court order.
- Stripe mantem registros financeiros conforme normas PCI/contabeis (10 anos),
  mas PII e mascarada apos 90 dias de inatividade.

## Roadmap

- **TODO**: criar UI admin pro DPO disparar exclusao sem precisar de SSH.
  Depende de admin role + 2FA pra evitar exclusao acidental.
- **TODO**: adicionar `ON DELETE CASCADE` nas FKs que ainda nao tem
  (`audit_log`, `polling_log`) via nova migration — simplificaria o script.
- **TODO**: webhook pra Stripe ao apagar tenant (cancel subscription auto).
