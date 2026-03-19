import type { HistoryEntry, PlayModeSessionEnvelope } from '../shared'

export type StoryLiteAgentRole = 'logic' | 'emotion' | 'twist'

export type StoryLitePhase =
  | 'seed'
  | 'briefing'
  | 'agents_response'
  | 'player_choice'
  | 'resolve'
  | 'check_ending'
  | 'ended'

export type StoryLiteRiskLevel = 'low' | 'medium' | 'high'

export interface StoryLiteChoice {
  id: string
  label: string
  risk: StoryLiteRiskLevel
}

export interface StoryState {
  act: 1 | 2 | 3
  suspicion: number
  danger: number
  trust: number
  clues: string[]
  activeThreads: string[]
  triggeredEvents: string[]
  pendingTwist?: string | null
}

export interface StoryTurnPayload {
  sceneSummary: string
  logic: {
    insight: string
    suggestions: string[]
  }
  emotion: {
    feeling: string
    tension: string
  }
  twist: {
    triggered: boolean
    event?: string
    reason?: string
  }
  choices: StoryLiteChoice[]
  outcome?: string
}

export interface StoryLiteSessionMeta {
  phase: StoryLitePhase
  storyState: StoryState
  currentChoices?: StoryLiteChoice[]
  currentBriefing?: string
}

export interface StoryLiteSessionEnvelope extends PlayModeSessionEnvelope {
  mode: 'story-lite'
  meta: StoryLiteSessionMeta & Record<string, unknown>
  history: Array<HistoryEntry & { type: 'story_turn' | 'special_event' | 'summary_snapshot' }>
}

export interface StoryLiteRoundContext {
  sessionId: string
  round: number
  seedLabel: string
  sceneSummary: string
  storyState: StoryState
  recentHistorySummary: string[]
  lastPlayerChoice?: string
  availableThreads?: string[]
}

export interface LogicOutput {
  insight: string
  risk: string
  choices: StoryLiteChoice[]
}

export interface EmotionOutput {
  feeling: string
  motivation: string
  tension: string
}

export interface TwistOutput {
  candidateEvent: string
  reason: string
  intensity: StoryLiteRiskLevel
}

export interface DirectorOutput {
  summary: string
  acceptedTwist: boolean
  briefing: string
  outcome: string
  statePatch: Record<string, unknown>
  historyEntry: Pick<HistoryEntry, 'type' | 'summary'>
}
