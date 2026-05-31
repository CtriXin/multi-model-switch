/**
 * Playwright Adapter - 封装 Playwright Node.js API
 */

import { existsSync, readdirSync } from 'fs'
import { createRequire } from 'module'
import { homedir, userInfo } from 'os'
import { join } from 'path'
import { pathToFileURL } from 'url'

import type {
  BrowserAdapter,
  Session,
  ScreenshotResult,
  SnapshotResult,
  ElementRef,
  OpenOptions,
  ScreenshotOptions,
  TypeOptions,
} from '../unified-browser'

// Lazy-loaded playwright module
let _playwright: any = null
const requireFromHere = createRequire(import.meta.url)

async function getPlaywright() {
  if (!_playwright) {
    const candidates = [process.env.PLAYWRIGHT_MODULE_PATH, 'playwright'].filter(Boolean) as string[]
    for (const specifier of candidates) {
      try {
        _playwright = await importPlaywright(specifier)
        break
      } catch { /* try next */ }
    }
    if (!_playwright) throw new Error('Playwright not installed. Run: npm install playwright')
  }
  return _playwright
}

async function importPlaywright(specifier: string): Promise<any> {
  try {
    return await import(specifier)
  } catch (directError) {
    const resolved = requireFromHere.resolve(specifier, { paths: moduleSearchPaths() })
    try {
      return await import(pathToFileURL(resolved).href)
    } catch {
      throw directError
    }
  }
}

function moduleSearchPaths(): string[] {
  const homes = hostHomeCandidates()
  const paths = [process.cwd(), ...homes]
  for (const home of homes) {
    paths.push(join(home, '.npm/_npx'))
    paths.push(...npxRunDirs(home))
  }
  return [...new Set(paths)]
}

function npxRunDirs(home: string): string[] {
  const root = join(home, '.npm/_npx')
  if (!existsSync(root)) return []
  try {
    return readdirSync(root, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => join(root, entry.name))
  } catch {
    return []
  }
}

function hostHomeCandidates(): string[] {
  const candidates = [
    process.env.WEB_ACCESS_HOST_HOME,
    process.env.HOST_HOME,
    process.env.REAL_HOME,
    safeUserHome(),
    homedir(),
  ].filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
  return [...new Set(candidates)]
}

function safeUserHome(): string {
  try {
    return userInfo().homedir
  } catch {
    return ''
  }
}

export class PlaywrightAdapter implements BrowserAdapter {
  readonly name = 'playwright'
  private browser: any = null
  private executablePath?: string
  private headless: boolean

  constructor(opts?: { executablePath?: string; headless?: boolean }) {
    this.executablePath = opts?.executablePath
    this.headless = opts?.headless !== false
  }

  async isAvailable(): Promise<boolean> {
    try {
      await getPlaywright()
      return true
    } catch {
      return false
    }
  }

