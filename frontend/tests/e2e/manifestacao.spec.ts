/**
 * E2E tests for manifestação flow.
 *
 * Seeds documents in Supabase and validates the UI:
 * - Single ciência via "Dar Ciência" button
 * - Batch ciência via checkboxes + "Dar Ciência em Lote"
 * - Error handling when SEFAZ returns failure
 *
 * SEFAZ calls are intercepted via page.route() so no real certificate
 * or SEFAZ connectivity is needed.
 */

import { test, expect } from "@playwright/test"
import {
  createTestUser,
  deleteTestUser,
  seedDocument,
  type TestUser,
} from "./helpers/fixtures"
import { loginViaUI } from "./helpers/auth"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

test.describe("Manifestação — ciência individual", () => {
  let user: TestUser
  let docId: string

  test.beforeAll(async () => {
    user = await createTestUser({ status: "active" })
    docId = await seedDocument(user.tenantId, user.cnpj, {
      manifestacao_status: "pendente",
      is_resumo: true,
    })
  })

  test.afterAll(async () => {
    if (user) await deleteTestUser(user)
  })

  test("clicar Dar Ciência abre dialog e confirma com sucesso", async ({
    page,
  }) => {
    // Intercept the manifestação API call with a mock SEFAZ success response
    await page.route(`${API_URL}/api/v1/manifestacao`, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            chave_acesso: "35260399000001900550010000000011234567890123",
            tipo_evento: "210210",
            descricao: "Ciência da Operação",
            cstat: "135",
            xmotivo: "Evento registrado e vinculado a NF-e",
            protocolo: "135260000001234",
            success: true,
          }),
        })
      } else {
        await route.continue()
      }
    })

    await loginViaUI(page, user)

    // Navigate directly to NF-e history (showMockData defaults to false)
    await page.goto("/historico/nfe")
    await page.waitForLoadState("networkidle")

    // Wait for data to load — look for the "Dar Ciência" button on pending docs
    const darCienciaBtn = page.getByRole("button", { name: /dar ci[eê]ncia/i }).first()
    await expect(darCienciaBtn).toBeVisible({ timeout: 15_000 })

    // Click opens confirmation dialog
    await darCienciaBtn.click()
    await expect(page.getByText(/confirmar manifesta/i)).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText(/ci[eê]ncia da opera/i)).toBeVisible()

    // Confirm the dialog
    const confirmarBtn = page.getByRole("button", { name: /confirmar/i }).last()
    await confirmarBtn.click()

    // Toast should appear with success
    await expect(page.getByText(/enviada com sucesso/i)).toBeVisible({
      timeout: 5_000,
    })
  })
})

test.describe("Manifestação — ciência em lote", () => {
  let user: TestUser
  const docIds: string[] = []

  test.beforeAll(async () => {
    user = await createTestUser({ status: "active" })
    for (let i = 0; i < 3; i++) {
      const id = await seedDocument(user.tenantId, user.cnpj, {
        manifestacao_status: "pendente",
        is_resumo: true,
      })
      docIds.push(id)
    }
  })

  test.afterAll(async () => {
    if (user) await deleteTestUser(user)
  })

  test("selecionar múltiplos docs e dar ciência em lote", async ({ page }) => {
    // Intercept batch API
    await page.route(`${API_URL}/api/v1/manifestacao/batch`, async (route) => {
      const body = JSON.parse(route.request().postData() || "{}")
      const resultados = (body.chaves || []).map((chave: string) => ({
        chave_acesso: chave,
        tipo_evento: "210210",
        descricao: "Ciência da Operação",
        cstat: "135",
        xmotivo: "Evento registrado",
        protocolo: "135260000001234",
        success: true,
      }))
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total: resultados.length,
          sucesso: resultados.length,
          erro: 0,
          resultados,
        }),
      })
    })

    await loginViaUI(page, user)
    await page.goto("/historico/nfe")
    await page.waitForLoadState("networkidle")

    // Wait for checkboxes to appear (one per pending document row + header)
    const rowCheckboxes = page.locator('tbody input[type="checkbox"]')
    await expect(rowCheckboxes.first()).toBeVisible({ timeout: 15_000 })

    // Click "select all" header checkbox
    const headerCheckbox = page.locator('thead input[type="checkbox"]')
    await headerCheckbox.click()

    // The batch button should appear
    const batchBtn = page.getByRole("button", { name: /ci[eê]ncia em lote/i })
    await expect(batchBtn).toBeVisible({ timeout: 5_000 })

    // Click batch button — this triggers the batch API
    await batchBtn.click()

    // Toast with batch result
    await expect(page.getByText(/sucesso|lote.*processado|OK/i)).toBeVisible({
      timeout: 5_000,
    })
  })
})

test.describe("Manifestação — erro SEFAZ", () => {
  let user: TestUser
  let docId: string

  test.beforeAll(async () => {
    user = await createTestUser({ status: "active" })
    docId = await seedDocument(user.tenantId, user.cnpj, {
      manifestacao_status: "pendente",
      is_resumo: true,
    })
  })

  test.afterAll(async () => {
    if (user) await deleteTestUser(user)
  })

  test("erro SEFAZ exibe toast de erro", async ({ page }) => {
    // Intercept with error response
    await page.route(`${API_URL}/api/v1/manifestacao`, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            chave_acesso: "35260399000001900550010000000011234567890123",
            tipo_evento: "210210",
            descricao: "Ciência da Operação",
            cstat: "999",
            xmotivo: "Rejeição: Certificado inválido",
            protocolo: null,
            success: false,
          }),
        })
      } else {
        await route.continue()
      }
    })

    await loginViaUI(page, user)
    await page.goto("/historico/nfe")
    await page.waitForLoadState("networkidle")

    // Click Dar Ciência
    const darCienciaBtn = page.getByRole("button", { name: /dar ci[eê]ncia/i }).first()
    await expect(darCienciaBtn).toBeVisible({ timeout: 15_000 })
    await darCienciaBtn.click()

    // Confirm dialog
    await expect(page.getByText(/confirmar manifesta/i)).toBeVisible({ timeout: 5_000 })
    const confirmarBtn = page.getByRole("button", { name: /confirmar/i }).last()
    await confirmarBtn.click()

    // Error toast should appear
    await expect(page.getByText(/erro|rejei/i)).toBeVisible({ timeout: 5_000 })
  })
})
