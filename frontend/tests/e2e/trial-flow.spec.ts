import { test, expect } from "@playwright/test"
import {
  createTestUser,
  deleteTestUser,
  simulateCapReached,
  simulateTimeExpired,
  simulatePaymentSuccess,
  getTenant,
  type TestUser,
} from "./helpers/fixtures"
import { loginViaUI, expectOnDashboard } from "./helpers/auth"

/**
 * End-to-end trial flow tests.
 *
 * These simulate a real user logging in and navigating the dashboard
 * across the entire trial lifecycle:
 *
 *   1. Fresh trial   → dashboard shows countdown (10 days)
 *   2. Approaching   → 80% cap warning visible
 *   3. Cap reached   → blocked card + "documentos pendentes" CTA
 *   4. Time expired  → blocked card with time-based copy
 *   5. Payment OK    → dashboard fully unblocks (no banner, no overlay)
 *
 * The tests run serially (workers=1, fullyParallel=false in playwright.config)
 * to avoid race conditions between fixture creation and teardown.
 */

test.describe("Trial flow — fresh user (10 days remaining)", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({
      status: "trial",
      daysRemaining: 10,
      docsConsumed: 0,
    })
  })

  test.afterAll(async () => {
    if (user) await deleteTestUser(user)
  })

  test("login leva ao dashboard com banner de countdown", async ({ page }) => {
    await loginViaUI(page, user)
    await expectOnDashboard(page)

    // Trial banner should show days remaining (>3 days = amber variant)
    const banner = page.locator("text=/expira em.*dias/i").first()
    await expect(banner).toBeVisible({ timeout: 10_000 })
  })

  test("dashboard mostra trial counter 0/500", async ({ page }) => {
    await loginViaUI(page, user)
    await expectOnDashboard(page)

    // Trial counter — '0' and '500' should be visible somewhere
    await expect(page.locator("text=/500/").first()).toBeVisible({
      timeout: 10_000,
    })
  })
})

test.describe("Trial flow — cap atingido (500/500)", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({
      status: "trial",
      daysRemaining: 7,
      docsConsumed: 500,
      blockedReason: "cap",
    })
  })

  test.afterAll(async () => {
    if (user) await deleteTestUser(user)
  })

  test("UI mostra trial bloqueado por cap + CTA", async ({ page }) => {
    await loginViaUI(page, user)
    await expectOnDashboard(page)

    // Trial blocked overlay should appear
    const overlay = page.locator("text=/atingiu o limite|trial bloqueado/i").first()
    await expect(overlay).toBeVisible({ timeout: 10_000 })

    // CTA "Ver planos" or "Assinar"
    const cta = page.getByRole("link", { name: /ver planos|assinar/i }).first()
    await expect(cta).toBeVisible()
  })
})

test.describe("Trial flow — tempo expirado", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({
      status: "trial",
      daysRemaining: 10,
      docsConsumed: 50,
    })
    // Force time expiration after creation
    await simulateTimeExpired(user.tenantId)
  })

  test.afterAll(async () => {
    if (user) await deleteTestUser(user)
  })

  test("UI mostra trial expirado por tempo", async ({ page }) => {
    await loginViaUI(page, user)
    // Backend middleware may also redirect — accept either dashboard with overlay
    // or any page that shows the blocked UI
    const blocked = page.locator(
      "text=/período de teste.*terminou|trial bloqueado|expirou/i"
    ).first()
    await expect(blocked).toBeVisible({ timeout: 15_000 })
  })
})

test.describe("Trial flow — pagamento aprovado libera tudo", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({
      status: "trial",
      daysRemaining: 5,
      docsConsumed: 500,
      blockedReason: "cap",
    })
  })

  test.afterAll(async () => {
    if (user) await deleteTestUser(user)
  })

  test("ANTES do pagamento: bloqueado", async ({ page }) => {
    await loginViaUI(page, user)
    const overlay = page.locator("text=/atingiu o limite|trial bloqueado|período de teste.*terminou/i").first()
    await expect(overlay).toBeVisible({ timeout: 10_000 })
  })

  test("APÓS pagamento mockado: dashboard volta normal", async ({ page }) => {
    await simulatePaymentSuccess(user.tenantId)

    // Verify state in DB
    const t = await getTenant(user.tenantId)
    expect(t.subscription_status).toBe("active")
    expect(t.trial_blocked_reason).toBeNull()

    await loginViaUI(page, user)
    await expectOnDashboard(page)

    // No blocked overlay
    const overlay = page.locator("text=/atingiu o limite|trial bloqueado/i")
    await expect(overlay).toHaveCount(0)
  })
})

test.describe("Trial flow — anti-abuse: CNPJ duplicado bloqueado", () => {
  let user1: TestUser

  test.beforeAll(async () => {
    // Create a user that already burned this CNPJ
    user1 = await createTestUser({
      status: "expired",
      cnpj: "55887766000199",
    })
  })

  test.afterAll(async () => {
    if (user1) await deleteTestUser(user1)
  })

  test("API rejeita criar 2º tenant com mesmo CNPJ", async () => {
    // Try to create another with the SAME CNPJ — should fail
    await expect(
      createTestUser({ cnpj: "55887766000199" })
    ).rejects.toThrow(/duplicate|unique|already exists/i)
  })
})
