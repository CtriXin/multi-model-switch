export type StoryLiveRole = 'logic' | 'emotion' | 'twist'
export type StoryLiveWrapMode = 'story' | 'script'

/** 5-stage phase machine: premise → directing → live → wrapping → ended */
export type StoryLivePhase = 'premise' | 'directing' | 'live' | 'wrapping' | 'ended'

export interface StoryLiveStoryState {
  location: string
  characters: string[]
  goals: string[]
  unresolved: string[]
  tension: number        // 0–5
  entities: string[]     // key objects / entities
  recentEvents: string[] // last 3 rounds (stagnation detection)
  roundsSinceChange: number
  latestUserIntent: string | null
  tensionHistory: number[] // persisted tension per round for arc detection
}

const VALID_PHASES: StoryLivePhase[] = ['premise', 'directing', 'live', 'wrapping', 'ended']

export function isValidPhase(v: unknown): v is StoryLivePhase {
  return typeof v === 'string' && (VALID_PHASES as string[]).includes(v)
}

export type ValidationWarning = {
  role: StoryLiveRole
  rule: string
  message: string
  confidence: number  // 0–1, only warnings ≥ 0.5 are injected into director memory
}

export interface StoryLiveRoleResponse {
  role: StoryLiveRole
  modelId: string
  modelName: string
  text: string
  status: 'idle' | 'generating' | 'done' | 'error'
  error?: string
  validationWarnings?: ValidationWarning[]
  twistSkipped?: boolean
  twistSkipReason?: string
}

export interface StoryLiveTurn {
  id: string
  userText: string
  createdAt: number
  responses: Record<StoryLiveRole, StoryLiveRoleResponse>
}

export interface StoryLiveModelAssignment {
  logic: string
  emotion: string
  twist: string
}

export interface StoryLiveWrapResult {
  mode: StoryLiveWrapMode
  modelId: string
  modelName: string
  text: string
  status: 'idle' | 'generating' | 'done' | 'error'
  error?: string
  updatedAt: number
}

export interface StoryLiveDirectorMemory {
  id: string
  fromRound: number
  toRound: number
  summary: string
}

export interface StoryLiveSessionMeta {
  premise: string
  modelAssignment: StoryLiveModelAssignment | null
  latestDirectorCue: string | null
  directorMemory: StoryLiveDirectorMemory[]
  wrapResult: StoryLiveWrapResult | null
  phase: StoryLivePhase
  storyState: StoryLiveStoryState
  lastTwistRound: number
  validationWarnings: ValidationWarning[]
}
