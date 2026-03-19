// Daily Challenge + Thinking Pattern Snapshot — Core Types

export type DailyCategory = 'tech' | 'society' | 'career' | 'philosophy' | 'life' | 'economy' | 'future' | 'grey' | 'mind' | 'culture' | 'ecology'

export const CATEGORY_LABELS: Record<DailyCategory, string> = {
  tech: '科技',
  society: '社会',
  career: '职场',
  philosophy: '伦理',
  life: '生活',
  economy: '经济',
  future: '未来',
  grey: '暗区',
  mind: '心智',
  culture: '潮流',
  ecology: '生态'
}

export const CATEGORY_ICONS: Record<DailyCategory, string> = {
  tech: '🤖',
  society: '👥',
  career: '💼',
  philosophy: '🏛️',
  life: '🌱',
  economy: '📈',
  future: '🚀',
  grey: '🕵️',
  mind: '🧠',
  culture: '🎮',
  ecology: '🌍'
}


export type DebateStance = 'support' | 'oppose' | 'mixed'
/** 用户在三辩制中的角色 */
export type UserDebateRole = 'pro' | 'con' | 'judge'
export type DebateModelMode = 'auto' | 'cheap' | 'balanced' | 'quality'
export type TopicSource = 'curated' | 'ai_seeded' | 'hybrid'
export type AxisId = 'evidence_intuition' | 'decisive_exploratory' | 'risk_seeking_risk_aware' | 'self_systems'
export type ArgumentStyle = 'evidence_first' | 'principle_first' | 'pragmatic' | 'possibility_first' | 'balanced'

export const AXIS_LABELS: Record<AxisId, [string, string]> = {
  evidence_intuition: ['直觉驱动', '证据驱动'],
  decisive_exploratory: ['果断型', '探索型'],
  risk_seeking_risk_aware: ['冒险偏好', '风险意识'],
  self_systems: ['自我聚焦', '系统思维'],
}

export interface ThinkingAxisScore {
  score: number       // 0-100, 50 is neutral
  confidence: number  // 0-1
  note: string
}

export interface ThinkingPatternSnapshot {
  version: 'v1'
  label: '思维快照 (AI 观察，仅供参考)'
  modelId: string
  generatedAt: number
  axes: Record<AxisId, ThinkingAxisScore>
  dominantAxes: AxisId[]
  summary: string
}

export type TopicDifficulty = 'casual' | 'deep' | 'philosophical'

export interface TopicCandidate {
  id: string
  title: string
  prompt: string
  sideA: string
  sideB: string
  category: DailyCategory
  /** 一句话勾子，吸引用户点击 */
  hook?: string
  /** 话题难度 */
  difficulty?: TopicDifficulty
  /** 争议度 1-5 */
  controversy?: number
  /** 推荐理由（基于画像） */
  whyRecommended?: string
}

/** 用户画像 — 积累在本地，用于改善推荐 */
export interface UserProfile {
  /** 各品类参与次数 */
  categoryHits: Partial<Record<DailyCategory, number>>
  /** 各品类 dismiss 次数 */
  categoryDismisses: Partial<Record<DailyCategory, number>>
  /** 高频关键词（从观点卡提取） */
  topKeywords: string[]
  /** 立场倾向 */
  stanceDistribution: Record<DebateStance, number>
  /** 最近思维轴平均值（用于推荐更具挑战的话题） */
  avgAxes: Partial<Record<AxisId, number>>
  /** 上次更新时间 */
  updatedAt: number
}

export interface TopicMeta {
  title: string
  prompt: string
  source: TopicSource
  seed: string
  historyCardIds: string[]
  alternatives: string[]
}

export interface DebateRound {
  speaker: 'pro' | 'con' | 'moderator'
  modelId: string
  text: string
  latencyMs?: number
}

export interface DebateTakeaway {
  strongestPointFor: string
  strongestPointAgainst: string
  decisiveQuestion: string
  oneLineVerdict: string
}

export interface DebateRecord {
  format: 'daily_challenge_v1'
  durationMs: number
  models: { generator: string; pro: string; con: string; moderator: string }
  rounds: DebateRound[]
  takeaway: DebateTakeaway
}

export interface OpinionCard {
  id: string
  challengeDate: string  // YYYY-MM-DD
  createdAt: number
  updatedAt: number
  category: DailyCategory
  topic: TopicMeta
  stance: {
    initial: DebateStance
    final: DebateStance
    changed: boolean
    userReason: string
  }
  debate: DebateRecord
  thinkingSnapshot: ThinkingPatternSnapshot
  personalizationSignals: {
    extractedKeywords: string[]
    argumentStyles: ArgumentStyle[]
  }
  shareCard?: { title: string; subtitle: string; quote: string }
}

export interface WeeklyReflection {
  weekStart: string
  weekEnd: string
  completedDays: number
  streak: number
  mostDiscussedCategory: DailyCategory
  dominantAxis: AxisId
  mostVolatileAxis: AxisId
  stanceChangeRate: number
  clarityScore: number
  clarityCurve: number[]
  summary: string
  representativeCardIds: string[]
}

export type ChallengePhase =
  | 'loading'
  | 'pick_topic'
  | 'pick_stance'
  | 'debating'
  | 'result'
  | 'history'

/** 辩论聊天中的单条消息 */
export interface DebateMessage {
  id: string
  side: 'pro' | 'con' | 'judge'
  round: number           // 1 or 2, 0 for judge
  label: string           // "正方一辩", "反方二辩", "裁判总结"
  isUser: boolean
  modelId?: string
  text: string
  status: 'done' | 'generating' | 'waiting'
}

/** 辩论计划中的一步 */
export interface TurnSpec {
  side: 'pro' | 'con' | 'judge'
  round: number
  label: string
  isUser: boolean
}

export interface DebateStartPayload {
  role: UserDebateRole
  argument: string
  modelMode?: DebateModelMode
}

const ROUND_LABELS = ['一辩', '二辩', '三辩', '四辩', '五辩', '六辩']

function buildTurnLabel(side: 'pro' | 'con', round: number): string {
  const sideLabel = side === 'pro' ? '正方' : '反方'
  const roundLabel = ROUND_LABELS[round - 1]
  return roundLabel ? `${sideLabel}${roundLabel}` : `${sideLabel}第${round}轮`
}

export function buildRoundPair(role: UserDebateRole, round: number): TurnSpec[] {
  if (role === 'pro') {
    return [
      { side: 'pro', round, label: buildTurnLabel('pro', round), isUser: true },
      { side: 'con', round, label: buildTurnLabel('con', round), isUser: false },
    ]
  }

  if (role === 'con') {
    return [
      { side: 'pro', round, label: buildTurnLabel('pro', round), isUser: false },
      { side: 'con', round, label: buildTurnLabel('con', round), isUser: true },
    ]
  }

  return [
    { side: 'pro', round, label: buildTurnLabel('pro', round), isUser: false },
    { side: 'con', round, label: buildTurnLabel('con', round), isUser: false },
  ]
}

export function buildJudgeTurn(role: UserDebateRole): TurnSpec {
  return {
    side: 'judge',
    round: 0,
    label: '裁判总结',
    isUser: role === 'judge',
  }
}

export function buildInitialDebatePlan(role: UserDebateRole, rounds = 2): TurnSpec[] {
  const plan: TurnSpec[] = []

  for (let round = 1; round <= rounds; round++) {
    plan.push(...buildRoundPair(role, round))
  }

  return plan
}

export function buildDebatePlan(role: UserDebateRole): TurnSpec[] {
  return [...buildInitialDebatePlan(role, 2), buildJudgeTurn(role)]
}
