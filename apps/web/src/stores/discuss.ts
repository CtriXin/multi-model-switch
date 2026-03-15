import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  DiscussSessionState,
  DiscussPhase,
  PhaseStatus,
  Phase1Summary,
  Phase2Review,
  Phase3Synthesis,
} from '@mms/contracts'
import { streamDiscuss } from '@/api/client'

export const useDiscussStore = defineStore('discuss', () => {
  // State
  const session = ref<DiscussSessionState | null>(null)
  const currentPhase = ref<DiscussPhase>(1)
  const phaseStatus = ref<PhaseStatus>('waiting')
  const phase1Summaries = ref<Phase1Summary[]>([])
  const phase2Reviews = ref<Phase2Review[]>([])
  const phase3Content = ref('')
  const synthesizer = ref<string | null>(null)
  const isStreaming = ref(false)

  // Getters
  const isActive = computed(() => session.value !== null)
  const prompt = computed(() => session.value?.prompt || '')

  const phaseProgress = computed(() => {
    switch (currentPhase.value) {
      case 1:
        return {
          current: phase1Summaries.value.filter(s => s.ok).length,
          total: phase1Summaries.value.length,
        }
      case 2:
        return {
          current: phase2Reviews.value.filter(r => r.ok && !r.skipped).length,
          total: phase2Reviews.value.length,
        }
      case 3:
        return {
          current: phase3Content.value ? 1 : 0,
          total: 1,
        }
      default:
        return { current: 0, total: 1 }
    }
  })

  const canStartPhase2 = computed(() =>
    phase1Summaries.value.every(s => s.ok || s.error)
  )

  const canStartPhase3 = computed(() =>
    phase2Reviews.value.every(r => r.ok || r.skipped)
  )

  // Actions
  function initSession(promptText: string, models: string[]) {
    session.value = {
      id: `discuss-${Date.now()}`,
      prompt: promptText,
      models,
      phase: 1,
      phaseStatus: 'waiting',
      phase1Summaries: [],
      phase2Reviews: [],
      phase3Synthesis: null,
      isActive: true,
      createdAt: new Date().toISOString(),
    }
    currentPhase.value = 1
    phaseStatus.value = 'waiting'
    phase1Summaries.value = models.map(m => ({
      model: m,
      ok: false,
      elapsed: 0,
    }))
    phase2Reviews.value = []
    phase3Content.value = ''
    synthesizer.value = null
  }

  async function startDiscuss(promptText: string, models: string[]) {
    initSession(promptText, models)
    isStreaming.value = true
    phaseStatus.value = 'running'

    return new Promise<void>((resolve, reject) => {
      streamDiscuss(
        { models, prompt: promptText, cross: true },
        (type, data) => {
          switch (type) {
            case 'phase_start': {
              const { phase, synthesizer: synth } = data as { phase: DiscussPhase; synthesizer?: string }
              currentPhase.value = phase
              if (synth) {
                synthesizer.value = synth
              }
              break
            }
            case 'phase1_result': {
              const { model, ok, data: briefData, error } = data as {
                model: string
                ok: boolean
                data?: Record<string, unknown>
                error?: string
              }
              const summary = phase1Summaries.value.find(s => s.model === model)
              if (summary) {
                summary.ok = ok
                summary.brief = briefData as any
                summary.error = error
                summary.elapsed = 2.5
              }
              break
            }
            case 'phase2_result': {
              const { reviewer, target, ok, data: reviewData, error, skipped } = data as {
                reviewer: string
                target: string
                ok: boolean
                data?: { agreement: string; challenge: string; betterOption: string }
                error?: string
                skipped?: boolean
              }
              phase2Reviews.value.push({
                reviewer,
                target,
                ok,
                agreement: reviewData?.agreement,
                challenge: reviewData?.challenge,
                betterOption: reviewData?.betterOption,
                error,
                skipped,
              })
              break
            }
            case 'phase3_chunk': {
              const { text } = data as { text: string }
              phase3Content.value += text
              break
            }
            case 'complete': {
              const { synthesizer: synth } = data as { synthesizer: string }
              synthesizer.value = synth
              phaseStatus.value = 'completed'
              if (session.value) {
                session.value.phase3Synthesis = {
                  synthesizer: synth,
                  content: phase3Content.value,
                  elapsed: 10.0,
                }
              }
              break
            }
          }
        },
        (error) => {
          isStreaming.value = false
          reject(error)
        },
        () => {
          isStreaming.value = false
          resolve()
        }
      )
    })
  }

  function clearSession() {
    session.value = null
    currentPhase.value = 1
    phaseStatus.value = 'waiting'
    phase1Summaries.value = []
    phase2Reviews.value = []
    phase3Content.value = ''
    synthesizer.value = null
    isStreaming.value = false
  }

  return {
    session,
    currentPhase,
    phaseStatus,
    phase1Summaries,
    phase2Reviews,
    phase3Content,
    synthesizer,
    isStreaming,
    isActive,
    prompt,
    phaseProgress,
    canStartPhase2,
    canStartPhase3,
    startDiscuss,
    clearSession,
  }
})
