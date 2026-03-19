import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useAppStore } from './app'
import { streamModelChat } from '@/services/runtime'
import type { PlayModeSessionEnvelope } from '@/features/play-modes/shared'
import {
  buildStoryLiveFallback,
  buildStoryLiveSystemPrompt,
  buildStoryLiveUserPrompt,
  buildStoryLiveWrapFallback,
  buildStoryLiveWrapSystemPrompt,
  buildStoryLiveWrapUserPrompt,
  createInitialState,
  detectEndingGrade,
  shouldTriggerTwist,
  updateStoryState,
  validateByRole,
  type StoryLiveModelAssignment,
  type StoryLivePhase,
  type StoryLiveRole,
  type StoryLiveSessionMeta,
  type StoryLiveStoryState,
  type StoryLiveTurn,
  type StoryLiveWrapMode,
  type StoryLiveWrapResult,
} from '@/features/play-modes/story-live'
import {
  CURRENT_PROMISE,
  type StoryLiveSessionRecord,
  buildDirectorMemory,
  buildHistoryEntry,
  buildSummary,
  chooseModelIds,
  cloneForStorage,
  collectText,
  createEnvelope,
  extractDirectorCue,
  getMeta,
  isoNow,
  normalizeAssignment,
  normalizeRecord,
  uid,
} from './story-live-helpers'

const STORAGE_KEY = 'mms-story-live-session'

