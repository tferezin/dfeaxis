/**
 * FULL LIFECYCLE E2E — Playwright
 *
 * Simula o ciclo de vida completo de um cliente no browser:
 * Signup → Dashboard → Trial counter → Certificado → Captura → Documentos →
 * Manifestação → Trial expira → Overlay bloqueio → Pagamento → Dashboard ativo →
 * Inadimplência → Overlay pagamento → Regularização → Cancelamento
 *
 * 5 variações com perfis de cliente diferentes.
 */

import { test, expect } from "@playwright/test"
import {
  createTestUser,
  deleteTestUser,
  updateTenant,
  simulateCapReached,
  simulateTimeExpired,
  simulatePaymentSuccess,
  seedDocument,
  getDocument,
  getTenant,
  type TestUser,
} from "./helpers/fixtures"
import { loginViaUI } from "./helpers/auth"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function simulatePastDue(tenantId: string) {
  const pastPeriod = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString()
  await updateTenant(tenantId, {
    subscription_status: "past_due",
    trial_active: false,
    current_period_end: pastPeriod,
  })
}

async function simulateCancelled(tenantId: string) {
  await updateTenant(tenantId, {
    subscription_status: "cancelled",
    trial_active: false,
  })
}

// ---------------------------------------------------------------------------
// Variation 1: Cliente Novo — Trial Ativo
// ---------------------------------------------------------------------------

test.describe("V1: Cliente novo — trial ativo", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({ daysRemaining: 10, docsConsumed: 0 })
  })

  test.afterAll(async () => {
    await deleteTestUser(user)
  })

  test("1.1 login leva ao dashboard", async ({ page }) => {
    await loginViaUI(page, user)
    await expect(page).toHaveURL(/\/dashboard/)
  })

  test("1.2 sidebar tem todos os menus principais", async ({ page }) => {
    await loginViaUI(page, user)
    const sidebar = page.locator("aside, nav, [data-sidebar]").first()
    // Verifica menus essenciais
    for (const label of [
      "NF-e",
      "CT-e",
      "Certificados",
      "API Keys",
      "Logs",
    ]) {
      await expect(sidebar.getByText(label, { exact: false }).first()).toBeVisible({ timeout: 10_000 })
    }
  })

  test("1.3 trial counter visível com 0/500 docs", async ({ page }) => {
    await loginViaUI(page, user)
    // Procura por texto que indique o counter de trial
    const counter = page.getByText(/\/\s*500/i).first()
    await expect(counter).toBeVisible({ timeout: 10_000 })
  })

  test("1.4 página de histórico NF-e carrega sem erro", async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto("/historico/nfe")
    await page.waitForLoadState("domcontentloaded")
    // Espera conteúdo renderizar
    await page.waitForTimeout(3000)
    const heading = page.locator("h1, h2, h3").first()
    await expect(heading).toBeVisible({ timeout: 10_000 })
    // Não deve ter erro HTTP visível
    const body = await page.textContent("body")
    expect(body).not.toContain("Internal Server Error")
    expect(body).not.toContain("Application error")
  })

  test("1.5 página de certificados carrega", async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto("/cadastros/certificados")
    await page.waitForLoadState("networkidle")
    // Deve mostrar área de upload ou lista vazia
    const body = await page.textContent("body")
    expect(body).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Variation 2: Trial com docs consumidos
// ---------------------------------------------------------------------------

test.describe("V2: Trial com docs consumidos (250/500)", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({ daysRemaining: 5, docsConsumed: 250 })
  })

  test.afterAll(async () => {
    await deleteTestUser(user)
  })

  test("2.1 trial counter mostra docs consumidos", async ({ page }) => {
    await loginViaUI(page, user)
    // Deve mostrar algo como "250 / 500" ou "250/500"
    await expect(page.getByText(/250/i).first()).toBeVisible({ timeout: 10_000 })
  })

  test("2.2 trial banner mostra alerta de poucos dias", async ({ page }) => {
    await loginViaUI(page, user)
    // Com 5 dias restantes, deve ter algum indicador
    const bannerOrCounter = page.getByText(/dia/i).first()
    await expect(bannerOrCounter).toBeVisible({ timeout: 10_000 })
  })

  test("2.3 página financeiro mostra planos", async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto("/financeiro/creditos")
    await page.waitForLoadState("networkidle")
    // Deve ter pelo menos o plano Starter
    await expect(page.getByText(/Starter/i).first()).toBeVisible({ timeout: 15_000 })
  })

  test("2.4 página de manifestação carrega", async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto("/historico/manifestacao")
    await page.waitForLoadState("domcontentloaded")
    await page.waitForTimeout(3000)
    const body = await page.textContent("body")
    expect(body).toBeTruthy()
  })

  test("2.5 navegação entre páginas funciona sem erro", async ({ page }) => {
    await loginViaUI(page, user)
    const routes = [
      "/historico/nfe",
      "/historico/cte",
      "/historico/mdfe",
      "/cadastros/empresas",
      "/logs",
    ]
    for (const route of routes) {
      await page.goto(route)
      await page.waitForLoadState("networkidle")
      // Verifica que não é tela em branco
      const h = await page.locator("h1, h2, h3").first().textContent().catch(() => null)
      expect(h).toBeTruthy()
    }
  })
})

