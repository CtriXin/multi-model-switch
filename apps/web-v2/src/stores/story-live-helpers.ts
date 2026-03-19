import { sanitizeModelOutput } from '@/utils/modelOutput'
import { useAppStore } from '@/stores/app'
import {
  PLAY_MODE_SCHEMA_VERSION,
  type HistoryEntry,
  type PlayModeSessionEnvelope,
  type SessionSummary,
} from '@/features/play-modes/shared'
import {
  buildStoryLiveFallback,
  buildStoryLiveWrapFallback,
  createInitialState,
  isValidPhase,
  type StoryLiveDirectorMemory,
  type StoryLiveModelAssignment,
  type StoryLivePhase,
  type StoryLiveRole,
  type StoryLiveSessionMeta,
  type StoryLiveStoryState,
  type StoryLiveTurn,
  type StoryLiveWrapResult,
} from '@/features/play-modes/story-live'

// --- Constants ---

export const CURRENT_PROMISE = '一个女人倒在血泊中'
const MEMORY_CHUNK_SIZE = 3
const RECENT_TURN_WINDOW = 4

// --- Types ---

export type StoryLiveSessionRecord = {
  envelope: PlayModeSessionEnvelope
  turns: StoryLiveTurn[]
  draftInput: string
}

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

export function extractDirectorCue(text: string) {
  const content = sanitizeModelOutput(text).content || ''
  const parts = content
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)

  return parts.at(-1) || ''
}

function toPlainText(text: string, maxLength = 88) {
  const content = sanitizeModelOutput(text).content || ''
  const compact = content.replace(/\s+/g, ' ').trim()
  if (!compact) return ''
  return compact.length > maxLength ? `${compact.slice(0, maxLength)}...` : compact
}

// --- Model assignment ---

export function chooseModelIds(appStore: ReturnType<typeof useAppStore>): StoryLiveModelAssignment | null {
  const selected = appStore.selectedModelIds.filter((id) => appStore.getModel(id))
  if (selected.length >= 3) {
    return {
      logic: selected[0],
      emotion: selected[1],
      twist: selected[2],
    }
  }

  const all = [...appStore.models]
  if (!all.length) return null

  const preferred = appStore.preferFree
    ? (all.filter((item) => item.free).length ? all.filter((item) => item.free) : all)
    : all

  const picked: string[] = []
  const providers = new Set<string>()

  for (const model of preferred) {
    if (providers.has(model.provider)) continue
    picked.push(model.id)
    providers.add(model.provider)
    if (picked.length === 3) break
  }

  for (const model of preferred) {
    if (picked.length === 3) break
    if (!picked.includes(model.id)) picked.push(model.id)
  }

  const [logic, emotion, twist] = picked.length >= 3
    ? picked
    : [preferred[0]?.id, preferred[1]?.id ?? preferred[0]?.id, preferred[2]?.id ?? preferred[0]?.id]

  if (!logic || !emotion || !twist) return null
  return { logic, emotion, twist }
}

export function normalizeAssignment(
  assignment: StoryLiveModelAssignment | null,
  appStore: ReturnType<typeof useAppStore>,
) {
  if (!assignment) return chooseModelIds(appStore)

  const ids = [assignment.logic, assignment.emotion, assignment.twist]
  if (ids.every((id) => appStore.getModel(id))) return assignment
  return chooseModelIds(appStore)
}

// --- Envelope construction ---

function createMeta(premise: string): StoryLiveSessionMeta {
  return {
    premise,
    modelAssignment: null,
    latestDirectorCue: null,
    directorMemory: [],
    wrapResult: null,
    phase: 'premise' as StoryLivePhase,
    storyState: createInitialState(premise),
    lastTwistRound: 0,
    validationWarnings: [],
  }
}

export function createEnvelope(premise = CURRENT_PROMISE): PlayModeSessionEnvelope {
  const now = isoNow()
  return {
    schemaVersion: PLAY_MODE_SCHEMA_VERSION,
    mode: 'story-live',
    sessionId: uid(),
    status: 'pending',
    round: 0,
    startedAt: now,
    updatedAt: now,
    seed: {
      id: 'story-live-opening',
      label: '剧情开场',
      payload: { premise },
    },
    summary: null,
    ending: null,
    history: [],
    pauseState: null,
    cache: null,
    meta: createMeta(premise) as unknown as Record<string, unknown>,
  }
}

export function getMeta(envelope: PlayModeSessionEnvelope): StoryLiveSessionMeta {
  return envelope.meta as unknown as StoryLiveSessionMeta
}

// --- History / memory building ---

function summarizeChunk(turns: StoryLiveTurn[], fromRound: number): StoryLiveDirectorMemory {
  const logicBeat = toPlainText(turns.map((turn) => turn.responses.logic.text).join(' '), 120)
  const emotionBeat = toPlainText(turns.map((turn) => turn.responses.emotion.text).join(' '), 88)
  const twistBeat = toPlainText(turns.map((turn) => turn.responses.twist.text).join(' '), 88)
  const userBeat = turns.map((turn) => turn.userText).join(' / ')

  return {
    id: `memory-${fromRound}-${fromRound + turns.length - 1}`,
    fromRound,
    toRound: fromRound + turns.length - 1,
    summary: [
      `第 ${fromRound}-${fromRound + turns.length - 1} 轮：用户依次做了 ${userBeat}。`,
      logicBeat ? `主镜头推进到：${logicBeat}` : '',
      emotionBeat ? `情绪暗流：${emotionBeat}` : '',
      twistBeat ? `异动信号：${twistBeat}` : '',
    ].filter(Boolean).join(' '),
  }
}

