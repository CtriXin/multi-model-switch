/**
 * Camoufox Adapter - 封装 Camoufox REST API (localhost:9377)
 */

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

const DEFAULT_BASE = 'http://localhost:9377'

export class CamoufoxAdapter implements BrowserAdapter {
  readonly name = 'camoufox'
  private baseUrl: string
  private userId: string

  constructor(opts?: { baseUrl?: string; userId?: string }) {
    this.baseUrl = opts?.baseUrl || DEFAULT_BASE
    this.userId = opts?.userId || 'weber-agent'
  }

  async isAvailable(): Promise<boolean> {
    try {
      const resp = await fetch(`${this.baseUrl}/health`)
      const data = await resp.json() as any
      return data.ok === true
    } catch {
      return false
    }
  }

  async open(url: string, opts?: OpenOptions): Promise<Session> {
    const sessionKey = `task-${Date.now()}`
    const resp = await this.post('/tabs', { userId: this.userId, sessionKey, url })
    return {
      id: resp.tabId,
      backend: this.name,
      url: resp.url || url,
      _native: { userId: this.userId, tabId: resp.tabId },
    }
  }

  async close(session: Session): Promise<void> {
    const { userId, tabId } = session._native
    await this.request('DELETE', `/tabs/${tabId}?userId=${userId}`)
  }

  async navigate(session: Session, url: string): Promise<void> {
    const { userId, tabId } = session._native
    await this.post(`/tabs/${tabId}/navigate`, { userId, url })
    session.url = url
  }

  async click(session: Session, target: string): Promise<void> {
    const { userId, tabId } = session._native
    const body: any = { userId }
    if (target.startsWith('e') && /^\d+$/.test(target.slice(1))) {
      body.ref = target
    } else {
      body.selector = target
    }
    await this.post(`/tabs/${tabId}/click`, body)
  }

  async type(session: Session, target: string, text: string, opts?: TypeOptions): Promise<void> {
    const { userId, tabId } = session._native
    const body: any = { userId, text }
    if (target.startsWith('e') && /^\d+$/.test(target.slice(1))) {
      body.ref = target
    } else {
      body.selector = target
    }
    if (opts?.pressEnter) body.pressEnter = true
    await this.post(`/tabs/${tabId}/type`, body)
  }

  async scroll(session: Session, direction: 'up' | 'down' | 'left' | 'right', amount?: number): Promise<void> {
    const { userId, tabId } = session._native
    await this.post(`/tabs/${tabId}/scroll`, { userId, direction, amount: amount || 500 })
  }

  async evaluate(session: Session, expression: string): Promise<any> {
    const { userId, tabId } = session._native
    const resp = await this.post(`/tabs/${tabId}/evaluate`, { userId, expression })
    return resp.result
  }

  async screenshot(session: Session, opts?: ScreenshotOptions): Promise<ScreenshotResult> {
    const { userId, tabId } = session._native
    const params = new URLSearchParams({ userId })
    if (opts?.fullPage) params.set('fullPage', 'true')

    const resp = await fetch(`${this.baseUrl}/tabs/${tabId}/screenshot?${params}`)
    const arrayBuf = await resp.arrayBuffer()
    const buffer = Buffer.from(arrayBuf)

    if (opts?.path) {
      const fs = await import('fs/promises')
      await fs.writeFile(opts.path, buffer)
    }

    return { buffer, path: opts?.path, format: 'png' }
  }

  async snapshot(session: Session): Promise<SnapshotResult> {
    const { userId, tabId } = session._native
    const resp = await fetch(`${this.baseUrl}/tabs/${tabId}/snapshot?userId=${userId}`)
    const data = await resp.json() as any

    const text = data.snapshot || ''
    const refs = parseCamoufoxRefs(text)

    return {
      text,
      refs,
      url: data.url || session.url,
      truncated: data.truncated || false,
    }
  }

  // ─── HTTP helpers ────────────────────────────────────────────────

  private async post(path: string, body: any): Promise<any> {
    return this.request('POST', path, body)
  }

  private async request(method: string, path: string, body?: any): Promise<any> {
    const opts: RequestInit = {
      method,
      headers: { 'Content-Type': 'application/json' },
    }
    if (body) opts.body = JSON.stringify(body)

    const resp = await fetch(`${this.baseUrl}${path}`, opts)
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`Camoufox ${method} ${path} failed (${resp.status}): ${text}`)
    }
    const ct = resp.headers.get('content-type') || ''
    if (ct.includes('application/json')) {
      return resp.json()
    }
    return resp.text()
  }
}

// ─── Ref parser ─────────────────────────────────────────────────────

/**
 * 解析 Camoufox a11y snapshot 文本中的元素引用
 * 格式: [button e1] Submit  [link e2] Learn more
 */
function parseCamoufoxRefs(text: string): ElementRef[] {
  const refs: ElementRef[] = []
  const regex = /\[(\w+)\s+(e\d+)\]\s*([^\[]*)/g
  let match
  while ((match = regex.exec(text)) !== null) {
    refs.push({
      ref: match[2],
      role: match[1],
      name: match[3].trim(),
    })
  }
  return refs
}