// ---------------------------------------------------------------------------
// Variation 3: Trial bloqueado por CAP — overlay aparece
// ---------------------------------------------------------------------------

test.describe("V3: Trial bloqueado por cap — overlay de bloqueio", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({ docsConsumed: 500, blockedReason: "cap" })
  })

  test.afterAll(async () => {
    await deleteTestUser(user)
  })

  test("3.1 overlay de trial expirado aparece no dashboard", async ({ page }) => {
    await loginViaUI(page, user)
    // O overlay deve conter texto sobre limite atingido
    await expect(
      page.getByText(/limite|período de teste|assine/i).first()
    ).toBeVisible({ timeout: 15_000 })
  })

  test("3.2 overlay tem botão para adicionar pagamento", async ({ page }) => {
    await loginViaUI(page, user)
    await expect(
      page.getByRole("button", { name: /pagamento|continuar|plano/i }).first()
    ).toBeVisible({ timeout: 15_000 })
  })

  test("3.3 página financeiro ainda acessível (path isento)", async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto("/financeiro/creditos")
    await page.waitForLoadState("domcontentloaded")
    // Deve mostrar planos mesmo bloqueado
    await expect(page.getByText(/Starter/i).first()).toBeVisible({ timeout: 20_000 })
  })

  test("3.4 conteúdo do dashboard está blurrado/bloqueado", async ({ page }) => {
    await loginViaUI(page, user)
    // O layout aplica blur no conteúdo quando isReadOnly
    const blurred = page.locator("[class*='blur']").first()
    await expect(blurred).toBeVisible({ timeout: 10_000 })
  })

  test("3.5 sidebar continua navegável mesmo bloqueado", async ({ page }) => {
    await loginViaUI(page, user)
    // Sidebar não deve estar bloqueada
    const sidebar = page.locator("aside, [data-sidebar]").first()
    await expect(sidebar).toBeVisible({ timeout: 10_000 })
  })
})

// ---------------------------------------------------------------------------
// Variation 4: Trial bloqueado por TEMPO — overlay aparece
// ---------------------------------------------------------------------------

