import { defineStore } from 'pinia'
import { ref, computed, shallowRef } from 'vue'
import { useAppStore } from '@/stores/app'
import { streamModelChat } from '@/services/runtime'
import { sanitizeModelOutput } from '@/utils/modelOutput'
import type { PlayModeSessionEnvelope } from '@/features/play-modes/shared'
import {
  getCase,
  type MultiLifeCase,
  type MultiLifeModelAssignment,
  type MultiLifeRound,
  type MultiLifeSessionMeta,
  type MultiLifeSessionRecord,
  type MultiLifeRoleResponse,
} from '@/features/play-modes/multi-life'
import {
  buildSceneSystemPrompt,
  buildSceneUserPrompt,
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
  streamInto,
  streamMockInto,
  createEnvelope,
  getMeta,
  getAssignmentMode,
  normalizeAssignment,
  buildBranchMemory,
  generateEvidenceCard,
  detectContradictions,
  normalizeRecord,
} from './multi-life-helpers'

const SCENE_STREAM_TIMEOUT_MS = 9000
const ROLE_STREAM_TIMEOUT_MS = 12000
const CHALLENGE_STREAM_TIMEOUT_MS = 10000
const ENDING_STREAM_TIMEOUT_MS = 12000

function createTimeoutController(timeoutMs: number) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  return {
    signal: controller.signal,
    stop() {
      window.clearTimeout(timer)
    },
    get timedOut() {
      return controller.signal.aborted
    },
  }
}

