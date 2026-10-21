import { defineConfig, devices } from '@playwright/test'

// End-to-end tests run against a separate API + database (see e2e/README.md).
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5174',
    viewport: { width: 1366, height: 860 },
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 860 } } }],
})
