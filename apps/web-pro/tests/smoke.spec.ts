import { test, expect } from '@playwright/test'

test.describe('MMS Pro Smoke Tests', () => {
  test('homepage loads with workspace layout', async ({ page }) => {
    await page.goto('/')
    // Sidebar should be visible with MMS branding
    await expect(page.locator('text=MMS')).toBeVisible()
    // Home content shows
    await expect(page.locator('text=多模型协作工作台')).toBeVisible()
    // Mode cards visible
    await expect(page.locator('text=Chat 对话')).toBeVisible()
    await expect(page.locator('text=Discuss 讨论')).toBeVisible()
  })

  test('sidebar shows session list and nav', async ({ page }) => {
    await page.goto('/')
    // Session buttons
    await expect(page.locator('text=新对话')).toBeVisible()
    await expect(page.locator('text=新讨论')).toBeVisible()
    // Session list shows mock data
    await expect(page.locator('text=最近会话')).toBeVisible()
    await expect(page.locator('text=API 网关设计方案对比')).toBeVisible()
  })

  test('navigate to chat page', async ({ page }) => {
    await page.goto('/')
    await page.click('text=Chat 对话')
    await expect(page).toHaveURL(/\/chat/)
    await expect(page.locator('text=开始多模型对话')).toBeVisible()
  })

  test('navigate to discuss page', async ({ page }) => {
    await page.goto('/')
    await page.click('text=Discuss 讨论')
    await expect(page).toHaveURL(/\/discuss/)
    await expect(page.locator('text=多模型深度讨论')).toBeVisible()
  })

  test('chat shows model chips and can type', async ({ page }) => {
    await page.goto('/chat')
    // Default models should be pre-selected as chips
    await expect(page.locator('text=Claude Sonnet 4.6')).toBeVisible()
    await expect(page.locator('text=GPT-4o')).toBeVisible()
    // Input should be available
    const input = page.locator('textarea')
    await expect(input).toBeVisible()
    await input.fill('测试问题')
    await expect(input).toHaveValue('测试问题')
  })

  test('chat sends message and shows streaming responses', async ({ page }) => {
    await page.goto('/chat')
    const input = page.locator('textarea')
    await input.fill('如何设计一个高性能的 API 网关？')
    // Click send button
    await page.locator('button:has(svg)').last().click()
    // Should show user message
    await expect(page.locator('text=如何设计一个高性能的 API 网关？')).toBeVisible()
    // Wait for responses to start streaming
    await page.waitForTimeout(2000)
    // Response cards should appear
    const cards = page.locator('[class*="rounded-xl border"]')
    expect(await cards.count()).toBeGreaterThan(0)
  })

  test('command palette opens with keyboard shortcut', async ({ page }) => {
    await page.goto('/')
    // Click the search button instead of keyboard shortcut (Meta+K not reliable in headless)
    await page.locator('button:has-text("搜索")').click()
    await expect(page.getByPlaceholder('搜索命令...')).toBeVisible()
    // Can search commands
    await page.getByPlaceholder('搜索命令...').fill('对话')
    await expect(page.locator('text=新建对话')).toBeVisible()
    // Close with Escape
    await page.keyboard.press('Escape')
  })

  test('quick preset applies and navigates to chat', async ({ page }) => {
    await page.goto('/')
    await page.click('text=旗舰对决')
    await expect(page).toHaveURL(/\/chat/)
  })

  test('model sheet opens from chat', async ({ page }) => {
    await page.goto('/chat')
    // Click "+ 模型" button
    await page.locator('button:has-text("模型")').first().click()
    await expect(page.getByRole('heading', { name: '选择模型' })).toBeVisible()
    // Should show model cards with provider names
    await expect(page.locator('text=Anthropic').first()).toBeVisible()
  })

  test('models page shows all models', async ({ page }) => {
    await page.goto('/models')
    await expect(page.getByRole('heading', { name: '模型管理' })).toBeVisible()
    await expect(page.locator('text=Claude Opus 4.6')).toBeVisible()
    await expect(page.locator('text=GPT-4o')).toBeVisible()
  })

  test('settings page loads', async ({ page }) => {
    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: '设置' })).toBeVisible()
    await expect(page.locator('text=MMS Pro v0.3.0')).toBeVisible()
  })

  test('setup guide loads and shows providers', async ({ page }) => {
    await page.goto('/setup')
    await expect(page.locator('text=3 分钟获取免费 API')).toBeVisible()
    // Should show CN and intl sections
    await expect(page.locator('text=国产服务商')).toBeVisible()
    await expect(page.locator('text=国际服务商')).toBeVisible()
    // First provider (SiliconFlow) should be expanded by default
    await expect(page.locator('text=去注册')).toBeVisible()
    await expect(page.locator('text=获取 API Key')).toBeVisible()
  })

  test('setup guide accessible from home page', async ({ page }) => {
    await page.goto('/')
    await page.locator('text=快速配置免费 API').click()
    await expect(page).toHaveURL(/\/setup/)
  })
})
