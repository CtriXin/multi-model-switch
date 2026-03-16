import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useToastStore } from './toast'
import { useAppStore } from './app'
import { ApiError, type ContentPart, type ChatMessage as ApiChatMessage } from '@/services/api'
import { streamModelChat } from '@/services/runtime'
import { buildContextMessages } from '@/utils/contextBuilder'

export type ContextMode = 'summary' | 'selected' | 'full'

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
  errorCode?: string
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
  const contextMode = ref<ContextMode>('summary')

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

  async function runModelRequest(options: {
    round: ChatRound
    modelId: string
    prompt: string
    attachments: ImageAttachment[]
    contextMsgs: ApiChatMessage[]
    signal: AbortSignal
  }) {
    const { round, modelId, prompt, attachments, contextMsgs, signal } = options
    const appStore = useAppStore()
    const model = appStore.models.find(m => m.id === modelId)
    const msg = round.responses.get(modelId)
    if (!msg || !model) return

    const startTime = Date.now()
    msg.content = ''
    msg.error = undefined
    msg.errorCode = undefined
    msg.brief = undefined
    msg.elapsed = undefined
    msg.streaming = true

    try {
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
        modelId,
        messages: [...contextMsgs, { role: 'user', content: userContent }],
        signal,
      })

      for await (const chunk of stream) {
        if (signal.aborted) return
        msg.content += chunk
      }

      const parsed = parseBrief(msg.content)
      msg.content = parsed.displayText
      msg.brief = parsed.brief
    } catch (e: any) {
      if (e.name === 'AbortError' || signal.aborted) return
      if (e instanceof ApiError) {
        msg.error = e.message
        msg.errorCode = e.code
        msg.content += `\n\n> 错误: ${e.message}`
        if (shouldSuppressModel(e)) {
          appStore.suppressModelForToday(modelId)
        }
      } else {
        msg.error = e.message
        msg.errorCode = 'request_failed'
        msg.content += `\n\n> 错误: ${e.message}`
      }
    } finally {
      msg.elapsed = (Date.now() - startTime) / 1000
      msg.streaming = false
    }
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

    // Build context from previous rounds (exclude the one just pushed)
    const contextMsgs = buildContextMessages(rounds.value.slice(0, -1), contextMode.value)

    streaming.value = true
    abortController.value = new AbortController()
    const signal = abortController.value.signal

    const tasks = modelIds.map(mid => runModelRequest({
      round: reactiveRound,
      modelId: mid,
      prompt,
      attachments,
      contextMsgs,
      signal,
    }))

    await Promise.allSettled(tasks)
    streaming.value = false
    abortController.value = null
  }

  function replaceModelResponse(roundId: string, oldModelId: string, newModelId: string) {
    const round = rounds.value.find(item => item.id === roundId)
    if (!round || oldModelId === newModelId) return

    const oldMsg = round.responses.get(oldModelId)
    const nextEntries = Array.from(round.responses.entries()).map(([id, message]) => {
      if (id !== oldModelId) return [id, message] as const
      return [newModelId, {
        ...(oldMsg ?? {
          id: `msg-${newModelId}-${Date.now()}`,
          role: 'model' as const,
          content: '',
          timestamp: Date.now(),
        }),
        id: `msg-${newModelId}-${Date.now()}`,
        model: newModelId,
        content: '',
        timestamp: Date.now(),
        error: undefined,
        errorCode: undefined,
        brief: undefined,
        elapsed: undefined,
        streaming: false,
      }] as const
    })

    round.responses = new Map(nextEntries)
    if (round.activeModelId === oldModelId) round.activeModelId = newModelId
    if (round.selectedModelId === oldModelId) round.selectedModelId = newModelId
  }

  async function retryModel(roundId: string, modelId: string, options: {
    replaceWith?: string
  } = {}) {
    if (streaming.value) return

    const roundIndex = rounds.value.findIndex(item => item.id === roundId)
    if (roundIndex < 0) return

    const round = rounds.value[roundIndex]
    const targetModelId = options.replaceWith ?? modelId

    if (options.replaceWith) {
      replaceModelResponse(roundId, modelId, options.replaceWith)
    } else {
      const msg = round.responses.get(modelId)
      if (msg) {
        msg.content = ''
        msg.error = undefined
        msg.errorCode = undefined
        msg.brief = undefined
        msg.elapsed = undefined
      }
    }

    const targetRound = rounds.value[roundIndex]
    const contextMsgs = buildContextMessages(rounds.value.slice(0, roundIndex), contextMode.value)

    streaming.value = true
    abortController.value = new AbortController()
    const signal = abortController.value.signal

    try {
      await runModelRequest({
        round: targetRound,
        modelId: targetModelId,
        prompt: targetRound.prompt,
        attachments: targetRound.attachments,
        contextMsgs,
        signal,
      })
    } finally {
      streaming.value = false
      abortController.value = null
    }
  }

  function stopStreaming() {
    abortController.value?.abort()
    streaming.value = false
    for (const round of rounds.value) {
      for (const msg of round.responses.values()) {
        if (msg.streaming) msg.streaming = false
      }
    }
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
    rounds, streaming, currentRound, contextMode,
    sendMessage, retryModel, stopStreaming, stopAndRestoreDraft, setActiveModel, selectModel, clearHistory,
  }
})
