import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useProviderStore } from './provider'
import { useToastStore } from './toast'
import { fetchModels } from '@/services/api'
import { getApiKey } from '@/services/keychain'

export interface ModelMeta {
  id: string
  name: string
  provider: string
  category: string
  tier: number
  priceInput: number
  priceOutput: number
  tags: string[]
  contextWindow: number
}

export interface Preset {
  id: string
  name: string
  models: string[]
  builtin: boolean
  icon?: string
}

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: '#f59e0b',
  openai: '#10b981',
  google: '#3b82f6',
  deepseek: '#8b5cf6',
  moonshot: '#ec4899',
  meta: '#ef4444',
  mistral: '#f97316',
  qwen: '#14b8a6',
}

export function getModelColor(provider: string): string {
  return PROVIDER_COLORS[provider] ?? '#6366f1'
}

const MOCK_PRESETS: Preset[] = [
  { id: 'preset-coding', name: '编程对决', models: ['anthropic/claude-sonnet-4', 'openai/gpt-4o', 'google/gemini-2.5-pro-preview'], builtin: true, icon: '🏆' },
  { id: 'preset-reasoning', name: '深度推理', models: ['anthropic/claude-opus-4', 'openai/o3', 'deepseek/deepseek-r1'], builtin: true, icon: '🧠' },
  { id: 'preset-fast', name: '快速响应', models: ['anthropic/claude-haiku-3.5', 'openai/gpt-4o-mini', 'google/gemini-2.5-flash-preview'], builtin: true, icon: '⚡' },
  { id: 'preset-balanced', name: '均衡搭配', models: ['anthropic/claude-sonnet-4', 'openai/gpt-4o', 'deepseek/deepseek-r1', 'google/gemini-2.5-flash-preview'], builtin: true, icon: '🎯' },
  { id: 'preset-economy', name: '经济实惠', models: ['openai/gpt-4o-mini', 'deepseek/deepseek-chat', 'google/gemini-2.5-flash-preview'], builtin: true, icon: '💰' },
]

export const useAppStore = defineStore('app', () => {
  const models = ref<ModelMeta[]>([])
  const presets = ref<Preset[]>(MOCK_PRESETS)
  const selectedModelIds = ref<string[]>([])
  const initialized = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const selectedModels = computed(() =>
    selectedModelIds.value
      .map(id => models.value.find(m => m.id === id))
      .filter(Boolean) as ModelMeta[]
  )

  const modelsByCategory = computed(() => {
    const map: Record<string, ModelMeta[]> = {}
    for (const m of models.value) {
      ;(map[m.category] ??= []).push(m)
    }
    return map
  })

  async function initialize() {
    if (initialized.value) return
    initialized.value = true
    await refreshModels()
  }

  async function refreshModels() {
    const providerStore = useProviderStore()
    await providerStore.refreshKeyStatus()

    const configured = providerStore.configuredProviders
    if (!configured.length) {
      models.value = []
      error.value = '未配置任何 API 通道，请在设置中配置'
      return
    }

    loading.value = true
    error.value = null

    const allModels: ModelMeta[] = []
    const errors: string[] = []

    await Promise.allSettled(
      configured.map(async (provider) => {
        try {
          const key = await getApiKey(provider.id)
          if (!key) return
          const fetched = await fetchModels(provider, key)
          allModels.push(...fetched)
        } catch (e: any) {
          errors.push(`${provider.name}: ${e.message}`)
        }
      }),
    )

    models.value = allModels
    loading.value = false

    if (errors.length) {
      error.value = errors.join('; ')
      useToastStore().error('部分通道加载失败')
    }

    // Clean up selected models that no longer exist
    selectedModelIds.value = selectedModelIds.value.filter(
      (id) => models.value.some((m) => m.id === id),
    )
  }

  function toggleModel(id: string) {
    const idx = selectedModelIds.value.indexOf(id)
    if (idx >= 0) {
      selectedModelIds.value.splice(idx, 1)
    } else if (selectedModelIds.value.length < 5) {
      selectedModelIds.value.push(id)
    }
  }

  function applyPreset(preset: Preset) {
    // Only apply model IDs that exist in current model list
    const available = preset.models.filter((id) =>
      models.value.some((m) => m.id === id),
    )
    if (available.length) {
      selectedModelIds.value = [...available]
    } else {
      useToastStore().info('预设中的模型不可用，请先配置对应通道')
    }
  }

  function clearSelection() {
    selectedModelIds.value = []
  }

  function randomPick(count = 3) {
    const byProvider: Record<string, ModelMeta[]> = {}
    for (const m of models.value) {
      ;(byProvider[m.provider] ??= []).push(m)
    }
    const providers = Object.keys(byProvider)
    for (let i = providers.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[providers[i], providers[j]] = [providers[j], providers[i]]
    }
    const picked: string[] = []
    for (const p of providers) {
      if (picked.length >= count) break
      const pool = byProvider[p]
      picked.push(pool[Math.floor(Math.random() * pool.length)].id)
    }
    selectedModelIds.value = picked
  }

  return {
    models, presets, selectedModelIds, selectedModels,
    modelsByCategory, initialized, loading, error,
    initialize, refreshModels, toggleModel, applyPreset, clearSelection, randomPick,
  }
})
