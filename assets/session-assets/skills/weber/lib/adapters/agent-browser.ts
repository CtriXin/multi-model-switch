/**
 * agent-browser Adapter - 封装 agent-browser CLI
 */

import { execFile } from 'child_process'
import { promisify } from 'util'
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

const exec = promisify(execFile)

const AB = 'agent-browser'

export class AgentBrowserAdapter implements BrowserAdapter {
  readonly name = 'agent-browser'

  async isAvailable(): Promise<boolean> {
    try {
      await exec(AB, ['--version'])
      return true
    } catch {
      return false
    }
  }

  async open(url: string, opts?: OpenOptions): Promise<Session> {
    const sessionName = opts?.sessionName || `weber-${Date.now()}`
    await exec(AB, ['open', url])
    return {
      id: sessionName,
      backend: this.name,
      url,
      _native: { sessionName },
    }
  }

  async close(_session: Session): Promise<void> {
    await exec(AB, ['close'])
  }

  async navigate(session: Session, url: string): Promise<void> {
    await exec(AB, ['open', url])
    session.url = url
  }

  async click(_session: Session, target: string): Promise<void> {
    await exec(AB, ['click', target])
  }

  async type(_session: Session, target: string, text: string, opts?: TypeOptions): Promise<void> {
    await exec(AB, ['fill', target, text])
    if (opts?.pressEnter) {
      await exec(AB, ['press', 'Enter'])
    }
  }

  async scroll(_session: Session, direction: 'up' | 'down' | 'left' | 'right', amount?: number): Promise<void> {
    const amt = String(amount || 500)
    await exec(AB, ['scroll', direction, amt])
  }

  async evaluate(_session: Session, expression: string): Promise<any> {
    const { stdout } = await exec(AB, ['eval', expression])
    return stdout.trim()
  }

  async screenshot(_session: Session, opts?: ScreenshotOptions): Promise<ScreenshotResult> {
    const outPath = opts?.path || join(tmpdir(), `ab-${Date.now()}.png`)
    const args = ['screenshot']
    if (opts?.fullPage) args.push('--full')
    args.push(outPath)

    await exec(AB, args)
    const buffer = await readFile(outPath)

    return { buffer, path: outPath, format: opts?.format || 'png' }
  }

  async snapshot(_session: Session): Promise<SnapshotResult> {
    const { stdout } = await exec(AB, ['snapshot'])
    const text = stdout.trim()
    const refs = parseAgentBrowserRefs(text)

    return {
      text,
      refs,
      url: await this.getCurrentUrl(),
      truncated: false,
    }
  }

  private async getCurrentUrl(): Promise<string> {
    try {
      const { stdout } = await exec(AB, ['get', 'url'])
      return stdout.trim()
    } catch {
      return ''
    }
  }
}

// ─── Ref parser ─────────────────────────────────────────────────────

/**
 * 解析 agent-browser snapshot 中的元素引用
 * 格式: [button @e1] Submit  [link @e2] Learn more
 */
function parseAgentBrowserRefs(text: string): ElementRef[] {
  const refs: ElementRef[] = []
  const regex = /\[(\w+)\s+@?(e\d+)\]\s*([^\[]*)/g
  let match
  while ((match = regex.exec(text)) !== null) {
    refs.push({
      ref: `@${match[2]}`,
      role: match[1],
      name: match[3].trim(),
    })
  }
  return refs
}
