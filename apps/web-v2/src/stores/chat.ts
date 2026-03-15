import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useToastStore } from './toast'
import { useAppStore } from './app'
import { ApiError, type ContentPart } from '@/services/api'
import { streamModelChat } from '@/services/runtime'

export interface ImageAttachment {
  id: string
  dataUrl: string      // base64 data URL
  name: string
  size: number         // original bytes
}

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
  attachments: ImageAttachment[]
  responses: Map<string, ChatMessage>
  activeModelId: string | null
  timestamp: number
}

export const useChatStore = defineStore('chat', () => {
  const rounds = ref<ChatRound[]>([])
  const streaming = ref(false)
  const abortController = ref<AbortController | null>(null)
  const lastSubmittedPrompt = ref('')

  const currentRound = computed(() =>
    rounds.value.length ? rounds.value[rounds.value.length - 1] : null
  )

  function shouldSuppressModel(error: ApiError) {
    return error.code === 'model_unavailable' || error.code === 'rate_limited'
  }

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

  async function sendMessage(prompt: string, modelIds: string[], attachments: ImageAttachment[] = []) {
    if (streaming.value || !modelIds.length) return
    const appStore = useAppStore()

    const round: ChatRound = {
      id: `round-${Date.now()}`,
      prompt,
      attachments,
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
    lastSubmittedPrompt.value = prompt

    const reactiveRound = rounds.value[rounds.value.length - 1]

    streaming.value = true
    abortController.value = new AbortController()
    const signal = abortController.value.signal

    const tasks = modelIds.map(async (mid) => {
      const model = appStore.models.find(m => m.id === mid)
      const msg = reactiveRound.responses.get(mid)
      if (!msg || !model) return

      const startTime = Date.now()
      try {
        // Build user message content
        // Vision-capable models get images; others get text-only (graceful degradation)
        let userContent: string | ContentPart[]
        if (attachments.length && model.supportsVision) {
          const parts: ContentPart[] = [{ type: 'text', text: prompt }]
          for (const img of attachments) {
            parts.push({ type: 'image_url', image_url: { url: img.dataUrl } })
          }
          userContent = parts
        } else {
          userContent = prompt
          if (attachments.length && !model.supportsVision) {
            msg.content = '> ⚠️ 该模型不支持图片，已自动降级为纯文本\n\n'
          }
        }

        const stream = streamModelChat({
          modelId: mid,
          messages: [{ role: 'user', content: userContent }],
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
          if (shouldSuppressModel(e)) {
            appStore.suppressModelForToday(mid)
          }
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

  function stopAndRestoreDraft() {
    const latestRound = rounds.value[rounds.value.length - 1]
    const prompt = latestRound?.prompt || lastSubmittedPrompt.value
    abortController.value?.abort()
    if (latestRound && !Array.from(latestRound.responses.values()).every((msg) => !!msg.elapsed)) {
      rounds.value.pop()
    }
    streaming.value = false
    abortController.value = null
    useToastStore().info('已终止并恢复到输入框')
    return prompt
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
    sendMessage, stopStreaming, stopAndRestoreDraft, setActiveModel, clearHistory,
  }
})
