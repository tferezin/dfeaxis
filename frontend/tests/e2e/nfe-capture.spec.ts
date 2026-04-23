/**
 * E2E tests for NFe capture (Etapa 1 manual).
 *
 * Valida a UI da página /execucao/captura pros diferentes retornos do
 * endpoint /api/v1/polling/nfe-resumos:
 *   - cStat 138 (sucesso com docs)      → card amarelo com resumo/ciência counts
 *   - cStat 137 (vazio)                  → card amarelo com 0s + <details> colapsado
 *   - cStat 656 (consumo indevido)       → card azul "Sem documentos novos" + <details>
 *   - status=rate_limited_by_sefaz       → card azul "Aguardando janela SEFAZ" (gate adaptativo)
 *
 * SEFAZ é totalmente mockado via page.route() — não precisa de cert real nem
 * de conectividade com SEFAZ.
 */

import { test, expect } from "@playwright/test"
import {
  createTestUser,
  deleteTestUser,
  type TestUser,
} from "./helpers/fixtures"
import { loginViaUI } from "./helpers/auth"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const NFE_RESUMOS_URL = `${API_URL}/api/v1/polling/nfe-resumos`

test.describe("NFe captura — card por cenário SEFAZ", () => {
  let user: TestUser

  test.beforeAll(async () => {
    // withCert=true garante que o select de CNPJ na página /execucao/captura
    // tenha opção pra clicar no botão "Buscar Resumos".
    user = await createTestUser({ status: "active", withCert: true })
  })

  test.afterAll(async () => {
    if (user) await deleteTestUser(user)
  })

  test("cStat 138 — render card amarelo com resumos e ciências", async ({
    page,
  }) => {
    await page.route(NFE_RESUMOS_URL, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "success",
            resumos_found: 2,
            ciencia_sent: 2,
            completos_found: 0,
            sefaz_cstat: "138",
            sefaz_xmotivo: "Documento localizado",
            results: [],
          }),
        })
      } else {
        await route.continue()
      }
    })

    await loginViaUI(page, user)
    await page.goto("/execucao/captura")
    await page.waitForLoadState("domcontentloaded")

    const btn = page.getByRole("button", { name: /buscar resumos/i }).first()
    await expect(btn).toBeVisible({ timeout: 15_000 })
    await btn.click()

    const card = page.getByTestId("nfe-card-summary")
    await expect(card).toBeVisible({ timeout: 10_000 })
    await expect(card).toContainText(/2 resumo/i)
    await expect(card).toContainText(/2 ci[eê]ncia/i)
  })

  test("cStat 656 — render card azul com <details> expansível", async ({
    page,
  }) => {
    await page.route(NFE_RESUMOS_URL, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "success",
            resumos_found: 0,
            ciencia_sent: 0,
            completos_found: 0,
            sefaz_cstat: "656",
            sefaz_xmotivo:
              "Rejeicao: Consumo Indevido (Deve ser aguardado 1 hora para efetuar nova solicitacao caso nao existam mais documentos a serem pesquisados. Tente apos 1 hora)",
            results: [],
          }),
        })
      } else {
        await route.continue()
      }
    })

    await loginViaUI(page, user)
    await page.goto("/execucao/captura")
    await page.waitForLoadState("domcontentloaded")

    const btn = page.getByRole("button", { name: /buscar resumos/i }).first()
    await expect(btn).toBeVisible({ timeout: 15_000 })
    await btn.click()

    const card = page.getByTestId("nfe-card-656")
    await expect(card).toBeVisible({ timeout: 10_000 })
    await expect(card).toContainText(/sem documentos novos/i)
    await expect(card).toContainText(/nova consulta a cada hora/i)

    // <details> começa colapsado — cstat 656 NÃO aparece ainda
    await expect(card).not.toContainText(/cStat 656/)

    // Expandir e verificar que o detalhe técnico aparece
    const summary = card.getByText(/detalhes t[eé]cnicos/i)
    await expect(summary).toBeVisible()
    await summary.click()
    await expect(card).toContainText(/cStat 656/)
    await expect(card).toContainText(/Consumo Indevido/i)
  })

  test("status=rate_limited_by_sefaz — gate adaptativo (card azul)", async ({
    page,
  }) => {
    await page.route(NFE_RESUMOS_URL, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "rate_limited_by_sefaz",
            retry_after_seconds: 2400,
            message:
              "SEFAZ exige aguardar antes da proxima consulta (NT 2014.002). Proxima janela em cerca de 40 min.",
            resumos_found: 0,
            ciencia_sent: 0,
            completos_found: 0,
            results: [],
          }),
        })
      } else {
        await route.continue()
      }
    })

    await loginViaUI(page, user)
    await page.goto("/execucao/captura")
    await page.waitForLoadState("domcontentloaded")

    const btn = page.getByRole("button", { name: /buscar resumos/i }).first()
    await expect(btn).toBeVisible({ timeout: 15_000 })
    await btn.click()

    const card = page.getByTestId("nfe-rate-limited")
    await expect(card).toBeVisible({ timeout: 10_000 })
    await expect(card).toContainText(/aguardando janela sefaz/i)
    await expect(card).toContainText(/40 min/i)

    // NÃO expõe cstat/xmotivo — é payload friendly puro
    await expect(card).not.toContainText(/cStat/i)
    await expect(card).not.toContainText(/Consumo Indevido/i)
  })

  test("cStat 137 — vazio com <details> colapsado", async ({ page }) => {
    await page.route(NFE_RESUMOS_URL, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "success",
            resumos_found: 0,
            ciencia_sent: 0,
            completos_found: 0,
            sefaz_cstat: "137",
            sefaz_xmotivo: "Nenhum documento localizado",
            results: [],
          }),
        })
      } else {
        await route.continue()
      }
    })

    await loginViaUI(page, user)
    await page.goto("/execucao/captura")
    await page.waitForLoadState("domcontentloaded")

    const btn = page.getByRole("button", { name: /buscar resumos/i }).first()
    await expect(btn).toBeVisible({ timeout: 15_000 })
    await btn.click()

    const card = page.getByTestId("nfe-card-summary")
    await expect(card).toBeVisible({ timeout: 10_000 })
    await expect(card).toContainText(/0 resumo/i)
    await expect(card).toContainText(/0 ci[eê]ncia/i)

    // cStat 137 começa colapsado no <details>
    await expect(card).not.toContainText(/cStat 137/)
    const summary = card.getByText(/detalhes t[eé]cnicos SEFAZ/i)
    await expect(summary).toBeVisible()
    await summary.click()
    await expect(card).toContainText(/cStat 137/)
    await expect(card).toContainText(/Nenhum documento localizado/i)
  })
})
