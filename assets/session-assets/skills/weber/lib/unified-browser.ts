/**
 * Unified Browser Adapter - 统一浏览器操作接口
 *
 * 屏蔽 Camoufox/Playwright/agent-browser/web-access 后端差异，
 * 提供统一的 open/click/type/screenshot/snapshot/scroll/eval/close 操作。
 */

// ─── Types ──────────────────────────────────────────────────────────

export interface Session {
  id: string
  backend: string
  url: string
  /** 后端原生引用（如 Camoufox tabId、Playwright page 等） */
  _native: any
}

export interface ScreenshotResult {
  buffer: Buffer
  path?: string
  format: 'png' | 'jpeg'
}

export interface ElementRef {
  ref: string      // "e1", "@e1", "ref_1"
  role: string     // "button", "textbox", "link"
  name: string     // 可读名称
}

export interface SnapshotResult {
  text: string
  refs: ElementRef[]
  url: string
  truncated: boolean
}

export interface OpenOptions {
  viewport?: { width: number; height: number }
  /** Playwright 专用：指定浏览器可执行路径 */
  executablePath?: string
  /** agent-browser 专用：session 名称 */
  sessionName?: string
}

export interface ScreenshotOptions {
  fullPage?: boolean
  path?: string
  format?: 'png' | 'jpeg'
}

export interface TypeOptions {
  pressEnter?: boolean
}

// ─── Adapter Interface ──────────────────────────────────────────────

export interface BrowserAdapter {
  readonly name: string

  /** 后端是否可用 */
  isAvailable(): Promise<boolean>

  /** 打开页面 */
  open(url: string, opts?: OpenOptions): Promise<Session>

  /** 关闭会话 */
  close(session: Session): Promise<void>

  /** 导航 */
  navigate(session: Session, url: string): Promise<void>

  /** 点击元素（ref 或 CSS selector） */
  click(session: Session, target: string): Promise<void>

  /** 输入文本 */
  type(session: Session, target: string, text: string, opts?: TypeOptions): Promise<void>

  /** 滚动 */
  scroll(session: Session, direction: 'up' | 'down' | 'left' | 'right', amount?: number): Promise<void>

  /** 执行 JS 表达式 */
  evaluate(session: Session, expression: string): Promise<any>

  /** 截图 */
  screenshot(session: Session, opts?: ScreenshotOptions): Promise<ScreenshotResult>

  /** 获取 a11y 快照 */
  snapshot(session: Session): Promise<SnapshotResult>
}

// ─── Adapter Config ─────────────────────────────────────────────────

export type BackendName = 'camoufox' | 'playwright' | 'agent-browser' | 'web-access'

export interface BrowserConfig {
  /** 指定后端或 'auto' 自动选择 */
  backend?: BackendName | 'auto'
  /** 降级优先级（auto 模式下使用） */
  fallbackOrder?: BackendName[]
  /** 任务必须使用用户已登录 Chrome 时，只允许 web-access 路由 */
  requireLoggedInChrome?: boolean
  /** 各后端配置 */
  backends?: {
    camoufox?: { baseUrl?: string }
    playwright?: { executablePath?: string; headless?: boolean }
    'agent-browser'?: { sessionName?: string }
    'web-access'?: { baseUrl?: string; checkDepsScript?: string; hostHome?: string; autoStart?: boolean }
  }
  /** 默认 viewport */
  viewport?: { width: number; height: number }
}

export const DEFAULT_CONFIG: BrowserConfig = {
  backend: 'auto',
  fallbackOrder: ['web-access', 'playwright', 'agent-browser', 'camoufox'],
  viewport: { width: 1920, height: 1080 },
}
