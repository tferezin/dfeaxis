# Tracking Setup — DFeAxis

Como instrumentar a landing com GA4, Google Ads, Meta Pixel, Clarity, GTM, GSC e LinkedIn. **Tudo é configurado editando um único bloco** no `frontend/public/landing-v3.html`.

---

## Onde editar

Arquivo: `frontend/public/landing-v3.html`, no topo do `<head>`, bloco `window.DFEAXIS_TRACKING`:

```js
window.DFEAXIS_TRACKING = {
  GA4_ID:         "G-XXXXXXXXXX",       // Google Analytics 4
  GTM_ID:         "GTM-XXXXXXX",        // Google Tag Manager (opcional)
  META_PIXEL_ID:  "123456789012345",    // Meta Pixel
  GOOGLE_ADS_ID:  "AW-XXXXXXXXXX",      // Google Ads
  CLARITY_ID:     "abc1234567",         // Microsoft Clarity
  LINKEDIN_ID:    "1234567"             // LinkedIn Insight (opcional)
};
```

E o `<meta name="google-site-verification" content="GSC_VERIFY_PLACEHOLDER">` logo abaixo do bloco de tracking.

**Regra:** enquanto um ID tiver `PLACEHOLDER` dentro, o script correspondente **não carrega**. Isso evita hits de teste na conta real.

---

## Ordem de prioridade (measure first, ads depois)

### Fase 1 — medição (obrigatório antes de ligar ads)

#### 1. Google Analytics 4 — `GA4_ID`
- **Onde**: https://analytics.google.com → Admin → Criar Propriedade
- **Como pegar o ID**: depois de criar, Admin → Data Streams → Web → copie o `Measurement ID` (começa com `G-`)
- **Validação**: https://analytics.google.com/analytics/web/#/a*/admin/streams/debugview
- **Por que primeiro**: é a base. Sem GA4, nenhum dado de comportamento, funil, fontes de tráfego.

#### 2. Google Search Console — `GSC_VERIFY_PLACEHOLDER`
- **Onde**: https://search.google.com/search-console → Adicionar Propriedade → **Prefixo de URL** → `https://www.dfeaxis.com.br/`
- **Método de verificação**: escolher **"Marca HTML"** (meta tag)
- **Como pegar**: copiar o `content="..."` da meta tag que aparece
- **Por que**: Impressions, CTR, posição média por keyword — indispensável pra SEO.
- **Bonus**: depois vincula ao GA4 (Admin → Property → Search Console Links).

#### 3. Microsoft Clarity — `CLARITY_ID`
- **Onde**: https://clarity.microsoft.com → New project → URL `https://www.dfeaxis.com.br`
- **Como pegar**: Settings → Setup → copie o ID de 10 chars do snippet
- **Por que**: heatmap + session recordings **grátis e ilimitado**. Pra um SaaS que tá começando, isso vale mais que ter Hotjar pago. Vê onde o usuário trava, onde clica, onde desiste.

### Fase 2 — ads (só depois que medição estiver rodando e você tiver >100 sessões/dia orgânicas)

#### 4. Google Ads — `GOOGLE_ADS_ID`
- **Onde**: https://ads.google.com → Ferramentas → Conversões → + Nova ação de conversão → **Site**
- **Configurar conversão**:
  - Goal: `Sign-up`
  - Conversion name: `DFeAxis Signup`
  - Value: Same value `50` (BRL)
  - Count: One
  - Conversion window: 30 days
- **Como pegar**: depois de criar, clica na conversão → Tag setup → **Use Google Tag** → copia o ID `AW-XXXXXXXXXX`
- **Conversion label**: copia o label (você vai precisar no `gtag('event','conversion',...)` — faremos isso quando você me passar)

#### 5. Meta Pixel — `META_PIXEL_ID` (opcional)
- **Onde**: https://business.facebook.com → Events Manager → Conectar fontes de dados → Web → Pixel Meta
- **Como pegar**: Data Sources → Pixel → copie o ID (15 dígitos)
- **Por que**: se for fazer remarketing no Instagram/Facebook no futuro.

#### 6. LinkedIn Insight — `LINKEDIN_ID` (opcional B2B)
- **Onde**: https://www.linkedin.com/campaignmanager → Account assets → Insight tag
- **Como pegar**: copie o Partner ID (7 dígitos)
- **Por que**: só se for rodar campanha LinkedIn Ads pra decisores de TI/fiscal. Caro pra começar.

#### 7. Google Tag Manager — `GTM_ID` (opcional)
- **Quando usar**: só se você quiser gerenciar todos os tags pela UI do GTM em vez de editar o HTML. Pra landing estática simples, **eu recomendo NÃO usar GTM** agora (menos complexidade, menos latency, mais fácil de debugar).

---

## Eventos de conversão disparados automaticamente

Todos os CTAs da landing agora usam `DFEAXIS_CONVERT(eventName, params)` que dispara em **todas as plataformas ativas simultaneamente**:

| CTA | Event name | Value (BRL) | Quando |
|---|---|---|---|
| Botão "Começar grátis" (nav) | `cta_nav` | 50 | Click |
| Hero "Criar conta — 10 dias grátis" | `cta_hero` | 50 | Click |
| Plano Starter "Começar agora" | `plan_click_starter` | 150 | Click |
| Plano Business "Começar agora" | `plan_click_business` | 400 | Click |
| Plano Enterprise "Começar agora" | `plan_click_enterprise` | 800 | Click |
| Footer "Criar conta e testar agora" | `cta_bottom` | 50 | Click |

Values são **estimativas de lead**, não LTV real. Base de cálculo: LTV anual × conversion rate estimada (~5%). Ajustar depois que tiver dados reais.

**Mapeamento pra Meta Pixel** (automático dentro do helper):
- `cta_*` → `Lead`
- `plan_click_*` → `InitiateCheckout`
- `signup_complete` → `CompleteRegistration` (ainda não está sendo disparado — TODO no `/signup` page)
- `purchase` → `Purchase` (ainda não está sendo disparado — TODO na thank-you page pós Stripe)

### TODO depois do go-live
- [ ] Disparar `DFEAXIS_CONVERT('signup_complete', {value: 200})` na tela de sucesso do /signup
- [ ] Disparar `DFEAXIS_CONVERT('purchase', {value: <plan_price>, transaction_id: <stripe_id>})` no callback do Stripe Checkout
- [ ] Configurar **offline conversion import** no Google Ads (via API ou upload CSV) pra puxar as compras reais do Stripe e atribuir ao clique original. Isso é o que transforma o Ads de "caro e burro" em "otimizado por receita real".

---

## Checklist do que eu preciso de você

Cola aqui e me devolve:

```
GA4_ID:         G-_________
GSC_VERIFY:     __________________________________
CLARITY_ID:     __________
GOOGLE_ADS_ID:  AW-__________
META_PIXEL_ID:  _______________ (opcional)
LINKEDIN_ID:    _______         (opcional)
```

Prioridade mínima pra começar: **GA4 + GSC + Clarity**. Os outros podem vir depois.
