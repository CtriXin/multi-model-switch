/**
 * web-access Adapter - 封装 web-access CDP HTTP API (localhost:3456)
 */

import { execFile } from 'child_process'
import { existsSync, readFileSync } from 'fs'
import { readFile } from 'fs/promises'
import { homedir, tmpdir, userInfo } from 'os'
import { join } from 'path'
import { promisify } from 'util'

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
const DEFAULT_CHECK_TIMEOUT_MS = 30_000
const exec = promisify(execFile)

export class WebAccessAdapter implements BrowserAdapter {
  readonly name = 'web-access'
  private baseUrl: string
  private checkDepsScript?: string
  private hostHome?: string
  private autoStart: boolean
  private refSelectors = new Map<string, Map<string, string>>()

  constructor(opts?: { baseUrl?: string; checkDepsScript?: string; hostHome?: string; autoStart?: boolean }) {
    this.baseUrl = opts?.baseUrl || process.env.MMS_WEB_ACCESS_PROXY_URL || process.env.MMS_WEB_ACCESS_PROXY || hostContextString('web_access', 'proxy_url') || DEFAULT_BASE
    this.checkDepsScript = opts?.checkDepsScript
    this.hostHome = opts?.hostHome
    this.autoStart = opts?.autoStart !== false
  }

  async isAvailable(): Promise<boolean> {
    if (await this.targetsAvailable()) return true
    if (!this.autoStart) return false
    try {
      await this.ensureProxy()
    } catch {
      return false
    }
    return this.targetsAvailable()
  }

  private async targetsAvailable(): Promise<boolean> {
    try {
      const resp = await fetch(`${this.baseUrl}/targets`)
      if (!resp.ok) return false
      const body = await resp.json().catch(() => undefined)
      return Array.isArray(body)
    } catch {
      return false
    }
  }

  private async ensureProxy(): Promise<void> {
    const script = this.resolveCheckDepsScript()
    if (!script) return
    const hostHome = this.resolveHostHome()
    await exec(process.execPath, [script], {
      timeout: DEFAULT_CHECK_TIMEOUT_MS,
      env: {
        ...process.env,
        WEB_ACCESS_HOST_HOME: hostHome,
        HOST_HOME: hostHome,
        REAL_HOME: hostHome,
      },
    })
  }

  private resolveCheckDepsScript(): string | undefined {
    const hostHome = this.resolveHostHome()
    const candidates = [
      this.checkDepsScript,
      process.env.WEB_ACCESS_CHECK_DEPS,
      process.env.MMS_WEB_ACCESS_CHECK_DEPS,
      hostContextString('web_access', 'check_deps'),
      join(hostHome, '.codex/skills/web-access/scripts/check-deps.mjs'),
      join(hostHome, '.claude/skills/web-access/scripts/check-deps.mjs'),
    ].filter(Boolean) as string[]
    return candidates.find((candidate) => existsSync(candidate))
  }

  private resolveHostHome(): string {
    const candidates = [
      this.hostHome,
      process.env.WEB_ACCESS_HOST_HOME,
      process.env.HOST_HOME,
      process.env.REAL_HOME,
      hostContextString('host', 'home'),
      safeUserHome(),
      homedir(),
    ].filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    return candidates[0] || homedir()
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
    await this.get(`/close?target=${encodeURIComponent(targetId)}`)
    this.refSelectors.delete(targetId)
  }

  async navigate(session: Session, url: string): Promise<void> {
    const { targetId } = session._native
    await this.get(`/navigate?target=${encodeURIComponent(targetId)}&url=${encodeURIComponent(url)}`)
    session.url = url
    this.refSelectors.delete(targetId)
  }

  async click(session: Session, target: string): Promise<void> {
    const { targetId } = session._native
    const selector = this.resolveTarget(session, target)
    // 使用 clickAt（真实鼠标事件）而非 click（JS el.click()）
    await this.post(`/clickAt?target=${encodeURIComponent(targetId)}`, selector)
  }

  async type(session: Session, target: string, text: string, opts?: TypeOptions): Promise<void> {
    const { targetId } = session._native
    const selector = this.resolveTarget(session, target)
    const selectorJson = JSON.stringify(selector)
    const textJson = JSON.stringify(text)
    // web-access 没有原生 type，用 eval + JS fill
    const js = `
      (() => {
        const selector = ${selectorJson};
        const text = ${textJson};
        const el = document.querySelector(selector);
        if (!el) throw new Error('Element not found: ' + selector);
        el.focus();
        if ('value' in el) {
          el.value = text;
        } else if (el.isContentEditable) {
          el.textContent = text;
        } else {
          el.textContent = text;
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      })()
    `
    await this.post(`/eval?target=${encodeURIComponent(targetId)}`, js)

    if (opts?.pressEnter) {
      await this.post(`/eval?target=${encodeURIComponent(targetId)}`, `
        (() => {
          const selector = ${selectorJson};
          const el = document.querySelector(selector);
          if (!el) throw new Error('Element not found: ' + selector);
          el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
          el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', keyCode: 13, bubbles: true }));
          return true;
        })()
      `)
    }
  }

