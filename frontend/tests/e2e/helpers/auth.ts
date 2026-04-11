/**
 * Auth helpers for Playwright tests.
 *
 * loginViaUI navigates to /login and submits the form like a real user.
 */

import { Page, expect } from "@playwright/test"
import type { TestUser } from "./fixtures"

/** Logs in a test user via the real /login form. */
export async function loginViaUI(page: Page, user: TestUser): Promise<void> {
  await page.goto("/login")

  await page.getByLabel(/e-?mail/i).fill(user.email)
  await page.getByLabel(/senha/i).fill(user.password)
  await page.getByRole("button", { name: /entrar/i }).click()

  // The login handler does a hard window.location.href = "/dashboard"
  // so we wait for that navigation to settle.
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 })
}

/** Asserts that the current page is the dashboard (not redirected). */
export async function expectOnDashboard(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/dashboard/)
}
