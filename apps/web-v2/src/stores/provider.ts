import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { saveApiKey, getApiKey, deleteApiKey, clearAll as clearAllKeys, listProviderIds } from '@/services/keychain'
import { useToastStore } from './toast'

export interface ProviderConfig {
  id: string
  name: string
  type: 'openrouter' | 'openai-compatible' | 'anthropic-compatible'
  baseUrl: string
  enabled: boolean
  builtIn: boolean
  models?: string[] // whitelist filter — empty = all
}

const BUILTIN_PROVIDERS: ProviderConfig[] = [
  {
    id: 'openrouter',
    name: 'OpenRouter',
    type: 'openrouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    enabled: true,
    builtIn: true,
  },
]

const STORAGE_KEY = 'mms-providers'

function loadProviders(): ProviderConfig[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return BUILTIN_PROVIDERS.map((p) => ({ ...p }))
    const saved: ProviderConfig[] = JSON.parse(raw)
    // Merge: ensure all builtins exist
    const result = BUILTIN_PROVIDERS.map((bp) => {
      const override = saved.find((s) => s.id === bp.id)
      return override ? { ...bp, ...override, builtIn: true } : { ...bp }
    })
    // Add non-builtin saved providers
    for (const s of saved) {
      if (!result.find((r) => r.id === s.id)) {
        result.push({ ...s, builtIn: false })
      }
    }
    return result
  } catch {
    return BUILTIN_PROVIDERS.map((p) => ({ ...p }))
  }
}

function persistProviders(providers: ProviderConfig[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(providers))
}

export const useProviderStore = defineStore('provider', () => {
  const providers = ref<ProviderConfig[]>(loadProviders())
  /** Tracks which provider IDs have a saved API key */
  const keyStatus = ref<Record<string, boolean>>({})

  const enabledProviders = computed(() =>
    providers.value.filter((p) => p.enabled),
  )

  const configuredProviders = computed(() =>
    enabledProviders.value.filter((p) => keyStatus.value[p.id]),
  )

  function save() {
    persistProviders(providers.value)
  }

  function addProvider(config: Omit<ProviderConfig, 'builtIn'>) {
    if (providers.value.find((p) => p.id === config.id)) return
    providers.value.push({ ...config, builtIn: false })
    save()
  }

  function removeProvider(id: string) {
    const p = providers.value.find((p) => p.id === id)
    if (!p || p.builtIn) return
    providers.value = providers.value.filter((p) => p.id !== id)
    deleteApiKey(id)
    delete keyStatus.value[id]
    save()
  }

  function updateProvider(id: string, patch: Partial<ProviderConfig>) {
    const idx = providers.value.findIndex((p) => p.id === id)
    if (idx < 0) return
    providers.value[idx] = { ...providers.value[idx], ...patch, id }
    save()
  }

  function getProvider(id: string): ProviderConfig | undefined {
    return providers.value.find((p) => p.id === id)
  }

  /** Refresh keyStatus from IndexedDB */
  async function refreshKeyStatus() {
    const ids = await listProviderIds()
    const status: Record<string, boolean> = {}
    for (const id of ids) status[id] = true
    keyStatus.value = status
  }

  /** Save API key and update status */
  async function setApiKey(providerId: string, key: string) {
    await saveApiKey(providerId, key)
    keyStatus.value[providerId] = true
  }

  /** Remove API key and update status */
  async function removeApiKey(providerId: string) {
    await deleteApiKey(providerId)
    delete keyStatus.value[providerId]
    keyStatus.value = { ...keyStatus.value }
  }

  /** Clear all credentials and reset status */
  async function clearAllCredentials() {
    await clearAllKeys()
    keyStatus.value = {}
  }

  /** Import config JSON (providers + keys) */
  async function importConfig(json: string) {
    const toast = useToastStore()
    try {
      const data = JSON.parse(json)
      if (data.version !== 1 || !Array.isArray(data.providers)) {
        toast.error('配置格式无效')
        return false
      }
      let importedCount = 0
      for (const p of data.providers) {
        if (!p.id || !p.baseUrl) continue
        const existing = providers.value.find((e) => e.id === p.id)
        if (existing) {
          // Update existing
          Object.assign(existing, {
            name: p.name ?? existing.name,
            type: p.type ?? existing.type,
            baseUrl: p.baseUrl ?? existing.baseUrl,
            enabled: p.enabled ?? true,
          })
        } else {
          providers.value.push({
            id: p.id,
            name: p.name ?? p.id,
            type: p.type ?? 'openai-compatible',
            baseUrl: p.baseUrl,
            enabled: p.enabled ?? true,
            builtIn: false,
            models: p.models,
          })
        }
        // Import API key if present
        if (p.apiKey) {
          await saveApiKey(p.id, p.apiKey)
          keyStatus.value[p.id] = true
        }
        importedCount++
      }
      save()
      toast.success(`成功导入 ${importedCount} 个通道配置`)
      return true
    } catch (e: any) {
      toast.error('导入失败: ' + e.message)
      return false
    }
  }

  /** Export config (without API keys) */
  function exportConfig(): string {
    return JSON.stringify(
      {
        version: 1,
        providers: providers.value.map((p) => ({
          id: p.id,
          name: p.name,
          type: p.type,
          baseUrl: p.baseUrl,
          enabled: p.enabled,
          models: p.models,
        })),
      },
      null,
      2,
    )
  }

  return {
    providers,
    keyStatus,
    enabledProviders,
    configuredProviders,
    addProvider,
    removeProvider,
    updateProvider,
    getProvider,
    refreshKeyStatus,
    setApiKey,
    removeApiKey,
    clearAllCredentials,
    importConfig,
    exportConfig,
  }
})
