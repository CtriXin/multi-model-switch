import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { DiscussPhase, PhaseStatus, Phase1Summary, Phase2Review } from '@mms/contracts'
import { simulateDiscussPhase1, simulateDiscussPhase2, simulateStream } from '@/api/mock'

export const useDiscussStore = defineStore('discuss', () => {
  const prompt = ref('')
  const isActive = ref(false)
  const isStreaming = ref(false)
  const currentPhase = ref<DiscussPhase>(1)
  const phaseStatus = ref<PhaseStatus>('waiting')
  const phase1Summaries = ref<Phase1Summary[]>([])
  const phase2Reviews = ref<Phase2Review[]>([])
  const phase3Content = ref('')
  const synthesizer = ref<string | null>(null)

  const phaseProgress = computed(() => {
    switch (currentPhase.value) {
      case 1: return { current: phase1Summaries.value.filter(s => s.ok).length, total: phase1Summaries.value.length || 1 }
      case 2: return { current: phase2Reviews.value.filter(r => r.ok).length, total: phase2Reviews.value.length || 1 }
      case 3: return { current: phase3Content.value ? 1 : 0, total: 1 }
      default: return { current: 0, total: 1 }
    }
  })

  async function startDiscuss(promptText: string, modelIds: string[]) {
    prompt.value = promptText
    isActive.value = true
    isStreaming.value = true
    phase1Summaries.value = modelIds.map(m => ({ model: m, ok: false, elapsed: 0 }))
    phase2Reviews.value = []
    phase3Content.value = ''

    // Phase 1: Independent summaries
    currentPhase.value = 1
    phaseStatus.value = 'running'

    const summaries = await Promise.all(modelIds.map(id => simulateDiscussPhase1(id)))
    phase1Summaries.value = summaries

    // Phase 2: Cross review
    currentPhase.value = 2
    const reviewPairs: Array<{ reviewer: string; target: string }> = []
    for (let i = 0; i < modelIds.length; i++) {
      for (let j = 0; j < modelIds.length; j++) {
        if (i !== j) reviewPairs.push({ reviewer: modelIds[i], target: modelIds[j] })
      }
    }
    const reviews = await Promise.all(
      reviewPairs.map(p => simulateDiscussPhase2(p.reviewer, p.target))
    )
    phase2Reviews.value = reviews

    // Phase 3: Synthesis
    currentPhase.value = 3
    synthesizer.value = modelIds[0]
    await new Promise<void>((resolve) => {
      simulateStream(
        modelIds[0],
        (text) => { phase3Content.value += text },
        () => {
          phaseStatus.value = 'completed'
          resolve()
        },
      )
    })

    isStreaming.value = false
  }

  function clearSession() {
    prompt.value = ''
    isActive.value = false
    isStreaming.value = false
    currentPhase.value = 1
    phaseStatus.value = 'waiting'
    phase1Summaries.value = []
    phase2Reviews.value = []
    phase3Content.value = ''
    synthesizer.value = null
  }

  return {
    prompt, isActive, isStreaming, currentPhase, phaseStatus,
    phase1Summaries, phase2Reviews, phase3Content, synthesizer,
    phaseProgress, startDiscuss, clearSession,
  }
})
