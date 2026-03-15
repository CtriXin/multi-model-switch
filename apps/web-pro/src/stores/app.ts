import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ModelMeta, Preset, Session, BootstrapConfig } from '@mms/contracts'
import {
  MOCK_MODELS, MOCK_PRESETS, MOCK_SESSIONS, MOCK_BOOTSTRAP,
} from '@/api/mock'

export const useAppStore = defineStore('app', () => {
  const config = ref<BootstrapConfig>(MOCK_BOOTSTRAP)
  const models = ref<ModelMeta[]>(MOCK_MODELS)
  const sessions = ref<Session[]>(MOCK_SESSIONS)
  const isLoading = ref(false)

  // Separate selections for chat/discuss
  const chatSelectedModels = ref<string[]>(['claude-sonnet-4-6', 'gpt-4o', 'gemini-2.5-pro'])
  const discussSelectedModels = ref<string[]>(['claude-opus-4-6', 'o3', 'deepseek-r1'])

  // Sidebar state - auto-collapse on mobile
  const sidebarOpen = ref(typeof window !== 'undefined' ? window.innerWidth >= 768 : true)
  const sidebarSection = ref<'sessions' | 'models'>('sessions')

  // Command palette
  const commandPaletteOpen = ref(false)

  const presets = computed(() => config.value.presets)

  const chatSelectedModelObjects = computed(() =>
    chatSelectedModels.value
      .map(id => models.value.find(m => m.id === id))
      .filter((m): m is ModelMeta => !!m)
  )

  const discussSelectedModelObjects = computed(() =>
    discussSelectedModels.value
      .map(id => models.value.find(m => m.id === id))
      .filter((m): m is ModelMeta => !!m)
  )

  function toggleModel(mode: 'chat' | 'discuss', modelId: string) {
    const list = mode === 'chat' ? chatSelectedModels : discussSelectedModels
    const idx = list.value.indexOf(modelId)
    if (idx > -1) {
      list.value.splice(idx, 1)
    } else if (list.value.length < 5) {
      list.value.push(modelId)
    }
  }

  function applyPreset(mode: 'chat' | 'discuss', presetId: string) {
    const preset = presets.value.find(p => p.id === presetId)
    if (!preset) return
    const list = mode === 'chat' ? chatSelectedModels : discussSelectedModels
    list.value = preset.models.filter(id => models.value.some(m => m.id === id))
  }

  function clearSelection(mode: 'chat' | 'discuss') {
    const list = mode === 'chat' ? chatSelectedModels : discussSelectedModels
    list.value = []
  }

  function copySelection(from: 'chat' | 'discuss', to: 'chat' | 'discuss') {
    const src = from === 'chat' ? chatSelectedModels.value : discussSelectedModels.value
    const dst = to === 'chat' ? chatSelectedModels : discussSelectedModels
    dst.value = [...src]
  }

  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
  }

  function toggleCommandPalette() {
    commandPaletteOpen.value = !commandPaletteOpen.value
  }

  function getModel(id: string): ModelMeta | undefined {
    return models.value.find(m => m.id === id)
  }

  function getModelName(id: string): string {
    return getModel(id)?.name || id
  }

  return {
    config, models, sessions, isLoading,
    chatSelectedModels, discussSelectedModels,
    chatSelectedModelObjects, discussSelectedModelObjects,
    presets, sidebarOpen, sidebarSection, commandPaletteOpen,
    toggleModel, applyPreset, clearSelection, copySelection,
    toggleSidebar, toggleCommandPalette, getModel, getModelName,
  }
})
