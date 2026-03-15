import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useToastStore } from './toast'
import { useAppStore } from './app'
import { useProviderStore } from './provider'
import { streamChat, ApiError } from '@/services/api'
import { getApiKey } from '@/services/keychain'

export interface ChatMessage {
  id: string
  role: 'user' | 'model'
  content: string
  model?: string
  elapsed?: number
  brief?: Record<string, string>
  timestamp: number
  error?: string
}

export interface ChatRound {
  id: string
  prompt: string
  responses: Map<string, ChatMessage>
  activeModelId: string | null
  timestamp: number
}

export const useChatStore = defineStore('chat', () => {
  const rounds = ref<ChatRound[]>([])
  const streaming = ref(false)
  const abortController = ref<AbortController | null>(null)

  const currentRound = computed(() =>
    rounds.value.length ? rounds.value[rounds.value.length - 1] : null
  )

  function parseBrief(text: string): { displayText: string; brief?: Record<string, string> } {
    const match = text.match(/<BRIEF>\n?([\s\S]*?)\n?<\/BRIEF>/)
    if (!match) return { displayText: text }
    const displayText = text.replace(/<BRIEF>[\s\S]*?<\/BRIEF>/, '').trim()
    const brief: Record<string, string> = {}
    for (const line of match[1].split('\n')) {
      const [key, ...rest] = line.split(':')
      if (key && rest.length) brief[key.trim()] = rest.join(':').trim()
    }
    return { displayText, brief }
  }

  async function sendMessage(prompt: string, modelIds: string[]) {
    if (streaming.value || !modelIds.length) return
    const appStore = useAppStore()
    const providerStore = useProviderStore()

    const round: ChatRound = {
      id: `round-${Date.now()}`,
      prompt,
      responses: new Map(),
      activeModelId: null,
      timestamp: Date.now(),
    }

    for (const mid of modelIds) {
      round.responses.set(mid, {
        id: `msg-${mid}-${Date.now()}`,
        role: 'model',
        content: '',
        model: mid,
        timestamp: Date.now(),
      })
    }
    rounds.value.push(round)

    const reactiveRound = rounds.value[rounds.value.length - 1]

    streaming.value = true
    abortController.value = new AbortController()
    const signal = abortController.value.signal

    const tasks = modelIds.map(async (mid) => {
      const model = appStore.models.find(m => m.id === mid)
      const msg = reactiveRound.responses.get(mid)
      if (!msg || !model) return

      // Find the provider for this model
      // For OpenRouter models, the provider ID is 'openrouter'
      // For direct providers, match by provider name
      let providerConfig = providerStore.providers.find(p => p.id === model.provider)
      // Fallback: if model came from OpenRouter, use openrouter provider
      if (!providerConfig) {
        providerConfig = providerStore.providers.find(p => p.type === 'openrouter')
      }
      if (!providerConfig) {
        msg.error = '未找到对应的 API 通道'
        msg.content = '> 错误: 未找到对应的 API 通道配置'
        return
      }

      const apiKey = await getApiKey(providerConfig.id)
      if (!apiKey) {
        msg.error = 'API Key 未配置'
        msg.content = '> 错误: 请先在设置中配置 API Key'
        return
      }

      const startTime = Date.now()
      try {
        const stream = streamChat({
          provider: providerConfig,
          apiKey,
          model: mid,
          messages: [{ role: 'user', content: prompt }],
          signal,
        })

        for await (const chunk of stream) {
          if (signal.aborted) return
          msg.content += chunk
        }
      } catch (e: any) {
        if (e.name === 'AbortError' || signal.aborted) return
        if (e instanceof ApiError) {
          msg.error = e.message
          msg.content += `\n\n> 错误: ${e.message}`
        } else {
          msg.error = e.message
          msg.content += `\n\n> 错误: ${e.message}`
        }
      }
      msg.elapsed = (Date.now() - startTime) / 1000
    })

    await Promise.allSettled(tasks)
    streaming.value = false
    abortController.value = null
  }

  function stopStreaming() {
    abortController.value?.abort()
    streaming.value = false
    useToastStore().info('已停止生成')
  }

  function setActiveModel(roundId: string, modelId: string) {
    const r = rounds.value.find(r => r.id === roundId)
    if (r) r.activeModelId = modelId
  }

  function clearHistory() {
    rounds.value = []
  }

  return {
    rounds, streaming, currentRound,
    sendMessage, stopStreaming, setActiveModel, clearHistory,
  }
})
