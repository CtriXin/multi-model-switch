import type { Puzzle, ValidationError } from '../types'

/**
 * Validate a puzzle's internal consistency.
 * Returns an array of validation errors/warnings.
 */
export function validatePuzzle(puzzle: Puzzle): ValidationError[] {
  const errors: ValidationError[] = []

  // Rule 1: solveKeywords must be substrings of truthKeywords
  for (const kw of puzzle.solveKeywords) {
    const covered = puzzle.truthKeywords.some(
      tk => tk.includes(kw) || kw.includes(tk),
    )
    if (!covered) {
      errors.push({
        rule: 'solve-keyword-coverage',
        message: `solveKeyword "${kw}" 不在 truthKeywords 中，玩家命中后无法触发通关`,
        severity: 'error',
      })
    }
  }

  // Rule 2: clues.text must not contain truthKeywords
  for (const clue of puzzle.clues) {
    for (const kw of puzzle.truthKeywords) {
      if (clue.text.includes(kw)) {
        errors.push({
          rule: 'clue-keyword-leak',
          message: `线索 ${clue.id} 的 text 直接包含真相关键词 "${kw}"，可能泄底`,
          severity: 'error',
        })
      }
    }
  }

  // Rule 3: hints.text must not contain truthKeywords
  for (const hint of puzzle.hints) {
    for (const kw of puzzle.truthKeywords) {
      if (hint.text.includes(kw)) {
        errors.push({
          rule: 'hint-keyword-leak',
          message: `Level ${hint.level} 提示直接包含真相关键词 "${kw}"，可能泄底`,
          severity: 'error',
        })
      }
    }
  }

  // Rule 4: misleads.direction should not contain truthKeywords
  for (const m of puzzle.misleads) {
    for (const kw of puzzle.truthKeywords) {
      if (m.direction.includes(kw)) {
        errors.push({
          rule: 'mislead-keyword-leak',
          message: `误导方向 "${m.direction}" 包含真相关键词 "${kw}"`,
          severity: 'warning',
        })
      }
    }
  }

  // Rule 5: hints must start from level 1, no gaps
  const hintLevels = puzzle.hints.map(h => h.level).sort()
  if (hintLevels.length > 0 && hintLevels[0] !== 1) {
    errors.push({
      rule: 'hint-level-start',
      message: '提示必须从 Level 1 开始',
      severity: 'error',
    })
  }
  for (let i = 1; i < hintLevels.length; i++) {
    if (hintLevels[i] - hintLevels[i - 1] > 1) {
      errors.push({
        rule: 'hint-level-gap',
        message: `提示级别跳级：${hintLevels[i - 1]} → ${hintLevels[i]}`,
        severity: 'error',
      })
    }
  }

  // Rule 6: solveThreshold cannot exceed solveKeywords count
  if (puzzle.solveThreshold > puzzle.solveKeywords.length) {
    errors.push({
      rule: 'solve-threshold',
      message: `solveThreshold (${puzzle.solveThreshold}) 超过 solveKeywords 数量 (${puzzle.solveKeywords.length})`,
      severity: 'error',
    })
  }

  // Rule 7: relatedClueIds must reference existing clues
  const clueIds = new Set(puzzle.clues.map(c => c.id))
  for (const hint of puzzle.hints) {
    for (const cid of hint.relatedClueIds) {
      if (!clueIds.has(cid)) {
        errors.push({
          rule: 'hint-clue-ref',
          message: `Level ${hint.level} 提示引用了不存在的线索 ${cid}`,
          severity: 'error',
        })
      }
    }
  }

  return errors
}
