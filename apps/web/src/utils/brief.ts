import type { Brief } from '@mms/contracts'

/**
 * Extract BRIEF structure from model response content
 * BRIEF format:
 * <BRIEF>
 * Approach: ...
 * Reasoning: ...
 * Risks: ...
 * Key Decisions: ...
 * Next Step: ...
 * </BRIEF>
 */
export function extractBrief(content: string): Brief | null {
  const match = content.match(/<BRIEF>([\s\S]*?)<\/BRIEF>/i)
  if (!match) return null

  const briefText = match[1]

  const approach = extractField(briefText, 'Approach')
  const reasoning = extractField(briefText, 'Reasoning')
  const risks = extractListField(briefText, 'Risks')
  const keyDecisions = extractListField(briefText, 'Key Decisions')
  const nextStep = extractField(briefText, 'Next Step')

  return {
    approach: approach || '',
    reasoning: reasoning || '',
    risks,
    keyDecisions,
    nextStep: nextStep || '',
  }
}

function extractField(text: string, field: string): string | null {
  const regex = new RegExp(`${field}:\\s*([^\\n]+)`, 'i')
  const match = text.match(regex)
  return match ? match[1].trim() : null
}

function extractListField(text: string, field: string): string[] {
  const regex = new RegExp(`${field}:\\s*([\\s\\S]*?)(?=\\n[A-Z]|$)`, 'i')
  const match = text.match(regex)
  if (!match) return []

  return match[1]
    .split(/[\n,]/)
    .map(s => s.trim())
    .filter(s => s && !s.startsWith('-'))
    .map(s => s.replace(/^-\s*/, ''))
}

/**
 * Extract display text (content without BRIEF block)
 */
export function extractDisplayText(content: string): string {
  return content.replace(/<BRIEF>[\s\S]*?<\/BRIEF>/gi, '').trim()
}

/**
 * Extract both brief and display text
 */
export function extractBriefWithDisplay(content: string): {
  brief: Brief | null
  displayText: string
} {
  return {
    brief: extractBrief(content),
    displayText: extractDisplayText(content),
  }
}