export function buildDirectorMemory(turns: StoryLiveTurn[]) {
  if (turns.length <= RECENT_TURN_WINDOW) return []

  const archived = turns.slice(0, Math.max(0, turns.length - RECENT_TURN_WINDOW))
  const result: StoryLiveDirectorMemory[] = []

  for (let index = 0; index < archived.length; index += MEMORY_CHUNK_SIZE) {
    const chunk = archived.slice(index, index + MEMORY_CHUNK_SIZE)
    if (!chunk.length) continue
    result.push(summarizeChunk(chunk, index + 1))
  }

  return result
}

export function buildHistoryEntry(turn: StoryLiveTurn, round: number): HistoryEntry {
  const logicBeat = toPlainText(turn.responses.logic.text, 84)
  const cue = extractDirectorCue(turn.responses.logic.text)

  return {
    id: `story-live-${turn.id}`,
    round,
    type: 'story_turn',
    createdAt: new Date(turn.createdAt).toISOString(),
    title: cue || '剧情继续推进',
    summary: logicBeat
      ? `你选择"${turn.userText}"，随后 ${logicBeat}`
      : `你选择"${turn.userText}"，故事继续往前推进。`,
    payload: {
      userText: turn.userText,
      directorCue: cue,
      logic: turn.responses.logic.text,
      emotion: turn.responses.emotion.text,
      twist: turn.responses.twist.text,
    },
    tags: ['story-live'],
  }
}

export function buildSummary(envelope: PlayModeSessionEnvelope, turns: StoryLiveTurn[]): SessionSummary | null {
  if (!turns.length) return null

  const meta = getMeta(envelope)
  const latestTurn = turns.at(-1)
  const brief = meta.latestDirectorCue || toPlainText(latestTurn?.responses.logic.text || '', 96)

  return {
    headline: meta.premise,
    brief: brief || '故事还停在一个可继续接戏的节点。',
    bullets: [
      `共演 ${turns.length} 轮`,
      meta.wrapResult ? `已生成${meta.wrapResult.mode === 'story' ? '故事' : '剧本'}草案` : '尚未收束',
    ],
    payload: {
      latestUserText: latestTurn?.userText || '',
      latestDirectorCue: meta.latestDirectorCue || '',
    },
  }
}

// --- Migration ---

export function normalizeRecord(
  record: StoryLiveSessionRecord,
  appStore: ReturnType<typeof useAppStore>,
): StoryLiveSessionRecord {
  const envelope = record.envelope
  const meta = getMeta(envelope)
  const premise = meta.premise || CURRENT_PROMISE

  // Migration: ensure new fields exist on meta
  // meta is typed as StoryLiveSessionMeta but runtime data may be from older versions
  const rawPhase = meta.phase
  const rawState = meta.storyState

  const normalizedMeta: StoryLiveSessionMeta = {
    ...meta,
    premise,
    phase: isValidPhase(rawPhase) ? rawPhase : ('live' as StoryLivePhase),
    storyState: rawState
      ? {
          ...rawState,
          tensionHistory: Array.isArray(rawState.tensionHistory) ? rawState.tensionHistory : [],
        }
      : createInitialState(premise),
    lastTwistRound: meta.lastTwistRound ?? 0,
    validationWarnings: meta.validationWarnings || [],
  }

  const rawTurns = Array.isArray(record.turns) ? record.turns : []
  const turns = rawTurns.map((turn) => {
    const next = cloneForStorage(turn)
    ;(['logic', 'emotion', 'twist'] as StoryLiveRole[]).forEach((role) => {
      if (next.responses[role].status === 'generating') {
        next.responses[role].status = 'error'
        next.responses[role].error = '会话中断，已使用恢复文案'
        next.responses[role].text = next.responses[role].text || buildStoryLiveFallback(role, premise)
      }
    })
    return next
  })

  const wrapResult = normalizedMeta.wrapResult?.status === 'generating'
    ? {
        ...normalizedMeta.wrapResult,
        status: 'error' as const,
        error: '会话中断，已恢复上次草稿',
        text: normalizedMeta.wrapResult.text || buildStoryLiveWrapFallback(normalizedMeta.wrapResult.mode, premise, turns),
        updatedAt: Date.now(),
      }
    : normalizedMeta.wrapResult

  envelope.meta = {
    ...normalizedMeta,
    modelAssignment: normalizeAssignment(normalizedMeta.modelAssignment, appStore),
    latestDirectorCue: turns.at(-1) ? extractDirectorCue(turns.at(-1)!.responses.logic.text) : normalizedMeta.latestDirectorCue,
    directorMemory: buildDirectorMemory(turns),
    wrapResult: wrapResult ?? null,
  }
  envelope.round = turns.length
  envelope.history = turns.map((turn, index) => buildHistoryEntry(turn, index + 1))
  envelope.summary = buildSummary(envelope, turns)
  envelope.updatedAt = isoNow()

  return {
    envelope,
    turns,
    draftInput: record.draftInput || '',
  }
}
