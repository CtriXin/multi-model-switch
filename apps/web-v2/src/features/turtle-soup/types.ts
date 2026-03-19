// Turtle Soup — Core Types

export type TurtleSoupPhase =
  | 'loading'
  | 'pick_puzzle'
  | 'playing'
  | 'completed'
  | 'abandoned'

export type HostTag = 'yes' | 'no' | 'yes_and_no' | 'irrelevant' | 'close'

export type PuzzleCategory =
  | 'mystery'
  | 'psychological'
  | 'dark'
  | 'lateral'
  | 'horror'
  | 'daily'
  | 'classic'

export type ClueDimension =
  | 'who'
  | 'what'
  | 'when'
  | 'where'
  | 'why'
  | 'how'
  | 'twist'

export interface PuzzleClue {
  id: string
  dimension: ClueDimension
  text: string
  isPublic: boolean
  revealOrder: number
}

export interface PuzzleMislead {
  direction: string
  whyItWorks: string
}

export interface PuzzleHint {
  level: 1 | 2 | 3
  text: string
  relatedClueIds: string[]
}

export interface IdealPath {
  question: string
  expectedAnswer: string
  why: string
}

export interface Puzzle {
  id: string
  version: 'v1'
  title: string
  surfaceText: string
  category: PuzzleCategory
  difficulty: 'easy' | 'normal' | 'hard'
  tags: string[]
  author: string
  createdAt: string
  playCount?: number
  truth: string
  truthKeywords: string[]
  clues: PuzzleClue[]
  misleads: PuzzleMislead[]
  hints: PuzzleHint[]
  solveKeywords: string[]
  solveThreshold: number
  reviewed: boolean
  rating?: number
  idealPaths?: IdealPath[]
}

export interface ValidationError {
  rule: string
  message: string
  severity: 'error' | 'warning'
}

// ─── Game state types ──────────────────────────────────

export interface HostOutput {
  tag: HostTag
  followUp?: string
}

export interface VerifierOutput {
  approved: boolean
  reason: string
  confidence: number
  leakRisk?: 'low' | 'medium' | 'high'
  suggestedTag?: HostTag
  suggestedFollowUp?: string
  suggestedFix?: string
  guessedCorrectly?: boolean
  solveConfidence?: number
}

export interface HintOutput {
  hint: string
  revealedDimension?: string
}

export interface RecapOutput {
  keyMisleads: Array<{
    round: number
    description: string
    why: string
  }>
  keyQuestions: Array<{
    round: number
    question: string
    answer: string
    significance: string
  }>
  replaySuggestions: string[]
}

export interface QuestionRecord {
  round: number
  question: string
  answer: string
  guidance?: string
  tags: HostTag[]
  verifierResult: 'approved' | 'rejected' | 'fallback'
  latencyMs?: number
}

export interface TurtleSoupResult {
  outcome: 'solved' | 'abandoned'
  totalRounds: number
  totalQuestions: number
  hintsUsed: number
  durationMs: number
  solveQuality?: 'perfect' | 'good' | 'hinted' | 'assisted'
}

export interface TurtleSoupMetadata {
  puzzleId: string
  puzzleTitle: string
  difficulty: 'easy' | 'normal' | 'hard'
  currentRound: number
  totalQuestions: number
  hintLevel: number
  questions: QuestionRecord[]
  result?: TurtleSoupResult
}

/** Internal persistence shape — wraps metadata with DB-level fields */
export interface TurtleSoupRecord {
  id: string
  phase: TurtleSoupPhase
  round: number
  metadata: TurtleSoupMetadata
  startedAt: number
  updatedAt: number
  completedPuzzleIds: string[]
}

// ─── Tag label map ─────────────────────────────────────

export const TAG_LABELS: Record<HostTag, string> = {
  yes: '是',
  no: '不是',
  yes_and_no: '是也不是',
  irrelevant: '无关',
  close: '接近了',
}

export const CATEGORY_LABELS: Record<PuzzleCategory, string> = {
  mystery: '悬疑推理',
  psychological: '心理反转',
  dark: '黑色幽默',
  lateral: '侧向思维',
  horror: '恐怖向',
  daily: '生活向',
  classic: '经典',
}

export const DIFFICULTY_LABELS: Record<Puzzle['difficulty'], string> = {
  easy: '入门',
  normal: '进阶',
  hard: '困难',
}
