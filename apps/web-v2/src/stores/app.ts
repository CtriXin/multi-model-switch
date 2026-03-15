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

export type ModelSelectionMode = 'chat' | 'committee'

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: '#f59e0b',
  openai: '#10b981',
  google: '#3b82f6',
  deepseek: '#ef4444',
  moonshot: '#0ea5e9',
  meta: '#ef4444',
  mistral: '#ff6f00',
  qwen: '#14b8a6',
  siliconflow: '#6366f1',
  zhipu: '#2563eb',
  groq: '#f97316',
  openrouter: '#8b5cf6',
  dashscope: '#7c3aed',
  lingyiwanwu: '#10b981',
  baichuan: '#d946ef',
  stepfun: '#f43f5e',
  minimax: '#ec4899',
  nvidia: '#84cc16',
  together: '#14b8a6',
  fireworks: '#f59e0b',
  demo: '#6b7280',
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
  const committeeSelectedModelIds = ref<string[]>([])
  const initialized = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const selectedModels = computed(() =>
    selectedModelIds.value
      .map(id => models.value.find(m => m.id === id))
      .filter(Boolean) as ModelMeta[]
  )

  const committeeSelectedModels = computed(() =>
    committeeSelectedModelIds.value
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
          const key = provider.type === 'mock' ? 'demo' : await getApiKey(provider.id)
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
    committeeSelectedModelIds.value = committeeSelectedModelIds.value.filter(
      (id) => models.value.some((m) => m.id === id),
    )
    ensureCommitteeSelection()
  }

  function getSelectionRef(mode: ModelSelectionMode = 'chat') {
    return mode === 'committee' ? committeeSelectedModelIds : selectedModelIds
  }

  function toggleModel(id: string, mode: ModelSelectionMode = 'chat') {
    const selection = getSelectionRef(mode)
    const idx = selection.value.indexOf(id)
    if (idx >= 0) {
      selection.value.splice(idx, 1)
    } else if (selection.value.length < 5) {
      selection.value.push(id)
    }
  }

  function applyPreset(preset: Preset, mode: ModelSelectionMode = 'chat') {
    // Only apply model IDs that exist in current model list
    const available = preset.models.filter((id) =>
      models.value.some((m) => m.id === id),
    )
    if (available.length) {
      getSelectionRef(mode).value = [...available]
    } else {
      useToastStore().info('预设中的模型不可用，请先配置对应通道')
    }
  }

  function clearSelection(mode: ModelSelectionMode = 'chat') {
    getSelectionRef(mode).value = []
  }

  function pickDiverseModels(count = 3): string[] {
    const byProvider: Record<string, ModelMeta[]> = {}
    for (const m of models.value) {
      ;(byProvider[m.provider] ??= []).push(m)
    }
    const providers = Object.keys(byProvider).sort((a, b) => {
      const aTop = Math.max(...byProvider[a].map((m) => m.tier))
      const bTop = Math.max(...byProvider[b].map((m) => m.tier))
      return bTop - aTop
    })
    const picked: string[] = []
    for (const provider of providers) {
      if (picked.length >= count) break
      const pool = [...byProvider[provider]].sort((a, b) => b.tier - a.tier)
      if (pool[0]) picked.push(pool[0].id)
    }
    if (picked.length >= count) return picked

    const remaining = [...models.value]
      .sort((a, b) => b.tier - a.tier || a.name.localeCompare(b.name))
      .map((model) => model.id)
    for (const id of remaining) {
      if (picked.length >= count) break
      if (!picked.includes(id)) picked.push(id)
    }
    return picked
  }

  function randomPick(count = 3, mode: ModelSelectionMode = 'chat') {
    getSelectionRef(mode).value = pickDiverseModels(count)
  }

  function copySelection(from: ModelSelectionMode, to: ModelSelectionMode) {
    const src = getSelectionRef(from).value
    getSelectionRef(to).value = [...src]
  }

  function ensureCommitteeSelection() {
    if (committeeSelectedModelIds.value.length || !models.value.length) return
    if (selectedModelIds.value.length) {
      committeeSelectedModelIds.value = [...selectedModelIds.value]
      return
    }
    committeeSelectedModelIds.value = pickDiverseModels(3)
  }

  return {
    models,
    presets,
    selectedModelIds,
    selectedModels,
    committeeSelectedModelIds,
    committeeSelectedModels,
    modelsByCategory, initialized, loading, error,
    initialize,
    refreshModels,
    toggleModel,
    applyPreset,
    clearSelection,
    randomPick,
    copySelection,
    ensureCommitteeSelection,
  }
})
