import { test, expect } from '@playwright/test'

test.describe('MMS Web V2', () => {
  test('loads chat page by default', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/chat/)
    await expect(page.getByText('多模型对话')).toBeVisible()
  })

  test('navigates between Chat and Discuss via new session buttons', async ({ page }) => {
    await page.goto('/chat')
    // Click "新讨论" button in sidebar
    await page.getByText('新讨论').first().click()
    await expect(page).toHaveURL(/\/discuss/)
    await expect(page.getByText('多模型讨论')).toBeVisible()

    // Click "新对话" button in sidebar
    await page.getByText('新对话').first().click()
    await expect(page).toHaveURL(/\/chat/)
  })

  test('toggles platform between desktop and mobile', async ({ page }) => {
    await page.goto('/chat')
    await expect(page.locator('aside')).toBeVisible()

    // Switch to mobile
    await page.getByText('移动端').click()
    await expect(page.locator('aside')).not.toBeVisible()

    // Open drawer and switch back to desktop
    await page.locator('header button').first().click()
    await page.getByText('桌面端').click()
    await expect(page.locator('aside')).toBeVisible()
  })

  test('auto-detects mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/chat')
    // Should auto-switch to mobile layout (no sidebar)
    await expect(page.locator('aside')).not.toBeVisible()
    // Menu button should be visible
    await expect(page.locator('header button').first()).toBeVisible()
  })

  test('command palette opens with Cmd+K', async ({ page }) => {
    await page.goto('/chat')
    await page.keyboard.press('Meta+k')
    await expect(page.getByPlaceholder('输入命令...')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByPlaceholder('输入命令...')).not.toBeVisible()
  })

  test('input bar disabled without models', async ({ page }) => {
    await page.goto('/chat')
    const textarea = page.locator('textarea')
    await expect(textarea).toBeDisabled()
    await expect(textarea).toHaveAttribute('placeholder', /请先选择/)
  })

  test('mobile model sheet opens', async ({ page }) => {
    await page.goto('/chat')
    // Switch to mobile
    await page.getByText('移动端').click()
    // Click model picker button (Layers icon)
    await page.locator('header button').last().click()
    await expect(page.getByText('选择模型', { exact: true })).toBeVisible()
  })

  test('theme toggles between dark and light', async ({ page }) => {
    await page.emulateMedia({ colorScheme: 'dark' })
    await page.goto('/chat')
    const html = page.locator('html')
    await expect(html).not.toHaveClass(/light/)

    // Click theme toggle (Sun icon in sidebar)
    await page.locator('aside button[title="浅色模式"]').click()
    await expect(html).toHaveClass(/light/)

    // Toggle back
    await page.locator('aside button[title="深色模式"]').click()
    await expect(html).not.toHaveClass(/light/)
  })

  test('settings page is accessible', async ({ page }) => {
    await page.goto('/chat')
    await page.getByText('设置').click()
    await expect(page).toHaveURL(/\/settings/)
    await expect(page.getByText('外观')).toBeVisible()
    await expect(page.getByText('MMS Pro')).toBeVisible()
  })

  test('models management page is accessible', async ({ page }) => {
    await page.goto('/chat')
    await page.getByText('模型管理').first().click()
    await expect(page).toHaveURL(/\/models/)
    await expect(page.getByRole('heading', { name: 'CLAUDE', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'OPENAI', exact: true })).toBeVisible()
  })

  test('create new session shows in history', async ({ page }) => {
    await page.goto('/chat')
    await expect(page.getByText('暂无历史会话')).toBeVisible()

    await page.getByText('新对话').first().click()
    await expect(page.getByText('新对话', { exact: false }).first()).toBeVisible()
  })

  test('mobile drawer opens with menu button', async ({ page }) => {
    await page.goto('/chat')
    // Switch to mobile
    await page.getByText('移动端').click()
    // Click menu button
    await page.locator('header button').first().click()
    // Drawer should show new session buttons
    await expect(page.getByText('新对话').first()).toBeVisible()
    await expect(page.getByText('新讨论').first()).toBeVisible()
  })
})