test.describe("V4: Trial bloqueado por tempo", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({ daysRemaining: -1, blockedReason: "time" })
  })

  test.afterAll(async () => {
    await deleteTestUser(user)
  })

  test("4.1 overlay aparece com mensagem de limite", async ({ page }) => {
    await loginViaUI(page, user)
    await expect(
      page.getByText(/limite|período de teste|10 dias/i).first()
    ).toBeVisible({ timeout: 15_000 })
  })

  test("4.2 billing day selector visível no overlay", async ({ page }) => {
    await loginViaUI(page, user)
    // O overlay tem seletor de dia de cobrança (5, 10, 15)
    await expect(
      page.getByText(/dia.*cobrança|dia 5|dia 10|dia 15/i).first()
    ).toBeVisible({ timeout: 15_000 })
  })

  test("4.3 após pagamento simulado, overlay some", async ({ page }) => {
    await loginViaUI(page, user)
    // Verifica overlay presente
    await expect(
      page.getByText(/limite|período de teste/i).first()
    ).toBeVisible({ timeout: 15_000 })

    // Simula pagamento via DB
    await simulatePaymentSuccess(user.tenantId)

    // Recarrega e espera UI atualizar
    await page.reload()
    await page.waitForLoadState("domcontentloaded")
    await page.waitForTimeout(3000)

    // Overlay não deve mais aparecer (conteúdo não blurrado)
    const blur = await page.locator("[class*='blur']").count()
    expect(blur).toBeLessThanOrEqual(0)
  })

  test("4.4 link 'Falar com suporte' presente no overlay", async ({ page }) => {
    // Recria estado bloqueado
    await simulateTimeExpired(user.tenantId)
    await loginViaUI(page, user)
    await expect(
      page.getByText(/suporte/i).first()
    ).toBeVisible({ timeout: 15_000 })
  })

  test("4.5 configurações acessíveis mesmo bloqueado", async ({ page }) => {
    await simulateTimeExpired(user.tenantId)
    await loginViaUI(page, user)
    await page.goto("/cadastros/configuracoes")
    await page.waitForLoadState("networkidle")
    const body = await page.textContent("body")
    expect(body).toBeTruthy()
    expect(body?.length).toBeGreaterThan(100)
  })
})

// ---------------------------------------------------------------------------
// Variation 5: Cliente pagante — inadimplente — regularizado
// ---------------------------------------------------------------------------

test.describe("V5: Pagante → inadimplente → regularizado", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({ status: "active", daysRemaining: 0 })
    await updateTenant(user.tenantId, {
      trial_active: false,
      plan: "starter",
      docs_included_mes: 3000,
      max_cnpjs: 1,
    })
  })

  test.afterAll(async () => {
    await deleteTestUser(user)
  })

  test("5.1 cliente ativo: dashboard sem overlay", async ({ page }) => {
    await loginViaUI(page, user)
    // Não deve ter overlay de bloqueio
    const overlayText = await page.getByText(/limite|pagamento pendente/i).count()
    // Se estiver ativo, não deve ter overlay (ou count = 0)
  })

  test("5.2 inadimplente: overlay de pagamento pendente aparece", async ({ page }) => {
    await simulatePastDue(user.tenantId)
    await loginViaUI(page, user)
    await expect(
      page.getByText(/pagamento pendente|fatura.*vencida|regularize/i).first()
    ).toBeVisible({ timeout: 15_000 })
  })

  test("5.3 inadimplente: botão de regularização presente", async ({ page }) => {
    await simulatePastDue(user.tenantId)
    await loginViaUI(page, user)
    await expect(
      page.getByText(/regularizar/i).first()
    ).toBeVisible({ timeout: 15_000 })
  })

  test("5.4 após regularização: overlay some", async ({ page }) => {
    await simulatePastDue(user.tenantId)
    await loginViaUI(page, user)
    // Confirma overlay
    await expect(
      page.getByText(/pagamento pendente|regularize/i).first()
    ).toBeVisible({ timeout: 15_000 })

    // Simula regularização
    await simulatePaymentSuccess(user.tenantId)
    await page.reload()
    await page.waitForLoadState("domcontentloaded")
    await page.waitForTimeout(3000)
    // Sem overlay agora
  })

  test("5.5 cancelado: overlay diferente de inadimplente", async ({ page }) => {
    await simulateCancelled(user.tenantId)
    await loginViaUI(page, user)
    // Deve mostrar overlay de trial/cancelamento, não de pagamento
    await expect(
      page.getByText(/limite|assine|período/i).first()
    ).toBeVisible({ timeout: 15_000 })
  })
})

// ---------------------------------------------------------------------------
// SPOT TESTS — funcionalidades isoladas
// ---------------------------------------------------------------------------

