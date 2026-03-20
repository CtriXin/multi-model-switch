import type { HistoryEntry, PlayModeSessionEnvelope, SessionSummary } from '../shared'

// --- Phase machine ---

export type MultiLifePhase = 'setup' | 'investigation' | 'resolution' | 'ended'

export const VALID_ML_PHASES: MultiLifePhase[] = ['setup', 'investigation', 'resolution', 'ended']

export function isValidMLPhase(v: unknown): v is MultiLifePhase {
  return typeof v === 'string' && (VALID_ML_PHASES as string[]).includes(v)
}

// --- Role & Case ---

export type MultiLifeArchetype = 'witness' | 'suspect' | 'analyst' | 'insider' | 'innocent'

export interface MultiLifeCaseRole {
  id: string
  name: string
  archetype: MultiLifeArchetype
  reliability: number
  hiddenKnowledge: number
  lyingPattern: 'never' | 'selective' | 'consistent' | 'increasing'
  personality: string
}

export interface MultiLifeCase {
  id: string
  title: string
  premise: string
  truth: string
  roles: MultiLifeCaseRole[]
  rounds: MultiLifeRoundConfig[]
  totalRounds: number
  challengeBudget: number
}

export interface MultiLifeRoundConfig {
  roundNumber: number
  scene: string
  contradictions?: ContradictionPoint[]
  roleDirectives: {
    [roleId: string]: {
      directive: string
      lying: boolean
    }
  }
}

export interface ContradictionPoint {
  betweenRoles: [string, string]
  topic: string
  keywords: string[]
  description: string
}

// --- Runtime state ---

export interface MultiLifeEvidenceCard {
  id: string
  round: number
  source: string
  summary: string
  tag: 'key' | 'suspicious' | 'debunked' | 'ambiguous'
}

export interface MultiLifeRoleResponse {
  roleId: string
  modelId: string
  modelName: string
  text: string
  status: 'idle' | 'generating' | 'done' | 'error'
  error?: string
  isChallenged?: boolean
  challengeResponse?: string
}

export interface MultiLifeRound {
  id: string
  roundNumber: number
  scene: string
  responses: MultiLifeRoleResponse[]
  contradictions: ContradictionPoint[]
  playerChoice: MultiLifePlayerChoice | null
  evidenceCard: MultiLifeEvidenceCard | null
  createdAt: number
}

export interface MultiLifePlayerChoice {
  type: 'accept' | 'challenge'
  challengedRoleId?: string
}

// --- Model assignment: 3 roles -> 3 different-provider models ---

export interface MultiLifeModelAssignment {
  a: string
  b: string
  c: string
}

// --- Session meta (inside envelope.meta) ---

export interface MultiLifeSessionMeta {
  caseId: string
  caseTitle: string
  phase: MultiLifePhase
  currentRound: number
  totalRounds: number
  challengeRemaining: number
  challengeUsed: number
  modelAssignment: MultiLifeModelAssignment | null
  trustMap: Record<string, number>
  evidenceCards: MultiLifeEvidenceCard[]
  branchMemory: string[]
  ending: MultiLifeSessionEnding | null
}

export interface MultiLifeSessionEnding {
  playerNarrative: string
  truthNarrative: string
  deviationAnalysis: string
  unexploredBranches: string[]
}

// --- Persistence record ---

export type MultiLifeSessionRecord = {
  envelope: PlayModeSessionEnvelope
  rounds: MultiLifeRound[]
  selectedCaseId: string
}

// --- Helpers for building shared types ---

export function buildMLHistoryEntry(
  round: MultiLifeRound,
  caseData: MultiLifeCase,
): HistoryEntry {
  const choice = round.playerChoice
  const choiceLabel = choice
    ? choice.type === 'challenge'
      ? `质疑了${caseData.roles.find((r) => r.id === choice.challengedRoleId)?.name ?? '某角色'}`
      : '接受了当前说法'
    : '（无操作）'

  return {
    id: `ml-${round.id}`,
    round: round.roundNumber,
    type: 'ml_round',
    createdAt: new Date(round.createdAt).toISOString(),
    title: `第 ${round.roundNumber} 轮：${round.scene.slice(0, 20)}…`,
    summary: `${choiceLabel}。${round.contradictions.length ? `矛盾：${round.contradictions.map((c) => c.topic).join('、')}` : '无矛盾。'}`,
    payload: {
      scene: round.scene,
      choice,
      contradictions: round.contradictions.map((c) => ({ topic: c.topic, description: c.description })),
    },
    tags: ['multi-life'],
  }
}

export function buildMLSummary(
  envelope: PlayModeSessionEnvelope,
  rounds: MultiLifeRound[],
  caseData: MultiLifeCase,
): SessionSummary {
  const meta = envelope.meta as unknown as MultiLifeSessionMeta
  const challengeCount = rounds.filter((r) => r.playerChoice?.type === 'challenge').length
  return {
    headline: caseData.title,
    brief: meta.ending
      ? '游戏结束，已生成你的版本与真相对比。'
      : `第 ${rounds.length}/${caseData.totalRounds} 轮，已质疑 ${challengeCount} 次。`,
    bullets: [
      `案件：${caseData.title}`,
      `进行了 ${rounds.length} 轮`,
      `质疑 ${challengeCount} 次`,
    ],
    payload: { caseId: caseData.id, roundsPlayed: rounds.length },
  }
}
