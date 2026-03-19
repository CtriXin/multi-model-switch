import type { Puzzle } from './types'
import { SAFE_FALLBACKS, GENERIC_LEAK_PATTERNS } from './constants'

export interface LeakGuardResult {
  safe: boolean
  replacement?: string
}

/**
 * Local keyword-based leak guard check.
 * Runs zero API calls — purely client-side keyword matching.
 */
export function leakGuardCheck(
  answer: string,
  puzzle: Puzzle,
): LeakGuardResult {
  // Check puzzle-specific truth keywords
  for (const kw of puzzle.truthKeywords) {
    if (answer.includes(kw)) {
      const tag = extractTag(answer)
      const pool = SAFE_FALLBACKS[tag] || SAFE_FALLBACKS.yes_and_no
      return {
        safe: false,
        replacement: pool[Math.floor(Math.random() * pool.length)],
      }
    }
  }

  // Check generic leak patterns
  for (const pattern of GENERIC_LEAK_PATTERNS) {
    if (pattern.test(answer)) {
      return {
        safe: false,
        replacement: '换个方向想想？',
      }
    }
  }

  return { safe: true }
}

function extractTag(answer: string): string {
  if (answer.includes('不是') && answer.includes('是')) return 'yes_and_no'
  if (answer.includes('接近了')) return 'close'
  if (answer.startsWith('是。') || answer === '是') return 'yes'
  if (answer.startsWith('无关')) return 'irrelevant'
  return 'no'
}
