import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { streamModelChat } from '@/services/runtime'
import {
  getCase,
  type MultiLifeCase,
  type MultiLifeRound,
  type MultiLifeSessionMeta,
  type MultiLifeSessionRecord,
  type MultiLifeRoleResponse,
} from '@/features/play-modes/multi-life'
import {
  buildRoleSystemPrompt,
  buildRoleUserPrompt,
  buildChallengePrompt,
  buildEndingSystemPrompt,
  buildEndingUserPrompt,
} from '@/features/play-modes/multi-life'
import { buildMLHistoryEntry, buildMLSummary } from '@/features/play-modes/multi-life'
import {
  STORAGE_KEY,
  uid,
  cloneForStorage,
  collectText,
  createEnvelope,
  getMeta,
  chooseCaseModels,
  normalizeAssignment,
  buildBranchMemory,
  generateEvidenceCard,
  detectContradictions,
  normalizeRecord,
} from './multi-life-helpers'

export const useMultiLifeStore = defineStore('multi-life', () => {
  // --- State ---
  const envelope = ref(createEmptyEnvelope())
  const rounds = ref<MultiLifeRound[]>([])
  const selectedCaseId = ref('')
  const caseData = ref<MultiLifeCase | null>(null)
  const processing = ref(false)
  const endingGenerating = ref(false)
  const error = ref('')
  const hydrated = ref(false)
  const resumed = ref(false)

  function createEmptyEnvelope() {
    const now = new Date().toISOString()
    return {
      schemaVersion: '1.0.0',
      mode: 'multi-life' as const,
      sessionId: '',
      status: 'pending' as const,
      round: 0,
      startedAt: now,
      updatedAt: now,
      seed: null,
      summary: null,
      ending: null,
      history: [] as const,
      pauseState: null,
      cache: null,
      meta: { phase: 'setup' } as Record<string, unknown>,
    }
  }

  // --- Computed ---
  const meta = computed(() => getMeta(envelope.value))
  const phase = computed(() => meta.value.phase)
  const currentRound = computed(() => meta.value.currentRound)
  const challengeRemaining = computed(() => meta.value.challengeRemaining)
  const modelAssignment = computed(() => meta.value.modelAssignment)
  const evidenceCards = computed(() => meta.value.evidenceCards)
  const trustMap = computed(() => meta.value.trustMap)
  const branchMemory = computed(() => meta.value.branchMemory)
  const ending = computed(() => meta.value.ending)
  const lastRound = computed(() => rounds.value.at(-1) ?? null)
  const hasContradiction = computed(() => (lastRound.value?.contradictions.length ?? 0) > 0)
  const started = computed(() => rounds.value.length > 0)
  const isLastRound = computed(() => {
    if (!caseData.value) return false
    return currentRound.value >= caseData.value.totalRounds
  })

  // --- Actions ---

  function init() {
    const appStore = useAppStore()
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      hydrated.value = true
      return
    }

    try {
      const record = JSON.parse(raw) as MultiLifeSessionRecord
      const normalized = normalizeRecord(record, appStore)

      envelope.value = normalized.envelope
      rounds.value = normalized.rounds
      selectedCaseId.value = normalized.selectedCaseId

      if (normalized.selectedCaseId) {
        caseData.value = getCase(normalized.selectedCaseId) ?? null
      }

      if (meta.value.phase !== 'setup' && rounds.value.length > 0) {
        resumed.value = true
      }

      hydrated.value = true
    } catch {
      hydrated.value = true
    }
  }

  function selectCase(caseId: string) {
    const c = getCase(caseId)
    if (!c) {
      error.value = '案件不存在'
      return
    }

    caseData.value = c
    selectedCaseId.value = caseId
    envelope.value = createEnvelope(c)
    rounds.value = []
    error.value = ''
    resumed.value = false
    persist()
  }

  async function startRound() {
    if (!caseData.value) return
    if (processing.value) return

    const c = caseData.value
    const appStore = useAppStore()
    const m = meta.value

    // Ensure model assignment
    const assignment = normalizeAssignment(m.modelAssignment, appStore)
    if (!assignment) {
      error.value = '需要至少 3 个不同 provider 的模型才能开始'
      return
    }

    processing.value = true
    error.value = ''

    const nextRound = m.currentRound + 1
    const roundConfig = c.rounds[nextRound - 1]
    if (!roundConfig) {
      processing.value = false
      error.value = '已达到最大轮次'
      return
    }

    // Initialize role responses with generating status
    const roleIds = c.roles.map((r) => r.id)
    const modelMap: Record<string, string> = { a: assignment.a, b: assignment.b, c: assignment.c }

    const responses: MultiLifeRoleResponse[] = roleIds.map((roleId) => {
      const modelId = modelMap[roleId]
      const model = appStore.getModel(modelId)
      return {
        roleId,
        modelId,
        modelName: model?.name ?? modelId,
        text: '',
        status: 'generating',
      }
    })

    const roundObj: MultiLifeRound = {
      id: uid(),
      roundNumber: nextRound,
      scene: roundConfig.scene,
      responses,
      contradictions: [],
      playerChoice: null,
      evidenceCard: null,
      createdAt: Date.now(),
    }

    // Push round early so UI can show generating state
    rounds.value.push(roundObj)

    try {
      // Generate 3 role responses in parallel
      const genPromises = c.roles.map(async (role) => {
        const resp = roundObj.responses.find((r) => r.roleId === role.id)!
        try {
          const systemPrompt = buildRoleSystemPrompt(role, c)
          const previousResponses = rounds.value
            .slice(0, -1)
            .flatMap((r) => r.responses.filter((rr) => rr.status === 'done').map((rr) => ({ roleId: rr.roleId, text: rr.text })))

          const userPrompt = buildRoleUserPrompt(
            role, c, roundConfig, previousResponses, branchMemory.value,
          )

          const text = await collectText(
            streamModelChat({
              modelId: resp.modelId,
              messages: [
                { role: 'system', content: systemPrompt },
                { role: 'user', content: userPrompt },
              ],
            }),
          )

          resp.text = text || '（未生成证词）'
          resp.status = 'done'
        } catch (e) {
          resp.status = 'error'
          resp.error = e instanceof Error ? e.message : '生成失败'
          resp.text = '（证词生成失败）'
        }
      })

      await Promise.all(genPromises)

      // Detect contradictions (local keyword matching)
      roundObj.contradictions = detectContradictions(
        roundConfig,
        roundObj.responses,
      )

      // Update meta
      updateMeta({
        phase: 'investigation',
        currentRound: nextRound,
        branchMemory: buildBranchMemory(rounds.value),
      })

      // Check if this was the last round
      if (nextRound >= c.totalRounds) {
        // Auto-accept and prepare for ending
        roundObj.playerChoice = { type: 'accept' }
        const card = generateEvidenceCard(roundObj, c)
        roundObj.evidenceCard = card

        updateMeta({
          phase: 'resolution',
          evidenceCards: card ? [...meta.value.evidenceCards, card] : meta.value.evidenceCards,
        })
      }

      persist()
    } catch (e) {
      error.value = e instanceof Error ? e.message : '生成出错'
    } finally {
      processing.value = false
    }
  }

  function acceptRound() {
    const last = lastRound.value
    if (!last || last.playerChoice) return
    if (!caseData.value) return

    last.playerChoice = { type: 'accept' }
    const card = generateEvidenceCard(last, caseData.value)
    last.evidenceCard = card

    updateMeta({
      evidenceCards: card ? [...meta.value.evidenceCards, card] : meta.value.evidenceCards,
      branchMemory: buildBranchMemory(rounds.value),
    })

    persist()
  }

  async function challengeRole(roleId: string) {
    const last = lastRound.value
    if (!last || last.playerChoice) return
    if (!caseData.value) return
    if (meta.value.challengeRemaining <= 0) return

    const role = caseData.value.roles.find((r) => r.id === roleId)
    if (!role) return

    const resp = last.responses.find((r) => r.roleId === roleId)
    if (!resp || resp.status !== 'done') return

    processing.value = true
    last.playerChoice = { type: 'challenge', challengedRoleId: roleId }

    try {
      const roundConfig = caseData.value.rounds[last.roundNumber - 1]
      const contradiction = last.contradictions[0]

      const challengePrompt = buildChallengePrompt(
        role,
        roundConfig,
        resp.text,
        contradiction?.topic ?? '证词',
        last.responses
          .filter((r) => r.roleId !== roleId && r.status === 'done')
          .map((r) => ({ roleId: r.roleId, text: r.text })),
      )

      const text = await collectText(
        streamModelChat({
          modelId: resp.modelId,
          messages: [
            { role: 'system', content: buildRoleSystemPrompt(role, caseData.value) },
            { role: 'user', content: challengePrompt },
          ],
        }),
      )

      resp.isChallenged = true
      resp.challengeResponse = text || '（未生成补充回答）'

      // Update trust
      const isHonest = role.lyingPattern === 'never' || role.reliability >= 0.7
      const currentTrust = meta.value.trustMap[roleId] ?? 0
      const newTrustMap = { ...meta.value.trustMap }
      newTrustMap[roleId] = isHonest ? currentTrust + 2 : currentTrust - 1

      const card = generateEvidenceCard(last, caseData.value)
      last.evidenceCard = card

      updateMeta({
        challengeRemaining: meta.value.challengeRemaining - 1,
        challengeUsed: meta.value.challengeUsed + 1,
        trustMap: newTrustMap,
        evidenceCards: card ? [...meta.value.evidenceCards, card] : meta.value.evidenceCards,
        branchMemory: buildBranchMemory(rounds.value),
      })

      persist()
    } catch (e) {
      error.value = e instanceof Error ? e.message : '质疑失败'
    } finally {
      processing.value = false
    }
  }

  async function generateEnding() {
    if (!caseData.value || endingGenerating.value) return

    endingGenerating.value = true
    error.value = ''

    try {
      const appStore = useAppStore()
      const assignment = normalizeAssignment(meta.value.modelAssignment, appStore)
      if (!assignment) {
        error.value = '无法获取模型'
        endingGenerating.value = false
        return
      }

      // Use first model for ending generation
      const modelId = assignment.a

      const text = await collectText(
        streamModelChat({
          modelId,
          messages: [
            { role: 'system', content: buildEndingSystemPrompt() },
            {
              role: 'user',
              content: buildEndingUserPrompt(
                caseData.value,
                rounds.value.map((r) => ({
                  playerChoice: r.playerChoice,
                  contradictions: r.contradictions,
                })),
                meta.value.evidenceCards,
                meta.value.trustMap,
                meta.value.challengeUsed,
              ),
            },
          ],
        }),
      )

      const sections = parseEndingSections(text)

      const endingData = {
        playerNarrative: sections.playerNarrative,
        truthNarrative: sections.truthNarrative,
        deviationAnalysis: sections.deviationAnalysis,
        unexploredBranches: sections.unexploredBranches,
      }

      updateMeta({
        phase: 'ended',
        ending: endingData,
      })

      // Update envelope ending
      envelope.value.ending = {
        title: '你的版本',
        grade: 'normal',
        summary: endingData.deviationAnalysis,
        payload: endingData,
      }

      // Update history
      envelope.value.history = rounds.value.map((r, i) =>
        buildMLHistoryEntry(r, caseData.value!),
      )
      envelope.value.summary = buildMLSummary(envelope.value, rounds.value, caseData.value)

      persist()
    } catch (e) {
      error.value = e instanceof Error ? e.message : '生成结局失败'
    } finally {
      endingGenerating.value = false
    }
  }

  function restart() {
    if (selectedCaseId.value) {
      selectCase(selectedCaseId.value)
    } else {
      envelope.value = createEmptyEnvelope()
      rounds.value = []
      caseData.value = null
      selectedCaseId.value = ''
    }
    error.value = ''
    resumed.value = false
    localStorage.removeItem(STORAGE_KEY)
  }

  function getModelName(modelId: string): string {
    const appStore = useAppStore()
    return appStore.getModel(modelId)?.name ?? modelId
  }

  // --- Internal helpers ---

  function updateMeta(partial: Partial<MultiLifeSessionMeta>) {
    const current = { ...meta.value, ...partial }
    envelope.value.meta = current as unknown as Record<string, unknown>
    envelope.value.round = current.currentRound
    envelope.value.updatedAt = new Date().toISOString()
  }

  function persist() {
    const record: MultiLifeSessionRecord = {
      envelope: cloneForStorage(envelope.value),
      rounds: cloneForStorage(rounds.value),
      selectedCaseId: selectedCaseId.value,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record))
  }

  function parseEndingSections(text: string) {
    const extract = (label: string): string => {
      const regex = new RegExp(`【${label}】\\s*([\\s\\S]*?)(?=【|$)`)
      const match = text.match(regex)
      return match?.[1]?.trim() || ''
    }

    return {
      playerNarrative: extract('你的版本'),
      truthNarrative: extract('真相版本'),
      deviationAnalysis: extract('偏差分析'),
      unexploredBranches: extract('未探索分支'),
    }
  }

  return {
    // State
    envelope,
    rounds,
    selectedCaseId,
    caseData,
    processing,
    endingGenerating,
    error,
    hydrated,
    resumed,

    // Computed
    meta,
    phase,
    currentRound,
    challengeRemaining,
    modelAssignment,
    evidenceCards,
    trustMap,
    branchMemory,
    ending,
    lastRound,
    hasContradiction,
    started,
    isLastRound,

    // Actions
    init,
    selectCase,
    startRound,
    acceptRound,
    challengeRole,
    generateEnding,
    restart,
    getModelName,
  }
})
