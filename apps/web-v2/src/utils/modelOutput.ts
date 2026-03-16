export interface SanitizedModelOutput {
  content: string
  hiddenThink: boolean
}

const THINK_BLOCK_RE = /<think>[\s\S]*?<\/think>/gi
const THINK_OPEN_RE = /<think>[\s\S]*$/i
const THINK_CLOSE_ONLY_RE = /<\/think>/gi
const MD_FENCE_RE = /^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$/i

export function sanitizeModelOutput(raw: string): SanitizedModelOutput {
  if (!raw) return { content: '', hiddenThink: false }

  let hiddenThink = false
  let content = raw

  if (THINK_BLOCK_RE.test(content) || THINK_OPEN_RE.test(content) || THINK_CLOSE_ONLY_RE.test(content)) {
    hiddenThink = true
  }

  content = content
    .replace(THINK_BLOCK_RE, '')
    .replace(THINK_OPEN_RE, '')
    .replace(THINK_CLOSE_ONLY_RE, '')
    .trim()

  const fenced = content.match(MD_FENCE_RE)
  if (fenced) {
    content = fenced[1].trim()
  }

  return {
    content,
    hiddenThink,
  }
}
