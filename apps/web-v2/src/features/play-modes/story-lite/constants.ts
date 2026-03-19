import type { EndingGrade, HistoryEntryType } from '../shared'

export const STORY_LITE_MODE_ID = 'story-lite'
export const STORY_LITE_PROMPT_VERSION = '1.0.0'
export const STORY_LITE_DEFAULT_SEED = '公路异变悬疑'
export const STORY_LITE_DEFAULT_MAX_ROUNDS = 10

export const STORY_LITE_HISTORY_TYPES: HistoryEntryType[] = [
  'story_turn',
  'special_event',
  'summary_snapshot',
]

export const STORY_LITE_ENDING_GRADES: EndingGrade[] = [
  'failure',
  'normal',
  'hidden',
  'optimal',
]
