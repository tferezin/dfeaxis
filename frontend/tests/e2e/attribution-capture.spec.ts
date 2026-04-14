import { test, expect } from "@playwright/test"

/**
 * E2E: captura de atribuição de campanha (UTM params + gclid) no
 * localStorage quando o usuário cai em uma página com query params.
 *
 * Valida o fluxo que permite relatórios internos de ROAS por canal/campanha:
 *
 *   URL com ?utm_*=... → AttributionCapture client component → localStorage
 *   → lido no signup → POST /tenants/register → tenants.utm_* no banco
 *
 * Não testamos o POST completo (isso depende de mockar o Supabase auth,
 * que é frágil em Playwright). Testamos a parte determinística: dado um
 * usuário caindo numa URL com UTMs, o localStorage fica com os valores
 * certos. A parte backend é coberta pelo schema Pydantic + tests existentes.
 */

const FAKE_GCLID = "Cj0KCQjw_fake-click-id-12345"

test.describe("Campaign attribution capture", () => {
  test("captura UTM params completos e grava em localStorage", async ({
    page,
  }) => {
    await page.context().clearCookies()

    // Simula um clique vindo do anúncio do Google Ads da campanha SAP DRC.
    // A URL inclui tanto UTMs (marcação manual) quanto gclid (auto-tagging).
    const url =
      "/signup?utm_source=google" +
      "&utm_medium=cpc" +
      "&utm_campaign=sap_drc" +
      "&utm_term=sap+drc+nfe" +
      "&utm_content=headline_a" +
      `&gclid=${encodeURIComponent(FAKE_GCLID)}`

    await page.goto(url)

    // O AttributionCapture roda no mount via useEffect. Dá um tempinho
    // pra React montar e o efeito disparar.
    await page.waitForFunction(
      () => {
        try {
          return window.localStorage.getItem("dfeaxis_attribution") !== null
        } catch {
          return false
        }
      },
      null,
      { timeout: 3000 }
    )

    // Lê o que foi salvo no storage e valida cada campo.
    const stored = await page.evaluate(() => {
      const raw = window.localStorage.getItem("dfeaxis_attribution")
      return raw ? JSON.parse(raw) : null
    })

    expect(stored).not.toBeNull()
    expect(stored.utm_source).toBe("google")
    expect(stored.utm_medium).toBe("cpc")
    expect(stored.utm_campaign).toBe("sap_drc")
    expect(stored.utm_term).toBe("sap drc nfe") // URLSearchParams decodifica `+` como espaço
    expect(stored.utm_content).toBe("headline_a")
    expect(stored.gclid).toBe(FAKE_GCLID)
    expect(stored.landing_path).toContain("/signup")
    expect(stored.captured_at).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  test("não sobrescreve atribuição existente quando navega sem UTM", async ({
    page,
  }) => {
    await page.context().clearCookies()

    // 1ª visita: landing com UTMs
    await page.goto(
      "/signup?utm_source=google&utm_medium=cpc&utm_campaign=captura_nfe"
    )

    await page.waitForFunction(
      () => {
        try {
          return window.localStorage.getItem("dfeaxis_attribution") !== null
        } catch {
          return false
        }
      },
      null,
      { timeout: 3000 }
    )

    const firstStored = await page.evaluate(() => {
      const raw = window.localStorage.getItem("dfeaxis_attribution")
      return raw ? JSON.parse(raw) : null
    })
    expect(firstStored.utm_campaign).toBe("captura_nfe")

    // 2ª navegação: /login sem UTMs — NÃO deve resetar a atribuição
    // (usuário só navegou internamente).
    await page.goto("/login")

    // Aguarda um pouco pra garantir que qualquer side-effect rodou.
    await page.waitForTimeout(500)

    const secondStored = await page.evaluate(() => {
      const raw = window.localStorage.getItem("dfeaxis_attribution")
      return raw ? JSON.parse(raw) : null
    })

    expect(secondStored).not.toBeNull()
    expect(secondStored.utm_campaign).toBe("captura_nfe")
    expect(secondStored.utm_source).toBe("google")
  })

  test("sobrescreve atribuição quando novo UTM chega (last-touch)", async ({
    page,
  }) => {
    await page.context().clearCookies()

    // 1ª visita: campanha A
    await page.goto(
      "/signup?utm_source=google&utm_medium=cpc&utm_campaign=sap_drc"
    )
    await page.waitForFunction(
      () => window.localStorage.getItem("dfeaxis_attribution") !== null,
      null,
      { timeout: 3000 }
    )

    // 2ª visita: campanha B (novo clique em outro anúncio)
    await page.goto(
      "/signup?utm_source=google&utm_medium=cpc&utm_campaign=totvs_oracle"
    )
    // Aguarda o useEffect do AttributionCapture processar o novo UTM
    await page.waitForFunction(
      () => {
        const raw = window.localStorage.getItem("dfeaxis_attribution")
        if (!raw) return false
        try {
          return JSON.parse(raw).utm_campaign === "totvs_oracle"
        } catch {
          return false
        }
      },
      null,
      { timeout: 3000 }
    )

    const stored = await page.evaluate(() => {
      const raw = window.localStorage.getItem("dfeaxis_attribution")
      return raw ? JSON.parse(raw) : null
    })

    // Last-touch venceu
    expect(stored.utm_campaign).toBe("totvs_oracle")
  })

  test("não cria entry em localStorage quando URL não tem nenhum UTM nem gclid", async ({
    page,
  }) => {
    await page.context().clearCookies()

    // Acesso direto à /signup, sem query string — tráfego "direto"
    await page.goto("/signup")
    await page.waitForTimeout(800)

    const stored = await page.evaluate(() => {
      try {
        return window.localStorage.getItem("dfeaxis_attribution")
      } catch {
        return null
      }
    })

    // Esperado: nada armazenado (não vale a pena guardar entry vazio)
    expect(stored).toBeNull()
  })
})