export const useMultiLifeStore = defineStore('multi-life', () => {
  // --- State ---
  const envelope = ref<PlayModeSessionEnvelope>(createEmptyEnvelope())
  const rounds = ref<MultiLifeRound[]>([])
  const selectedCaseId = ref('')
  const caseData = ref<MultiLifeCase | null>(null)
  const processing = ref(false)
  const endingGenerating = ref(false)
  const error = ref('')
  const hydrated = ref(false)
  const resumed = ref(false)
  const modelDiverse = ref(true)
  const useMock = ref(false)
  const modelPicked = ref(false)
  const modelWarning = ref('')
  const roundStarting = ref(false)
  const streamingTexts = shallowRef<Record<string, string>>({})
  const streamingScene = shallowRef<string>('')

  function emitStream(key: string, text: string) {
    streamingTexts.value = { ...streamingTexts.value, [key]: text }
  }

  function appendStream(key: string, chunk: string) {
    emitStream(key, `${streamingTexts.value[key] ?? ''}${chunk}`)
  }

  function clearStream(key: string) {
    const next = { ...streamingTexts.value }
    delete next[key]
    streamingTexts.value = next
  }

  function formatStreamedText(raw: string) {
    return sanitizeModelOutput(raw)
      .content
      .replace(/\r\n?/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
  }

  function paragraphizeNarrative(text: string) {
    const normalized = formatStreamedText(text)
    if (!normalized) return ''

    const existingParagraphs = normalized
      .split(/\n{2,}/)
      .map((part) => part.trim())
      .filter(Boolean)

    if (existingParagraphs.length > 1) {
      return existingParagraphs.join('\n\n')
    }

    const sentences = normalized
      .split(/(?<=[。！？])/)
      .map((part) => part.trim())
      .filter(Boolean)

    if (sentences.length <= 1) return normalized

    const chunkSize = sentences.length >= 4 ? 2 : 1
    const paragraphs: string[] = []

    for (let index = 0; index < sentences.length; index += chunkSize) {
      paragraphs.push(sentences.slice(index, index + chunkSize).join(''))
    }

    if (paragraphs.length > 3) {
      const head = paragraphs.slice(0, 2)
      const tail = paragraphs.slice(2).join('')
      return [...head, tail].join('\n\n')
    }

    return paragraphs.join('\n\n')
  }

  function createEmptyEnvelope(): PlayModeSessionEnvelope {
    const now = new Date().toISOString()
    return {
      schemaVersion: '1.0.0',
      mode: 'multi-life',
      sessionId: '',
      status: 'pending',
      round: 0,
      startedAt: now,
      updatedAt: now,
      seed: null,
      summary: null,
      ending: null,
      history: [],
      pauseState: null,
      cache: null,
      meta: { phase: 'setup' },
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
  const assignmentMode = computed(() => getAssignmentMode(modelAssignment.value))
  const assignmentLabel = computed(() => {
    if (assignmentMode.value === 'live') return 'Live Multi-Model'
    if (assignmentMode.value === 'demo') return 'Mock Demo'
    if (assignmentMode.value === 'mock') return 'Local Mock'
    if (assignmentMode.value === 'mixed') return 'Mixed Assignment'
    return 'No Models'
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
      if (meta.value.modelAssignment) {
        modelPicked.value = true
        const ids = Object.values(meta.value.modelAssignment)
        const allMock = ids.every((id) => typeof id === 'string' && id.startsWith('mock'))
        useMock.value = allMock
        modelDiverse.value = allMock
          ? false
          : new Set(ids.map((id) => appStore.getModel(id)?.provider).filter(Boolean)).size >= 3
      }
      streamingScene.value = normalized.rounds.at(-1)?.scene ?? ''
      streamingTexts.value = {}

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
    modelDiverse.value = true
    useMock.value = false
    modelPicked.value = false
    modelWarning.value = ''
    roundStarting.value = false
    streamingTexts.value = {}
    streamingScene.value = ''
    resumed.value = false
    persist()
  }

  function pickRandomModels() {
    const appStore = useAppStore()
    const pickedIds = appStore.pickLabModelIds(3, undefined, 'multi-life:auto')
    const pickedModels = pickedIds
      .map((id) => appStore.getModel(id))
      .filter(Boolean)

    modelWarning.value = ''

    if (pickedModels.length === 0) {
      modelWarning.value = '没有可用模型，将使用模拟数据'
      modelDiverse.value = false
      useMock.value = true
      updateMeta({ modelAssignment: { a: 'mock-a', b: 'mock-b', c: 'mock-c' } as any })
      modelPicked.value = true
      return
    }

    const picked = pickedModels.slice(0, 3)
    while (picked.length < 3) {
      picked.push(pickedModels[picked.length % pickedModels.length])
    }

    const ids = picked.map(m => m.id)
    const uniqueIds = new Set(ids)
    const providers = new Set(picked.map(m => m.provider))
    modelDiverse.value = uniqueIds.size === 3 && providers.size >= 3

    if (uniqueIds.size < ids.length) {
      modelWarning.value = '模型不足，部分角色将使用相同模型，证词差异可能较小'
    } else if (providers.size < 3) {
      modelWarning.value = '当前优先使用快答模型，部分角色可能来自同一 provider'
    }

    updateMeta({ modelAssignment: { a: ids[0], b: ids[1], c: ids[2] } as any })
    useMock.value = false
    modelPicked.value = true
  }

  function getAssignedModelName(roleId: string): string {
    const assignment = meta.value.modelAssignment
    if (!assignment) return ''
    const modelId = (assignment as unknown as Record<string, string>)[roleId]
    if (!modelId || modelId.startsWith('mock')) return '模拟角色'
    return useAppStore().getModel(modelId)?.name ?? modelId
  }

  function resolveModels(appStore: ReturnType<typeof useAppStore>): { assignment: MultiLifeModelAssignment; diverse: boolean; mock: boolean } {
    const rawAssignment = meta.value.modelAssignment as MultiLifeModelAssignment | null

    if (rawAssignment && Object.values(rawAssignment).every(id => typeof id === 'string' && id.startsWith('mock'))) {
      modelDiverse.value = false
      return { assignment: rawAssignment, diverse: false, mock: true }
    }

    const normalized = normalizeAssignment(rawAssignment, appStore)
    if (!normalized) {
      modelDiverse.value = false
      return { assignment: { a: 'mock-a', b: 'mock-b', c: 'mock-c' }, diverse: false, mock: true }
    }

    if (
      !rawAssignment
      || rawAssignment.a !== normalized.assignment.a
      || rawAssignment.b !== normalized.assignment.b
      || rawAssignment.c !== normalized.assignment.c
    ) {
      updateMeta({ modelAssignment: normalized.assignment })
    }

    modelDiverse.value = normalized.diverse
    return { assignment: normalized.assignment, diverse: normalized.diverse, mock: false }
  }

  async function startRound() {
    if (!caseData.value) return
    if (processing.value) return
    if (!modelPicked.value) return

    const c = caseData.value
    const appStore = useAppStore()
    const m = meta.value
    const previousPhase = m.phase
    const previousRound = m.currentRound

    const models = resolveModels(appStore)
    const modelMap = models.assignment as unknown as Record<string, string>
    useMock.value = models.mock
    if (!models.mock && !models.diverse && !modelWarning.value) {
      modelWarning.value = '当前优先使用快答模型，部分角色可能来自同一 provider'
    }

    processing.value = true
    roundStarting.value = true
    error.value = ''

    const nextRound = m.currentRound + 1
    const roundConfig = c.rounds[nextRound - 1]
    if (!roundConfig) {
      processing.value = false
      roundStarting.value = false
      error.value = '已达到最大轮次'
      return
    }

    const roleIds = c.roles.map((r) => r.id)
    const responses: MultiLifeRoleResponse[] = roleIds.map((roleId) => {
      const modelId = modelMap[roleId]
      const model = appStore.getModel(modelId)
      return {
        roleId,
        modelId,
        modelName: models.mock ? '模拟角色' : (model?.name ?? modelId),
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

    try {
      rounds.value.push(roundObj)
      updateMeta({ phase: 'investigation', currentRound: nextRound })

      if (!meta.value.modelAssignment) {
        updateMeta({ modelAssignment: models.assignment as any })
      }

      roundStarting.value = false

      // Stream scene text (paragraph by paragraph)
      const sceneText = paragraphizeNarrative(roundConfig.scene)
      streamingScene.value = ''
      if (models.mock) {
        await streamMockInto(sceneText, (chunk) => {
          streamingScene.value += chunk
        }, 10)
      } else {
        const timeout = createTimeoutController(SCENE_STREAM_TIMEOUT_MS)
        try {
          let sceneRaw = ''
          let sceneUseFallback = false
          const sceneResult = await streamInto(
              streamModelChat({
                modelId: models.assignment.a,
                signal: timeout.signal,
                traceLabel: 'multi-life:scene',
                traceMeta: {
                  caseId: c.id,
                  round: nextRound,
                },
                messages: [
                  { role: 'system', content: buildSceneSystemPrompt() },
                  { role: 'user', content: buildSceneUserPrompt(c, roundConfig) },
                ],
              }),
              (chunk) => {
                sceneRaw += chunk
                if (sceneUseFallback || shouldFallbackToNarrative(sceneRaw)) {
                  sceneUseFallback = true
                  streamingScene.value = sceneText
                  return
                }
                const cleaned = paragraphizeNarrative(sceneRaw)
                if (cleaned) streamingScene.value = cleaned
              },
            )
          const cleanedScene = paragraphizeNarrative(sceneResult)
          streamingScene.value = sceneUseFallback || shouldFallbackToNarrative(sceneResult)
            ? sceneText
            : (cleanedScene || sceneText)
        } catch {
          if (timeout.timedOut) {
            appStore.recordSlowResponse(models.assignment.a)
          }
          streamingScene.value = sceneText
        } finally {
          timeout.stop()
        }
      }

      if (models.mock) {
        const tasks = c.roles.map(async (role) => {
          const resp = roundObj.responses.find((r) => r.roleId === role.id)!
          const fullText = generateMockTestimony(role, roundConfig.roleDirectives[role.id], nextRound)
          const sentences = fullText.split(/(?<=[。！？])/).filter(Boolean)
          const key = `${roundObj.id}-${role.id}`
          for (let si = 0; si < sentences.length; si++) {
            const soFar = sentences.slice(0, si + 1).join('')
            emitStream(key, soFar)
            await new Promise(r => setTimeout(r, 140))
          }
          resp.text = fullText
          resp.status = 'done'
          clearStream(key)
        })
        await Promise.allSettled(tasks)
      } else {
        const previousResponses = rounds.value
          .slice(0, -1)
          .flatMap((r) => r.responses.filter((rr) => rr.status === 'done').map((rr) => ({ roleId: rr.roleId, text: rr.text })))

        const tasks = c.roles.map(async (role) => {
          const resp = roundObj.responses.find((r) => r.roleId === role.id)!
          const fallbackText = generateMockTestimony(role, roundConfig.roleDirectives[role.id], nextRound)
          const timeout = createTimeoutController(ROLE_STREAM_TIMEOUT_MS)
          try {
            const systemPrompt = buildRoleSystemPrompt(role, c)
            const userPrompt = buildRoleUserPrompt(
              role, c, roundConfig, previousResponses, branchMemory.value,
            )

            const key = `${roundObj.id}-${role.id}`
            let responseRaw = ''
            let responseUseFallback = false
            const text = await streamInto(
              streamModelChat({
                modelId: resp.modelId,
                signal: timeout.signal,
                traceLabel: `multi-life:role:${role.id}`,
                traceMeta: {
                  caseId: c.id,
                  round: nextRound,
                },
                messages: [
                  { role: 'system', content: systemPrompt },
                  { role: 'user', content: userPrompt },
                ],
              }),
              (chunk) => {
                responseRaw += chunk
                if (responseUseFallback || shouldFallbackToNarrative(responseRaw)) {
                  responseUseFallback = true
                  emitStream(key, fallbackText)
                  return
                }
                const cleaned = formatStreamedText(responseRaw)
                if (cleaned) emitStream(key, cleaned)
              },
            )

            const cleanedText = formatStreamedText(text)
            resp.text = responseUseFallback || shouldFallbackToNarrative(text)
              ? fallbackText
              : (cleanedText || fallbackText)
            resp.status = 'done'
            clearStream(key)
          } catch (e) {
            if (timeout.timedOut) {
              appStore.recordSlowResponse(resp.modelId)
            }
            resp.status = 'done'
            resp.error = undefined
            resp.text = fallbackText
            clearStream(`${roundObj.id}-${role.id}`)
          } finally {
            timeout.stop()
          }
        })
        await Promise.allSettled(tasks)
      }

      for (const response of roundObj.responses) {
        if (response.status !== 'done' && response.status !== 'error') {
          response.status = 'done'
          response.text ||= generateMockTestimony(
            c.roles.find((role) => role.id === response.roleId)!,
            roundConfig.roleDirectives[response.roleId],
            nextRound,
          )
        }
      }

      roundObj.contradictions = detectContradictions(roundConfig, roundObj.responses)

      updateMeta({
        branchMemory: buildBranchMemory(rounds.value),
      })

      if (nextRound >= c.totalRounds) {
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
      rounds.value = rounds.value.filter((round) => round.id !== roundObj.id)
      updateMeta({ phase: previousPhase, currentRound: previousRound })
      streamingScene.value = rounds.value.at(-1)?.scene ?? ''
      for (const roleId of roleIds) {
        clearStream(`${roundObj.id}-${roleId}`)
      }
      error.value = e instanceof Error ? e.message : '生成出错'
    } finally {
      processing.value = false
      roundStarting.value = false
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
    const appStore = useAppStore()

    const role = caseData.value.roles.find((r) => r.id === roleId)
    if (!role) return

    const resp = last.responses.find((r) => r.roleId === roleId)
    if (!resp || resp.status !== 'done') return

    processing.value = true
    last.playerChoice = { type: 'challenge', challengedRoleId: roleId }
    const isHonest = role.lyingPattern === 'never' || role.reliability >= 0.7

    try {
      if (useMock.value) {
        const fullText = isHonest
          ? generateMockChallengeHonest(role, last.contradictions[0]?.topic ?? '证词')
          : generateMockChallengeLiar(role, last.contradictions[0]?.topic ?? '证词')
        const key = `${last.id}-ch-${roleId}`
        await streamMockInto(fullText, (chunk) => {
          appendStream(key, chunk)
        }, 18 + Math.random() * 6)
        resp.isChallenged = true
        resp.challengeResponse = fullText
        clearStream(key)
      } else {
        const roundConfig = caseData.value.rounds[last.roundNumber - 1]
        const contradiction = last.contradictions[0]

        const challengePrompt = buildChallengePrompt(
          role, roundConfig, resp.text,
          contradiction?.topic ?? '证词',
          last.responses.filter((r) => r.roleId !== roleId && r.status === 'done').map((r) => ({ roleId: r.roleId, text: r.text })),
        )

        const key = `${last.id}-ch-${roleId}`
        const fallbackText = isHonest
          ? generateMockChallengeHonest(role, contradiction?.topic ?? '证词')
          : generateMockChallengeLiar(role, contradiction?.topic ?? '证词')
        const timeout = createTimeoutController(CHALLENGE_STREAM_TIMEOUT_MS)
        try {
          let challengeRaw = ''
          let challengeUseFallback = false
          const text = await streamInto(
            streamModelChat({
              modelId: resp.modelId,
              signal: timeout.signal,
              traceLabel: `multi-life:challenge:${roleId}`,
              traceMeta: {
                caseId: caseData.value.id,
                round: last.roundNumber,
              },
              messages: [
                { role: 'system', content: buildRoleSystemPrompt(role, caseData.value) },
                { role: 'user', content: challengePrompt },
              ],
            }),
            (chunk) => {
              challengeRaw += chunk
              if (challengeUseFallback || shouldFallbackToNarrative(challengeRaw)) {
                challengeUseFallback = true
                emitStream(key, fallbackText)
                return
              }
              const cleaned = formatStreamedText(challengeRaw)
              if (cleaned) emitStream(key, cleaned)
            },
          )
          const cleanedText = formatStreamedText(text)
          resp.challengeResponse = challengeUseFallback || shouldFallbackToNarrative(text)
            ? fallbackText
            : (cleanedText || fallbackText)
        } catch {
          if (timeout.timedOut) {
            appStore.recordSlowResponse(resp.modelId)
          }
          resp.challengeResponse = fallbackText
        } finally {
          timeout.stop()
        }
        resp.isChallenged = true
        clearStream(key)
      }

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
      clearStream(`${last.id}-ch-${roleId}`)
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
      const models = resolveModels(appStore)

      let endingData: MultiLifeSessionMeta['ending']

      if (models.mock) {
        await new Promise((r) => setTimeout(r, 200))
        endingData = generateMockEnding(caseData.value, rounds.value, meta.value)
      } else {
        const modelId = models.assignment.a
        const timeout = createTimeoutController(ENDING_STREAM_TIMEOUT_MS)
        try {
          const text = await collectText(
            streamModelChat({
              modelId,
              signal: timeout.signal,
              traceLabel: 'multi-life:ending',
              traceMeta: {
                caseId: caseData.value.id,
                rounds: rounds.value.length,
              },
              messages: [
                { role: 'system', content: buildEndingSystemPrompt() },
                {
                  role: 'user',
                  content: buildEndingUserPrompt(
                    caseData.value,
                    rounds.value.map((r) => ({ playerChoice: r.playerChoice, contradictions: r.contradictions })),
                    meta.value.evidenceCards,
                    meta.value.trustMap,
                    meta.value.challengeUsed,
                  ),
                },
              ],
            }),
          )
          const sections = parseEndingSections(text)
          endingData = {
            playerNarrative: sections.playerNarrative,
            truthNarrative: sections.truthNarrative,
            deviationAnalysis: sections.deviationAnalysis,
            unexploredBranches: sections.unexploredBranches,
          }
        } catch {
          if (timeout.timedOut) {
            appStore.recordSlowResponse(modelId)
          }
          endingData = generateMockEnding(caseData.value, rounds.value, meta.value)
        } finally {
          timeout.stop()
        }
      }

      updateMeta({ phase: 'ended', ending: endingData })

      envelope.value.ending = {
        title: '你的版本',
        grade: 'normal',
        summary: endingData?.deviationAnalysis ?? '',
        payload: endingData as unknown as Record<string, unknown>,
      }
      envelope.value.history = rounds.value.map((r) => buildMLHistoryEntry(r, caseData.value!))
      envelope.value.summary = buildMLSummary(envelope.value, rounds.value, caseData.value!)
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
    modelDiverse.value = true
    useMock.value = false
    modelPicked.value = false
    modelWarning.value = ''
    roundStarting.value = false
    streamingTexts.value = {}
    streamingScene.value = ''
    resumed.value = false
    localStorage.removeItem(STORAGE_KEY)
  }

  function getModelName(modelId: string): string {
    if (modelId.startsWith('mock')) return '模拟角色'
    return useAppStore().getModel(modelId)?.name ?? modelId
  }

  // --- Internal ---

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
      unexploredBranches: extract('未探索分支').split('\n').filter(Boolean),
    }
  }

  return {
    envelope, rounds, selectedCaseId, caseData,
    processing, endingGenerating, error, hydrated, resumed,
    modelDiverse, useMock, modelPicked, modelWarning, roundStarting,
    streamingTexts, streamingScene,
    meta, phase, currentRound, challengeRemaining,
    modelAssignment, evidenceCards, trustMap, branchMemory,
    ending, lastRound, hasContradiction, started,
    assignmentMode, assignmentLabel,
    init, selectCase, pickRandomModels, getAssignedModelName,
    startRound, acceptRound,
    challengeRole, generateEnding, restart, getModelName,
  }
})

// --- Mock data generators ---

const MOCK_TEMPLATES = {
  witness: [
    '我当时在现场附近，大概凌晨一点左右听到了一些响动。我往仓库方向看了一眼，雨太大看不太清楚，只能隐约看到一个人影快速离开了。',
    '我记得当时雨下得很大，我打着伞在附近巡逻。突然听到仓库那边传来一声闷响，我赶紧看过去，但只看到一个模糊的身影从门口匆匆离开。',
    '那个时间点我应该在正常巡逻。我确实注意到仓库那边有些不对劲，灯光在闪，但我没有走近去看。',
    '案发那晚我确实看到了一些东西。一个人从仓库方向走出来的速度很快，几乎是在跑。但因为雨和距离，我没法确认是谁。',
    '我承认我看到的画面其实非常模糊。当时雨声很大，我只能看到大约一个人的轮廓从仓库门口离开，身高中等偏矮。',
    '我还记得一个细节：那个人离开的时候似乎手里拿着什么东西，但我没法确认那是什么。当时太黑了。',
    '最近我一直在回忆那晚的情景。我越来越确定我看到的那个人影就是从仓库出来的，而且方向是往南边走的。',
  ],
  suspect: [
    '那天晚上我一直待在家里看电视，根本就没有出门过。你们可以去查我的网络记录和监控。',
    '我跟你说过很多次了，案发时我在家。我看了那部警匪片《暗夜追踪》，从十一点半一直看到凌晨两点才睡。',
    '我和赵六之间确实有过生意往来，但那都是半年前的事情了，我们早就没什么联系了。我不可能因为那点事去做什么。',
    '你说我工具箱里有扳手？谁家没有把扳手？型号一样不代表就是我的。这种工具到处都是，这个证据根本站不住脚。',
    '好吧，我承认和赵六确实有些经济上的往来。但那笔账早就结清了，不存在什么纠纷。你们可以去查银行记录。',
    '我现在越来越紧张了。我没有去过那个仓库，那天晚上我真的在家。你们不能仅凭一把扳手就认定我是凶手吧？',
    '我…我需要冷静一下。是的我和赵六有经济往来，但那笔钱…那确实没有完全结清。但这不代表我做了什么。',
  ],
  analyst: [
    '根据现场物证分析，仓库门没有破坏痕迹，说明凶手有进入仓库的方式。凶器铁扳手被擦拭过，只有死者指纹，说明凶手有一定的反侦查意识。',
    '仓库内发现的工装靴脚印和运动鞋脚印是两个人留下的。赵六穿运动鞋，另一个穿工装靴的人很可能就是凶手。',
    '法医报告显示击打角度来自约1.8米高处，说明凶手身高至少在一米七五以上。凶器上残留的微量纤维还在进一步鉴定中。',
    '通往仓库的监控因暴雨无法辨认，但确实拍到有一辆车在案发时间段经过。这辆车的信息可能是突破口。',
    '嫌疑人李四有仓库的备用钥匙，这是非常关键的证据。加上他工具箱里的扳手和八十万的经济纠纷，嫌疑正在大幅上升。',
    '综合所有证据：李四有动机（经济纠纷）、有能力（备用钥匙）、有机会（工装靴脚印）。我建议对他正式立案调查。',
    '目前的证据链已经相当完整。李四的所谓不在场证明经不起推敲，银行记录也证明他说谎。这就是我们的最佳嫌疑人。',
  ],
} as const

function generateMockTestimony(
  role: { archetype: string; id: string },
  directive: { directive: string; lying: boolean } | undefined,
  roundNumber: number,
): string {
  const templates = MOCK_TEMPLATES[role.archetype as keyof typeof MOCK_TEMPLATES] ?? MOCK_TEMPLATES.witness
  return templates[(roundNumber - 1) % templates.length]
}

function generateMockChallengeHonest(role: { name: string }, topic: string): string {
  return `我真的是在说实话啊！关于${topic}这件事，我可以补充一些细节。我当时很确定自己看到的就是那样的，虽然可能因为光线和距离有些不准确，但大方向是没有错的。你们可以去核实我说的时间点。`
}

function generateMockChallengeLiar(role: { name: string }, topic: string): string {
  return `我…我需要再说一遍，关于${topic}，我说的是事实。你们不能因为别人说了什么就来怀疑我。每个人看到的、记忆的可能都不一样，这不代表我在说谎。`
}

function shouldFallbackToNarrative(text: string): boolean {
  const normalized = text.trim()
  if (!normalized) return true

  if (/<\/?BR(?:I(?:E(?:F)?)?)?>?/i.test(normalized)) {
    return true
  }

  return [
    '<BRIEF>',
    '<BRIE',
    '<BRI',
    '<BR',
    '## 结论',
    '## 关键点',
    '转化率 / 错误率 / 时延',
    '先做小闭环',
    '先上线最小版本',
  ].some((marker) => normalized.includes(marker))
}

function generateMockEnding(
  caseData: MultiLifeCase,
  rounds: MultiLifeRound[],
  m: MultiLifeSessionMeta,
): NonNullable<MultiLifeSessionMeta['ending']> {
  const challengeCount = rounds.filter((r) => r.playerChoice?.type === 'challenge').length
  const challengedIds = rounds
    .filter((r) => r.playerChoice?.type === 'challenge')
    .map((r) => r.playerChoice?.challengedRoleId)

  const trustLi = (m.trustMap['b'] ?? 0) > 0
    ? '你全程倾向于信任李四，这导致你的推理方向出现了明显偏差。'
    : '你对李四的证词持保留态度，这使你的推理相对更接近真相。'

  return {
    playerNarrative: `经过${rounds.length}轮调查、${challengeCount}次质疑，你最终形成了一个推理版本：${trustLi}你注意到张三的人影描述和王警官的物证分析有诸多吻合之处，但李四坚称自己不在场的说辞始终存在疑点。`,
    truthNarrative: caseData.truth,
    deviationAnalysis: `你的推理与真相之间的主要偏差在于：${trustLi}实际上李四就是凶手，他因为八十万的经济纠纷杀害了赵六。张三目击了李四离开仓库的身影，但因为距离和光线认成了"黑影"。王警官的物证分析基本正确。`,
    unexploredBranches: challengedIds.includes('b')
      ? ['如果你在第3轮就质疑了李四，可能会更早发现他说谎的破绽，从而更快锁定嫌疑人。']
      : ['如果你当时质疑了李四关于"案发时在家"的说法，配合物证可能会直接拆穿他的不在场证明。'],
  }
}
