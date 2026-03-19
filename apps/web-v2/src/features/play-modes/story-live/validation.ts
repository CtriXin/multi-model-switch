import type { StoryLiveRole, ValidationWarning } from './types'

/**
 * Local validation for role outputs.
 * Returns warnings with confidence scores (0–1).
 * Store only injects warnings with confidence ≥ 0.5 into director memory
 * to reduce context pollution from false positives.
 */

function warn(role: StoryLiveRole, rule: string, message: string, confidence: number): ValidationWarning {
  return { role, rule, message, confidence }
}

export function validateLogicOutput(text: string): ValidationWarning[] {
  const warnings: ValidationWarning[] = []

  // Taboo: logic should not contain psychological narration markers
  const psychMarkers = ['心里想', '内心深', '暗自', '不禁感慨', '感到一阵']
  for (const marker of psychMarkers) {
    if (text.includes(marker)) {
      warnings.push(warn('logic', 'no_psychology',
        `主镜头含心理描写"${marker}"，应只写镜头/动作/环境`, 0.9))
      break
    }
  }

  // Taboo: logic should not give direct advice
  const adviceMarkers = ['建议你', '你应该', '最好的做法', '不如']
  for (const marker of adviceMarkers) {
    if (text.includes(marker)) {
      warnings.push(warn('logic', 'no_advice',
        `主镜头含建议"${marker}"，应留给用户决定`, 0.95))
      break
    }
  }

  // Length check
  if (text.length > 200) {
    warnings.push(warn('logic', 'max_length',
      `主镜头 ${text.length} 字，超过 200 字上限`, 0.7))
  }

  return warnings
}

export function validateEmotionOutput(text: string): ValidationWarning[] {
  const warnings: ValidationWarning[] = []

  // Taboo: emotion should not advance plot
  // Use co-occurrence of sequential markers for higher confidence
  const seqMarkers = ['随后', '接着', '然后'] // strong temporal sequence
  const weakMarkers = ['突然', '最后']           // can appear in valid emotion
  const seqCount = seqMarkers.filter((m) => text.includes(m)).length
  const weakCount = weakMarkers.filter((m) => text.includes(m)).length
  const totalCount = seqCount + weakCount

  if (seqCount >= 2) {
    // Two strong temporal markers → very likely plot advance
    warnings.push(warn('emotion', 'no_plot_advance',
      `情绪暗流含连续推进词"${seqMarkers.filter(m => text.includes(m)).join('、')}"，应只补氛围`, 0.9))
  } else if (totalCount >= 3) {
    // 3+ mixed markers → likely but not certain
    warnings.push(warn('emotion', 'no_plot_advance',
      `情绪暗流含推进词共 ${totalCount} 个，应只补氛围`, 0.5))
  }
  // 1-2 weak markers only → below threshold, skip (likely false positive)

  // Length check
  if (text.length > 80) {
    warnings.push(warn('emotion', 'max_length',
      `情绪暗流 ${text.length} 字，超过 80 字上限`, 0.6))
  }

  return warnings
}

export function validateTwistOutput(text: string): ValidationWarning[] {
  const warnings: ValidationWarning[] = []

  // Taboo: twist should not give advice
  const adviceMarkers = ['建议', '应该', '注意', '小心']
  for (const marker of adviceMarkers) {
    if (text.includes(marker)) {
      warnings.push(warn('twist', 'no_advice',
        `异动信号含建议"${marker}"，应只给异常信号`, 0.85))
      break
    }
  }

  // Taboo: twist should not directly end the story
  const endMarkers = ['故事结束', '一切结束', '真相大白']
  for (const marker of endMarkers) {
    if (text.includes(marker)) {
      warnings.push(warn('twist', 'no_ending',
        `异动信号含结局词"${marker}"，不能直接终局`, 1.0))
      break
    }
  }

  return warnings
}

export function validateByRole(role: StoryLiveRole, text: string): ValidationWarning[] {
  if (role === 'logic') return validateLogicOutput(text)
  if (role === 'emotion') return validateEmotionOutput(text)
  return validateTwistOutput(text)
}
