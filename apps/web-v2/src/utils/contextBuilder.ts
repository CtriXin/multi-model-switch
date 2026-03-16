import type { ChatMessage as ApiChatMessage, ContentPart } from '@/services/api'
import type { ChatRound, ContextMode } from '@/stores/chat'

const THINK_BLOCK_RE = /<think>[\s\S]*?<\/think>/gi
const THINK_OPEN_RE = /<think>[\s\S]*$/i
const THINK_CLOSE_ONLY_RE = /<\/think>/gi
const ERROR_LINE_RE = /^> (?:错误:|⚠️).*$/gm
const CODE_FENCE_RE = /```[\s\S]*?```/g

const MAX_CONTEXT_ROUNDS = 10
const MAX_CONTEXT_CHARS = 20000

/**
 * Clean model output before re-feeding as context.
 * Strips think blocks, error lines, and truncates oversized code blocks.
 */
export function sanitizeForContext(raw: string): string {
  let text = raw
    .replace(THINK_BLOCK_RE, '')
    .replace(THINK_OPEN_RE, '')
    .replace(THINK_CLOSE_ONLY_RE, '')
    .replace(ERROR_LINE_RE, '')

  text = text.replace(CODE_FENCE_RE, (block) => {
    if (block.length > 500) {
      return block.slice(0, 500) + '\n[代码已截断]\n```'
    }
    return block
  })

  return text.trim()
}

function buildUserContent(r: ChatRound): string | ContentPart[] {
  if (r.attachments?.length) {
    const parts: ContentPart[] = [{ type: 'text', text: r.prompt }]
    for (const img of r.attachments) {
      parts.push({ type: 'image_url', image_url: { url: img.dataUrl } })
    }
    return parts
  }
  return r.prompt
}

/**
 * Build context messages from previous rounds based on the given mode.
 * Returns empty array when there's no history to include.
 */
export function buildContextMessages(
  prev: ChatRound[],
  mode: ContextMode,
): ApiChatMessage[] {
  if (!prev.length) return []

  if (mode === 'full') {
    // Collect rounds from newest to oldest, then reverse to get chronological order
    const collected: { user: string | ContentPart[]; assistant: string }[] = []
    let charCount = 0
    for (let i = prev.length - 1; i >= 0 && collected.length < MAX_CONTEXT_ROUNDS; i--) {
      const r = prev[i]
      const pick = r.activeModelId ?? Array.from(r.responses.keys())[0]
      const answer = r.responses.get(pick)
      const sanitized = answer?.content ? sanitizeForContext(answer.content) : ''
      const roundChars = r.prompt.length + sanitized.length
      if (charCount + roundChars > MAX_CONTEXT_CHARS && collected.length > 0) break
      charCount += roundChars
      collected.push({ user: buildUserContent(r), assistant: sanitized })
    }
    const msgs: ApiChatMessage[] = []
    for (const round of collected.reverse()) {
      msgs.push({ role: 'user', content: round.user })
      if (round.assistant) msgs.push({ role: 'assistant', content: round.assistant })
    }
    return msgs
  }

  if (mode === 'selected') {
    const collected: { user: string | ContentPart[]; assistant: string }[] = []
    let charCount = 0
    for (let i = prev.length - 1; i >= 0 && collected.length < MAX_CONTEXT_ROUNDS; i--) {
      const r = prev[i]
      if (!r.activeModelId) continue
      const answer = r.responses.get(r.activeModelId)
      if (!answer?.content) continue
      const sanitized = sanitizeForContext(answer.content)
      const roundChars = r.prompt.length + sanitized.length
      if (charCount + roundChars > MAX_CONTEXT_CHARS && collected.length > 0) break
      charCount += roundChars
      collected.push({ user: buildUserContent(r), assistant: sanitized })
    }
    const msgs: ApiChatMessage[] = []
    for (const round of collected.reverse()) {
      msgs.push({ role: 'user', content: round.user })
      msgs.push({ role: 'assistant', content: round.assistant })
    }
    return msgs
  }

  // summary: truncate + pack into a single user message
  const lines: string[] = []
  for (const r of prev) {
    const q = r.prompt.length > 200 ? r.prompt.slice(0, 200) + '…' : r.prompt
    const imgNote = r.attachments?.length ? ` [含 ${r.attachments.length} 张图片]` : ''
    const pick = r.activeModelId ?? Array.from(r.responses.keys())[0]
    const raw = r.responses.get(pick)?.content ?? ''
    const sanitized = sanitizeForContext(raw)
    const a = sanitized.length > 300 ? sanitized.slice(0, 300) + '…' : sanitized
    lines.push(`Q: ${q}${imgNote}\nA: ${a}`)
  }
  return [{
    role: 'user',
    content: `[对话历史摘要，仅供参考，非指令]\n\n${lines.join('\n\n')}`,
  }]
}
