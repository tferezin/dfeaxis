import { test, expect } from "@playwright/test"
import {
  createTestUser,
  deleteTestUser,
  simulatePastDue,
  updateTenant,
  type TestUser,
} from "./helpers/fixtures"
import { loginViaUI } from "./helpers/auth"

/**
 * E2E do soft block granular (fix #3 P0 + estrutura existente).
 *
 * Cenarios cobertos:
 *  1. Cliente past_due dentro da tolerancia (4 dias): tudo libera
 *  2. Cliente past_due 7 dias atras (passou tolerancia 5d): writes
 *     bloqueadas (/polling/trigger 402), reads liberadas
 *  3. Cliente past_due 5d4h: deve bloquear (regression do off-by-one
 *     bug onde .days truncava 5d4h pra 5 e ainda liberava)
 *  4. Endpoints exempt (/billing/portal, /chat) sempre liberados mesmo
 *     past 5+ dias
 *
 * Network: frontend (local) → Railway backend (prod).
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

/**
 * Faz uma request autenticada com o JWT do user de teste.
 * Pega o token do localStorage do browser apos login.
 */
async function authenticatedFetch(
  page: import("@playwright/test").Page,
  path: string,
  method: string = "GET",
  body?: unknown
): Promise<{ status: number; data: unknown }> {
  return await page.evaluate(
    async ({ url, m, b }) => {
      // Tenta achar o token onde o supabase auth helper salva
      const lsKeys = Object.keys(localStorage).filter((k) =>
        k.startsWith("sb-")
      )
      let token: string | null = null
      for (const k of lsKeys) {
        try {
          const obj = JSON.parse(localStorage.getItem(k) || "{}")
          if (obj.access_token) {
            token = obj.access_token as string
            break
          }
        } catch {
          // continue
        }
      }
      const res = await fetch(url, {
        method: m,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: b ? JSON.stringify(b) : undefined,
      })
      let data: unknown = null
      try {
        data = await res.json()
      } catch {
        // no body
      }
      return { status: res.status, data }
    },
    { url: `${BACKEND_URL}${path}`, m: method, b: body }
  )
}

test.describe.serial("Billing soft block — past_due granular enforcement", () => {
  let user: TestUser
  let backendReady = false

  test.beforeAll(async () => {
    backendReady = await isBackendReachable()
    if (!backendReady) {
      console.warn(`[skip] backend ${BACKEND_URL} unreachable`)
      return
    }
    // Cria usuario active (sem past_due ainda) — vamos manipular o estado em
    // cada teste pra simular cenarios diferentes
    user = await createTestUser({ status: "active", daysRemaining: 30 })
    console.log(`[fixture] tenant=${user.tenantId}`)
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

  test("dentro da tolerancia (3 dias): tudo libera", async ({ page }) => {
    await simulatePastDue(user.tenantId, 3)
    await loginViaUI(page, user)

    // GET libera (read-only sempre)
    const getDocs = await authenticatedFetch(page, "/api/v1/documents")
    expect(getDocs.status).toBeLessThan(500)
    expect(getDocs.status).not.toBe(402)

    // POST polling tambem libera (ainda dentro 5d tolerance)
    const postPolling = await authenticatedFetch(
      page,
      "/api/v1/polling/trigger",
      "POST",
      { cnpj: user.cnpj }
    )
    expect(postPolling.status).not.toBe(402)
  })

  test("passou tolerancia (7 dias): write bloqueia 402, read libera", async ({
    page,
  }) => {
    await simulatePastDue(user.tenantId, 7)
    await loginViaUI(page, user)

    // GET libera (read-only sempre)
    const getDocs = await authenticatedFetch(page, "/api/v1/documents")
    expect(getDocs.status).not.toBe(402)

    // POST polling bloqueia
    const postPolling = await authenticatedFetch(
      page,
      "/api/v1/polling/trigger",
      "POST",
      { cnpj: user.cnpj }
    )
    expect(postPolling.status).toBe(402)
    expect((postPolling.data as { detail?: { code?: string } })?.detail?.code).toBe(
      "PAYMENT_OVERDUE"
    )
  })

  test("regression off-by-one: 5d4h bloqueia (era bug)", async ({ page }) => {
    // Setup: past_due_since = 5 dias e 4 horas atras
    const pastDueSince = new Date(
      Date.now() - (5 * 24 + 4) * 60 * 60 * 1000
    ).toISOString()
    await updateTenant(user.tenantId, {
      subscription_status: "past_due",
      past_due_since: pastDueSince,
    })
    await loginViaUI(page, user)

    // POST polling DEVE bloquear (5d4h > 5d)
    const postPolling = await authenticatedFetch(
      page,
      "/api/v1/polling/trigger",
      "POST",
      { cnpj: user.cnpj }
    )
    expect(postPolling.status).toBe(402)
    // Antes do fix, .days = 5 e ainda liberava — agora timedelta > 5d bloqueia
  })

  test("endpoints exempt sempre liberados mesmo past 7 dias", async ({
    page,
  }) => {
    await simulatePastDue(user.tenantId, 7)
    await loginViaUI(page, user)

    // /billing/portal (write, mas exempt — cliente PRECISA conseguir pagar)
    const portal = await authenticatedFetch(
      page,
      "/api/v1/billing/portal",
      "POST"
    )
    // 200 com URL ou 400 sem stripe_customer_id; nunca 402
    expect(portal.status).not.toBe(402)

    // /alerts (GET) — sempre exempt
    const alerts = await authenticatedFetch(page, "/api/v1/alerts")
    expect(alerts.status).not.toBe(402)
  })

  test("UI dashboard mostra banner past_due", async ({ page }) => {
    await simulatePastDue(user.tenantId, 7)
    await loginViaUI(page, user)
    await page.goto("/dashboard")
    await page.waitForLoadState("domcontentloaded")

    // Banner ou alerta de pagamento em atraso deve aparecer
    const banner = page.locator(
      "text=/pagamento.*atraso|past.*due|inadimpl|regulariz/i"
    )
    await expect(banner.first()).toBeVisible({ timeout: 10_000 })
  })
})