  async open(url: string, opts?: OpenOptions): Promise<Session> {
    const pw = await getPlaywright()
    const chromium = pw.chromium || pw.default?.chromium

    if (!this.browser) {
      const launchOpts: any = { headless: this.headless }
      if (this.executablePath) launchOpts.executablePath = this.executablePath
      this.browser = await chromium.launch(launchOpts)
    }

    const viewport = opts?.viewport || { width: 1920, height: 1080 }
    const context = await this.browser.newContext({ viewport })
    const page = await context.newPage()
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 })

    return {
      id: `pw-${Date.now()}`,
      backend: this.name,
      url,
      _native: { context, page },
    }
  }

  async close(session: Session): Promise<void> {
    const { context, page } = session._native
    try { await page?.close() } catch { /* ok */ }
    try { await context?.close() } catch { /* ok */ }
    // 如果没有其他 session，关闭 browser
    if (this.browser) {
      try {
        const contexts = this.browser.contexts()
        if (contexts.length === 0) {
          await this.browser.close()
          this.browser = null
        }
      } catch { /* ok */ }
    }
  }

  async navigate(session: Session, url: string): Promise<void> {
    const { page } = session._native
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 })
    session.url = url
  }

  async click(session: Session, target: string): Promise<void> {
    const { page } = session._native
    // Playwright 支持 ref 格式 e1 → 转为 CSS 或用 locator
    const selector = normalizeSelector(target)
    await page.locator(selector).click({ timeout: 10000 })
  }

  async type(session: Session, target: string, text: string, opts?: TypeOptions): Promise<void> {
    const { page } = session._native
    const selector = normalizeSelector(target)
    await page.locator(selector).fill(text)
    if (opts?.pressEnter) {
      await page.keyboard.press('Enter')
    }
  }

  async scroll(session: Session, direction: 'up' | 'down' | 'left' | 'right', amount?: number): Promise<void> {
    const { page } = session._native
    const delta = amount || 500
    const sign = direction === 'down' || direction === 'right' ? 1 : -1
    const axis = direction === 'up' || direction === 'down' ? 'y' : 'x'
    await page.mouse.wheel(axis === 'x' ? sign * delta : 0, axis === 'y' ? sign * delta : 0)
  }

  async evaluate(session: Session, expression: string): Promise<any> {
    const { page } = session._native
    return page.evaluate(expression)
  }

  async screenshot(session: Session, opts?: ScreenshotOptions): Promise<ScreenshotResult> {
    const { page } = session._native
    const buf: Buffer = await page.screenshot({
      fullPage: opts?.fullPage || false,
      type: opts?.format || 'png',
    })

    if (opts?.path) {
      const fs = await import('fs/promises')
      await fs.writeFile(opts.path, buf)
    }

    return { buffer: buf, path: opts?.path, format: opts?.format || 'png' }
  }

  async snapshot(session: Session): Promise<SnapshotResult> {
    const { page } = session._native

    // 尝试 Playwright 内置 accessibility snapshot
    let text = ''
    let refs: ElementRef[] = []
    try {
      const axTree = await page.accessibility.snapshot({ interestingOnly: false })
      if (axTree) {
        text = formatA11yTree(axTree)
        refs = extractA11yRefs(axTree)
      }
    } catch {
      // fallback: 取页面标题和 URL
      text = `Title: ${await page.title()}\nURL: ${page.url()}`
    }

    return {
      text,
      refs,
      url: page.url(),
      truncated: false,
    }
  }
}

// ─── Helpers ────────────────────────────────────────────────────────

/**
 * 将 ref 格式 (e1) 转换为 Playwright 可用的 selector
 */
function normalizeSelector(target: string): string {
  // e1, e2, ... → 保持原样（可能需要外部映射）
  // 已经是 CSS selector → 直接用
  if (target.startsWith('.') || target.startsWith('#') || target.startsWith('[') || target.includes(' ')) {
    return target
  }
  // 其他情况当作 CSS selector
  return target
}

/**
 * 格式化 a11y tree 为文本
 */
function formatA11yTree(node: any, depth = 0): string {
  const indent = '  '.repeat(depth)
  const role = node.role || ''
  const name = node.name || ''
  let line = `${indent}[${role}] ${name}`

  if (node.children) {
    const childLines = node.children.map((c: any) => formatA11yTree(c, depth + 1))
    line += '\n' + childLines.join('\n')
  }

  return line
}

/**
 * 从 a11y tree 提取元素引用
 */
function extractA11yRefs(node: any, refs: ElementRef[] = [], counter = { n: 0 }): ElementRef[] {
  if (node.role && node.role !== 'WebArea') {
    counter.n++
    refs.push({
      ref: `e${counter.n}`,
      role: node.role,
      name: node.name || '',
    })
  }
  if (node.children) {
    for (const child of node.children) {
      extractA11yRefs(child, refs, counter)
    }
  }
  return refs
}
