import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: 'http://localhost:5188',
    headless: true,
  },
  webServer: {
    command: 'npm run dev',
    port: 5188,
    reuseExistingServer: true,
    timeout: 15_000,
  },
})
