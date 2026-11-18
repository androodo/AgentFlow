import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: process.env.AGENTFLOW_WEB_URL ?? 'http://127.0.0.1:3001',
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
    viewport: { width: 1440, height: 950 },
  },
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 12_000 },
  reporter: 'list',
})
