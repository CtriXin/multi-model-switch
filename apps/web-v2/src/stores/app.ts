import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useProviderStore } from './provider'
import { useToastStore } from './toast'
import { fetchModels } from '@/services/api'
import { getFetchRuntime } from '@/services/runtime'

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
  free: boolean
  supportsVision: boolean
  supportsNativeWebSearch: boolean
  supportsTools: boolean
  capabilitySource: ModelCapabilitySource
  capabilityVerifiedAt: string | null
}

export type ModelCapabilitySource = 'default' | 'heuristic' | 'registry' | 'manual' | 'verified'

export interface Preset {
  id: string
  name: string
  models: string[]
  builtin: boolean
  icon?: string
}

export type ModelSelectionMode = 'chat' | 'committee'
export type ModelPoolTag = 'free' | 'std' | 'pro'

export interface ModelFilterOptions {
  tags?: ModelPoolTag[]
  requireVision?: boolean
}

const MODEL_SUPPRESSION_KEY = 'mms-disabled-models'
const FAILURE_COUNTS_KEY = 'mms-failure-counts'

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
  cerebras: '#f97316',
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

function shuffleArray<T>(items: T[]): T[] {
  const next = [...items]
  for (let i = next.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[next[i], next[j]] = [next[j], next[i]]
  }
  return next
}

const MOCK_PRESETS: Preset[] = [
  { id: 'preset-full-demo', name: '全流程演示', models: ['demo/claude-sonnet-4', 'demo/gpt-4.1', 'demo/gemini-2.5-pro', 'demo/deepseek-r1'], builtin: true, icon: '🎬' },
  { id: 'preset-reasoning', name: '深度推理', models: ['demo/claude-sonnet-4', 'demo/deepseek-r1', 'demo/qwen-max'], builtin: true, icon: '🧠' },
  { id: 'preset-fast', name: '快速响应', models: ['demo/claude-haiku-3.5', 'demo/glm-4.5', 'demo/mistral-large'], builtin: true, icon: '⚡' },
  { id: 'preset-balanced', name: '均衡搭配', models: ['demo/claude-sonnet-4', 'demo/gpt-4.1', 'demo/gemini-2.5-pro', 'demo/qwen-max'], builtin: true, icon: '🎯' },
  { id: 'preset-resilience', name: '故障演练', models: ['demo/offline-strategy-agent', 'demo/throttled-risk-agent', 'demo/claude-sonnet-4'], builtin: true, icon: '🛠️' },
]

