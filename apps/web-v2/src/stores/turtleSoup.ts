import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAppStore, type ModelMeta } from './app'
import { useProviderStore } from './provider'
import { useToastStore } from './toast'
import { streamModelChat } from '@/services/runtime'
import { filterAutoPlayableModels } from '@/utils/modelSelection'
import { SEED_PUZZLES } from '@/features/turtle-soup/puzzles/seeds'
import {
  buildHostSystemPrompt,
  buildHostUserPrompt,
  buildVerifierSystemPrompt,
  buildVerifierUserPrompt,
  buildHintPrompt,
  buildRecapPrompt,
} from '@/features/turtle-soup/prompts'
import { leakGuardCheck } from '@/features/turtle-soup/leak-guard'
import {
  MAX_ROUNDS,
  MAX_HINTS,
  HOST_REVEALED_SUMMARY_LENGTH,
} from '@/features/turtle-soup/constants'
import type {
  TurtleSoupPhase,
  Puzzle,
  QuestionRecord,
  HostTag,
  HostOutput,
  VerifierOutput,
  TurtleSoupResult,
  TurtleSoupRecord,
  TurtleSoupMetadata,
  RecapOutput,
} from '@/features/turtle-soup/types'

// ─── IndexedDB helpers ─────────────────────────────────
const DB_NAME = 'mms-turtle-soup'
const DB_VERSION = 1
const STORE_NAME = 'sessions'
const COMPLETED_KEY = 'mms-turtle-soup-completed'

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' })
        store.createIndex('puzzleId', 'puzzleId', { unique: false })
        store.createIndex('phase', 'phase', { unique: false })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function cloneForIDB<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj))
}

async function saveSession(session: TurtleSoupRecord): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).put(cloneForIDB(session))
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

async function loadSession(sessionId: string): Promise<TurtleSoupRecord | null> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const req = tx.objectStore(STORE_NAME).get(sessionId)
    req.onsuccess = () => resolve(req.result || null)
    req.onerror = () => reject(req.error)
  })
}

