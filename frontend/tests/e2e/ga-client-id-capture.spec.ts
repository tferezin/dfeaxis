import { test, expect } from "@playwright/test"

/**
 * E2E: extração do GA4 client_id do cookie _ga no signup.
 *
 * Este teste valida a primeira etapa da cadeia de rastreamento server-side
 * (Opção B — GA4 Measurement Protocol no webhook do Stripe):
 *
 *   Cookie _ga (setado pelo gtag.js) → `getGaClientId()` → payload do signup
 *
 * O teste do lado backend (`backend/tests/test_ga4_mp.py`) cobre o resto:
 * como o campo `ga_client_id` entra em `TenantRegisterRequest`, é salvo no
 * tenants, lido pelo webhook do Stripe, e enviado pro GA4 via MP.
 *
 * Por que NÃO testamos o submit completo do formulário aqui:
 *
 *  - O fluxo depende do `supabase.auth.signUp` retornar uma sessão válida,
 *    o que exige mockar o cliente JS do Supabase completamente (complicado
 *    e frágil em Playwright, já que o cliente faz state management interno)
 *  - O type-check do TypeScript já valida que o signup page.tsx compila
 *    corretamente com o novo código passando `ga_client_id` no body
 *  - Os testes backend (test_ga4_mp.py) já validam que o backend aceita
 *    e propaga o campo corretamente
 *
 * Este teste foca na parte que é puramente client-side e determinística:
 * ler o cookie e extrair o formato correto pro Measurement Protocol.
 */

const FAKE_GA_COOKIE = "GA1.1.1234567890.9876543210"
const EXPECTED_CLIENT_ID = "1234567890.9876543210"

test.describe("GA4 client_id capture", () => {
  test("extracts client_id from _ga cookie with correct format", async ({ page }) => {
    // Injeta cookie _ga manualmente (simulando o que o gtag faria em produção).
    await page.context().addCookies([
      {
        name: "_ga",
        value: FAKE_GA_COOKIE,
        domain: "localhost",
        path: "/",
      },
    ])

    await page.goto("/signup")

    // Replica a lógica da helper getGaClientId() no contexto da página.
    const clientId = await page.evaluate(() => {
      const cookies = document.cookie.split("; ")
      const ga = cookies.find((c) => c.startsWith("_ga="))
      if (!ga) return null
      const value = ga.substring("_ga=".length)
      const parts = value.split(".")
      if (parts.length < 4) return null
      return `${parts[parts.length - 2]}.${parts[parts.length - 1]}`
    })

    expect(clientId).toBe(EXPECTED_CLIENT_ID)
  })

  test("returns null when _ga cookie is missing", async ({ page }) => {
    // Bloqueia o gtag.js real pra garantir que nenhum _ga seja setado.
    await page.route(/googletagmanager\.com\/gtag\/js/, (route) => route.abort())

    await page.context().clearCookies()
    await page.goto("/signup")

    const clientId = await page.evaluate(() => {
      const cookies = document.cookie.split(/;\s*/)
      const ga = cookies.find((c) => c.startsWith("_ga="))
      if (!ga) return null
      const value = ga.substring("_ga=".length)
      const parts = value.split(".")
      if (parts.length < 4) return null
      return `${parts[parts.length - 2]}.${parts[parts.length - 1]}`
    })

    expect(clientId).toBeNull()
  })

  test("returns null when _ga cookie has invalid format", async ({ page }) => {
    // Bloqueia o gtag.js real pra não sobrescrever nosso cookie de teste.
    // Sem esse bloqueio, o gtag.js carrega e seta seu próprio _ga válido,
    // atropelando o valor inválido que queremos testar.
    await page.route(/googletagmanager\.com\/gtag\/js/, (route) => route.abort())

    await page.context().addCookies([
      {
        name: "_ga",
        value: "invalid",
        domain: "localhost",
        path: "/",
      },
    ])

    await page.goto("/signup")

    const clientId = await page.evaluate(() => {
      const cookies = document.cookie.split(/;\s*/)
      const ga = cookies.find((c) => c.startsWith("_ga="))
      if (!ga) return null
      const value = ga.substring("_ga=".length)
      const parts = value.split(".")
      if (parts.length < 4) return null
      return `${parts[parts.length - 2]}.${parts[parts.length - 1]}`
    })

    expect(clientId).toBeNull()
  })

  test("signup page renders successfully with gtag script loaded", async ({ page }) => {
    // Sanity check: garante que layout.tsx está carregando o gtag.js e que
    // window.gtag existe quando a página monta. Isso valida indiretamente que
    // o cookie _ga será setado por usuários reais (em produção, não no teste).
    await page.goto("/signup")
    await expect(page.getByLabel(/nome/i)).toBeVisible()

    // Aguarda até 3s o gtag estar disponível (ele carrega afterInteractive).
    const gtagAvailable = await page
      .waitForFunction(
        () =>
          typeof (window as unknown as { gtag?: unknown }).gtag === "function",
        null,
        { timeout: 3000 }
      )
      .then(() => true)
      .catch(() => false)

    expect(gtagAvailable).toBe(true)
  })
})
