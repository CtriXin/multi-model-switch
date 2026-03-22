import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAppStore, type ModelMeta } from './app'
import { useToastStore } from './toast'
import { streamModelChat } from '@/services/runtime'
import { preferLiveAutoModels } from '@/utils/modelSelection'
import { createTimingSpan } from '@/utils/timingLogger'
import { TOPIC_SEEDS } from '@/features/challenge/topicSeeds'
import { buildTopicGeneratorPrompt, buildRoundDebaterPrompt, buildModeratorTaggerPrompt } from '@/features/challenge/prompts'
import type {
  OpinionCard, TopicCandidate, DailyCategory, DebateStance,
  ChallengePhase, ThinkingPatternSnapshot, DebateTakeaway, AxisId,
  UserProfile, UserDebateRole, DebateMessage, TurnSpec,
  DebateModelMode, DebateStartPayload,
} from '@/features/challenge/types'
import {
  buildDebatePlan,
  buildInitialDebatePlan,
  buildJudgeTurn,
  buildRoundPair,
} from '@/features/challenge/types'

const DB_NAME = 'mms-daily-challenge'
const DB_VERSION = 1
const STORE_NAME = 'opinion-cards'
const PREFS_KEY = 'mms-challenge-prefs'
const PROFILE_KEY = 'mms-challenge-profile'
const BATCH_CACHE_KEY = 'mms-challenge-batch'

// ─── IndexedDB helpers ────────────────────────────────────
function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' })
        store.createIndex('challengeDate', 'challengeDate', { unique: false })
        store.createIndex('category', 'category', { unique: false })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function getAllCards(): Promise<OpinionCard[]> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const store = tx.objectStore(STORE_NAME)
    const req = store.getAll()
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function saveCard(card: OpinionCard): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    store.put(card)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

// ─── Utilities ────────────────────────────────────────────
function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// ─── User profile persistence ─────────────────────────────
function loadProfile(): UserProfile {
  try {
    const raw = localStorage.getItem(PROFILE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return {
    categoryHits: {},
    categoryDismisses: {},
    topKeywords: [],
    stanceDistribution: { support: 0, oppose: 0, mixed: 0 },
    avgAxes: {},
    updatedAt: 0,
  }
}

function saveProfile(profile: UserProfile) {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile))
}

// ─── Batch cache persistence ──────────────────────────────
interface BatchCache {
  date: string
  categoriesKey: string
  topics: TopicCandidate[]
}

interface OpeningPreview {
  topicId: string
  userRole: 'con' | 'judge'
  modelId: string
  modelName: string
  text: string
  status: 'loading' | 'done' | 'error'
}

