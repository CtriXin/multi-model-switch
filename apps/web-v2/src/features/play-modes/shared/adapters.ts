import type {
  EndingGrade,
  HistoryCardViewModel,
  HistoryEntry,
  ResultCardViewModel,
  SessionEnding,
} from './types'

const HISTORY_TYPE_LABELS: Record<HistoryEntry['type'], string> = {
  story_turn: '剧情推进',
  question_round: '提问轮',
  investigation_turn: '调查推进',
  special_event: '关键事件',
  summary_snapshot: '阶段总结',
  ml_round: '证词轮',
}

const ENDING_GRADE_LABELS: Record<EndingGrade, string> = {
  failure: '失败结局',
  normal: '普通结局',
  hidden: '隐藏结局',
  optimal: '最佳结局',
}

function buildRoundLabel(entry: HistoryEntry) {
  return `第 ${entry.round} 轮`
}

export function toHistoryCardViewModel(entry: HistoryEntry): HistoryCardViewModel {
  return {
    id: entry.id,
    roundLabel: buildRoundLabel(entry),
    typeLabel: HISTORY_TYPE_LABELS[entry.type],
    summary: entry.summary,
    badges: entry.tags ?? [],
  }
}

export function toResultCardViewModel(
  ending: SessionEnding,
  highlights: string[] = [],
): ResultCardViewModel {
  return {
    title: `${ENDING_GRADE_LABELS[ending.grade]} · ${ending.title}`,
    grade: ending.grade,
    summary: ending.summary,
    highlights,
  }
}
