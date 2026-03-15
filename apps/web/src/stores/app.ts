import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  BootstrapConfig,
  ModelMeta,
  Preset,
  ProviderConfig,
  AccountInfo,
} from '@mms/contracts'
import { fetchBootstrap, fetchModels } from '@/api/client'

export const useAppStore = defineStore('app', () => {
  // State
  const config = ref<BootstrapConfig | null>(null)
  const models = ref<ModelMeta[]>([])

  // Separate selection states for chat and discuss
  const chatSelectedModels = ref<string[]>([])
  const discussSelectedModels = ref<string[]>([])

  const favorites = ref<string[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const providers = computed(() => config.value?.providers || [])
  const accounts = computed(() => config.value?.accounts || [])
  const presets = computed(() => config.value?.presets || [])
  const limits = computed(() => config.value?.limits || { maxModels: 5, minModelsChat: 2, minModelsDiscuss: 2 })

  // Chat mode getters
  const chatSelectedModelObjects = computed(() => {
    return chatSelectedModels.value
      .map(id => models.value.find(m => m.id === id))
      .filter((m): m is ModelMeta => m !== undefined)
  })

  // Discuss mode getters
  const discussSelectedModelObjects = computed(() => {
    return discussSelectedModels.value
      .map(id => models.value.find(m => m.id === id))
      .filter((m): m is ModelMeta => m !== undefined)
  })

  const categorizedModels = computed(() => {
    const result: Record<string, ModelMeta[]> = {}
    for (const model of models.value) {
      if (!result[model.category]) {
        result[model.category] = []
      }
      result[model.category].push(model)
    }
    return result
  })

  function canAddMore(mode: 'chat' | 'discuss' = 'chat') {
    const selected = mode === 'chat' ? chatSelectedModels.value : discussSelectedModels.value
    return selected.length < limits.value.maxModels
  }

  // Actions
  async function initialize() {
    isLoading.value = true
    error.value = null

    try {
      const [bootstrapData, modelsData] = await Promise.all([
        fetchBootstrap(),
        fetchModels(),
      ])

      config.value = bootstrapData
      models.value = modelsData.map(m => ({
        ...m,
        favorited: favorites.value.includes(m.id),
        selected: false, // Don't sync selected state here
      }))

      loadFavorites()
    } catch (e) {
      error.value = e instanceof Error ? e.message : '初始化失败'
    } finally {
      isLoading.value = false
    }
  }

  function toggleModel(mode: 'chat' | 'discuss', modelId: string) {
    const selected = mode === 'chat' ? chatSelectedModels : discussSelectedModels
    const index = selected.value.indexOf(modelId)

    if (index > -1) {
      selected.value.splice(index, 1)
    } else if (canAddMore(mode)) {
      selected.value.push(modelId)
    }
  }

  function selectModels(mode: 'chat' | 'discuss', modelIds: string[]) {
    const selected = mode === 'chat' ? chatSelectedModels : discussSelectedModels
    selected.value = modelIds.slice(0, limits.value.maxModels)
  }

  function clearSelection(mode: 'chat' | 'discuss') {
    const selected = mode === 'chat' ? chatSelectedModels : discussSelectedModels
    selected.value = []
  }

  function applyPreset(mode: 'chat' | 'discuss', presetId: string) {
    const preset = presets.value.find(p => p.id === presetId)
    if (preset) {
      const availableModels = preset.models.filter(id =>
        models.value.some(m => m.id === id)
      )
      selectModels(mode, availableModels)
    }
  }

  // Copy selection from one mode to another
  function copySelection(from: 'chat' | 'discuss', to: 'chat' | 'discuss') {
    const fromSelected = from === 'chat' ? chatSelectedModels.value : discussSelectedModels.value
    const toSelected = to === 'chat' ? chatSelectedModels : discussSelectedModels
    toSelected.value = [...fromSelected]
  }

  function toggleFavorite(modelId: string) {
    const index = favorites.value.indexOf(modelId)

    if (index > -1) {
      favorites.value.splice(index, 1)
    } else {
      favorites.value.push(modelId)
    }

    saveFavorites()
    updateModelState()
  }

  function loadFavorites() {
    try {
      const stored = localStorage.getItem('mms:favorites')
      if (stored) {
        favorites.value = JSON.parse(stored)
        updateModelState()
      }
    } catch {
      favorites.value = []
    }
  }

  function saveFavorites() {
    try {
      localStorage.setItem('mms:favorites', JSON.stringify(favorites.value))
    } catch {
      // Ignore storage errors
    }
  }

  function updateModelState() {
    for (const model of models.value) {
      model.favorited = favorites.value.includes(model.id)
    }
  }

  // Backward compatibility - default to chat mode
  const selectedModels = chatSelectedModels
  const selectedModelObjects = chatSelectedModelObjects

  return {
    config,
    models,
    // Chat mode
    chatSelectedModels,
    chatSelectedModelObjects,
    // Discuss mode
    discussSelectedModels,
    discussSelectedModelObjects,
    // Backward compatibility
    selectedModels,
    selectedModelObjects,
    favorites,
    isLoading,
    error,
    providers,
    accounts,
    presets,
    limits,
    categorizedModels,
    canAddMore,
    initialize,
    toggleModel,
    selectModels,
    clearSelection,
    applyPreset,
    copySelection,
    toggleFavorite,
  }
})