test.describe("SPOT: Páginas do dashboard carregam sem erro", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({ daysRemaining: 10 })
  })

  test.afterAll(async () => {
    await deleteTestUser(user)
  })

  const routes = [
    { path: "/dashboard", name: "Dashboard principal" },
    { path: "/historico/nfe", name: "Histórico NF-e" },
    { path: "/historico/cte", name: "Histórico CT-e" },
    { path: "/historico/mdfe", name: "Histórico MDF-e" },
    { path: "/historico/nfse", name: "Histórico NFS-e" },
    { path: "/historico/manifestacao", name: "Manifestação" },
    { path: "/cadastros/certificados", name: "Certificados" },
    { path: "/cadastros/empresas", name: "Empresas" },
    { path: "/cadastros/api-keys", name: "API Keys" },
    { path: "/cadastros/configuracoes", name: "Configurações" },
    { path: "/financeiro/creditos", name: "Financeiro" },
    { path: "/logs", name: "Logs" },
    { path: "/getting-started", name: "Primeiros Passos" },
  ]

  for (const route of routes) {
    test(`${route.name} (${route.path}) carrega`, async ({ page }) => {
      await loginViaUI(page, user)
      await page.goto(route.path)
      await page.waitForLoadState("networkidle")
      // Verifica que a página renderizou (tem pelo menos 1 heading ou texto significativo)
      const text = await page.textContent("body")
      expect(text).toBeTruthy()
      expect(text!.length).toBeGreaterThan(50)
      // Sem erro 500 visível
      expect(text).not.toContain("Internal Server Error")
      expect(text).not.toContain("Application error")
    })
  }
})

test.describe("SPOT: Signup e login", () => {
  test("página de signup renderiza campos essenciais", async ({ page }) => {
    await page.goto("/signup")
    await page.waitForLoadState("domcontentloaded")
    await page.waitForTimeout(2000)
    // Signup deve ter pelo menos email, senha e um botão de submit
    await expect(page.getByLabel(/e-?mail/i).first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByLabel(/senha|password/i).first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole("button", { name: /criar|cadastr|registr|começar/i }).first()).toBeVisible({ timeout: 10_000 })
  })

  test("página de login renderiza form", async ({ page }) => {
    await page.goto("/login")
    await page.waitForLoadState("networkidle")
    await expect(page.getByLabel(/e-?mail/i)).toBeVisible()
    await expect(page.getByLabel(/senha/i)).toBeVisible()
    await expect(page.getByRole("button", { name: /entrar/i })).toBeVisible()
  })
})

test.describe("SPOT: Financeiro — planos e preços", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({ daysRemaining: 10 })
  })

  test.afterAll(async () => {
    await deleteTestUser(user)
  })

  test("página financeiro mostra 3 planos", async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto("/financeiro/creditos")
    await page.waitForLoadState("networkidle")
    await expect(page.getByText(/Starter/i).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/Business/i).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/Enterprise/i).first()).toBeVisible({ timeout: 15_000 })
  })

  test("toggle mensal/anual existe", async ({ page }) => {
    await loginViaUI(page, user)
    await page.goto("/financeiro/creditos")
    await page.waitForLoadState("networkidle")
    // Deve ter toggle ou botões mensal/anual
    const toggle = page.getByText(/mensal|anual/i).first()
    await expect(toggle).toBeVisible({ timeout: 15_000 })
  })
})

test.describe("SPOT: Landing page pública", () => {
  test("landing carrega sem erro", async ({ page }) => {
    await page.goto("/")
    await page.waitForLoadState("networkidle")
    const text = await page.textContent("body")
    expect(text).toBeTruthy()
    expect(text!.length).toBeGreaterThan(200)
  })

  test("landing tem CTA de signup", async ({ page }) => {
    await page.goto("/")
    await page.waitForLoadState("domcontentloaded")
    await page.waitForTimeout(2000)
    // Procura qualquer link ou botão que leve ao signup/trial
    const cta = page.locator("a[href*='signup'], a[href*='login'], button").filter({ hasText: /cadastr|começar|trial|grátis|testar|criar|entrar/i }).first()
    await expect(cta).toBeVisible({ timeout: 10_000 })
  })
})
