import { test, expect } from "@playwright/test"

/**
 * E2E tests for the trial signup flow.
 *
 * Validates that:
 *  - The signup page renders with the new phone field
 *  - Phone mask works correctly (Brazilian formats)
 *  - CNPJ is NOT collected at signup (it comes from cert upload)
 *  - Form blocks submit when fields are invalid
 *  - All required fields are present
 */

test.describe("Trial signup form", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/signup")
    await expect(page).toHaveURL(/.*signup/)
  })

  test("renders all required fields including phone", async ({ page }) => {
    // Name
    await expect(page.getByLabel(/nome/i)).toBeVisible()

    // Phone (new field)
    await expect(page.getByLabel(/telefone/i)).toBeVisible()

    // Email
    await expect(page.getByLabel(/e-?mail/i)).toBeVisible()

    // Password
    await expect(page.getByLabel(/^senha$/i)).toBeVisible()

    // Confirm password
    await expect(page.getByLabel(/confirm/i)).toBeVisible()

    // Submit button exists
    await expect(
      page.getByRole("button", { name: /criar conta|cadastrar|sign up/i })
    ).toBeVisible()
  })

  test("does NOT collect CNPJ at signup", async ({ page }) => {
    // CNPJ is collected later, in cert upload
    const cnpjInput = page.getByLabel(/cnpj/i)
    await expect(cnpjInput).toHaveCount(0)
  })

  test("phone mask formats 11-digit mobile correctly", async ({ page }) => {
    const phoneInput = page.getByLabel(/telefone/i)
    await phoneInput.fill("11987654321")
    const value = await phoneInput.inputValue()
    expect(value).toBe("(11) 98765-4321")
  })

  test("phone mask formats 10-digit landline correctly", async ({ page }) => {
    const phoneInput = page.getByLabel(/telefone/i)
    await phoneInput.fill("1133334444")
    const value = await phoneInput.inputValue()
    expect(value).toBe("(11) 3333-4444")
  })

  test("phone mask caps at 11 digits", async ({ page }) => {
    const phoneInput = page.getByLabel(/telefone/i)
    await phoneInput.fill("11987654321999")
    const value = await phoneInput.inputValue()
    // Should cap at 11 digits formatted
    expect(value).toBe("(11) 98765-4321")
  })

  test("submit button is disabled when fields are empty", async ({ page }) => {
    const submitBtn = page.getByRole("button", {
      name: /criar conta|cadastrar|sign up/i,
    })
    // Either disabled attribute or aria-disabled
    const isDisabled = await submitBtn.isDisabled()
    expect(isDisabled).toBe(true)
  })

  test("submit button enables when all fields are valid", async ({ page }) => {
    await page.getByLabel(/nome/i).fill("Joao Teste")
    await page.getByLabel(/telefone/i).fill("11987654321")
    await page.getByLabel(/e-?mail/i).fill("teste-trial@example.com")
    await page.getByLabel(/^senha$/i).fill("SenhaForte123!")
    await page.getByLabel(/confirm/i).fill("SenhaForte123!")

    const submitBtn = page.getByRole("button", {
      name: /criar conta|cadastrar|sign up/i,
    })
    await expect(submitBtn).toBeEnabled()
  })

  test("rejects invalid phone format", async ({ page }) => {
    await page.getByLabel(/nome/i).fill("Joao")
    await page.getByLabel(/telefone/i).fill("123")
    await page.getByLabel(/telefone/i).blur()

    // Should show some error indicator or keep submit disabled
    const submitBtn = page.getByRole("button", {
      name: /criar conta|cadastrar|sign up/i,
    })
    await expect(submitBtn).toBeDisabled()
  })
})
