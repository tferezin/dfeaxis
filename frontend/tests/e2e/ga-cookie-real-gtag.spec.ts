import { test, expect } from "@playwright/test"

/**
 * E2E SMOKE: valida que o gtag.js real (carregado pelo layout.tsx) seta um
 * cookie `_ga` com formato válido que a helper `getGaClientId()` consegue
 * parsear.
 *
 * Diferente do ga-client-id-capture.spec.ts (que usa cookies injetados pra
 * testar o parser isoladamente), este teste **NÃO mocka nada** — deixa o
 * gtag real carregar do googletagmanager.com, observa o cookie que ele seta,
 * e valida o formato.
 *
 * Rodar com:
 *   npx playwright test ga-cookie-real-gtag.spec.ts
 *
 * Pré-requisito: `npm run build` já rodado (playwright.config usa next start).
 */

test.describe("Real gtag cookie smoke test", () => {
  test("gtag.js real seta _ga no formato esperado e parser extrai client_id", async ({
    page,
  }) => {
    // Garante estado limpo — nenhum cookie previamente injetado
    await page.context().clearCookies()

    // Vai pra signup (a page carrega o layout.tsx que dispara o gtag.js)
    await page.goto("/signup")

    // Aguarda até 10s o gtag estar disponível globalmente
    await page.waitForFunction(
      () => typeof (window as unknown as { gtag?: unknown }).gtag === "function",
      null,
      { timeout: 10_000 }
    )

    // Dá um tempinho pro gtag inicializar e setar cookies
    // (o `afterInteractive` strategy do Next.js + init do gtag leva ~100ms
    //  depois do onload).
    await page.waitForTimeout(1500)

    // Lê cookies via context (não precisa ser via document.cookie)
    const cookies = await page.context().cookies()

    // Pode ter _ga (o principal) e _ga_<MID> (o de sessão). Queremos o _ga.
    const gaCookie = cookies.find((c) => c.name === "_ga")

    // VALIDAÇÃO 1: cookie existe
    expect(gaCookie, "cookie _ga deveria ser setado pelo gtag real").toBeDefined()

    // VALIDAÇÃO 2: formato correto — GA1.1.<num>.<num>
    // O valor é do tipo "GA1.1.1234567890.1234567890" (4+ partes)
    expect(gaCookie!.value).toMatch(/^GA\d+\.\d+\.\d+\.\d+$/)

    // VALIDAÇÃO 3: a helper getGaClientId (replicada aqui) extrai o client_id
    const extractedClientId = await page.evaluate(() => {
      const all = document.cookie.split(/;\s*/)
      const ga = all.find((c) => c.startsWith("_ga="))
      if (!ga) return null
      const value = ga.substring("_ga=".length)
      const parts = value.split(".")
      if (parts.length < 4) return null
      return `${parts[parts.length - 2]}.${parts[parts.length - 1]}`
    })

    // O client_id deve ser 2 números separados por ponto
    expect(extractedClientId).not.toBeNull()
    expect(extractedClientId).toMatch(/^\d+\.\d+$/)

    // Log pra debugging — util pra investigar se algo estranho aparecer
    console.log(`  [real gtag] _ga cookie value:  ${gaCookie!.value}`)
    console.log(`  [real gtag] extracted client_id: ${extractedClientId}`)
  })

  test("cookie _ga persiste entre navegações (necessário pro signup funcionar)", async ({
    page,
  }) => {
    // Valida que se o usuário navega pela landing antes de ir pra /signup,
    // o cookie _ga é o mesmo — garantindo que a atribuição do clique original
    // no anúncio é mantida até o momento do cadastro.
    await page.context().clearCookies()

    // 1º page load
    await page.goto("/")
    await page.waitForFunction(
      () => typeof (window as unknown as { gtag?: unknown }).gtag === "function",
      null,
      { timeout: 10_000 }
    )
    await page.waitForTimeout(1500)

    const cookiesAfterLanding = await page.context().cookies()
    const gaAfterLanding = cookiesAfterLanding.find((c) => c.name === "_ga")
    expect(gaAfterLanding).toBeDefined()
    const landingValue = gaAfterLanding!.value

    // 2º page load — signup
    await page.goto("/signup")
    await page.waitForFunction(
      () => typeof (window as unknown as { gtag?: unknown }).gtag === "function",
      null,
      { timeout: 10_000 }
    )
    await page.waitForTimeout(500)

    const cookiesAfterSignup = await page.context().cookies()
    const gaAfterSignup = cookiesAfterSignup.find((c) => c.name === "_ga")
    expect(gaAfterSignup).toBeDefined()

    // O valor deve ser o MESMO — gtag não reescreve o cookie em navegações
    // subsequentes, ele persiste (é isso que preserva a atribuição).
    expect(gaAfterSignup!.value).toBe(landingValue)
  })
})
