import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  // 1 retry apenas — testes que hit Supabase/backend real podem ter flakiness
  // de timing (criação de N tenants em sequência durante a suite completa).
  // Retry absorve isso sem mascarar bug real: se falhar 2x, é bug real.
  retries: 1,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    // Use production server (next start) — much faster cold-start than turbopack dev.
    // Run `npm run build` first manually if .next is missing.
    command: "npx next start -p 3000",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },
})
