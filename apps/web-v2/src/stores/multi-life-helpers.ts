import { useAppStore } from '@/stores/app'
import {
  PLAY_MODE_SCHEMA_VERSION,
  type PlayModeSessionEnvelope,
} from '@/features/play-modes/shared'
import {
  type MultiLifeCase,
  type MultiLifeModelAssignment,
  type MultiLifeRound,
  type MultiLifeSessionMeta,
  type MultiLifeSessionRecord,
  type MultiLifeEvidenceCard,
  type ContradictionPoint,
  type MultiLifeRoleResponse,
  isValidMLPhase,
} from '@/features/play-modes/multi-life'

// --- Constants ---

export const STORAGE_KEY = 'mms-multi-life-session'

// --- Pure utility functions ---

export function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function isoNow() {
  return new Date().toISOString()
}

export function cloneForStorage<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

export async function collectText(stream: AsyncGenerator<string>) {
  let text = ''
  for await (const chunk of stream) {
    text += chunk
  }
  return text.trim()
}

/** Stream an async generator into a reactive callback, returns the final text */
export async function streamInto(
  stream: AsyncGenerator<string>,
  onChunk: (chunk: string) => void,
): Promise<string> {
  let text = ''
  for await (const chunk of stream) {
    text += chunk
    onChunk(chunk)
  }
  return text.trim()
}

/** Simulate streaming a static string character by character */
export async function streamMockInto(
  text: string,
  onChunk: (chunk: string) => void,
  speed = 25,
): Promise<void> {
  for (const char of text) {
    onChunk(char)
    await new Promise((r) => setTimeout(r, speed))
  }
}

// --- Model assignment ---

export interface ModelPickResult {
  assignment: MultiLifeModelAssignment
  diverse: boolean  // true = 3 different providers
}

export function chooseCaseModels(
  appStore: ReturnType<typeof useAppStore>,
): ModelPickResult | null {
  const all = [...appStore.models]
  if (all.length < 1) return null

  const preferred = appStore.preferFree
    ? (all.filter((item) => item.free).length ? all.filter((item) => item.free) : all)
    : all

  // Group by provider, pick one model per provider
  const byProvider = new Map<string, typeof preferred>()
  for (const model of preferred) {
    if (!byProvider.has(model.provider)) {
      byProvider.set(model.provider, [])
    }
    byProvider.get(model.provider)!.push(model)
  }

  if (byProvider.size >= 3) {
    const picked: { id: string }[] = []
    for (const [, models] of byProvider) {
      picked.push({ id: models[0].id })
      if (picked.length === 3) break
    }
    return { assignment: { a: picked[0].id, b: picked[1].id, c: picked[2].id }, diverse: true }
  }

  // Fallback: pick top 3 regardless of provider
  const top3 = preferred.slice(0, 3)
  while (top3.length < 3 && all.length > top3.length) {
    const next = all[top3.length]
    if (next && !top3.find(m => m.id === next.id)) top3.push(next)
    else break
  }
  if (top3.length < 1) return null

  return {
    assignment: {
      a: top3[0]?.id ?? top3[0].id,
      b: top3[1]?.id ?? top3[0].id,
      c: top3[2]?.id ?? top3[0].id,
    },
    diverse: false,
  }
}

export function normalizeAssignment(
  assignment: MultiLifeModelAssignment | null,
  appStore: ReturnType<typeof useAppStore>,
): ModelPickResult | null {
  if (!assignment) return chooseCaseModels(appStore)

  const ids = [assignment.a, assignment.b, assignment.c]
  if (ids.every((id) => appStore.getModel(id))) {
    const providers = new Set(ids.map((id) => appStore.getModel(id)?.provider).filter(Boolean))
    return { assignment, diverse: providers.size >= 3 }
  }
  return chooseCaseModels(appStore)
}

// --- Envelope construction ---

function createMeta(caseData: MultiLifeCase): MultiLifeSessionMeta {
  return {
    caseId: caseData.id,
    caseTitle: caseData.title,
    phase: 'setup',
    currentRound: 0,
    totalRounds: caseData.totalRounds,
    challengeRemaining: caseData.challengeBudget,
    challengeUsed: 0,
    modelAssignment: null,
    trustMap: Object.fromEntries(caseData.roles.map((r) => [r.id, 0])),
    evidenceCards: [],
    branchMemory: [],
    ending: null,
  }
}

