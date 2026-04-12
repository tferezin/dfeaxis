import { test, expect, type Page } from "@playwright/test"
import {
  createTestUser,
  deleteTestUser,
  getTenant,
  type TestUser,
} from "./helpers/fixtures"
import { loginViaUI, expectOnDashboard } from "./helpers/auth"

/**
 * REAL end-to-end Stripe checkout flow.
 *
 * This test simulates a real customer:
 *   1. Lands on the trial-blocked dashboard
 *   2. Clicks the "Assinar plano" CTA
 *   3. Lands on /financeiro/creditos and sees pricing table
 *   4. Clicks "Assinar agora" on the Starter plan
 *   5. Gets redirected to checkout.stripe.com (real hosted page)
 *   6. Fills the payment form with test card 4242 4242 4242 4242
 *   7. Pays
 *   8. Stripe sends checkout.session.completed webhook to Railway backend
 *   9. Backend updates tenant.subscription_status='active'
 *  10. User lands back on /dashboard?checkout=success
 *  11. Dashboard is fully unblocked
 *
 * Network: frontend (local) → Railway backend (prod) → Stripe sandbox.
 * The webhook hits Railway because that's the URL configured in Stripe Dashboard.
 *
 * Cleanup is best-effort: we delete the tenant + Stripe customer.
 *
 * Test card: 4242 4242 4242 4242 / 12/30 / 123 / 12345 (US ZIP) or 01310-100 (BR CEP).
 */

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/api\/v1\/?$/, "") ||
  "http://localhost:8000"

async function isBackendReachable(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/billing/plans`, {
      signal: AbortSignal.timeout(3000),
    })
    if (!res.ok) return false
    const data = (await res.json()) as Array<{ price_id_monthly?: string }>
    // Must have at least 1 plan with a real price_id configured
    return Array.isArray(data) && data.some((p) => !!p.price_id_monthly)
  } catch {
    return false
  }
}

test.describe.serial("Stripe checkout — real end-to-end with test card", () => {
  let user: TestUser
  let backendReady = false

  test.beforeAll(async () => {
    backendReady = await isBackendReachable()
    if (!backendReady) {
      console.warn(
        `[skip] backend ${BACKEND_URL} unreachable or plans not seeded — billing tests will be skipped`
      )
      return
    }
    user = await createTestUser({
      status: "trial",
      daysRemaining: 5,
      docsConsumed: 500,
      blockedReason: "cap",
    })
    console.log(`[fixture] tenant=${user.tenantId} email=${user.email}`)
  })

  test.beforeEach(() => {
    test.skip(
      !backendReady,
      `Backend ${BACKEND_URL} not available or plans not seeded. Run seed_stripe_products.py first.`
    )
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

  test("usuário bloqueado vai pra /financeiro/creditos e vê pricing table", async ({
    page,
  }) => {
    await loginViaUI(page, user)
    await page.goto("/financeiro/creditos")
    await page.waitForLoadState("domcontentloaded")

    // Pricing table should render with at least one "Assinar agora"
    await expect(
      page.getByRole("button", { name: /assinar agora/i }).first()
    ).toBeVisible({ timeout: 15_000 })

    // Should show 3 plans (starter / business / enterprise)
    const planCards = page.locator("h3").filter({
      hasText: /Starter|Business|Enterprise/,
    })
    await expect(planCards).toHaveCount(3, { timeout: 10_000 })
  })

  test("checkout completo: Stripe Checkout → cartão 4242 → webhook → unblock", async ({
    page,
    context,
  }) => {
    test.setTimeout(180_000) // checkout flow can take ~60s

    await loginViaUI(page, user)
    await page.goto("/financeiro/creditos")
    await page.waitForLoadState("domcontentloaded")

    // Find the Starter plan card and click its "Assinar agora" button
    const starterCard = page.locator("div.rounded-2xl").filter({
      has: page.locator("h3", { hasText: /^Starter$/ }),
    })
    await expect(starterCard).toBeVisible({ timeout: 10_000 })

    const assinarBtn = starterCard.getByRole("button", { name: /assinar agora/i })
    await assinarBtn.click()

    // Wait for navigation to Stripe Checkout
    await page.waitForURL(/checkout\.stripe\.com/, { timeout: 30_000 })
    console.log("[checkout] landed on Stripe Checkout")

    // Don't use networkidle — Stripe loads analytics/trackers continuously.
    // Wait for the "Subscribe" button instead, which means form is ready.
    const payBtn = page.getByRole("button", { name: /^subscribe$/i })
    await payBtn.waitFor({ state: "visible", timeout: 30_000 })
    console.log("[checkout] form rendered")

    // -----------------------------------------------------------------------
    // Fill the payment form
    // -----------------------------------------------------------------------
    // Card number — placeholder shows "1234 1234 1234 1234"
    const cardInput = page.getByPlaceholder("1234 1234 1234 1234")
    await cardInput.fill("4242424242424242")

    // Expiration — placeholder MM / YY
    const expInput = page.getByPlaceholder("MM / YY")
    await expInput.fill("12 / 34")

    // CVC
    const cvcInput = page.getByPlaceholder("CVC")
    await cvcInput.fill("123")

    // Cardholder name — placeholder "Full name on card"
    const nameInput = page.getByPlaceholder("Full name on card")
    if (await nameInput.isVisible().catch(() => false)) {
      await nameInput.fill("Joao Teste")
    }

    // Country is already Brazil (verified in screenshot) — skip

    console.log("[checkout] form filled, submitting...")
    await payBtn.click()

    // -----------------------------------------------------------------------
    // Wait for redirect back to our success URL
    // -----------------------------------------------------------------------
    await page.waitForURL(/checkout=success|\/dashboard/, { timeout: 60_000 })
    console.log("[checkout] redirected back to:", page.url())

    // -----------------------------------------------------------------------
    // Wait for webhook to be processed (asynchronous on Stripe side)
    // We poll the DB until subscription_status flips to 'active'.
    // -----------------------------------------------------------------------
    const maxWaitMs = 30_000
    const pollIntervalMs = 1500
    const startTime = Date.now()

    let tenantState: Record<string, unknown> | null = null
    while (Date.now() - startTime < maxWaitMs) {
      tenantState = await getTenant(user.tenantId)
      if (tenantState.subscription_status === "active") {
        console.log(
          `[webhook] tenant flipped to active after ${Date.now() - startTime}ms`
        )
        break
      }
      await page.waitForTimeout(pollIntervalMs)
    }

    expect(tenantState).not.toBeNull()
    expect(tenantState!.subscription_status).toBe("active")
    expect(tenantState!.trial_blocked_reason).toBeNull()
    expect(tenantState!.trial_blocked_at).toBeNull()
    expect(tenantState!.stripe_subscription_id).toBeTruthy()
    expect(tenantState!.stripe_customer_id).toBeTruthy()
    expect(tenantState!.current_period_end).toBeTruthy()

    // -----------------------------------------------------------------------
    // Reload the dashboard and confirm the trial overlay is gone
    // -----------------------------------------------------------------------
    await page.goto("/dashboard")
    await page.waitForLoadState("domcontentloaded")

    // Trial blocked overlay should NOT be present
    const blockedOverlay = page.locator(
      "text=/atingiu o limite|trial bloqueado|período de teste.*terminou/i"
    )
    await expect(blockedOverlay).toHaveCount(0, { timeout: 10_000 })

    // Trial counter should also be gone (subscription is active now)
    const trialCounter = page.locator("text=/Trial:.*\\/\\s*500/i")
    await expect(trialCounter).toHaveCount(0)

    console.log("[success] full checkout flow validated end-to-end")
  })
})
