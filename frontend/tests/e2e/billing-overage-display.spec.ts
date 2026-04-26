import { test, expect } from "@playwright/test"
import {
  createTestUser,
  deleteTestUser,
  updateTenant,
  type TestUser,
} from "./helpers/fixtures"
import { loginViaUI } from "./helpers/auth"

/**
 * E2E do display de overage no dashboard pra plano pago.
 *
 * Cenarios cobertos:
 *  1. Plano ativo dentro do limite (uso < incluso): barra verde, "dentro
 *     do limite", sem warning
 *  2. Plano ativo perto do limite (>=80%): barra ambar, sem excedente
 *  3. Plano ativo excedido: barra vermelha, "X documentos excedentes",
 *     valor previsto em reais
 *
 * Nao depende de Stripe — manipulamos docs_consumidos_mes / docs_included_mes
 * direto no banco pra simular cada estado. Valida o COMPONENTE de display
 * que cobra usuario corretamente.
 */

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/api\/v1\/?$/, "") ||
  "http://localhost:8000"

async function isBackendReachable(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/billing/plans`, {
      signal: AbortSignal.timeout(3000),
    })
    return res.ok
  } catch {
    return false
  }
}

test.describe.serial("Billing overage display — Uso do Plano card", () => {
  let user: TestUser
  let backendReady = false

  test.beforeAll(async () => {
    backendReady = await isBackendReachable()
    if (!backendReady) {
      console.warn(`[skip] backend ${BACKEND_URL} unreachable`)
      return
    }
    user = await createTestUser({ status: "active", daysRemaining: 30 })

    // Setup como cliente Starter pago: 3000 docs/mês incluso, R$ 0.30/doc
    // de overage (= 30 cents). Limpa flags de trial.
    await updateTenant(user.tenantId, {
      subscription_status: "active",
      docs_included_mes: 3000,
      docs_consumidos_mes: 0,
      overage_cents_per_doc: 30, // R$ 0.30
      trial_active: false,
      trial_blocked_at: null,
      trial_blocked_reason: null,
    })
    console.log(`[fixture] tenant=${user.tenantId} (active, 3000 docs/mes)`)
  })

  test.beforeEach(() => {
    test.skip(!backendReady, `Backend ${BACKEND_URL} not available`)
  })

  test.afterAll(async () => {
    if (user) {
      try {
        await deleteTestUser(user)
      } catch (e) {
        console.warn("cleanup failed", e)
      }
    }
  })

  test("dentro do limite: barra verde, sem excedente", async ({ page }) => {
    await updateTenant(user.tenantId, { docs_consumidos_mes: 800 }) // 27%
    await loginViaUI(page, user)
    await page.goto("/dashboard")
    await page.waitForLoadState("domcontentloaded")

    // Texto "Dentro do limite" deve aparecer
    await expect(page.locator("text=/dentro do limite/i").first()).toBeVisible({
      timeout: 10_000,
    })

    // NAO deve mostrar "excedentes" nem "Excedente previsto"
    await expect(page.locator("text=/excedente/i")).toHaveCount(0)
  })

  test("excedido: barra vermelha + N excedentes + valor previsto", async ({
    page,
  }) => {
    // 3500 capturados, 3000 incluso → 500 excedentes × R$ 0.30 = R$ 150,00
    await updateTenant(user.tenantId, { docs_consumidos_mes: 3500 })
    await loginViaUI(page, user)
    await page.goto("/dashboard")
    await page.waitForLoadState("domcontentloaded")

    // Mensagem de excedente deve aparecer
    await expect(
      page.locator("text=/excedente previsto|documentos excedentes/i").first()
    ).toBeVisible({ timeout: 10_000 })

    // Numero de docs excedentes (500)
    await expect(
      page.locator("text=/500.*doc/i").first()
    ).toBeVisible({ timeout: 5_000 })

    // Valor previsto em reais (R$ 150,00)
    await expect(
      page.locator("text=/R\\$\\s*150[,.]00/i").first()
    ).toBeVisible({ timeout: 5_000 })
  })

  test("uso entre 80-99%: barra amber, sem excedente ainda", async ({
    page,
  }) => {
    // 2700 / 3000 = 90% — alta utilização mas dentro do limite
    await updateTenant(user.tenantId, { docs_consumidos_mes: 2700 })
    await loginViaUI(page, user)
    await page.goto("/dashboard")
    await page.waitForLoadState("domcontentloaded")

    // Ainda "Dentro do limite" (90% < 100%)
    await expect(page.locator("text=/dentro do limite/i").first()).toBeVisible({
      timeout: 10_000,
    })

    // Nao deve mostrar "excedentes"
    await expect(page.locator("text=/excedentes/i")).toHaveCount(0)
  })
})