function loadCompletedIds(): string[] {
  try {
    const raw = localStorage.getItem(COMPLETED_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return []
}

function saveCompletedIds(ids: string[]) {
  localStorage.setItem(COMPLETED_KEY, JSON.stringify(ids))
}

// ─── Utilities ──────────────────────────────────────────
function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

async function collectFullText(gen: AsyncGenerator<string>): Promise<string> {
  let text = ''
  for await (const chunk of gen) {
    text += chunk
  }
  return text
}

function parseJSON<T>(text: string): T | null {
  const clean = text.replace(/```json?\s*/g, '').replace(/```\s*$/g, '').trim()
  try {
    return JSON.parse(clean)
  } catch {
    const start = clean.indexOf('{')
    const end = clean.lastIndexOf('}')
    if (start >= 0 && end > start) {
      try { return JSON.parse(clean.slice(start, end + 1)) } catch { /* ignore */ }
    }
    return null
  }
}

function shouldRunVerifier(
  hostOutput: HostOutput | null,
  tag: HostTag,
  followUp: string,
): boolean {
  if (!hostOutput) return true
  if (tag === 'yes_and_no') return true
  if (followUp.length > 16) return true
  if (/[；：;]/.test(followUp)) return true
  if (/(真相|答案|因为|其实|也就是说|意味着|关键|就是)/.test(followUp)) return true
  return false
}

const VERIFIER_META_PATTERNS = [
  /改为/,
  /建议/,
  /更安全/,
  /直接否定/,
  /候选回答/,
  /玩家提问/,
  /只输出\s*json/i,
]

// ─── Model picking ─────────────────────────────────────
// Reuse app store's preferFree and tier logic instead of hardcoding provider assumption.
// Host: medium model (tier 0 or 1, free first if preferFree)

function listPlayableHostModels(
  appStore: ReturnType<typeof useAppStore>,
  providerStore: ReturnType<typeof useProviderStore>,
): ModelMeta[] {
  const playable = filterAutoPlayableModels(appStore.models).filter((model) => {
    if (model.id.startsWith('demo/')) return true
    return providerStore.getFallbackAccounts(model.provider).length > 0
  })

  const liveModels = playable.filter((model) => !model.id.startsWith('demo/'))
  const source = liveModels.length ? liveModels : playable
  return appStore.getLabAutoPool(source)
}

function pickHostModel(
  appStore: ReturnType<typeof useAppStore>,
): string | null {
  const providerStore = useProviderStore()
  const available = listPlayableHostModels(appStore, providerStore)
  if (!available.length) return null
  return appStore.pickLabModelId(available, 'turtle-soup:auto-host')
}

// ─── Store ──────────────────────────────────────────────
export const useTurtleSoupStore = defineStore('turtleSoup', () => {
  const phase = ref<TurtleSoupPhase>('loading')
  const puzzles = ref<Puzzle[]>([])
  const currentPuzzle = ref<Puzzle | null>(null)
  const round = ref(0)
  const totalQuestions = ref(0)
  const hintLevel = ref(0)
  const questions = ref<QuestionRecord[]>([])
  const processing = ref(false)
  const currentHint = ref<string | null>(null)
  const result = ref<TurtleSoupResult | null>(null)
  const recap = ref<RecapOutput | null>(null)
  const error = ref<string | null>(null)
  const sessionId = ref('')
  const abortController = ref<AbortController | null>(null)
  const completedPuzzleIds = ref<string[]>(loadCompletedIds())
  const startedAt = ref(0)
  const selectedHostModelId = ref<string | null>(null)
  const userPickedModel = ref(false)
  const callingPhase = ref<'idle' | 'ringing' | 'connected' | 'done'>('idle')
  const selectedHostModel = computed(() =>
    availableModels.value.find((model) => model.id === selectedHostModelId.value) ?? null,
  )
  const runtimeMode = computed<'live' | 'demo' | 'unavailable'>(() => {
    const selected = selectedHostModel.value
    if (selected) return selected.id.startsWith('demo/') ? 'demo' : 'live'
    if (!availableModels.value.length) return 'unavailable'
    return availableModels.value.some((model) => !model.id.startsWith('demo/')) ? 'live' : 'demo'
  })

  // Models that have at least one active account with API key (or demo)
  const availableModels = computed(() => {
    const appStore = useAppStore()
    const providerStore = useProviderStore()
    if (!appStore.initialized) return []
    return listPlayableHostModels(appStore, providerStore)
  })

  const remainingRounds = computed(() => MAX_ROUNDS - round.value)
  const canAskHint = computed(() => hintLevel.value < MAX_HINTS && phase.value === 'playing')
  const isGameOver = computed(() => phase.value === 'completed' || phase.value === 'abandoned')

  // Build revealed summary for host prompt (last N rounds)
  function buildRevealedSummary(): string {
    const recent = questions.value.slice(-HOST_REVEALED_SUMMARY_LENGTH)
    if (!recent.length) return ''
    return recent
      .map(q => `[第 ${q.round} 轮] 问：${q.question} → 答：${q.answer}`)
      .join('\n')
  }

  // Get IDs of clues that have been "touched" by player questions getting close
  function getTouchedClueIds(): string[] {
    return currentPuzzle.value
      ?.clues.filter(c => c.isPublic).map(c => c.id) ?? []
  }

  // ─── Init ──────────────────────────────────────────
  async function init() {
    phase.value = 'loading'
    error.value = null

    const appStore = useAppStore()
    const providerStore = useProviderStore()
    await appStore.initialize()

    // Use seed puzzles
    const easyPuzzles = SEED_PUZZLES.filter(p => p.difficulty === 'easy')
    puzzles.value = easyPuzzles.length >= 10 ? easyPuzzles : SEED_PUZZLES

    // Check for in-progress session
    try {
      const recentSession = await findRecentSession()
      if (recentSession && recentSession.phase === 'playing') {
        const puzzle = SEED_PUZZLES.find(p => p.id === recentSession.metadata.puzzleId)
        if (puzzle) {
          sessionId.value = recentSession.id
          currentPuzzle.value = puzzle
          round.value = recentSession.metadata.currentRound
          totalQuestions.value = recentSession.metadata.totalQuestions
          hintLevel.value = recentSession.metadata.hintLevel
          questions.value = recentSession.metadata.questions
          startedAt.value = recentSession.startedAt
          selectedHostModelId.value = pickHostModel(appStore) ?? selectedHostModelId.value
          phase.value = 'playing'
          return
        }
      }
    } catch { /* ignore */ }

    phase.value = 'pick_puzzle'
  }

  async function findRecentSession(): Promise<TurtleSoupRecord | null> {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly')
      const store = tx.objectStore(STORE_NAME)
      const req = store.getAll()
      req.onsuccess = () => {
        const sessions: TurtleSoupRecord[] = req.result
        const playing = sessions.filter(s => s.phase === 'playing')
        if (playing.length > 0) {
          // Return the most recent playing session
          const sorted = playing.sort((a, b) => b.updatedAt - a.updatedAt)
          resolve(sorted[0])
        } else {
          resolve(null)
        }
      }
      req.onerror = () => reject(req.error)
    })
  }

  // ─── Select puzzle ─────────────────────────────────
  async function selectPuzzle(puzzle: Puzzle) {
    currentPuzzle.value = puzzle
    round.value = 0
    totalQuestions.value = 0
    hintLevel.value = 0
    questions.value = []
    result.value = null
    recap.value = null
    currentHint.value = null
    error.value = null
    sessionId.value = uid()
    startedAt.value = Date.now()

    // Auto-pick default, user can override
    const appStore = useAppStore()
    selectedHostModelId.value = pickHostModel(appStore)
    userPickedModel.value = false

    phase.value = 'pick_puzzle' // stay on pick to show model selection UI
  }

  function setModel(modelId: string) {
    selectedHostModelId.value = modelId
    userPickedModel.value = true
  }

  async function startGame() {
    const appStore = useAppStore()
    if (!selectedHostModelId.value) {
      selectedHostModelId.value = pickHostModel(appStore)
    }

    if (!selectedHostModelId.value) {
      const toast = useToastStore()
      toast.error('没有可用模型，请先配置 Provider，或保留 Demo 模式')
      return
    }

    phase.value = 'playing'
    const session = buildSession('playing')
    await saveSession(session)
  }

  // ─── Ask question (core game loop) ─────────────────
  async function askQuestion(playerQuestion: string) {
    if (!currentPuzzle.value || processing.value || isGameOver.value) return

    const puzzle = currentPuzzle.value
    const toast = useToastStore()
    const appStore = useAppStore()
    const hostModelId = selectedHostModelId.value ?? pickHostModel(appStore)
    if (!hostModelId) {
      toast.error('当前没有可用主持模型，请先配置 Provider 或切回 Demo')
      return
    }

    selectedHostModelId.value = hostModelId
    processing.value = true
    error.value = null
    round.value++
    totalQuestions.value++

    const ac = new AbortController()
    abortController.value = ac

    const startTime = Date.now()
    const record: QuestionRecord = {
      round: round.value,
      question: playerQuestion,
      answer: '',
      tags: [],
      verifierResult: 'approved',
      status: 'pending',
    }
    questions.value.push(record)

    try {
      // Step 1: Host generates answer
      const revealedSummary = buildRevealedSummary()
      const hostSystem = buildHostSystemPrompt(puzzle, revealedSummary)
      const hostUser = buildHostUserPrompt(playerQuestion, round.value)

      const hostText = await collectFullText(streamModelChat({
        modelId: hostModelId,
        traceLabel: 'turtle-soup:host',
        traceMeta: {
          puzzleId: puzzle.id,
          round: round.value,
        },
        messages: [
          { role: 'system', content: hostSystem },
          { role: 'user', content: hostUser },
        ],
        signal: ac.signal,
      }))

      const hostOutput = parseJSON<HostOutput>(hostText)
      let finalTag: HostTag = hostOutput?.tag || 'irrelevant'
      let finalFollowUp = sanitizeFollowUp(hostOutput?.followUp || '')

      // Step 2: Verifier 审核（置信度联动）
      let verifierGuidance = ''
      let vOutput: VerifierOutput | null = null

      if (shouldRunVerifier(hostOutput, finalTag, finalFollowUp)) {
        const verifierSystem = buildVerifierSystemPrompt(puzzle, round.value)
        const verifierUser = buildVerifierUserPrompt(buildFinalAnswer(finalTag, finalFollowUp), playerQuestion)

        const verifierText = await collectFullText(streamModelChat({
          modelId: hostModelId,
          traceLabel: 'turtle-soup:verifier',
          traceMeta: {
            puzzleId: puzzle.id,
            round: round.value,
          },
          messages: [
            { role: 'system', content: verifierSystem },
            { role: 'user', content: verifierUser },
          ],
          signal: ac.signal,
        }))

        vOutput = parseJSON<VerifierOutput>(verifierText)
      }

      const needsRefinement = Boolean(
        vOutput && (!vOutput.approved || vOutput.confidence < 0.8 || (vOutput.leakRisk && vOutput.leakRisk !== 'low')),
      )
      const verifierSuggestion = normalizeVerifierSuggestion(vOutput, finalTag)

      if (vOutput?.approved === false && verifierSuggestion) {
        finalTag = verifierSuggestion.tag
        finalFollowUp = verifierSuggestion.followUp
      } else if (
        needsRefinement &&
        verifierSuggestion &&
        verifierSuggestion.tag === finalTag &&
        verifierSuggestion.followUp &&
        !finalFollowUp
      ) {
        verifierGuidance = verifierSuggestion.followUp
      }

      const finalAnswer = buildFinalAnswer(finalTag, finalFollowUp)

      // 检查通关判定
      if (vOutput?.guessedCorrectly && (vOutput.solveConfidence ?? 0) >= 0.8) {
        // 玩家猜中真相，触发通关
        const solveQuality = hintLevel.value === 0
          ? (round.value <= 15 ? 'perfect' : 'good')
          : (hintLevel.value <= 2 ? 'hinted' : 'assisted')

        result.value = {
          outcome: 'solved',
          totalRounds: round.value,
          totalQuestions: totalQuestions.value,
          hintsUsed: hintLevel.value,
          durationMs: startedAt.value ? Date.now() - startedAt.value : 0,
          solveQuality,
        }

        phase.value = 'completed'
        completedPuzzleIds.value = [...completedPuzzleIds.value, puzzle.id]
        saveCompletedIds(completedPuzzleIds.value)
        await saveSession(buildSession('completed'))
        processing.value = false
        abortController.value = null
        await generateRecap()
        return
      }

      // Step 3: Leak-Guard (local keyword check, zero API calls)
      const guardResult = leakGuardCheck(finalAnswer, puzzle)
      const displayAnswer = guardResult.safe ? finalAnswer : guardResult.replacement!
      const answerBody = extractAnswerBody(displayAnswer)
      const displayGuidance = !answerBody && verifierGuidance ? verifierGuidance : undefined

      // Step 3: Local solve detection (check solveKeywords against player question)
      const solvedLocally = checkLocalSolve(playerQuestion, puzzle)

      record.answer = displayAnswer
      record.guidance = displayGuidance
      record.tags = [finalTag]
      record.verifierResult = guardResult.safe ? (vOutput?.approved === false ? 'rejected' : 'approved') : 'fallback'
      record.latencyMs = Date.now() - startTime
      record.status = 'done'

      if (solvedLocally) {
        const solveQuality = hintLevel.value === 0
          ? (round.value <= 15 ? 'perfect' : 'good')
          : (hintLevel.value <= 2 ? 'hinted' : 'assisted')

        result.value = {
          outcome: 'solved',
          totalRounds: round.value,
          totalQuestions: totalQuestions.value,
          hintsUsed: hintLevel.value,
          durationMs: startedAt.value ? Date.now() - startedAt.value : 0,
          solveQuality,
        }

        phase.value = 'completed'
        completedPuzzleIds.value = [...completedPuzzleIds.value, puzzle.id]
        saveCompletedIds(completedPuzzleIds.value)
        await saveSession(buildSession('completed'))
        processing.value = false
        abortController.value = null
        await generateRecap()
        return
      }

      await saveSession(buildSession('playing'))

      // Check round limit
      if (round.value >= MAX_ROUNDS) {
        result.value = {
          outcome: 'abandoned',
          totalRounds: round.value,
          totalQuestions: totalQuestions.value,
          hintsUsed: hintLevel.value,
          durationMs: startedAt.value ? Date.now() - startedAt.value : 0,
        }
        phase.value = 'abandoned'
        await saveSession(buildSession('abandoned'))
        await generateRecap()
      }
    } catch (e: any) {
      const pendingIndex = questions.value.indexOf(record)
      if (pendingIndex >= 0 && record.status === 'pending') {
        questions.value.splice(pendingIndex, 1)
      }
      if (e?.name === 'AbortError') return
      error.value = e?.message || '处理提问时出错'
      toast.error(error.value!)
    } finally {
      processing.value = false
      abortController.value = null
    }
  }

  /** Local solve detection: check if player question contains enough solve keywords */
  function checkLocalSolve(question: string, puzzle: Puzzle): boolean {
    const q = question.toLowerCase()
    const matched = puzzle.solveKeywords.filter(kw => q.includes(kw.toLowerCase()))
    return matched.length >= puzzle.solveThreshold
  }

  function parseTagFromText(text: string, fallback: HostTag): HostTag {
    if (text.startsWith('是也不是')) return 'yes_and_no'
    if (text.startsWith('接近了')) return 'close'
    if (text.startsWith('是')) return 'yes'
    if (text.startsWith('无关')) return 'irrelevant'
    if (text.startsWith('不是')) return 'no'
    return fallback
  }

  function extractAnswerBody(text: string): string {
    const cut = text.indexOf('。')
    return cut >= 0 ? text.slice(cut + 1).trim() : ''
  }

  function sanitizeFollowUp(text: string): string {
    const trimmed = text
      .replace(/^[。！!？?、，,\s"'“”‘’]+/, '')
      .replace(/\s+/g, ' ')
      .trim()

    if (!trimmed) return ''
    if (VERIFIER_META_PATTERNS.some((pattern) => pattern.test(trimmed))) return ''
    return trimmed.slice(0, 30)
  }

  function stripTagPrefix(text: string): string {
    return text.replace(/^(是也不是|接近了|无关|不是|是)[。！!？?、，,\s]*/, '').trim()
  }

  function normalizeVerifierSuggestion(
    output: VerifierOutput | null,
    fallbackTag: HostTag,
  ): { tag: HostTag; followUp: string } | null {
    if (!output) return null

    if (output.suggestedTag) {
      return {
        tag: output.suggestedTag,
        followUp: sanitizeFollowUp(output.suggestedFollowUp || ''),
      }
    }

    if (!output.suggestedFix) return null

    const raw = output.suggestedFix.trim()
    if (!raw) return null
    if (VERIFIER_META_PATTERNS.some((pattern) => pattern.test(raw))) return null

    return {
      tag: parseTagFromText(raw, fallbackTag),
      followUp: sanitizeFollowUp(stripTagPrefix(raw)),
    }
  }

  function buildFinalAnswer(tag: HostTag, followUp: string): string {
    const tagLabel = { yes: '是', no: '不是', yes_and_no: '是也不是', irrelevant: '无关', close: '接近了' }[tag]
    return followUp ? `${tagLabel}。${followUp}` : tagLabel
  }

  // ─── Hint (场外求助 with phone call animation) ─────
  async function requestHint() {
    if (!currentPuzzle.value || !canAskHint.value || processing.value) return

    const puzzle = currentPuzzle.value
    const nextLevel = (hintLevel.value + 1) as 1 | 2 | 3
    processing.value = true
    callingPhase.value = 'ringing'

    // Ringing phase: keep a short transition, but avoid blocking too long
    await new Promise(resolve => setTimeout(resolve, 650))
    callingPhase.value = 'connected'

    try {
      const prompt = buildHintPrompt(puzzle, nextLevel, getTouchedClueIds())
      const appStore = useAppStore()
      const providerStore = useProviderStore()
      const hintModel = selectedHostModelId.value ?? pickHostModel(appStore)

      let hint = ''
      if (hintModel) {
        const text = await collectFullText(streamModelChat({
          modelId: hintModel,
          traceLabel: 'turtle-soup:hint',
          traceMeta: {
            puzzleId: puzzle.id,
            hintLevel: nextLevel,
          },
          messages: [{ role: 'user', content: prompt }],
        }))

        const parsed = parseJSON<{ hint: string }>(text)
        if (parsed?.hint) {
          const guardResult = leakGuardCheck(parsed.hint, puzzle)
          hint = guardResult.safe ? parsed.hint : '换个方向想想，注意那些你还没问过的细节。'
        }
      }

      if (!hint) {
        const preHint = puzzle.hints.find(h => h.level === nextLevel)
        hint = preHint?.text || '换个方向想想。'
      }

      currentHint.value = hint
      hintLevel.value = nextLevel
      callingPhase.value = 'done'
      await saveSession(buildSession('playing'))

      // Reset calling UI after showing hint
      setTimeout(() => { callingPhase.value = 'idle' }, 1200)
    } catch {
      const preHint = puzzle.hints.find(h => h.level === nextLevel)
      currentHint.value = preHint?.text || '换个方向想想。'
      hintLevel.value = nextLevel
      callingPhase.value = 'done'
      setTimeout(() => { callingPhase.value = 'idle' }, 1200)
    } finally {
      processing.value = false
    }
  }

  // ─── Abandon ───────────────────────────────────────
  async function abandon() {
    if (!currentPuzzle.value || isGameOver.value) return

    result.value = {
      outcome: 'abandoned',
      totalRounds: round.value,
      totalQuestions: totalQuestions.value,
      hintsUsed: hintLevel.value,
      durationMs: startedAt.value ? Date.now() - startedAt.value : 0,
    }

    phase.value = 'abandoned'
    await saveSession(buildSession('abandoned'))
    await generateRecap()
  }

  // ─── Recap generation ──────────────────────────────
  async function generateRecap() {
    if (!currentPuzzle.value) return

    const puzzle = currentPuzzle.value
    const appStore = useAppStore()
    const providerStore = useProviderStore()
    const recapModel = selectedHostModelId.value ?? pickHostModel(appStore)

    if (recapModel) {
      try {
        const questionHistory = questions.value
          .map(q => `[第${q.round}轮] 问：${q.question} 答：${q.answer}`)
          .join('\n')

        const prompt = buildRecapPrompt(
          puzzle,
          questionHistory,
          result.value?.outcome || 'abandoned',
          round.value,
          hintLevel.value,
          Math.round((startedAt.value ? Date.now() - startedAt.value : 60000) / 60000) || 1,
        )

        const text = await collectFullText(streamModelChat({
          modelId: recapModel,
          traceLabel: 'turtle-soup:recap',
          traceMeta: {
            puzzleId: puzzle.id,
            round: round.value,
            hintLevel: hintLevel.value,
          },
          messages: [{ role: 'user', content: prompt }],
        }))

        const parsed = parseJSON<RecapOutput>(text)
        if (parsed) {
          recap.value = parsed
        }
      } catch { /* ignore — recap is optional */ }
    }
  }

  // ─── Build session for persistence ─────────────────
  function buildSession(sessionPhase: TurtleSoupRecord['phase']): TurtleSoupRecord {
    const metadata: TurtleSoupMetadata = {
      puzzleId: currentPuzzle.value?.id || '',
      puzzleTitle: currentPuzzle.value?.title || '',
      difficulty: currentPuzzle.value?.difficulty || 'easy',
      currentRound: round.value,
      totalQuestions: totalQuestions.value,
      hintLevel: hintLevel.value,
      questions: questions.value,
      result: result.value || undefined,
    }
    return {
      id: sessionId.value,
      phase: sessionPhase,
      round: round.value,
      metadata,
      startedAt: startedAt.value || Date.now(),
      updatedAt: Date.now(),
      completedPuzzleIds: completedPuzzleIds.value,
    }
  }

  // ─── Reset ─────────────────────────────────────────
  async function reset() {
    abortController.value?.abort()
    abortController.value = null

    currentPuzzle.value = null
    round.value = 0
    totalQuestions.value = 0
    hintLevel.value = 0
    questions.value = []
    result.value = null
    recap.value = null
    currentHint.value = null
    error.value = null
    processing.value = false
    sessionId.value = ''
    startedAt.value = 0
    selectedHostModelId.value = null
    userPickedModel.value = false
    callingPhase.value = 'idle'

    phase.value = 'pick_puzzle'
  }

  return {
    // State
    phase,
    puzzles,
    currentPuzzle,
    round,
    totalQuestions,
    hintLevel,
    questions,
    processing,
    currentHint,
    result,
    recap,
    error,
    completedPuzzleIds,
    selectedHostModelId,
    userPickedModel,
    callingPhase,
    selectedHostModel,
    runtimeMode,
    // Computed
    availableModels,
    remainingRounds,
    canAskHint,
    isGameOver,
    // Actions
    init,
    selectPuzzle,
    setModel,
    startGame,
    askQuestion,
    requestHint,
    abandon,
    reset,
  }
})
