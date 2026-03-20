export type PlayModeId =
  | 'daily-challenge'
  | 'story-lite'
  | 'story-live'
  | 'turtle-soup'
  | 'case-reconstruction'
  | 'multi-life'

export type SessionStatus =
  | 'pending'
  | 'active'
  | 'paused'
  | 'completed'
  | 'abandoned'

export type HistoryEntryType =
  | 'story_turn'
  | 'question_round'
  | 'investigation_turn'
  | 'special_event'
  | 'summary_snapshot'
  | 'ending'
  | 'ml_round'

export type EndingGrade =
  | 'failure'
  | 'normal'
  | 'hidden'
  | 'optimal'
  | 'good'
  | 'bad'
  | 'mystery'

export interface SessionSeed {
  id: string
  label: string
  payload: Record<string, unknown>
}

export interface SessionSummary {
  headline: string
  brief: string
  bullets?: string[]
  payload?: Record<string, unknown>
}

export interface HistoryEntry {
  id: string
  round: number
  type: HistoryEntryType
  createdAt: string
  title?: string
  summary: string
  payload: Record<string, unknown>
  tags?: string[]
}

export interface SessionEnding {
  title: string
  grade: EndingGrade
  summary: string
  payload: Record<string, unknown>
}

export interface PauseState {
  pausedAt: string
  resumeHint: string
  snapshot: Record<string, unknown>
}

export interface SessionCacheEntry {
  key: string
  createdAt: string
  status: 'ready' | 'stale' | 'consumed'
  payload: Record<string, unknown>
}

export interface SessionCacheState {
  strategy: 'none' | 'prefetch' | 'batched'
  entries: SessionCacheEntry[]
}

export interface PlayModeSessionEnvelope {
  schemaVersion: string
  mode: PlayModeId
  sessionId: string
  status: SessionStatus
  round: number
  startedAt: string
  updatedAt: string
  seed: SessionSeed | null
  summary: SessionSummary | null
  ending: SessionEnding | null
  history: HistoryEntry[]
  pauseState: PauseState | null
  cache: SessionCacheState | null
  meta: Record<string, unknown>
}

export interface PlayModeDefinition {
  id: PlayModeId
  label: string
  promptNamespace?: string
  historyKinds: HistoryEntryType[]
  endingGrades: EndingGrade[]
  lifecycle: {
    supportsPause: boolean
    supportsResume: boolean
    supportsAbandon: boolean
  }
}

export interface HistoryCardViewModel {
  id: string
  roundLabel: string
  typeLabel: string
  summary: string
  badges: string[]
}

export interface ResultCardViewModel {
  title: string
  grade: EndingGrade
  summary: string
  highlights: string[]
}
