export interface SanitizedModelOutput {
  content: string
  visibleContent: string
  hiddenThink: boolean
  /** Extracted <think> blocks joined */
  thinkText: string
  /** Extracted <BRIEF> blocks joined */
  briefText: string
}

const THINK_BLOCK_RE = /<think>([\s\S]*?)<\/think>/gi
const THINK_OPEN_RE = /<think>([\s\S]*)$/i
const THINK_CLOSE_ONLY_RE = /<\/think>/gi
const BRIEF_BLOCK_RE = /<BRIEF>([\s\S]*?)<\/BRIEF>/gi
const BRIEF_OPEN_RE = /<BRIEF>([\s\S]*)$/i
const BRIEF_CLOSE_ONLY_RE = /<\/BRIEF>/gi
const MD_FENCE_RE = /^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$/i

function extractBlocks(text: string, blockRe: RegExp, openRe: RegExp, closeRe: RegExp): { cleaned: string; extracted: string } {
  const parts: string[] = []

  // Extract complete blocks
  let cleaned = text.replace(blockRe, (_match, inner) => {
    parts.push(inner.trim())
    return ''
  })

  // Extract unclosed open tag (streaming)
  cleaned = cleaned.replace(openRe, (_match, inner) => {
    if (inner.trim()) parts.push(inner.trim())
    return ''
  })

  // Remove orphan close tags
  cleaned = cleaned.replace(closeRe, '')

  return { cleaned, extracted: parts.join('\n\n').trim() }
}

export function sanitizeModelOutput(raw: string): SanitizedModelOutput {
  if (!raw) return { content: '', visibleContent: '', hiddenThink: false, thinkText: '', briefText: '' }

  let content = raw

  const think = extractBlocks(content, THINK_BLOCK_RE, THINK_OPEN_RE, THINK_CLOSE_ONLY_RE)
  content = think.cleaned

  const brief = extractBlocks(content, BRIEF_BLOCK_RE, BRIEF_OPEN_RE, BRIEF_CLOSE_ONLY_RE)
  content = brief.cleaned.trim()

  const fenced = content.match(MD_FENCE_RE)
  if (fenced) {
    content = fenced[1].trim()
  }

  return {
    content,
    visibleContent: content || think.extracted,
    hiddenThink: think.extracted.length > 0,
    thinkText: think.extracted,
    briefText: brief.extracted,
  }
}
