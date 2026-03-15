import { defineStore } from 'pinia'
import { ref, computed, reactive } from 'vue'
import type {
  ChatRound,
  ChatResponse,
  ResponseStatus,
  Brief,
} from '@mms/contracts'
import { streamChat } from '@/api/client'

export const useChatStore = defineStore('chat', () => {
  // State
  const rounds = ref<ChatRound[]>([])
  const currentResponses = reactive<Record<string, ChatResponse>>({})
  const isStreaming = ref(false)
  const sessionId = ref<string | null>(null)
  // Track which responses have been viewed by the user per round
  const viewedResponses = ref<Record<string, Set<string>>>({})

  // Getters
  const hasRounds = computed(() => rounds.value.length > 0)
  const allResponses = computed(() => Object.values(currentResponses))
  const completedCount = computed(() =>
    allResponses.value.filter(r => r.status === 'done').length
  )
  const totalCount = computed(() => allResponses.value.length)
  const isAllDone = computed(() => {
    if (totalCount.value === 0) return false
    return allResponses.value.every(r =>
      r.status === 'done' || r.status === 'error' || r.status === 'cancelled'
    )
  })

  // Actions
  function initResponses(modelIds: string[]) {
    Object.keys(currentResponses).forEach(key => delete currentResponses[key])

    for (const modelId of modelIds) {
      currentResponses[modelId] = {
        model: modelId,
        content: '',
        displayText: '',
        brief: null,
        elapsed: 0,
        status: 'loading',
        timestamp: new Date().toISOString(),
      }
    }
  }

  function startChat(models: string[], prompt: string, attachments?: string[]): string {
    initResponses(models)
    isStreaming.value = true

    // Create new round
    const round: ChatRound = {
      id: `round-${Date.now()}`,
      prompt,
      responses: [],
      timestamp: new Date().toISOString(),
    }
    if (attachments?.length) {
      round.attachments = attachments.map((url, i) => ({
        id: `att-${i}`,
        type: 'image',
        name: `image-${i}.png`,
        size: 0,
        url,
        mimeType: 'image/png',
      }))
    }
    rounds.value.push(round)

    // Start streaming asynchronously
    streamChat(
      { models, prompt, sessionId: sessionId.value || undefined },
      (type, data) => {
        switch (type) {
          case 'chunk': {
            const { model, text } = data as { model: string; text: string }
            if (currentResponses[model]) {
              currentResponses[model].content += text
              currentResponses[model].status = 'streaming'
            }
            break
          }
          case 'model_done': {
            const { model, elapsed, status, error } = data as {
              model: string
              elapsed: number
              status: ResponseStatus
              error?: string
            }
            if (currentResponses[model]) {
              currentResponses[model].elapsed = elapsed
              currentResponses[model].status = status
              if (error) {
                currentResponses[model].error = error
              }
            }
            break
          }
          case 'all_done':
            round.responses = Object.values(currentResponses).map(r => ({ ...r }))
            break
        }
      },
      (error) => {
        isStreaming.value = false
        console.error('Chat error:', error)
      },
      () => {
        isStreaming.value = false
      }
    )

    return round.id
  }

  function selectResponse(roundId: string, modelId: string) {
    const round = rounds.value.find(r => r.id === roundId)
    if (round) {
      round.selectedModel = modelId
      // Mark as viewed when selected
      markResponseViewed(roundId, modelId)
    }
  }

  function markResponseViewed(roundId: string, modelId: string) {
    if (!viewedResponses.value[roundId]) {
      viewedResponses.value[roundId] = new Set()
    }
    viewedResponses.value[roundId].add(modelId)
  }

  function isResponseViewed(roundId: string, modelId: string): boolean {
    return viewedResponses.value[roundId]?.has(modelId) ?? false
  }

  function hasUnviewedResponses(roundId: string): boolean {
    const round = rounds.value.find(r => r.id === roundId)
    if (!round) return false
    const viewed = viewedResponses.value[roundId] ?? new Set()
    return round.responses.some(r => !viewed.has(r.model))
  }

  function clearSession() {
    rounds.value = []
    Object.keys(currentResponses).forEach(key => delete currentResponses[key])
    viewedResponses.value = {}
    isStreaming.value = false
    sessionId.value = null
  }

  return {
    rounds,
    currentResponses,
    isStreaming,
    sessionId,
    viewedResponses,
    hasRounds,
    allResponses,
    completedCount,
    totalCount,
    isAllDone,
    startChat,
    selectResponse,
    markResponseViewed,
    isResponseViewed,
    hasUnviewedResponses,
    clearSession,
  }
})
