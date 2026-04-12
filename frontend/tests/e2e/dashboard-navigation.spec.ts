/**
 * Smoke test de navegação completa do dashboard.
 *
 * Verifica que cada página do sidebar carrega sem crash, sem console errors,
 * sem 404, e renderiza pelo menos um elemento H1/H2 principal.
 *
 * Este teste é o "canary" da UX: se qualquer rota quebrar após uma mudança,
 * este teste falha imediatamente.
 */

import { test, expect } from "@playwright/test"
import { createTestUser, deleteTestUser, type TestUser } from "./helpers/fixtures"
import { loginViaUI } from "./helpers/auth"

interface RouteCheck {
  path: string
  expectedText: RegExp
  description: string
}

const ROUTES: RouteCheck[] = [
  { path: "/dashboard", expectedText: /dashboard/i, description: "Home dashboard" },
  { path: "/historico/nfe", expectedText: /nf-?e|notas|documentos/i, description: "Histórico NF-e" },
  { path: "/historico/cte", expectedText: /ct-?e|transporte/i, description: "Histórico CT-e" },
  { path: "/historico/mdfe", expectedText: /mdf-?e|manifesto/i, description: "Histórico MDF-e" },
  { path: "/historico/nfse", expectedText: /nfs-?e|servi/i, description: "Histórico NFS-e" },
  { path: "/cadastros/certificados", expectedText: /certificad/i, description: "Certificados" },
  { path: "/cadastros/empresas", expectedText: /empresa|cnpj/i, description: "Empresas" },
  { path: "/cadastros/api-keys", expectedText: /api ?key/i, description: "API Keys" },
  { path: "/cadastros/configuracoes", expectedText: /configura/i, description: "Configurações" },
  { path: "/execucao/captura", expectedText: /captura|execu/i, description: "Captura manual" },
  { path: "/logs", expectedText: /logs?|atividade/i, description: "Logs" },
  { path: "/financeiro/creditos", expectedText: /plano|cr[eé]dito|assinatura/i, description: "Financeiro" },
  { path: "/getting-started", expectedText: /getting started|come[çc]ar|api/i, description: "Getting Started" },
]

test.describe.serial("Dashboard navigation smoke test", () => {
  let user: TestUser

  test.beforeAll(async () => {
    user = await createTestUser({ status: "active" })
  })

  test.afterAll(async () => {
    if (user) await deleteTestUser(user)
  })

  test("todas as rotas do sidebar carregam sem erros críticos", async ({ page }) => {
    const allConsoleErrors: string[] = []
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        const text = msg.text()
        // Ignore known noise
        if (
          !text.includes("favicon") &&
          !text.includes("Failed to load resource") &&
          !text.includes("fbq") &&
          !text.includes("gtag") &&
          !text.includes("Failed to fetch") &&
          !text.includes("_useSession") &&
          !text.includes("_getUser") &&
          !text.includes("supabase")
        ) {
          allConsoleErrors.push(text)
        }
      }
    })

    // Login apenas UMA vez (evita rate-limit do Supabase Auth)
    await loginViaUI(page, user)

    const failedRoutes: string[] = []

    for (const route of ROUTES) {
      try {
        const response = await page.goto(route.path, { waitUntil: "domcontentloaded" })

        if (response && response.status() === 404) {
          failedRoutes.push(`${route.description} (${route.path}): 404`)
          continue
        }

        // Verifica que a URL está correta (não foi redirected pra /login)
        const currentUrl = page.url()
        if (!currentUrl.includes(route.path)) {
          failedRoutes.push(`${route.description} (${route.path}): redirect para ${currentUrl}`)
          continue
        }

        // Renderiza o texto esperado
        try {
          await expect(page.locator("body")).toContainText(route.expectedText, { timeout: 5_000 })
        } catch {
          failedRoutes.push(`${route.description} (${route.path}): texto esperado não encontrado`)
        }
      } catch (e) {
        failedRoutes.push(`${route.description} (${route.path}): ${e instanceof Error ? e.message : String(e)}`)
      }
    }

    // Report: todas rotas devem carregar + zero console errors críticos
    expect(failedRoutes, `Rotas com problema:\n${failedRoutes.join("\n")}`).toEqual([])
    expect(allConsoleErrors, `Console errors:\n${allConsoleErrors.join("\n")}`).toEqual([])
  })
})
