import { defineStore } from 'pinia'
import { ref, computed, reactive } from 'vue'
import type { ChatRound, ChatResponse, ResponseStatus } from '@mms/contracts'
import { simulateStream } from '@/api/mock'

export const useChatStore = defineStore('chat', () => {
  const rounds = ref<ChatRound[]>([])
  const currentResponses = reactive<Record<string, ChatResponse>>({})
  const isStreaming = ref(false)
  const viewedResponses = ref<Record<string, Set<string>>>({})

  const hasRounds = computed(() => rounds.value.length > 0)
  const allResponses = computed(() => Object.values(currentResponses))

  function startChat(modelIds: string[], prompt: string): string {
    // Init responses
    for (const key of Object.keys(currentResponses)) delete currentResponses[key]
    for (const id of modelIds) {
      currentResponses[id] = {
        model: id, content: '', displayText: '', brief: null,
        elapsed: 0, status: 'loading', timestamp: new Date().toISOString(),
      }
    }

    isStreaming.value = true
    const round: ChatRound = {
      id: `round-${Date.now()}`,
      prompt,
      responses: [],
      timestamp: new Date().toISOString(),
    }
    rounds.value.push(round)

    const cancellers: (() => void)[] = []
    let doneCount = 0
    const startTime = Date.now()

    for (const modelId of modelIds) {
      const cancel = simulateStream(
        modelId,
        (text) => {
          if (currentResponses[modelId]) {
            currentResponses[modelId].content += text
            currentResponses[modelId].status = 'streaming'
          }
        },
        () => {
          if (currentResponses[modelId]) {
            currentResponses[modelId].status = 'done'
            currentResponses[modelId].elapsed = (Date.now() - startTime) / 1000
          }
          doneCount++
          if (doneCount >= modelIds.length) {
            round.responses = Object.values(currentResponses).map(r => ({ ...r }))
            isStreaming.value = false
          }
        },
      )
      cancellers.push(cancel)
    }

    return round.id
  }

  function selectResponse(roundId: string, modelId: string) {
    const round = rounds.value.find(r => r.id === roundId)
    if (round) {
      round.selectedModel = modelId
      markViewed(roundId, modelId)
    }
  }

  function markViewed(roundId: string, modelId: string) {
    if (!viewedResponses.value[roundId]) {
      viewedResponses.value[roundId] = new Set()
    }
    viewedResponses.value[roundId].add(modelId)
  }

  function clearSession() {
    rounds.value = []
    for (const key of Object.keys(currentResponses)) delete currentResponses[key]
    viewedResponses.value = {}
    isStreaming.value = false
  }

  return {
    rounds, currentResponses, isStreaming, viewedResponses,
    hasRounds, allResponses,
    startChat, selectResponse, markViewed, clearSession,
  }
})
