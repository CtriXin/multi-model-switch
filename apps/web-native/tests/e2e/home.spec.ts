import { test, expect } from '@playwright/test'

test('web-native home page loads correctly', async ({ page }) => {
  await page.goto('http://localhost:5179')

  // Wait for the page to load
  await page.waitForSelector('h1', { timeout: 5000 })

  // Check if the title is correct
  await expect(page.locator('h1')).toContainText('Multi-Model Studio')

  // Take a screenshot
  await page.screenshot({ path: 'test-results/home-page.png', fullPage: true })
})

test('web-native workspace mode switching', async ({ page }) => {
  await page.goto('http://localhost:5179')

  // Wait for the page to load
  await page.waitForSelector('button:has-text("Chat")', { timeout: 5000 })

  // Click on Chat mode
  await page.click('button:has-text("Chat")')

  // Wait for the workspace to load
  await page.waitForSelector('[class*="glass"]', { timeout: 5000 })

  // Take a screenshot
  await page.screenshot({ path: 'test-results/chat-mode.png', fullPage: true })

  // Go back and try Discuss mode
  await page.goBack()
  await page.waitForSelector('button:has-text("Discuss")', { timeout: 5000 })

  // Click on Discuss mode
  await page.click('button:has-text("Discuss")')

  // Wait for the workspace to load
  await page.waitForSelector('[class*="glass"]', { timeout: 5000 })

  // Take a screenshot
  await page.screenshot({ path: 'test-results/discuss-mode.png', fullPage: true })
})

test('web-native model selection', async ({ page }) => {
  await page.goto('http://localhost:5179')

  // Wait for the page to load
  await page.waitForSelector('button:has-text("Chat")', { timeout: 5000 })

  // Click on Chat mode
  await page.click('button:has-text("Chat")')

  // Wait for the workspace to load
  await page.waitForSelector('[class*="glass"]', { timeout: 5000 })

  // Click on model selection button
  await page.click('button:has-text("模型")')

  // Wait for the model sheet to open
  await page.waitForSelector('text=选择模型', { timeout: 5000 })

  // Take a screenshot
  await page.screenshot({ path: 'test-results/model-selection.png', fullPage: true })

  // Select a model
  await page.click('button:has-text("Claude 4")')

  // Take another screenshot
  await page.screenshot({ path: 'test-results/model-selected.png', fullPage: true })
})
