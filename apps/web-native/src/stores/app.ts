import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Model {
  id: string
  name: string
  provider: string
  tier: 'free' | 'standard' | 'premium'
  avatar: string
  role?: 'planner' | 'skeptic' | 'builder' | 'synthesizer'
}

export interface Message {
  id: string
  modelId: string
  content: string
  timestamp: string
  isStreaming?: boolean
}

export interface Thread {
  id: string
  prompt: string
  messages: Message[]
  selectedModelId?: string
}

export const useAppStore = defineStore('app', () => {
  const models = ref<Model[]>([
    { id: 'claude-4', name: 'Claude 4', provider: 'Anthropic', tier: 'premium', avatar: '🟠', role: 'planner' },
    { id: 'gpt-5', name: 'GPT-5', provider: 'OpenAI', tier: 'premium', avatar: '🟢', role: 'skeptic' },
    { id: 'gemini-3', name: 'Gemini 3', provider: 'Google', tier: 'premium', avatar: '🔵', role: 'builder' },
    { id: 'codex-2', name: 'Codex 2', provider: 'OpenAI', tier: 'standard', avatar: '🟣', role: 'builder' },
    { id: 'claude-haiku', name: 'Claude Haiku', provider: 'Anthropic', tier: 'free', avatar: '🟡', role: 'synthesizer' },
    { id: 'gpt-4o-mini', name: 'GPT-4o Mini', provider: 'OpenAI', tier: 'free', avatar: '⚪', role: 'skeptic' },
    { id: 'deepseek-v3', name: 'DeepSeek V3', provider: 'DeepSeek', tier: 'standard', avatar: '🔴', role: 'builder' },
    { id: 'llama-3', name: 'Llama 3', provider: 'Meta', tier: 'free', avatar: '🟤', role: 'planner' },
    { id: 'qwen-2.5', name: 'Qwen 2.5', provider: 'Alibaba', tier: 'premium', avatar: '🟣', role: 'skeptic' },
    { id: 'mistral', name: 'Mistral', provider: 'Mistral AI', tier: 'premium', avatar: '🟦', role: 'synthesizer' },
    { id: 'grok-3', name: 'Grok 3', provider: 'xAI', tier: 'premium', avatar: '⚫', role: 'skeptic' },
    { id: 'qwen-3', name: 'Qwen 3', provider: 'Alibaba', tier: 'standard', avatar: '🟣', role: 'builder' },
    { id: 'kimi', name: 'Kimi', provider: 'Moonshot', tier: 'premium', avatar: '🌙', role: 'synthesizer' },
    { id: 'doubao', name: 'Doubao', provider: 'Doubao', tier: 'free', avatar: '🟢', role: 'planner' },
    { id: 'chatgpt', name: 'ChatGPT', provider: 'OpenAI', tier: 'standard', avatar: '💬', role: 'builder' },
    { id: 'yi-light', name: 'Yi Light', provider: '01.AI', tier: 'standard', avatar: '🟠', role: 'skeptic' },
    { id: 'palm', name: 'Palm', provider: 'Palm', tier: 'free', avatar: '🌴', role: 'synthesizer' }
  ])

  const selectedModels = ref<string[]>([])
  const threads = ref<Thread[]>([])
  const currentMode = ref<'chat' | 'discuss'>('chat')
  const isDark = ref(false)

  const selectedModelObjects = computed(() =>
    models.value.filter(m => selectedModels.value.includes(m.id))
  )

  function toggleModel(modelId: string) {
    const index = selectedModels.value.indexOf(modelId)
    if (index > -1) {
      selectedModels.value.splice(index, 1)
    } else {
      if (selectedModels.value.length < 5) {
        selectedModels.value.push(modelId)
      }
    }
  }

  function setModels(modelIds: string[]) {
    selectedModels.value = modelIds
  }

  function setMode(mode: 'chat' | 'discuss') {
    currentMode.value = mode
  }

  function toggleDark() {
    isDark.value = !isDark.value
    document.documentElement.classList.toggle('dark', isDark.value)
  }

  return {
    models,
    selectedModels,
    selectedModelObjects,
    threads,
    currentMode,
    isDark,
    toggleModel,
    setModels,
    setMode,
    toggleDark
  }
})
