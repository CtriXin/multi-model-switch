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

  // Use fresh regexes for .test() to avoid global-flag lastIndex issues
  if (/<think>[\s\S]*?<\/think>/i.test(content) || /<think>[\s\S]*$/i.test(content) || /<\/think>/i.test(content)) {
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
