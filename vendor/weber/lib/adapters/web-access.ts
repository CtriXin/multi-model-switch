/**
 * web-access Adapter - 封装 web-access CDP HTTP API (localhost:3456)
 */

import { readFile, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'

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

const DEFAULT_BASE = 'http://localhost:3456'

export class WebAccessAdapter implements BrowserAdapter {
  readonly name = 'web-access'
  private baseUrl: string

  constructor(opts?: { baseUrl?: string }) {
    this.baseUrl = opts?.baseUrl || DEFAULT_BASE
  }

  async isAvailable(): Promise<boolean> {
    try {
      const resp = await fetch(`${this.baseUrl}/targets`)
      return resp.ok
    } catch {
      return false
    }
  }

  async open(url: string, _opts?: OpenOptions): Promise<Session> {
    const resp = await this.get(`/new?url=${encodeURIComponent(url)}`)
    const data = await resp.json() as any
    const targetId = data.id || data.targetId

    if (!targetId) throw new Error('web-access: no target ID returned')

    return {
      id: targetId,
      backend: this.name,
      url,
      _native: { targetId },
    }
  }

  async close(session: Session): Promise<void> {
    const { targetId } = session._native
    await this.get(`/close?target=${targetId}`)
  }

  async navigate(session: Session, url: string): Promise<void> {
    const { targetId } = session._native
    await this.get(`/navigate?target=${targetId}&url=${encodeURIComponent(url)}`)
    session.url = url
  }

  async click(session: Session, target: string): Promise<void> {
    const { targetId } = session._native
    // 使用 clickAt（真实鼠标事件）而非 click（JS el.click()）
    await this.post(`/clickAt?target=${targetId}`, target)
  }

  async type(session: Session, target: string, text: string, opts?: TypeOptions): Promise<void> {
    const { targetId } = session._native
    // web-access 没有原生 type，用 eval + JS fill
    const escapedText = text.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
    const js = `
      (() => {
        const el = document.querySelector('${target}');
        if (!el) throw new Error('Element not found: ${target}');
        el.focus();
        el.value = '${escapedText}';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      })()
    `
    await this.post(`/eval?target=${targetId}`, js)

    if (opts?.pressEnter) {
      await this.post(`/eval?target=${targetId}`, `
        document.querySelector('${target}')?.dispatchEvent(
          new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true })
        )
      `)
    }
  }

  async scroll(session: Session, direction: 'up' | 'down' | 'left' | 'right', amount?: number): Promise<void> {
    const { targetId } = session._native
    const y = direction === 'down' ? (amount || 500) : -(amount || 500)
    await this.get(`/scroll?target=${targetId}&y=${y}`)
  }

  async evaluate(session: Session, expression: string): Promise<any> {
    const { targetId } = session._native
    const resp = await this.post(`/eval?target=${targetId}`, expression)
    const data = await resp.json() as any
    return data.result
  }

  async screenshot(session: Session, opts?: ScreenshotOptions): Promise<ScreenshotResult> {
    const { targetId } = session._native
    const outPath = opts?.path || join(tmpdir(), `wa-${Date.now()}.png`)
    await this.get(`/screenshot?target=${targetId}&file=${encodeURIComponent(outPath)}`)

    const buffer = await readFile(outPath)
    return { buffer, path: outPath, format: 'png' }
  }

  async snapshot(session: Session): Promise<SnapshotResult> {
    const { targetId } = session._native
    // web-access 无内置 snapshot，用 JS 提取 a11y 信息
    const js = `
      (() => {
        const items = [];
        document.querySelectorAll('button, a, input, textarea, select, [role], [aria-label]').forEach(el => {
          const role = el.getAttribute('role') || el.tagName.toLowerCase();
          const name = el.getAttribute('aria-label') || el.textContent?.trim().substring(0, 50) || '';
          const tag = el.tagName.toLowerCase();
          items.push({ role, name, tag, id: el.id, className: el.className?.substring?.(0, 30) });
        });
        return JSON.stringify(items);
      })()
    `
    const resp = await this.post(`/eval?target=${targetId}`, js)
    const data = await resp.json() as any
    let elements: any[] = []
    try {
      elements = JSON.parse(data.result || '[]')
    } catch { /* ok */ }

    const refs: ElementRef[] = elements.map((el: any, i: number) => ({
      ref: `e${i + 1}`,
      role: el.role,
      name: el.name,
    }))

    const text = elements
      .map((el: any, i: number) => `[${el.role} e${i + 1}] ${el.name}`)
      .join('\n')

    return {
      text,
      refs,
      url: session.url,
      truncated: false,
    }
  }

  // ─── HTTP helpers ────────────────────────────────────────────────

  private async get(path: string): Promise<Response> {
    const resp = await fetch(`${this.baseUrl}${path}`)
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`web-access GET ${path} failed (${resp.status}): ${text}`)
    }
    return resp
  }

  private async post(path: string, body: string): Promise<Response> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body,
    })
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`web-access POST ${path} failed (${resp.status}): ${text}`)
    }
    return resp
  }
}
