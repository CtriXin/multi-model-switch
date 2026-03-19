import type { EndingGrade } from '../shared'
import type { StoryLiveStoryState } from './types'

/** High-risk keywords that trigger twist on user input */
/** High-confidence triggers — can fire alone */
export const TWIST_HIGH_CONFIDENCE = [
  '枪', '血', '炸弹', '尸体', '凶器', '绑架', '谋杀',
]

/** Soft triggers — need a second signal (tension ≥ 3) to activate */
export const TWIST_SOFT_TRIGGERS = [
  '突然', '追', '逃', '质问', '暴怒', '尖叫',
  '崩溃', '威胁', '刀', '埋伏', '陷阱', '背叛',
  '暗算', '失踪',
]

const ENDING_KEYWORDS = ['故事结束', '就这样吧', '收束', '到此为止', '落幕', '结局']

const TWIST_COOLDOWN = 4
const STAGNATION_THRESHOLD = 3

export interface TwistCheckResult {
  shouldTrigger: boolean
  reason?: string
}

export function shouldTriggerTwist(
  userText: string,
  currentRound: number,
  lastTwistRound: number,
  storyState: StoryLiveStoryState,
): TwistCheckResult {
  // Priority 1: user-triggered keywords (two-tier)
  const userHit = checkUserTrigger(userText, storyState.tension)
  if (userHit) {
    return { shouldTrigger: true, reason: `keyword: "${userHit}"` }
  }

  // Priority 2: stagnation detection
  if (storyState.roundsSinceChange >= STAGNATION_THRESHOLD) {
    return { shouldTrigger: true, reason: 'stagnation' }
  }

  // Priority 3: round-based cooldown
  if (currentRound - lastTwistRound >= TWIST_COOLDOWN) {
    return { shouldTrigger: true, reason: 'cooldown_elapsed' }
  }

  return { shouldTrigger: false }
}

export function checkUserTrigger(userText: string, tension: number): string | null {
  // High-confidence: fires unconditionally
  for (const kw of TWIST_HIGH_CONFIDENCE) {
    if (userText.includes(kw)) return kw
  }
  // Soft triggers: require tension ≥ 3
  if (tension >= 3) {
    for (const kw of TWIST_SOFT_TRIGGERS) {
      if (userText.includes(kw)) return kw
    }
  }
  return null
}

export function detectEndingIntent(userText: string): boolean {
  const trimmed = userText.trim()
  for (const kw of ENDING_KEYWORDS) {
    if (trimmed.includes(kw)) return true
  }
  return false
}

export function detectEndingGrade(
  totalRounds: number,
  tension: number,
  unresolved: string[],
  tensionHistory: number[],
): EndingGrade {
  const unresolvedCount = unresolved.length
  const hasTensionArc = detectTensionArc(tensionHistory)

  // Optimal: long session, tension arc resolved, most clues resolved
  if (totalRounds >= 10 && hasTensionArc && unresolvedCount <= 1) {
    return 'optimal'
  }

  // Hidden: long session, high tension, many unresolved clues
  if (totalRounds >= 12 && tension >= 4 && unresolvedCount >= 3) {
    return 'hidden'
  }

  // Failure: user-initiated end with high tension
  if (tension >= 4) {
    return 'failure'
  }

  // Normal: default
  return 'normal'
}

function detectTensionArc(history: number[]): boolean {
  if (history.length < 6) return false
  const peak = Math.max(...history)
  if (peak < 4) return false
  // Relaxed: at least 2 of last 3 rounds must drop below peak - 1
  const last3 = history.slice(-3)
  const dropped = last3.filter((t) => t < peak - 1).length
  return dropped >= 2
}
