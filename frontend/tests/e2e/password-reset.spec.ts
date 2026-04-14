import { test, expect } from "@playwright/test"

/**
 * E2E: fluxo de recuperação de senha.
 *
 * Cobre:
 *   1. Link "Esqueci minha senha" aparece na página de login
 *   2. Página /forgot-password renderiza e aceita email
 *   3. Submit chama Supabase.auth.resetPasswordForEmail (interceptado)
 *   4. Após submit, mostra mensagem de sucesso (genérica, sem user enumeration)
 *   5. Página /reset-password renderiza mensagem de "link inválido" quando
 *      acessada diretamente (sem token de recovery)
 *
 * O fluxo completo com e-mail real não é testado aqui — isso requer
 * SMTP + inbox + clique em link real, que é fora do escopo do Playwright
 * local. O teste valida a parte determinística (UI + integração com a
 * API do Supabase client).
 */

test.describe("Password reset flow", () => {
  test("página de login mostra link 'Esqueci minha senha'", async ({ page }) => {
    await page.goto("/login")
    const link = page.getByRole("link", { name: /esqueci minha senha/i })
    await expect(link).toBeVisible()

    // Clicar no link deve levar pra /forgot-password
    await link.click()
    await expect(page).toHaveURL(/.*forgot-password/)
  })

  test("página /forgot-password renderiza form com campo de email", async ({
    page,
  }) => {
    await page.goto("/forgot-password")

    // CardTitle no shadcn/ui é um <div> estilizado, não heading HTML —
    // usa getByText em vez de getByRole.
    await expect(page.getByText(/esqueci minha senha/i).first()).toBeVisible()
    await expect(page.getByLabel(/e-?mail/i)).toBeVisible()
    await expect(
      page.getByRole("button", { name: /enviar link/i })
    ).toBeVisible()
  })

  test("botão de enviar fica desabilitado com email vazio", async ({ page }) => {
    await page.goto("/forgot-password")

    const submitBtn = page.getByRole("button", { name: /enviar link/i })
    await expect(submitBtn).toBeDisabled()

    // Preenche o email — botão habilita
    await page.getByLabel(/e-?mail/i).fill("qualquer@email.com")
    await expect(submitBtn).toBeEnabled()
  })

  test("submit exibe mensagem de sucesso (mesmo se email não existir)", async ({
    page,
  }) => {
    // Intercepta a chamada ao Supabase recovery — a gente simula sucesso
    // sem depender de SMTP real. Endpoint: /auth/v1/recover
    await page.route(/\/auth\/v1\/recover/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      })
    })

    await page.goto("/forgot-password")
    await page.getByLabel(/e-?mail/i).fill("teste.reset@example.com")
    await page.getByRole("button", { name: /enviar link/i }).click()

    // Mensagem genérica de sucesso — sem revelar se o email existe
    await expect(
      page.getByText(/se o e-mail estiver cadastrado.*receberá um link/i)
    ).toBeVisible({ timeout: 5_000 })

    // Botão "Voltar para o login" aparece
    await expect(
      page.getByRole("link", { name: /voltar para o login/i })
    ).toBeVisible()
  })

  test("página /reset-password mostra mensagem de link inválido quando acessada sem token", async ({
    page,
  }) => {
    // Acesso direto sem fragment de recovery — o client não vai receber
    // o evento PASSWORD_RECOVERY, então deve mostrar a mensagem de "link
    // inválido".
    await page.goto("/reset-password")

    // Aguarda o componente renderizar (useEffect do onAuthStateChange roda
    // no mount, mas sem token não dispara PASSWORD_RECOVERY).
    await expect(
      page.getByText(/link de recuperação expirou ou é inválido/i)
    ).toBeVisible({ timeout: 5_000 })

    // CTA pra solicitar novo link
    await expect(
      page.getByRole("link", { name: /solicitar novo link/i })
    ).toBeVisible()
  })
})
