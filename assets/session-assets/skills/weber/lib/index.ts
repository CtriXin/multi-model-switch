/**
 * Unified Browser - 统一浏览器操作入口
 *
 * Usage:
 *   import { createBrowser } from './lib'
 *
 *   const browser = createBrowser({ backend: 'auto' })
 *   const session = await browser.open('https://example.com')
 *   await browser.click(session, 'button.submit')
 *   const shot = await browser.screenshot(session, { path: '/tmp/result.png' })
 *   await browser.close(session)
 */

export type {
  BrowserAdapter,
  Session,
  ScreenshotResult,
  SnapshotResult,
  ElementRef,
  OpenOptions,
  ScreenshotOptions,
  TypeOptions,
  BackendName,
  BrowserConfig,
} from './unified-browser'

export { DEFAULT_CONFIG } from './unified-browser'
export { CamoufoxAdapter } from './adapters/camoufox'
export { PlaywrightAdapter } from './adapters/playwright'
export { AgentBrowserAdapter } from './adapters/agent-browser'
export { WebAccessAdapter } from './adapters/web-access'
export { createAdapter, checkAvailability, probeAll, withFallback, selectAdapters } from './fallback'

import type { BrowserAdapter, BrowserConfig, BackendName } from './unified-browser'
import { DEFAULT_CONFIG } from './unified-browser'
import { selectAdapters, withFallback } from './fallback'

// ─── Factory ────────────────────────────────────────────────────────

export interface UnifiedBrowser {
  /** 当前使用的 adapter（auto 模式下可能变化） */
  readonly active: BrowserAdapter
  /** 所有可用 adapter */
  readonly adapters: BrowserAdapter[]
  /** 执行操作（自动降级） */
  exec: <T>(operation: (adapter: BrowserAdapter) => Promise<T>) => Promise<T>
}

/**
 * 创建统一浏览器实例
 *
 * @example
 * // 自动选后端
 * const ub = createBrowser()
 * const session = await ub.exec(a => a.open('https://example.com'))
 *
 * @example
 * // 指定后端
 * const ub = createBrowser({ backend: 'camoufox' })
 *
 * @example
 * // 带配置
 * const ub = createBrowser({
 *   backend: 'auto',
 *   backends: { camoufox: { baseUrl: 'http://localhost:9377' } }
 * })
 */
export async function createBrowser(config?: Partial<BrowserConfig>): Promise<UnifiedBrowser> {
  const cfg = { ...DEFAULT_CONFIG, ...config }
  const backend = cfg.requireLoggedInChrome ? 'web-access' : (cfg.backend || 'auto')
  const fallbackOrder: BackendName[] = cfg.requireLoggedInChrome
    ? ['web-access']
    : (cfg.fallbackOrder || DEFAULT_CONFIG.fallbackOrder!)
  const adapters = await selectAdapters(
    backend,
    fallbackOrder,
    cfg.backends
  )

  return {
    active: adapters[0],
    adapters,
    exec: <T>(operation: (adapter: BrowserAdapter) => Promise<T>) =>
      withFallback(adapters, operation, {
        onFallback: (from, to, err) => {
          console.warn(`[unified-browser] ${from} -> ${to}: ${err.message}`)
        },
      }),
  }
}

// ─── Convenience functions ──────────────────────────────────────────

/**
 * 快捷函数：创建浏览器 → 执行操作 → 关闭
 */
export async function withBrowser<T>(
  operation: (browser: UnifiedBrowser) => Promise<T>,
  config?: Partial<BrowserConfig>
): Promise<T> {
  const browser = await createBrowser(config)
  try {
    return await operation(browser)
  } finally {
    // 清理：关闭所有 adapter 的 session（如需）
  }
}