function loadBatchCache(): BatchCache | null {
  try {
    const raw = localStorage.getItem(BATCH_CACHE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return null
}

function saveBatchCache(cache: BatchCache) {
  localStorage.setItem(BATCH_CACHE_KEY, JSON.stringify(cache))
}

function batchCategoriesKey(cats: DailyCategory[]): string {
  return [...cats].sort().join(',')
}

// ─── Prefs ────────────────────────────────────────────────
function loadPrefs(): { categories: DailyCategory[]; modelMode: DebateModelMode } {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return { categories: ['tech', 'life', 'career'], modelMode: 'auto' }
}

function savePrefs(prefs: { categories: DailyCategory[]; modelMode: DebateModelMode }) {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
}

// ─── Model picking ────────────────────────────────────────
function pickCheapModel(appStore: ReturnType<typeof useAppStore>): string | null {
  const pool = getAvailableModels(appStore)
  if (!pool.length) return null

  const ranked = [...pool].sort((left, right) => {
    if (left.tier !== right.tier) return left.tier - right.tier
    if (left.free !== right.free) return left.free ? -1 : 1

    const costDelta = modelCost(left) - modelCost(right)
    if (costDelta !== 0) return costDelta

    return left.name.localeCompare(right.name)
  })

  return ranked[0]?.id || null
}

function getAvailableModels(appStore: ReturnType<typeof useAppStore>): ModelMeta[] {
  const liveModels = preferLiveAutoModels(appStore.models)
  return liveModels.length ? liveModels : appStore.models
}

function modelCost(model: ModelMeta): number {
  return model.priceInput + model.priceOutput
}

function buildRolePriority(mode: DebateModelMode, role: 'pro' | 'con' | 'moderator') {
  const fallbackMidTier = role === 'moderator'
    ? [1, 0, 2]
    : [1, 0, 2]

  if (mode === 'cheap') {
    return {
      preferFree: true,
      tierOrder: [0, 1, 2],
      costWeight: role === 'moderator' ? 2 : 3,
    }
  }

  if (mode === 'quality') {
    return {
      preferFree: false,
      tierOrder: role === 'moderator' ? [1, 2, 0] : [2, 1, 0],
      costWeight: 1,
    }
  }

  if (mode === 'balanced') {
    return {
      preferFree: false,
      tierOrder: fallbackMidTier,
      costWeight: 2,
    }
  }

  return {
    preferFree: true,
    tierOrder: fallbackMidTier,
    costWeight: 2,
  }
}

function rankModels(
  source: ModelMeta[],
  mode: DebateModelMode,
  role: 'pro' | 'con' | 'moderator',
): ModelMeta[] {
  if (source.every((model) => model.id.startsWith('demo/'))) {
    return [...source]
  }

  const priority = buildRolePriority(mode, role)
  const tierIndex = new Map(priority.tierOrder.map((tier, index) => [tier, index]))

  return [...source].sort((left, right) => {
    if (priority.preferFree && left.free !== right.free) {
      return left.free ? -1 : 1
    }

    const leftTier = tierIndex.get(left.tier) ?? priority.tierOrder.length
    const rightTier = tierIndex.get(right.tier) ?? priority.tierOrder.length
    if (leftTier !== rightTier) return leftTier - rightTier

    const costDelta = modelCost(left) - modelCost(right)
    if (costDelta !== 0) return costDelta * priority.costWeight

    return left.name.localeCompare(right.name)
  })
}

function pickRoleModel(
  ranked: ModelMeta[],
  takenIds: Set<string>,
  takenProviders: Set<string>,
  requireDifferentProvider = true,
): ModelMeta | null {
  if (!ranked.length) return null

  const candidate = ranked.find((model) => !takenIds.has(model.id) && (!requireDifferentProvider || !takenProviders.has(model.provider)))
  if (candidate) return candidate

  const sameProviderFallback = ranked.find((model) => !takenIds.has(model.id))
  if (sameProviderFallback) return sameProviderFallback

  return ranked[0] || null
}

function pickDebateModels(
  appStore: ReturnType<typeof useAppStore>,
  mode: DebateModelMode,
): { pro: string; con: string; moderator: string } | null {
  const pool = getAvailableModels(appStore)
  if (!pool.length) return null

  if (appStore.shouldUseSparkringSpeed() && pool.some((model) => model.provider === 'sparkring')) {
    const picked = appStore.pickLabModelIds(3, pool, `daily-challenge:${mode}`)
    const [pro, con, moderator] = picked
    if (!pro) return null
    return {
      pro,
      con: con ?? pro,
      moderator: moderator ?? con ?? pro,
    }
  }

  const takenIds = new Set<string>()
  const takenProviders = new Set<string>()

  const proModel = pickRoleModel(rankModels(pool, mode, 'pro'), takenIds, takenProviders)
  if (!proModel) return null
  takenIds.add(proModel.id)
  takenProviders.add(proModel.provider)

  const conModel = pickRoleModel(rankModels(pool, mode, 'con'), takenIds, takenProviders)
  const finalCon = conModel || proModel
  takenIds.add(finalCon.id)
  takenProviders.add(finalCon.provider)

  const moderatorModel = pickRoleModel(rankModels(pool, mode, 'moderator'), takenIds, takenProviders)
  const finalModerator = moderatorModel || finalCon || proModel

  appStore.debugLabSelection(`daily-challenge:${mode}`, [
    proModel.id,
    finalCon.id,
    finalModerator.id,
  ], {
    poolSize: pool.length,
    strategy: 'ranked',
  })

  return {
    pro: proModel.id,
    con: finalCon.id,
    moderator: finalModerator.id,
  }
}

// ─── Stream / JSON helpers ────────────────────────────────
async function collectFullText(gen: AsyncGenerator<string>): Promise<string> {
  let text = ''
  for await (const chunk of gen) {
    text += chunk
  }
  return text
}

async function streamText(
  gen: AsyncGenerator<string>,
  onText: (text: string) => void,
): Promise<string> {
  let text = ''
  for await (const chunk of gen) {
    text += chunk
    onText(text)
  }
  return text
}

function wait(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function streamLocalText(text: string, onText: (text: string) => void) {
  const step = Math.max(8, Math.ceil(text.length / 14))
  for (let index = 0; index < text.length; index += step) {
    onText(text.slice(0, index + step))
    if (index + step < text.length) {
      await wait(18)
    }
  }
}

function clipText(text: string, max = 22) {
  return text.length > max ? `${text.slice(0, max)}…` : text
}

function buildFallbackDebaterText(opts: {
  topic: TopicCandidate
  stance: 'pro' | 'con'
  round: number
  history: DebateMessage[]
}) {
  const own = opts.stance === 'pro' ? opts.topic.sideA : opts.topic.sideB
  const other = opts.stance === 'pro' ? opts.topic.sideB : opts.topic.sideA
  const opponentSide = opts.stance === 'pro' ? 'con' : 'pro'
  const opponentLast = [...opts.history]
    .reverse()
    .find((message) => message.side === opponentSide && message.status === 'done')
    ?.text
    ?.replace(/\s+/g, ' ')
    .trim()

  if (opts.round === 1) {
    return [
      `${own}。`,
      '',
      `第一，这道题真正要比较的是“先保住什么，代价才最可控”。`,
      `第二，${own}并不是否定${other}，而是承认顺序一旦错了，后续补救会更贵。`,
      `第三，面对冲突场景，优先级本身就是判断力，不能只看眼前情绪。`,
    ].join('\n')
  }

  return [
    opponentLast
      ? `你刚才强调“${clipText(opponentLast)}”，但这并没有推翻 ${own} 应该先被守住。`
      : `对方的发言看似完整，但仍然没有推翻 ${own} 应该先被守住。`,
    '',
    `第一，你把局部感受放大成了整体优先级，却没有回答延误之后谁来承担连锁代价。`,
    `第二，即使承认 ${other} 有价值，也不代表它该排在 ${own} 前面。`,
    `第三，真正稳的选择不是谁都顾，而是先守住最难回补的那一端。`,
  ].join('\n')
}

function buildFallbackModeratorResult(opts: {
  topic: TopicCandidate
  userRole: UserDebateRole
}) {
  return {
    takeaway: {
      strongestPointFor: `正方最强的一点是把重点放在“${opts.topic.sideA}”的长期连锁代价上。`,
      strongestPointAgainst: `反方最强的一点是提醒“${opts.topic.sideB}”背后的具体人和即时损失不能被抽象吞掉。`,
      decisiveQuestion: '这道题真正的分水岭，是你更在意不可逆后果，还是眼前责任。',
      oneLineVerdict: '两边都不是错，关键在于你认定哪一种代价更不能回补。',
    },
    thinkingSnapshot: {
      axes: {
        evidence_intuition: { score: opts.userRole === 'judge' ? 50 : 58, confidence: 0.45, note: '当前演示模式使用本地总结，不代表真实测评。' },
        decisive_exploratory: { score: 52, confidence: 0.4, note: '你会先形成立场，再继续追问。' },
        risk_seeking_risk_aware: { score: 57, confidence: 0.4, note: '你的表达更关注代价控制。' },
        self_systems: { score: 55, confidence: 0.4, note: '你会同时看个人责任与系统后果。' },
      },
      dominantAxes: ['evidence_intuition'],
      summary: '演示模式下给出的是保守快照，真实模型时会根据完整辩论重新判断。',
    },
  }
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

function buildHistoryDigest(cards: OpinionCard[]): string {
  if (!cards.length) return ''
  return cards
    .slice(-8)
    .map(c => `[${c.category}] ${c.topic.title} — 立场:${c.stance.final} 关键词:${c.personalizationSignals.extractedKeywords.join(',')}`)
    .join('\n')
}

// ─── Shuffled fallback (seeded by date + call counter) ────
let fallbackCallCount = 0

function seededShuffle<T>(arr: T[], seed: number): T[] {
  const out = [...arr]
  let s = seed
  for (let i = out.length - 1; i > 0; i--) {
    s = (s * 1103515245 + 12345) & 0x7fffffff
    const j = s % (i + 1)
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

function fallbackTopics(categories: DailyCategory[], exclusions: string[]): TopicCandidate[] {
  const day = new Date().getDate()
  const seed = day * 1000 + (++fallbackCallCount)
  const available = TOPIC_SEEDS.filter(s =>
    categories.includes(s.category) && !exclusions.includes(s.id)
  )
  const pool = available.length >= 6 ? available : TOPIC_SEEDS
  const shuffled = seededShuffle(pool, seed)
  return shuffled.slice(0, 6).map((s, i) => ({
    id: `fallback-${s.id}-${fallbackCallCount}`,
    title: `${s.tensionA} vs ${s.tensionB}`,
    prompt: `在当下环境中，${s.tensionA}和${s.tensionB}哪个更值得追求？`,
    sideA: `${s.tensionA}更重要`,
    sideB: `${s.tensionB}更重要`,
    category: s.category,
    difficulty: i < 3 ? 'casual' as const : 'deep' as const,
    controversy: 3,
  }))
}

// ─── Store ────────────────────────────────────────────────
export const useDailyChallengeStore = defineStore('dailyChallenge', () => {
  const prefs = loadPrefs()
  const phase = ref<ChallengePhase>('loading')
  const candidates = ref<TopicCandidate[]>([])
  const selectedTopic = ref<TopicCandidate | null>(null)
  const userStance = ref<DebateStance>('support')
  const userRole = ref<UserDebateRole>('pro')
  const userArgument = ref('')
  const userReason = ref('')
  const messages = ref<DebateMessage[]>([])
  const debatePlan = ref<TurnSpec[]>([])
  const turnIndex = ref(0)
  const currentRound = ref(0)
  const awaitingUserInput = ref(false)
  const awaitingDecision = ref(false)
  const proText = ref('')
  const conText = ref('')
  const debating = ref(false)
  const loading = ref(false)
  const takeaway = ref<DebateTakeaway | null>(null)
  const snapshot = ref<ThinkingPatternSnapshot | null>(null)
  const currentCard = ref<OpinionCard | null>(null)
  const cards = ref<OpinionCard[]>([])
  const categories = ref<DailyCategory[]>(prefs.categories)
  const modelMode = ref<DebateModelMode>(prefs.modelMode || 'auto')
  const abortController = ref<AbortController | null>(null)
  const error = ref<string | null>(null)
  const debateModels = ref<{ generator: string; pro: string; con: string; moderator: string } | null>(null)
  const profile = ref<UserProfile>(loadProfile())
  const openingPreview = ref<OpeningPreview | null>(null)
  const openingPreviewNonce = ref(0)
  let openingPreviewTask: Promise<void> | null = null

  const todayCard = computed(() =>
    cards.value.find(c => c.challengeDate === todayStr())
  )

  const recentCards = computed(() =>
    [...cards.value].sort((a, b) => b.createdAt - a.createdAt).slice(0, 30)
  )

  const streak = computed(() => {
    let count = 0
    const sorted = [...cards.value].sort((a, b) => b.createdAt - a.createdAt)
    const today = new Date()
    for (let i = 0; i < 30; i++) {
      const d = new Date(today)
      d.setDate(d.getDate() - i)
      const dateStr = d.toISOString().slice(0, 10)
      if (sorted.some(c => c.challengeDate === dateStr)) count++
      else break
    }
    return count
  })

  // ─── Init ─────────────────────────────────────────────
  async function init() {
    try {
      cards.value = await getAllCards()
      rebuildProfile()
    } catch { /* ignore */ }

    if (todayCard.value) {
      currentCard.value = todayCard.value
      phase.value = 'result'
    } else {
      phase.value = 'pick_topic'
      await generateTopics()
    }
  }

  function updateCategories(cats: DailyCategory[]) {
    categories.value = cats.length ? cats : ['tech', 'life', 'career']
    savePrefs({ categories: categories.value, modelMode: modelMode.value })
  }

  function updateModelMode(next: DebateModelMode) {
    modelMode.value = next
    savePrefs({ categories: categories.value, modelMode: modelMode.value })
  }

  // ─── Topic generation (6 topics, with batch cache) ────
  async function generateTopics(options: { forceFresh?: boolean } = {}) {
    const { forceFresh = false } = options
    error.value = null

    const recentTopicTitles = cards.value
      .filter(c => {
        const d = new Date(c.challengeDate)
        const now = new Date()
        return (now.getTime() - d.getTime()) < 7 * 86400000
      })
      .map(c => c.topic.title)

    const fallbackBatch = fallbackTopics(categories.value, recentTopicTitles)

    if (!candidates.value.length || forceFresh) {
      candidates.value = fallbackBatch
      debateModels.value = {
        generator: 'curated-seeds',
        pro: '',
        con: '',
        moderator: '',
      }
    }

    loading.value = true

    // Check batch cache (same day + same categories → reuse)
    const cached = loadBatchCache()
    const catKey = batchCategoriesKey(categories.value)
    if (!forceFresh && cached && cached.date === todayStr() && cached.categoriesKey === catKey && cached.topics.length > 0) {
      candidates.value = cached.topics
      loading.value = false
      return
    }

    const appStore = useAppStore()
    const genModel = pickCheapModel(appStore)

    // Try AI generation
    if (genModel) {
      try {
        const prompt = buildTopicGeneratorPrompt({
          dateSeed: todayStr(),
          categories: categories.value,
          historyDigest: buildHistoryDigest(cards.value),
          exclusions: recentTopicTitles,
          profile: profile.value,
        })

        const text = await collectFullText(
          streamModelChat({
            modelId: genModel,
            traceLabel: 'daily-challenge:topic-generator',
            traceMeta: {
              categories: categories.value.join(','),
            },
            messages: [{ role: 'user', content: prompt }],
          })
        )

        const parsed = parseJSON<{ candidates: TopicCandidate[] }>(text)
        if (parsed?.candidates?.length) {
          const topics = parsed.candidates.map((c, i) => ({
            ...c,
            id: c.id || `ai-${i}`,
          }))
          candidates.value = topics
          saveBatchCache({ date: todayStr(), categoriesKey: catKey, topics })
          debateModels.value = {
            generator: genModel,
            pro: '', con: '', moderator: '',
          }
          loading.value = false
          return
        }
      } catch (e) {
        console.warn('AI topic generation failed, using fallback:', e)
      }
    }

    // Keep a non-empty board even when generation fails or is still warming up.
    candidates.value = fallbackBatch
    debateModels.value = {
      generator: 'curated-seeds',
      pro: '', con: '', moderator: '',
    }
    loading.value = false
  }

  // ─── Refresh: clear cache + regenerate ────────────────
  async function refreshTopics() {
    localStorage.removeItem(BATCH_CACHE_KEY)
    await generateTopics({ forceFresh: true })
  }

  // ─── Dismiss: "不感兴趣" ──────────────────────────────
  function dismissTopic(topicId: string) {
    const topic = candidates.value.find(t => t.id === topicId)
    if (topic) {
      // Track dismiss in profile
      const p = profile.value
      p.categoryDismisses[topic.category] = (p.categoryDismisses[topic.category] || 0) + 1
      p.updatedAt = Date.now()
      saveProfile(p)
    }
    candidates.value = candidates.value.filter(t => t.id !== topicId)

    // Update batch cache
    const catKey = batchCategoriesKey(categories.value)
    saveBatchCache({ date: todayStr(), categoriesKey: catKey, topics: candidates.value })
  }

  // ─── Select topic ─────────────────────────────────────
  function selectTopic(topic: TopicCandidate) {
    selectedTopic.value = topic
    clearOpeningPreview()
    // Track selection in profile
    const p = profile.value
    p.categoryHits[topic.category] = (p.categoryHits[topic.category] || 0) + 1
    p.updatedAt = Date.now()
    saveProfile(p)
    phase.value = 'pick_stance'
  }

  function clearOpeningPreview() {
    openingPreviewNonce.value += 1
    openingPreview.value = null
    openingPreviewTask = null
  }

  function getMatchingOpeningPreview(topicId: string, role: UserDebateRole, modelId: string) {
    const preview = openingPreview.value
    if (!preview) return null
    if (preview.topicId !== topicId) return null
    if (preview.userRole !== role) return null
    if (preview.modelId !== modelId) return null
    return preview
  }

  async function prefetchOpening(topic: TopicCandidate, role: UserDebateRole) {
    if (role !== 'con' && role !== 'judge') {
      clearOpeningPreview()
      return
    }

    const appStore = useAppStore()
    const pickedModels = pickDebateModels(appStore, modelMode.value || 'auto')
    if (!pickedModels) {
      clearOpeningPreview()
      return
    }

    const nonce = openingPreviewNonce.value + 1
    openingPreviewNonce.value = nonce
    const modelId = pickedModels.pro
    openingPreview.value = {
      topicId: topic.id,
      userRole: role,
      modelId,
      modelName: appStore.getModel(modelId)?.name || modelId,
      text: '',
      status: 'loading',
    }

    if (modelId.startsWith('demo/')) {
      const trace = createTimingSpan('daily-challenge:prefetch:pro-opening', {
        modelId,
        topicId: topic.id,
        userRole: role,
        source: 'local-demo',
      })
      const text = buildFallbackDebaterText({
        topic,
        stance: 'pro',
        round: 1,
        history: [],
      })

      openingPreviewTask = (async () => {
        let marked = false
        await streamLocalText(text, (nextText) => {
          if (openingPreviewNonce.value !== nonce) return
          const current = getMatchingOpeningPreview(topic.id, role, modelId)
          if (!current) return
          current.text = nextText
          if (!marked && nextText) {
            marked = true
            trace.mark('first_chunk', { localDemo: true })
          }
        })

        if (openingPreviewNonce.value !== nonce) return
        openingPreview.value = {
          topicId: topic.id,
          userRole: role,
          modelId,
          modelName: appStore.getModel(modelId)?.name || modelId,
          text,
          status: 'done',
        }
        trace.success({ localDemo: true, charCount: text.length })
      })()

      await openingPreviewTask
      return
    }

    openingPreviewTask = (async () => {
      try {
        const text = await streamText(streamModelChat({
          modelId,
          traceLabel: 'daily-challenge:prefetch:pro-opening',
          traceMeta: {
            topicId: topic.id,
            userRole: role,
          },
          messages: [{ role: 'user', content: buildRoundDebaterPrompt({
            topic,
            stance: 'pro',
            round: 1,
            history: [],
          }) }],
        }), (nextText) => {
          if (openingPreviewNonce.value !== nonce) return
          const current = getMatchingOpeningPreview(topic.id, role, modelId)
          if (!current) return
          current.text = nextText
        })

        if (openingPreviewNonce.value !== nonce) return
        openingPreview.value = {
          topicId: topic.id,
          userRole: role,
          modelId,
          modelName: appStore.getModel(modelId)?.name || modelId,
          text,
          status: 'done',
        }
      } catch {
        if (openingPreviewNonce.value !== nonce) return
        openingPreview.value = {
          topicId: topic.id,
          userRole: role,
          modelId,
          modelName: appStore.getModel(modelId)?.name || modelId,
          text: openingPreview.value?.text || '',
          status: 'error',
        }
      }
    })()

    await openingPreviewTask
  }

  // ─── Start debate (多轮聊天式) ──────────────────────────
  async function startDebate(payload: DebateStartPayload) {
    if (!selectedTopic.value) return
    const appStore = useAppStore()
    const role = payload.role === 'con' || payload.role === 'judge' ? payload.role : 'pro'
    const argument = typeof payload.argument === 'string' ? payload.argument.trim() : ''
    const selectedMode = payload.modelMode || modelMode.value || 'auto'

    if (role === 'pro' && !argument) {
      error.value = '请先输入你的开场观点'
      return
    }

    userRole.value = role
    userArgument.value = argument
    userStance.value = role === 'pro' ? 'support' : role === 'con' ? 'oppose' : 'mixed'
    userReason.value = argument.slice(0, 200)
    phase.value = 'debating'
    debating.value = true
    messages.value = []
    takeaway.value = null
    snapshot.value = null
    error.value = null
    awaitingUserInput.value = false
    awaitingDecision.value = false
    currentRound.value = 0
    updateModelMode(selectedMode)

    const pickedModels = pickDebateModels(appStore, selectedMode)
    if (!pickedModels) {
      error.value = '未找到可用模型，请先在设置中配置 API Key'
      debating.value = false
      return
    }

    debateModels.value = {
      generator: debateModels.value?.generator || 'curated-seeds',
      pro: role === 'pro' ? 'user' : pickedModels.pro,
      con: role === 'con' ? 'user' : pickedModels.con,
      moderator: pickedModels.moderator,
    }

    // Build the debate plan
    debatePlan.value = role === 'judge'
      ? buildDebatePlan(role)
      : buildInitialDebatePlan(role, 2)
    turnIndex.value = 0

    const ac = new AbortController()
    abortController.value = ac

    // The first turn: if user, insert their opening; if AI, generate
    const firstTurn = debatePlan.value[0]
    if (firstTurn.isUser) {
      addMessage(firstTurn, argument)
      turnIndex.value = 1
      await advanceDebate(ac)
    } else {
      const cachedOpening = openingPreview.value
      if (
        cachedOpening
        && cachedOpening.status === 'done'
        && cachedOpening.topicId === selectedTopic.value.id
        && cachedOpening.userRole === role
        && cachedOpening.modelId === pickedModels.pro
      ) {
        addMessage(firstTurn, cachedOpening.text)
        turnIndex.value = 1
      }
      await advanceDebate(ac)
    }
  }

  function addMessage(turn: TurnSpec, text: string) {
    messages.value.push({
      id: uid(),
      side: turn.side,
      round: turn.round,
      label: turn.label,
      isUser: turn.isUser,
      modelId: turn.isUser ? undefined : debateModels.value?.[turn.side === 'judge' ? 'moderator' : turn.side],
      text,
      status: 'done',
    })
  }

  /** Advance through the debate plan, generating AI turns until a user turn is needed */
  async function advanceDebate(ac: AbortController) {
    if (!selectedTopic.value) return
    const topic = selectedTopic.value
    const toast = useToastStore()

    try {
      while (turnIndex.value < debatePlan.value.length) {
        const turn = debatePlan.value[turnIndex.value]
        if (turn.round > currentRound.value) {
          currentRound.value = turn.round
        }

        if (turn.isUser) {
          // Wait for user input
          awaitingUserInput.value = true
          debating.value = false
          return // pause here, submitUserTurn will continue
        }

        // AI turn — show "generating" placeholder
        const placeholderId = uid()
        messages.value.push({
          id: placeholderId,
          side: turn.side,
          round: turn.round,
          label: turn.label,
          isUser: false,
          modelId: turn.side === 'judge' ? debateModels.value?.moderator : debateModels.value?.[turn.side],
          text: '',
          status: 'generating',
        })

        const placeholder = messages.value.find((message) => message.id === placeholderId)
        const isOpeningPreviewTurn = turn.side === 'pro'
          && turn.round === 1
          && turnIndex.value === 0
          && (userRole.value === 'con' || userRole.value === 'judge')

        if (isOpeningPreviewTurn && placeholder?.modelId) {
          const preview = getMatchingOpeningPreview(topic.id, userRole.value, placeholder.modelId)
          if (preview?.text) {
            placeholder.text = preview.text
          }

          if (preview?.status === 'loading' && openingPreviewTask) {
            try {
              await openingPreviewTask
            } catch {
              // ignore preview failure and fallback to normal generation below
            }
          }

          const latestPreview = getMatchingOpeningPreview(topic.id, userRole.value, placeholder.modelId)
          if (latestPreview?.status === 'done' && latestPreview.text) {
            placeholder.text = latestPreview.text
            placeholder.status = 'done'
            proText.value = latestPreview.text
            turnIndex.value++
            continue
          }
        }

        if (turn.side === 'judge') {
          // Judge/moderator: summarize everything + thinking snapshot
          const allProText = messages.value.filter(m => m.side === 'pro' && m.status === 'done').map(m => m.text).join('\n\n')
          const allConText = messages.value.filter(m => m.side === 'con' && m.status === 'done').map(m => m.text).join('\n\n')
          const moderatorModelId = debateModels.value?.moderator || ''

          if (moderatorModelId.startsWith('demo/')) {
            const trace = createTimingSpan('daily-challenge:moderator', {
              modelId: moderatorModelId,
              topicId: topic.id,
              round: currentRound.value,
              source: 'local-demo',
            })
            const fallback = buildFallbackModeratorResult({
              topic,
              userRole: userRole.value,
            })
            takeaway.value = fallback.takeaway
            snapshot.value = {
              version: 'v1',
              label: '思维快照 (AI 观察，仅供参考)',
              modelId: moderatorModelId,
              generatedAt: Date.now(),
              axes: fallback.thinkingSnapshot.axes,
              dominantAxes: fallback.thinkingSnapshot.dominantAxes,
              summary: fallback.thinkingSnapshot.summary,
            }
            trace.mark('first_chunk', { localDemo: true })
            trace.success({ localDemo: true })
          } else {
            const modResult = await collectFullText(streamModelChat({
              modelId: moderatorModelId,
              traceLabel: 'daily-challenge:moderator',
              traceMeta: {
                topicId: topic.id,
                round: currentRound.value,
              },
              messages: [{ role: 'user', content: buildModeratorTaggerPrompt({
                topic,
                proText: allProText,
                conText: allConText,
                userStance: userRole.value === 'pro' ? topic.sideA : userRole.value === 'con' ? topic.sideB : '裁判',
                userReason: userArgument.value,
              })}],
              signal: ac.signal,
            }))

            const parsed = parseJSON<{
              takeaway: DebateTakeaway
              thinkingSnapshot: { axes: Record<AxisId, any>; dominantAxes: AxisId[]; summary: string }
            }>(modResult)

            takeaway.value = parsed?.takeaway || {
              strongestPointFor: '正方提出了有力论点',
              strongestPointAgainst: '反方也有合理反驳',
              decisiveQuestion: '核心问题仍待你自己判断',
              oneLineVerdict: '双方各有道理，关键在于你的具体场景',
            }

            if (parsed?.thinkingSnapshot) {
              snapshot.value = {
                version: 'v1',
                label: '思维快照 (AI 观察，仅供参考)',
                modelId: moderatorModelId,
                generatedAt: Date.now(),
                axes: parsed.thinkingSnapshot.axes,
                dominantAxes: parsed.thinkingSnapshot.dominantAxes || [],
                summary: parsed.thinkingSnapshot.summary || '',
              }
            }
          }

          // Update the placeholder
          const msg = messages.value.find(m => m.id === placeholderId)
          if (msg) {
            msg.text = takeaway.value.oneLineVerdict
            msg.status = 'done'
          }
        } else {
          // Pro or Con AI turn
          const modelId = debateModels.value?.[turn.side] || ''

          if (modelId.startsWith('demo/')) {
            const trace = createTimingSpan(`daily-challenge:${turn.side}:round-${turn.round}`, {
              modelId,
              topicId: topic.id,
              side: turn.side,
              round: turn.round,
              source: 'local-demo',
            })
            const text = buildFallbackDebaterText({
              topic,
              stance: turn.side as 'pro' | 'con',
              round: turn.round,
              history: messages.value.filter(m => m.status === 'done'),
            })
            let marked = false
            await streamLocalText(text, (nextText) => {
              const msg = messages.value.find(m => m.id === placeholderId)
              if (msg) msg.text = nextText
              if (!marked && nextText) {
                marked = true
                trace.mark('first_chunk', { localDemo: true })
              }
            })

            const msg = messages.value.find(m => m.id === placeholderId)
            if (msg) {
              msg.text = text
              msg.status = 'done'
            }
            if (turn.side === 'pro') proText.value = text
            if (turn.side === 'con') conText.value = text
            trace.success({ localDemo: true, charCount: text.length })
            turnIndex.value++
            continue
          }

          // For judge mode, round 1 pro and con can be parallel
          // But for simplicity and chat feel, keep sequential
          const aiText = await streamText(streamModelChat({
            modelId,
            traceLabel: `daily-challenge:${turn.side}:round-${turn.round}`,
            traceMeta: {
              topicId: topic.id,
              side: turn.side,
              round: turn.round,
            },
            messages: [{ role: 'user', content: buildRoundDebaterPrompt({
              topic,
              stance: turn.side as 'pro' | 'con',
              round: turn.round,
              history: messages.value.filter(m => m.status === 'done'),
            })}],
            signal: ac.signal,
          }), (nextText) => {
            const msg = messages.value.find(m => m.id === placeholderId)
            if (msg) msg.text = nextText
          })

          // Update placeholder
          const msg = messages.value.find(m => m.id === placeholderId)
          if (msg) {
            msg.text = aiText
            msg.status = 'done'
          }

          // Store proText/conText for compatibility
          if (turn.side === 'pro') proText.value = aiText
          if (turn.side === 'con') conText.value = aiText
        }

        turnIndex.value++
      }

      abortController.value = null

      if (userRole.value !== 'judge' && !debatePlan.value.some(turn => turn.side === 'judge')) {
        awaitingDecision.value = true
        debating.value = false
        return
      }

      // All turns done → result phase
      debating.value = false
      phase.value = 'result'
    } catch (e: any) {
      if (e?.name === 'AbortError') return
      for (const message of messages.value) {
        if (message.status !== 'generating') continue
        message.status = 'done'
        if (!message.text.trim()) {
          message.text = '这一轮生成失败了，请重试或切换模型后继续。'
        }
      }
      error.value = e?.message || '辩论过程出错'
      toast.error(error.value!)
      debating.value = false
      abortController.value = null
    }
  }

  /** Called when user submits their turn during debate */
  async function submitUserTurn(text: string) {
    if (!awaitingUserInput.value) return
    awaitingUserInput.value = false
    debating.value = true

    const turn = debatePlan.value[turnIndex.value]
    addMessage(turn, text)

    // Store for compatibility
    if (turn.side === 'pro') proText.value = text
    if (turn.side === 'con') conText.value = text

    turnIndex.value++

    // Continue the debate
    const ac = abortController.value || new AbortController()
    abortController.value = ac
    await advanceDebate(ac)
  }

  async function continueDebate() {
    if (!awaitingDecision.value || userRole.value === 'judge') return

    awaitingDecision.value = false
    debating.value = true

    const nextRound = currentRound.value + 1
    debatePlan.value.push(...buildRoundPair(userRole.value, nextRound))

    const ac = new AbortController()
    abortController.value = ac
    await advanceDebate(ac)
  }

  async function finishDebate() {
    if (!awaitingDecision.value || userRole.value === 'judge') return

    awaitingDecision.value = false
    debating.value = true
    debatePlan.value.push(buildJudgeTurn(userRole.value))

    const ac = new AbortController()
    abortController.value = ac
    await advanceDebate(ac)
  }

  // ─── Save card + update profile ───────────────────────
  async function saveCurrentCard(finalStance?: DebateStance) {
    if (!selectedTopic.value || !takeaway.value) return

    const debateRounds = messages.value
      .filter((message) => message.status === 'done')
      .map((message) => ({
        speaker: (message.side === 'judge' ? 'moderator' : message.side) as 'pro' | 'con' | 'moderator',
        modelId: message.isUser
          ? 'user'
          : (message.modelId || debateModels.value?.[message.side === 'judge' ? 'moderator' : message.side] || ''),
        text: message.text,
      }))

    const card: OpinionCard = {
      id: uid(),
      challengeDate: todayStr(),
      createdAt: Date.now(),
      updatedAt: Date.now(),
      category: selectedTopic.value.category,
      topic: {
        title: selectedTopic.value.title,
        prompt: selectedTopic.value.prompt,
        source: debateModels.value?.generator === 'curated-seeds' ? 'curated' : 'ai_seeded',
        seed: selectedTopic.value.id,
        historyCardIds: cards.value.slice(-8).map(c => c.id),
        alternatives: candidates.value.filter(c => c.id !== selectedTopic.value!.id).map(c => c.id),
      },
      stance: {
        initial: userStance.value,
        final: finalStance || userStance.value,
        changed: (finalStance || userStance.value) !== userStance.value,
        userReason: userReason.value,
      },
      debate: {
        format: 'daily_challenge_v1',
        durationMs: 0,
        models: debateModels.value || { generator: '', pro: '', con: '', moderator: '' },
        rounds: debateRounds,
        takeaway: takeaway.value,
      },
      thinkingSnapshot: snapshot.value || {
        version: 'v1',
        label: '思维快照 (AI 观察，仅供参考)',
        modelId: '',
        generatedAt: Date.now(),
        axes: {
          evidence_intuition: { score: 50, confidence: 0, note: '' },
          decisive_exploratory: { score: 50, confidence: 0, note: '' },
          risk_seeking_risk_aware: { score: 50, confidence: 0, note: '' },
          self_systems: { score: 50, confidence: 0, note: '' },
        },
        dominantAxes: [],
        summary: '',
      },
      personalizationSignals: {
        extractedKeywords: [],
        argumentStyles: [],
      },
    }

    await saveCard(card)
    cards.value.push(card)
    currentCard.value = card

    // Update profile after saving
    updateProfileFromCard(card)
  }

  // ─── Profile management ───────────────────────────────
  function updateProfileFromCard(card: OpinionCard) {
    const p = profile.value
    // Stance distribution
    p.stanceDistribution[card.stance.final]++
    // Category hits (already tracked on select, but reinforce)
    p.categoryHits[card.category] = (p.categoryHits[card.category] || 0)
    // Update avg axes
    if (card.thinkingSnapshot.summary) {
      const axes = card.thinkingSnapshot.axes
      for (const [axisId, score] of Object.entries(axes)) {
        const existing = p.avgAxes[axisId as AxisId] ?? 50
        // Exponential moving average
        p.avgAxes[axisId as AxisId] = Math.round(existing * 0.7 + score.score * 0.3)
      }
    }
    // Extract keywords from reason
    const words = card.stance.userReason
      .replace(/[，。！？、\s]+/g, ' ')
      .split(' ')
      .filter(w => w.length >= 2)
    if (words.length) {
      const existing = new Set(p.topKeywords)
      words.forEach(w => existing.add(w))
      p.topKeywords = [...existing].slice(-20) // Keep last 20
    }
    p.updatedAt = Date.now()
    saveProfile(p)
  }

  function rebuildProfile() {
    if (!cards.value.length) return
    const p = profile.value
    // Rebuild from all cards if profile is empty
    if (p.updatedAt === 0) {
      for (const card of cards.value) {
        p.categoryHits[card.category] = (p.categoryHits[card.category] || 0) + 1
        p.stanceDistribution[card.stance.final]++
        if (card.thinkingSnapshot.summary) {
          for (const [axisId, score] of Object.entries(card.thinkingSnapshot.axes)) {
            const existing = p.avgAxes[axisId as AxisId] ?? 50
            p.avgAxes[axisId as AxisId] = Math.round(existing * 0.7 + score.score * 0.3)
          }
        }
      }
      p.updatedAt = Date.now()
      saveProfile(p)
    }
  }

  // ─── Navigation ───────────────────────────────────────
  function abort() {
    abortController.value?.abort()
    abortController.value = null
    debating.value = false
  }

  function reset() {
    phase.value = 'pick_topic'
    selectedTopic.value = null
    clearOpeningPreview()
    userStance.value = 'support'
    userRole.value = 'pro'
    userArgument.value = ''
    userReason.value = ''
    proText.value = ''
    conText.value = ''
    takeaway.value = null
    snapshot.value = null
    currentCard.value = null
    error.value = null
    messages.value = []
    debatePlan.value = []
    turnIndex.value = 0
    currentRound.value = 0
    awaitingUserInput.value = false
    awaitingDecision.value = false
  }

  function goToHistory() {
    phase.value = 'history'
  }

  return {
    phase, candidates, selectedTopic, userStance, userRole, userArgument, userReason,
    proText, conText, debating, loading, takeaway, snapshot, currentCard,
    cards, categories, modelMode, error, debateModels, profile,
    messages, awaitingUserInput, awaitingDecision, currentRound,
    todayCard, recentCards, streak,
    init, updateCategories, updateModelMode, generateTopics, refreshTopics,
    dismissTopic, selectTopic, prefetchOpening, clearOpeningPreview,
    startDebate, submitUserTurn, continueDebate, finishDebate,
    saveCurrentCard, abort, reset, goToHistory,
    openingPreview,
  }
})