export function createEnvelope(caseData: MultiLifeCase): PlayModeSessionEnvelope {
  const now = isoNow()
  return {
    schemaVersion: PLAY_MODE_SCHEMA_VERSION,
    mode: 'multi-life',
    sessionId: uid(),
    status: 'pending',
    round: 0,
    startedAt: now,
    updatedAt: now,
    seed: {
      id: `ml-${caseData.id}`,
      label: caseData.title,
      payload: { caseId: caseData.id },
    },
    summary: null,
    ending: null,
    history: [],
    pauseState: null,
    cache: null,
    meta: createMeta(caseData) as unknown as Record<string, unknown>,
  }
}

export function getMeta(envelope: PlayModeSessionEnvelope): MultiLifeSessionMeta {
  return envelope.meta as unknown as MultiLifeSessionMeta
}

// --- Branch memory ---

export function buildBranchMemory(rounds: MultiLifeRound[], limit = 6): string[] {
  return rounds.slice(-limit).map((r) => {
    const choice = r.playerChoice
    const choiceStr = choice
      ? choice.type === 'challenge'
        ? `质疑了某角色`
        : '接受说法'
      : '继续'
    return `第${r.roundNumber}轮：${r.scene.slice(0, 30)}…（${choiceStr}）`
  })
}

// --- Evidence card generation ---

export function generateEvidenceCard(
  round: MultiLifeRound,
  caseData: MultiLifeCase,
): MultiLifeEvidenceCard | null {
  const choice = round.playerChoice
  if (!choice) return null

  const responses = round.responses.filter((r) => r.status === 'done')
  if (!responses.length) return null

  const roleNames = responses.map((r) => caseData.roles.find((cr) => cr.id === r.roleId)?.name ?? r.roleId)
  const hasContradiction = round.contradictions.length > 0
  const wasChallenged = choice.type === 'challenge'

  let summary: string
  let tag: MultiLifeEvidenceCard['tag']

  if (wasChallenged) {
    const challengedRole = caseData.roles.find((r) => r.id === choice.challengedRoleId)
    summary = `质疑${challengedRole?.name ?? '某角色'}关于${round.contradictions[0]?.topic ?? '证词'}的说法`
    tag = 'suspicious'
  } else if (hasContradiction) {
    summary = `${round.contradictions[0]?.topic ?? '矛盾'}：${roleNames.join('、')}说法存在分歧`
    tag = 'ambiguous'
  } else {
    summary = `${roleNames.slice(0, 2).join('、')}的证词一致`
    tag = 'key'
  }

  return {
    id: `evidence-${round.id}`,
    round: round.roundNumber,
    source: roleNames.slice(0, 2).join('、'),
    summary,
    tag,
  }
}

// --- Contradiction detection (pure local, keyword matching) ---

export function detectContradictions(
  roundConfig: { contradictions?: ContradictionPoint[] },
  responses: MultiLifeRoleResponse[],
): ContradictionPoint[] {
  if (!roundConfig.contradictions?.length) return []

  return roundConfig.contradictions.filter((cp) => {
    const roleA = responses.find((r) => r.roleId === cp.betweenRoles[0])
    const roleB = responses.find((r) => r.roleId === cp.betweenRoles[1])
    if (!roleA?.text || !roleB?.text) return false

    return cp.keywords.some(
      (kw) => roleA.text.includes(kw) || roleB.text.includes(kw),
    )
  })
}

// --- Migration ---

export function normalizeRecord(
  record: MultiLifeSessionRecord,
  appStore: ReturnType<typeof useAppStore>,
): MultiLifeSessionRecord {
  const envelope = record.envelope
  const meta = getMeta(envelope)

  const rawPhase = meta.phase
  const normalizedPhase = isValidMLPhase(rawPhase) ? rawPhase : 'setup'

  const normalizedMeta: MultiLifeSessionMeta = {
    ...meta,
    phase: normalizedPhase,
    trustMap: meta.trustMap && typeof meta.trustMap === 'object' ? meta.trustMap : {},
    evidenceCards: Array.isArray(meta.evidenceCards) ? meta.evidenceCards : [],
    branchMemory: Array.isArray(meta.branchMemory) ? meta.branchMemory : [],
    challengeUsed: meta.challengeUsed ?? 0,
    modelAssignment: normalizeAssignment(meta.modelAssignment, appStore)?.assignment ?? null,
  }

  const rawRounds = Array.isArray(record.rounds) ? record.rounds : []
  const rounds = rawRounds.map((round) => {
    const next = cloneForStorage(round)
    for (const resp of next.responses) {
      if (resp.status === 'generating') {
        resp.status = 'error'
        resp.error = '会话中断'
        resp.text = resp.text || '（证词因中断丢失）'
      }
    }
    return next
  })

  envelope.meta = normalizedMeta as unknown as Record<string, unknown>
  envelope.round = normalizedMeta.currentRound
  envelope.updatedAt = isoNow()

  return { envelope, rounds, selectedCaseId: record.selectedCaseId }
}