export const useAppStore = defineStore('app', () => {
  const models = ref<ModelMeta[]>([])
  const presets = ref<Preset[]>(MOCK_PRESETS)
  const selectedModelIds = ref<string[]>([])
  const committeeSelectedModelIds = ref<string[]>([])
  const initialized = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const preferFree = ref(true)

  function loadSuppressedModelIds() {
    try {
      const raw = localStorage.getItem(MODEL_SUPPRESSION_KEY)
      if (!raw) return new Set<string>()
      const data = JSON.parse(raw) as Record<string, number>
      const now = Date.now()
      const valid = Object.entries(data)
        .filter(([, expiresAt]) => expiresAt > now)
        .map(([id]) => id)
      if (valid.length !== Object.keys(data).length) {
        const next = Object.fromEntries(valid.map((id) => [id, data[id]]))
        localStorage.setItem(MODEL_SUPPRESSION_KEY, JSON.stringify(next))
      }
      return new Set(valid)
    } catch {
      return new Set<string>()
    }
  }

  function persistSuppressedModelIds(ids: Record<string, number>) {
    localStorage.setItem(MODEL_SUPPRESSION_KEY, JSON.stringify(ids))
  }

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
          const runtime = await getFetchRuntime(provider.id)
          if (!runtime) return
          const fetched = await fetchModels(runtime.provider, runtime.apiKey)
          allModels.push(...fetched)
        } catch (e: any) {
          errors.push(`${provider.name}: ${e.message}`)
        }
      }),
    )

    const suppressed = loadSuppressedModelIds()
    models.value = allModels.filter((model) => !suppressed.has(model.id))
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

  function pickDiverseModelIds(pool: ModelMeta[], count = 3): string[] {
    const byProvider: Record<string, ModelMeta[]> = {}
    for (const m of pool) {
      ;(byProvider[m.provider] ??= []).push(m)
    }

    const providers = shuffleArray(Object.keys(byProvider))
    const picked: string[] = []

    for (const provider of providers) {
      if (picked.length >= count) break
      const candidates = shuffleArray(byProvider[provider])
      const candidate = candidates[0]
      if (candidate) picked.push(candidate.id)
    }
    if (picked.length >= count) return picked

    // Fill remaining from broader pool if needed
    const remaining = shuffleArray(pool).map(m => m.id)
    for (const id of remaining) {
      if (picked.length >= count) break
      if (!picked.includes(id)) picked.push(id)
    }
    return picked
  }

  function pickDiverseModels(count = 3): string[] {
    // Keep the general/default diverse pick behavior unchanged for non-random flows.
    const pool = preferFree.value
      ? (models.value.filter(m => m.free).length ? models.value.filter(m => m.free) : models.value)
      : models.value

    return pickDiverseModelIds(pool, count)
  }

  function matchesModelTag(model: ModelMeta, tag: ModelPoolTag): boolean {
    if (tag === 'free') return model.free
    if (tag === 'std') return model.tier === 1
    return model.tier === 2
  }

  function filterModels(options: ModelFilterOptions = {}, source = models.value): ModelMeta[] {
    const tags = options.tags ?? []
    return source.filter((model) => {
      if (options.requireVision && !model.supportsVision) return false
      if (!tags.length) return true
      return tags.some((tag) => matchesModelTag(model, tag))
    })
  }

  function buildDefaultRandomPickPool(count = 3): ModelMeta[] {
    if (!models.value.length) return []

    const tiers = [...new Set(models.value.map(model => model.tier))].sort((left, right) => left - right)
    const highestTier = tiers.at(-1)
    const nonTopPool = highestTier === undefined
      ? []
      : models.value.filter((model) => model.tier < highestTier)

    if (!preferFree.value) return nonTopPool

    const freePool = models.value.filter((model) => model.free)
    if (freePool.length >= count) return freePool

    if (!nonTopPool.length) return freePool

    const nonFreePool = nonTopPool.filter((model) => !model.free)
    if (!nonFreePool.length) return freePool

    const fallbackTier = Math.min(...nonFreePool.map((model) => model.tier))
    const fallbackPool = nonFreePool.filter((model) => model.tier === fallbackTier)
    return [...freePool, ...fallbackPool]
  }

  function buildRandomPickPool(count = 3, options: ModelFilterOptions = {}): ModelMeta[] {
    const hasTagFilter = !!options.tags?.length
    const basePool = hasTagFilter ? models.value : buildDefaultRandomPickPool(count)
    return filterModels(options, basePool)
  }

  function randomPick(count = 3, mode: ModelSelectionMode = 'chat', options: ModelFilterOptions = {}) {
    const pool = buildRandomPickPool(count, options)
    if (!pool.length) {
      useToastStore().info('当前筛选下没有可随机模型')
      return
    }

    const targetCount = Math.min(count, pool.length)
    const picked = pickDiverseModelIds(pool, targetCount)
    getSelectionRef(mode).value = picked
    if (pool.length < count) {
      useToastStore().info(`当前筛选下只有 ${pool.length} 个模型，已全部选中`)
    }
  }

  function replaceSelectedModel(oldId: string, newId: string, mode: ModelSelectionMode = 'chat') {
    const selection = getSelectionRef(mode)
    const idx = selection.value.indexOf(oldId)
    if (idx >= 0) {
      selection.value.splice(idx, 1, newId)
      return
    }
    if (!selection.value.includes(newId) && selection.value.length < 5) {
      selection.value.push(newId)
    }
  }

  function pickReplacementModel(options: {
    excludeIds?: string[]
    requireVision?: boolean
  } = {}): string | null {
    const exclude = new Set(options.excludeIds ?? [])
    const eligible = models.value.filter((model) => {
      if (exclude.has(model.id)) return false
      if (options.requireVision && !model.supportsVision) return false
      return true
    })

    if (!eligible.length) return null

    const preferred = preferFree.value
      ? eligible.filter(model => model.free)
      : eligible

    const pool = preferred.length ? preferred : eligible
    const shuffled = shuffleArray(pool)
    return shuffled[0]?.id ?? null
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

  // Track pending suppressions so we don't show multiple toasts for the same model
  const pendingSuppressions = new Set<string>()

  function suppressModelForToday(modelId: string) {
    const model = models.value.find((item) => item.id === modelId)
    if (!model || pendingSuppressions.has(modelId)) return

    pendingSuppressions.add(modelId)
    const toastStore = useToastStore()

    toastStore.countdown(`${model.name} 即将隐藏`, 5, '取消').then((confirmed) => {
      pendingSuppressions.delete(modelId)
      if (!confirmed) return

      // Actually suppress
      const expiresAt = new Date().setHours(23, 59, 59, 999)
      let data: Record<string, number> = {}
      try {
        data = JSON.parse(localStorage.getItem(MODEL_SUPPRESSION_KEY) || '{}')
      } catch {
        data = {}
      }
      data[modelId] = expiresAt
      persistSuppressedModelIds(data)

      models.value = models.value.filter((item) => item.id !== modelId)
      selectedModelIds.value = selectedModelIds.value.filter((id) => id !== modelId)
      committeeSelectedModelIds.value = committeeSelectedModelIds.value.filter((id) => id !== modelId)
      ensureCommitteeSelection()
    })
  }

  /** Record a model failure. Auto-suppresses after 3 failures in one day. */
  function recordFailure(modelId: string) {
    const today = new Date().toISOString().slice(0, 10)
    let data: Record<string, { date: string; count: number }> = {}
    try {
      data = JSON.parse(localStorage.getItem(FAILURE_COUNTS_KEY) || '{}')
    } catch {
      data = {}
    }

    const entry = data[modelId]
    if (entry && entry.date === today) {
      entry.count += 1
    } else {
      data[modelId] = { date: today, count: 1 }
    }

    localStorage.setItem(FAILURE_COUNTS_KEY, JSON.stringify(data))

    if (data[modelId].count >= 3) {
      const model = models.value.find((m) => m.id === modelId)
      useToastStore().info(`${model?.name ?? modelId} 今日失败 ${data[modelId].count} 次，自动隐藏`)
      suppressModelForToday(modelId)
    }
  }

  function getFailureCount(modelId: string): number {
    try {
      const data = JSON.parse(localStorage.getItem(FAILURE_COUNTS_KEY) || '{}')
      const today = new Date().toISOString().slice(0, 10)
      const entry = data[modelId]
      return entry?.date === today ? entry.count : 0
    } catch {
      return 0
    }
  }

  /** Get list of currently suppressed model IDs (not expired) */
  function getSuppressedModelIds(): string[] {
    try {
      const raw = localStorage.getItem(MODEL_SUPPRESSION_KEY)
      if (!raw) return []
      const data = JSON.parse(raw) as Record<string, number>
      const now = Date.now()
      return Object.entries(data).filter(([, exp]) => exp > now).map(([id]) => id)
    } catch {
      return []
    }
  }

  /** Restore all suppressed models by clearing suppression and re-fetching */
  async function restoreSuppressedModels() {
    localStorage.removeItem(MODEL_SUPPRESSION_KEY)
    await refreshModels()
    useToastStore().info('已恢复所有隐藏模型')
  }

  function getModel(id: string): ModelMeta | undefined {
    return models.value.find(m => m.id === id)
  }

  return {
    models,
    presets,
    selectedModelIds,
    selectedModels,
    committeeSelectedModelIds,
    committeeSelectedModels,
    modelsByCategory, initialized, loading, error, preferFree,
    initialize,
    refreshModels,
    toggleModel,
    applyPreset,
    clearSelection,
    filterModels,
    randomPick,
    replaceSelectedModel,
    pickReplacementModel,
    copySelection,
    ensureCommitteeSelection,
    suppressModelForToday,
    recordFailure,
    getFailureCount,
    getSuppressedModelIds,
    restoreSuppressedModels,
    getModel,
  }
})