export const useStoryLiveStore = defineStore('storyLive', () => {
  const envelope = ref<PlayModeSessionEnvelope>(createEnvelope())
  const turns = ref<StoryLiveTurn[]>([])
  const draftInput = ref('')
  const processing = ref(false)
  const error = ref('')
  const wrapError = ref('')
  const hydrated = ref(false)
  const resumed = ref(false)

  const premise = computed(() => getMeta(envelope.value).premise)
  const modelAssignment = computed(() => getMeta(envelope.value).modelAssignment)
  const wrapResult = computed(() => getMeta(envelope.value).wrapResult)
  const directorMemory = computed(() => getMeta(envelope.value).directorMemory)
  const latestDirectorCue = computed(() => getMeta(envelope.value).latestDirectorCue || '')
  const started = computed(() => turns.value.length > 0)
  const wrapBusy = computed(() => wrapResult.value?.status === 'generating')
  const phase = computed<StoryLivePhase>(() => getMeta(envelope.value).phase)
  const storyState = computed<StoryLiveStoryState>(() => getMeta(envelope.value).storyState)
  const lastTwistRound = computed(() => getMeta(envelope.value).lastTwistRound)

  function getModelName(id: string) {
    return useAppStore().getModel(id)?.name || id
  }

  function updateMeta(patch: Partial<StoryLiveSessionMeta>) {
    envelope.value.meta = {
      ...getMeta(envelope.value),
      ...patch,
    }
  }

  function persist() {
    const meta = getMeta(envelope.value)
    envelope.value.round = turns.value.length
    envelope.value.updatedAt = isoNow()
    envelope.value.summary = buildSummary(envelope.value, turns.value)
    envelope.value.pauseState = turns.value.length
      ? {
          pausedAt: isoNow(),
          resumeHint: meta.latestDirectorCue || `你停在第 ${turns.value.length} 轮，故事还在等你接下一句。`,
          snapshot: {
            premise: meta.premise,
            latestDirectorCue: meta.latestDirectorCue,
            draftInput: draftInput.value,
            directorMemory: meta.directorMemory,
          },
        }
      : null

    const record: StoryLiveSessionRecord = {
      envelope: cloneForStorage(envelope.value),
      turns: cloneForStorage(turns.value),
      draftInput: draftInput.value,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record))
  }

  function resetSession(premiseText = CURRENT_PROMISE) {
    envelope.value = createEnvelope(premiseText)
    turns.value = []
    draftInput.value = ''
    error.value = ''
    wrapError.value = ''
    processing.value = false
    resumed.value = false

    const appStore = useAppStore()
    updateMeta({
      premise: premiseText,
      modelAssignment: chooseModelIds(appStore),
      latestDirectorCue: null,
      directorMemory: [],
      wrapResult: null,
      phase: 'premise' as StoryLivePhase,
      storyState: createInitialState(premiseText),
      lastTwistRound: 0,
      validationWarnings: [],
    })
    persist()
  }

  function syncEnvelopeState() {
    const meta = getMeta(envelope.value)
    updateMeta({
      latestDirectorCue: turns.value.at(-1) ? extractDirectorCue(turns.value.at(-1)!.responses.logic.text) : null,
      directorMemory: buildDirectorMemory(turns.value),
      wrapResult: meta.wrapResult,
    })
    envelope.value.history = turns.value.map((turn, index) => buildHistoryEntry(turn, index + 1))
    envelope.value.round = turns.value.length
    envelope.value.summary = buildSummary(envelope.value, turns.value)
    persist()
  }

  async function init() {
    const appStore = useAppStore()
    await appStore.initialize()

    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as StoryLiveSessionRecord
        const normalized = normalizeRecord(parsed, appStore)
        envelope.value = normalized.envelope
        turns.value = normalized.turns
        draftInput.value = normalized.draftInput
        resumed.value = normalized.turns.length > 0
      } else {
        resetSession(CURRENT_PROMISE)
      }
    } catch {
      resetSession(CURRENT_PROMISE)
    }

    updateMeta({ modelAssignment: normalizeAssignment(modelAssignment.value, appStore) })
    if (envelope.value.status === 'paused') {
      const currentPhase = phase.value
      if (currentPhase === 'ended') {
        envelope.value.status = 'completed'
      } else {
        envelope.value.status = turns.value.length ? 'active' : 'pending'
      }
    }
    hydrated.value = true
    persist()
  }

  function markPaused() {
    if (!hydrated.value || processing.value) return
    if (turns.value.length) {
      if (phase.value !== 'ended') {
        envelope.value.status = 'paused'
      }
      persist()
    }
  }

  function markActive() {
    const currentPhase = phase.value
    if (currentPhase === 'ended') {
      envelope.value.status = 'completed'
    } else {
      envelope.value.status = turns.value.length ? 'active' : 'pending'
    }
    persist()
  }

  function updateDraft(value: string) {
    draftInput.value = value
    persist()
  }

  function ensureAssignment() {
    const appStore = useAppStore()
    const next = normalizeAssignment(modelAssignment.value, appStore)
    updateMeta({ modelAssignment: next })
    persist()
    return next
  }

  function buildPendingTurn(text: string, assignment: StoryLiveModelAssignment): StoryLiveTurn {
    return {
      id: uid(),
      userText: text,
      createdAt: Date.now(),
      responses: {
        logic: {
          role: 'logic',
          modelId: assignment.logic,
          modelName: getModelName(assignment.logic),
          text: '',
          status: 'generating',
        },
        emotion: {
          role: 'emotion',
          modelId: assignment.emotion,
          modelName: getModelName(assignment.emotion),
          text: '',
          status: 'idle',
        },
        twist: {
          role: 'twist',
          modelId: assignment.twist,
          modelName: getModelName(assignment.twist),
          text: '',
          status: 'idle',
        },
      },
    }
  }

  async function generateRole(
    turn: StoryLiveTurn,
    role: StoryLiveRole,
    currentStoryState: StoryLiveStoryState,
  ) {
    const assignment = ensureAssignment()
    if (!assignment) throw new Error('当前没有可用模型')

    const modelId = assignment[role]
    turn.responses[role].status = 'generating'
    persist()

    try {
      const meta = getMeta(envelope.value)
      const validationWarningTexts = meta.validationWarnings
        .filter((w) => w.role === role)
        .map((w) => w.message)

      const text = await collectText(
        streamModelChat({
          modelId,
          messages: [
            { role: 'system', content: buildStoryLiveSystemPrompt(role) },
            {
              role: 'user',
              content: buildStoryLiveUserPrompt({
                role,
                premise: premise.value,
                latestUserText: turn.userText,
                directorMemory: directorMemory.value.map((item) => item.summary).join('\n'),
                turns: turns.value.slice(0, -1),
                storyState: currentStoryState,
                twistArmed: role === 'twist',
                validationWarnings: validationWarningTexts,
              }),
            },
          ],
        }),
      )

      const finalText = text || buildStoryLiveFallback(role, premise.value)
      turn.responses[role].text = finalText
      turn.responses[role].status = 'done'

      // Run local validation
      const warnings = validateByRole(role, finalText)
      if (warnings.length > 0) {
        turn.responses[role].validationWarnings = warnings
        // Only inject high-confidence warnings (≥0.5) into director memory
        const highConf = warnings.filter((w) => w.confidence >= 0.5)
        if (highConf.length > 0) {
          const metaNow = getMeta(envelope.value)
          updateMeta({
            validationWarnings: [...metaNow.validationWarnings, ...highConf].slice(-6),
          })
        }
      }
    } catch (err: any) {
      useAppStore().recordFailure(modelId)
      turn.responses[role].text = buildStoryLiveFallback(role, premise.value)
      turn.responses[role].status = 'error'
      turn.responses[role].error = err?.message || '生成失败'
    }

    syncEnvelopeState()
  }

  /** Raw story generation (ending check done by useStoryFlow) */
  async function _continueStoryRaw(input: string) {
    const assignment = ensureAssignment()
    if (!assignment) {
      error.value = '当前没有可用模型，请先在设置或模型页配置。'
      return false
    }

    const trimmed = input.trim()
    if (!trimmed || processing.value) return false

    processing.value = true
    error.value = ''
    wrapError.value = ''
    updateMeta({ wrapResult: null, phase: 'directing' as StoryLivePhase })

    const turn = buildPendingTurn(trimmed, assignment)
    turns.value.push(turn)
    draftInput.value = ''
    envelope.value.status = 'active'

    // Phase 1: logic + emotion first
    const currentState = storyState.value
    await generateRole(turn, 'logic', currentState)
    await generateRole(turn, 'emotion', currentState)

    // Update story state after logic+emotion (before twist evaluation)
    const intermediateState = updateStoryState(
      storyState.value,
      trimmed,
      turn.responses.logic.text || '',
      turn.responses.emotion.text || '',
    )

    // Build tension history before persisting to avoid stale intermediate state
    intermediateState.tensionHistory = [
      ...storyState.value.tensionHistory,
      intermediateState.tension,
    ].slice(-20)
    updateMeta({ storyState: intermediateState, phase: 'live' as StoryLivePhase })

    // Phase 2: evaluate twist conditions, fire as deferred event
    const currentRound = turns.value.length
    const twistResult = shouldTriggerTwist(
      trimmed,
      currentRound,
      lastTwistRound.value,
      intermediateState,
    )

    if (twistResult.shouldTrigger) {
      updateMeta({ lastTwistRound: currentRound })
      await generateRole(turn, 'twist', intermediateState)
    } else {
      // Mark twist as explicitly skipped
      turn.responses.twist.status = 'done'
      turn.responses.twist.text = ''
    }

    processing.value = false
    syncEnvelopeState()
    return true
  }

  async function endSession(userText: string) {
    const totalRounds = turns.value.length
    const grade = detectEndingGrade(
      totalRounds,
      storyState.value.tension,
      storyState.value.unresolved,
      storyState.value.tensionHistory,
    )

    updateMeta({ phase: 'ended' as StoryLivePhase })
    envelope.value.status = 'completed'
    envelope.value.ending = {
      title: grade === 'optimal' ? '完美落幕' : grade === 'hidden' ? '隐线浮现' : grade === 'failure' ? '戛然而止' : '故事收束',
      grade,
      summary: `共演 ${totalRounds} 轮后，用户选择结束故事。张力 ${storyState.value.tension}/5，未解线索 ${storyState.value.unresolved.length} 条。`,
      payload: {
        totalRounds,
        tension: storyState.value.tension,
        unresolvedCount: storyState.value.unresolved.length,
        characters: storyState.value.characters,
        userText,
      },
    }
    persist()
  }

  async function startStory(premiseText: string) {
    const trimmed = premiseText.trim()
    if (!trimmed) return false

    if (!turns.value.length) {
      resetSession(trimmed)
    } else {
      updateMeta({
        premise: trimmed,
        storyState: createInitialState(trimmed),
        phase: 'premise' as StoryLivePhase,
      })
      envelope.value.seed = {
        id: 'story-live-opening',
        label: '剧情开场',
        payload: { premise: trimmed },
      }
      persist()
    }

    return _continueStoryRaw(trimmed)
  }

  async function generateWrap(mode: StoryLiveWrapMode) {
    const assignment = ensureAssignment()
    if (!assignment || !turns.value.length || processing.value || wrapBusy.value) return

    updateMeta({ phase: 'wrapping' as StoryLivePhase })

    const modelId = assignment.logic
    const pending: StoryLiveWrapResult = {
      mode,
      modelId,
      modelName: getModelName(modelId),
      text: '',
      status: 'generating',
      updatedAt: Date.now(),
    }
    wrapError.value = ''
    updateMeta({ wrapResult: pending })
    persist()

    try {
      const text = await collectText(
        streamModelChat({
          modelId,
          messages: [
            { role: 'system', content: buildStoryLiveWrapSystemPrompt(mode) },
            {
              role: 'user',
              content: buildStoryLiveWrapUserPrompt({
                mode,
                premise: premise.value,
                directorMemory: directorMemory.value.map((item) => item.summary).join('\n'),
                turns: turns.value,
              }),
            },
          ],
        }),
      )

      updateMeta({
        wrapResult: {
          mode,
          modelId,
          modelName: getModelName(modelId),
          text: text || buildStoryLiveWrapFallback(mode, premise.value, turns.value),
          status: 'done',
          updatedAt: Date.now(),
        },
        phase: 'live' as StoryLivePhase,
      })
    } catch (err: any) {
      useAppStore().recordFailure(modelId)
      wrapError.value = err?.message || '整理失败，已给出本地草稿'
      updateMeta({
        wrapResult: {
          mode,
          modelId,
          modelName: getModelName(modelId),
          text: buildStoryLiveWrapFallback(mode, premise.value, turns.value),
          status: 'error',
          error: err?.message || '整理失败',
          updatedAt: Date.now(),
        },
        phase: 'live' as StoryLivePhase,
      })
    }

    persist()
  }

  function restart(premiseText = premise.value || CURRENT_PROMISE) {
    resetSession(premiseText || CURRENT_PROMISE)
  }

  return {
    envelope,
    turns,
    draftInput,
    processing,
    error,
    wrapError,
    hydrated,
    resumed,
    premise,
    modelAssignment,
    wrapResult,
    latestDirectorCue,
    started,
    wrapBusy,
    phase,
    storyState,
    init,
    markPaused,
    markActive,
    updateDraft,
    ensureAssignment,
    startStory,
    _continueStoryRaw,
    endSession,
    generateWrap,
    restart,
    getModelName,
  }
})
