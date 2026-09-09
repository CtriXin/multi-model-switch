/**
 * Fallback Chain - 自动降级逻辑
 */

import type { BrowserAdapter, BackendName } from './unified-browser'
import { CamoufoxAdapter } from './adapters/camoufox'
import { PlaywrightAdapter } from './adapters/playwright'
import { AgentBrowserAdapter } from './adapters/agent-browser'
import { WebAccessAdapter } from './adapters/web-access'

// ─── Factory ────────────────────────────────────────────────────────

export function createAdapter(name: BackendName, config?: any): BrowserAdapter {
  const adapterConfig = getBackendConfig(name, config)
  switch (name) {
    case 'camoufox':
      return new CamoufoxAdapter(adapterConfig)
    case 'playwright':
      return new PlaywrightAdapter(adapterConfig)
    case 'agent-browser':
      return new AgentBrowserAdapter()
    case 'web-access':
      return new WebAccessAdapter(adapterConfig)
    default:
      throw new Error(`Unknown backend: ${name}`)
  }
}

function getBackendConfig(name: BackendName, config?: any): any {
  if (!config || typeof config !== 'object') return config
  if (Object.prototype.hasOwnProperty.call(config, name)) return config[name]
  return config
}

// ─── Health Check ───────────────────────────────────────────────────

export async function checkAvailability(name: BackendName, config?: any): Promise<boolean> {
  try {
    const adapter = createAdapter(name, config)
    return await adapter.isAvailable()
  } catch {
    return false
  }
}

export async function probeAll(config?: any): Promise<Record<BackendName, boolean>> {
  const backends: BackendName[] = ['web-access', 'playwright', 'agent-browser', 'camoufox']
  const results: Partial<Record<BackendName, boolean>> = {}

  await Promise.all(
    backends.map(async (name) => {
      results[name] = await checkAvailability(name, config)
    })
  )

  return results as Record<BackendName, boolean>
}

// ─── Fallback Executor ──────────────────────────────────────────────

/**
 * 按优先级尝试多个后端，直到成功
 */
export async function withFallback<T>(
  adapters: BrowserAdapter[],
  operation: (adapter: BrowserAdapter) => Promise<T>,
  opts?: { onFallback?: (from: string, to: string, error: Error) => void }
): Promise<T> {
  let lastError: Error | null = null

  for (const adapter of adapters) {
    try {
      return await operation(adapter)
    } catch (e) {
      lastError = e as Error
      const nextIdx = adapters.indexOf(adapter) + 1
      if (nextIdx < adapters.length) {
        const next = adapters[nextIdx]
        opts?.onFallback?.(adapter.name, next.name, lastError)
      }
    }
  }

  throw new Error(`All adapters failed. Last error: ${lastError?.message}`)
}

// ─── Auto-selector ──────────────────────────────────────────────────

/**
 * 根据配置和可用性，返回按优先级排列的 adapter 列表
 */
export async function selectAdapters(
  preferred: BackendName | 'auto',
  fallbackOrder: BackendName[],
  config?: any
): Promise<BrowserAdapter[]> {
  if (preferred !== 'auto') {
    const adapter = createAdapter(preferred, config)
    const available = await adapter.isAvailable()
    if (available) {
      // 指定后端可用，但仍附加降级链
      const fallbacks = fallbackOrder
        .filter((b) => b !== preferred)
        .map((b) => createAdapter(b, config))
      return [adapter, ...fallbacks]
    }
    // 指定后端不可用，走 auto
  }

  // Auto: 按优先级探测
  const adapters: BrowserAdapter[] = []
  for (const name of fallbackOrder) {
    const adapter = createAdapter(name, config)
    const available = await adapter.isAvailable()
    if (available) {
      adapters.push(adapter)
    }
  }

  if (adapters.length === 0) {
    throw new Error('No browser backend available')
  }

  return adapters
}