  async scroll(session: Session, direction: 'up' | 'down' | 'left' | 'right', amount?: number): Promise<void> {
    const { targetId } = session._native
    const y = direction === 'down' ? (amount || 500) : -(amount || 500)
    await this.get(`/scroll?target=${encodeURIComponent(targetId)}&y=${y}`)
  }

  async evaluate(session: Session, expression: string): Promise<any> {
    const { targetId } = session._native
    const resp = await this.post(`/eval?target=${encodeURIComponent(targetId)}`, expression)
    const data = await resp.json() as any
    return getEvalValue(data)
  }

  async screenshot(session: Session, opts?: ScreenshotOptions): Promise<ScreenshotResult> {
    const { targetId } = session._native
    const outPath = opts?.path || join(tmpdir(), `wa-${Date.now()}.png`)
    await this.get(`/screenshot?target=${encodeURIComponent(targetId)}&file=${encodeURIComponent(outPath)}`)

    const buffer = await readFile(outPath)
    return { buffer, path: outPath, format: 'png' }
  }

  async snapshot(session: Session): Promise<SnapshotResult> {
    const { targetId } = session._native
    // web-access 无内置 snapshot，用 JS 提取 a11y 信息
    const js = `
      (() => {
        const selectorFor = (el) => {
          if (el.id && globalThis.CSS && typeof globalThis.CSS.escape === 'function') {
            return '#' + globalThis.CSS.escape(el.id);
          }
          if (el.id && /^[A-Za-z][\\w-]*$/.test(el.id)) return '#' + el.id;
          const parts = [];
          let node = el;
          while (node && node.nodeType === Node.ELEMENT_NODE && node !== document.body) {
            let part = node.tagName.toLowerCase();
            const parent = node.parentElement;
            if (parent) {
              const sameTag = Array.from(parent.children).filter(child => child.tagName === node.tagName);
              if (sameTag.length > 1) part += ':nth-of-type(' + (sameTag.indexOf(node) + 1) + ')';
            }
            parts.unshift(part);
            if (parts.length >= 6) break;
            node = parent;
          }
          return parts.join(' > ');
        };
        return Array.from(document.querySelectorAll('button, a, input, textarea, select, [role], [aria-label]')).map(el => {
          const role = el.getAttribute('role') || el.tagName.toLowerCase();
          const label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
          const text = el.textContent?.trim().substring(0, 50) || '';
          const value = 'value' in el ? String(el.value || '').substring(0, 50) : '';
          const name = label || text || value;
          const tag = el.tagName.toLowerCase();
          const className = typeof el.className === 'string' ? el.className.substring(0, 30) : '';
          return { role, name, tag, id: el.id, className, selector: selectorFor(el) };
        });
      })()
    `
    const resp = await this.post(`/eval?target=${encodeURIComponent(targetId)}`, js)
    const data = await resp.json() as any
    const elements = toElementArray(getEvalValue(data))
    const selectorMap = new Map<string, string>()

    const refs: ElementRef[] = elements.map((el: any, i: number) => ({
      ref: `e${i + 1}`,
      role: el.role,
      name: el.name,
    }))
    elements.forEach((el: any, i: number) => {
      if (el.selector) selectorMap.set(`e${i + 1}`, el.selector)
    })
    this.refSelectors.set(targetId, selectorMap)

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

  private resolveTarget(session: Session, target: string): string {
    const ref = target.startsWith('@') ? target.slice(1) : target
    if (/^e\d+$/.test(ref)) {
      const selector = this.refSelectors.get(session._native.targetId)?.get(ref)
      if (selector) return selector
    }
    return target
  }
}

function safeUserHome(): string {
  try {
    return userInfo().homedir
  } catch {
    return ''
  }
}

let hostContextCache: any | undefined

function hostContextString(section: string, key: string): string {
  const context = readHostContext()
  const table = context?.[section]
  if (!table || typeof table !== 'object') return ''
  const value = table[key]
  return typeof value === 'string' || typeof value === 'number' ? String(value).trim() : ''
}

function readHostContext(): any {
  if (hostContextCache !== undefined) return hostContextCache
  const path = process.env.MMS_HOST_CONTEXT_JSON || process.env.MMS_HOST_CAPABILITIES_JSON || ''
  if (!path || !existsSync(path)) {
    hostContextCache = null
    return hostContextCache
  }
  try {
    hostContextCache = JSON.parse(readFileSync(path, 'utf-8'))
  } catch {
    hostContextCache = null
  }
  return hostContextCache
}

function getEvalValue(data: any): any {
  if (data && typeof data === 'object') {
    if (Object.prototype.hasOwnProperty.call(data, 'value')) return data.value
    if (Object.prototype.hasOwnProperty.call(data, 'result')) return data.result
  }
  return data
}

function toElementArray(value: any): any[] {
  if (Array.isArray(value)) return value
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}
