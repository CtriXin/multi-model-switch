import type { HostTag } from './types'

export const MAX_ROUNDS = 25
export const HOST_RETRY_LIMIT = 2
export const MAX_HINTS = 3
export const HOST_REVEALED_SUMMARY_LENGTH = 5

export const SAFE_FALLBACKS: Record<string, string[]> = {
  yes_and_no: [
    '是也不是。你漏掉了一个关键点。',
    '是也不是。再仔细想想你刚才说的。',
    '是也不是。方向对了，但还差一步。',
  ],
  no: [
    '不是。换个方向想想？',
    '不是。但你的思路有意思。',
    '不是。试着换个角度提问。',
  ],
  irrelevant: [
    '无关。试试从其他角度提问。',
    '无关。不过这个问题挺有意思。',
    '无关。这条线索暂时走不通。',
  ],
  close: [
    '接近了。但你还需要再想深一层。',
    '接近了。再追问一个关键问题。',
  ],
  yes: [
    '是。沿着这个方向继续问下去。',
    '是。你已经摸到边了，继续。',
  ],
}

export function pickFallback(hostTag: HostTag): string {
  const pool = SAFE_FALLBACKS[hostTag] || SAFE_FALLBACKS.yes_and_no
  return pool[Math.floor(Math.random() * pool.length)]
}

export const PROMPT_VERSIONS = {
  host: 'v1.0',
  verifier: 'v1.0',
  leakGuard: 'v1.0',
  hintReveal: 'v1.0',
  recapGenerator: 'v1.0',
} as const

export const GENERIC_LEAK_PATTERNS: RegExp[] = [
  /答案是?/i,
  /真相是?/i,
  /其实.*就是/i,
  /秘密就是/i,
  /结果是因为/i,
  /原来是因为/i,
]
