/**
 * Unified API layer for OpenRouter / OpenAI-compatible providers.
 * Handles streaming chat completions and model listing.
 */

import type { ProviderConfig } from '@/stores/provider'
import type { ModelMeta } from '@/stores/app'
import { resolveModelCapabilities } from '@/config/modelCapabilities'

export type ContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string; detail?: 'auto' | 'low' | 'high' } }

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string | ContentPart[]
}

export interface StreamChatOptions {
  provider: ProviderConfig
  apiKey: string
  model: string
  messages: ChatMessage[]
  signal?: AbortSignal
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public details?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function extractApiErrorDetail(body: string): string {
  if (!body) return ''
  try {
    const parsed = JSON.parse(body)
    const detail =
      parsed?.error?.message
      ?? parsed?.message
      ?? parsed?.detail
      ?? parsed?.errors?.[0]?.message
      ?? parsed?.errors?.[0]?.detail
    if (typeof detail === 'string') return detail
  } catch {
    // Fall back to the raw response body.
  }
  return body
}

function buildApiError(status: number, body: string): ApiError {
  const detail = extractApiErrorDetail(body).trim()
  const lower = detail.toLowerCase()

  if (status === 401) {
    return new ApiError('API Key 无效，请检查配置', status, 'invalid_key', detail)
  }

  if (status === 429) {
    return new ApiError('该模型触发频率或额度限制，今天先别再测它了', status, 'rate_limited', detail)
  }

  // Image-input 404 — model exists but doesn't support images; NOT model_unavailable
  if (
    (status === 404 || status === 400)
    && /no endpoints found that support image|does not support image|image.*(not|un).*support/i.test(lower)
  ) {
    return new ApiError('该模型不支持图片输入，已自动降级为纯文本', status, 'image_unsupported', detail)
  }

  if (
    status === 400
    && /does not support chat completions|chat completions.*not support|not support.*chat|unsupported.*chat/i.test(lower)
  ) {
    return new ApiError('该模型不支持聊天对话接口，请换模型重试', status, 'chat_unsupported', detail)
  }

  if (
    status === 404
    || /no endpoints found|model .*not found|does not exist|not available|temporarily unavailable/.test(lower)
  ) {
    return new ApiError('模型当前不可用，已建议临时隐藏', status, 'model_unavailable', detail)
  }

  if (
    status === 400
    && /maximum context length|context length|context window|too many tokens|prompt is too long|reduce the length/.test(lower)
  ) {
    return new ApiError('上下文过长，免费模型通常更容易超长，请缩短输入或减少历史后重试', status, 'context_too_long', detail)
  }

  return new ApiError(
    `API 请求失败 (${status}): ${(detail || '未知错误').slice(0, 200)}`,
    status,
    status === 400 ? 'request_invalid' : 'request_failed',
    detail,
  )
}

/**
 * Stream chat completions from an OpenAI-compatible endpoint.
 * Yields text chunks as they arrive.
 */
export async function* streamChat(options: StreamChatOptions): AsyncGenerator<string> {
  const { provider, apiKey, model, messages, signal } = options

  // Mock provider — simulate streaming without network
  if (provider.type === 'mock') {
    yield* mockStreamChat(model, messages, signal)
    return
  }

  // Strip provider prefix for non-OpenRouter providers
  // e.g. "deepseek/deepseek-chat" → "deepseek-chat"
  const apiModel = provider.type === 'openrouter' ? model : stripProviderPrefix(model, provider.id)

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${apiKey}`,
  }

  // OpenRouter-specific headers
  if (provider.type === 'openrouter') {
    headers['HTTP-Referer'] = globalThis.location?.origin ?? 'https://mms.app'
    headers['X-Title'] = 'MMS Pro'
  }

  const res = await fetch(`${provider.baseUrl}/chat/completions`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      model: apiModel,
      messages,
      stream: true,
    }),
    signal,
  })

  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw buildApiError(res.status, body)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new ApiError('响应体为空', 0)

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    // Keep the last incomplete line in buffer
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || trimmed === 'data: [DONE]') continue
      if (!trimmed.startsWith('data: ')) continue

      try {
        const json = JSON.parse(trimmed.slice(6))
        const content = json.choices?.[0]?.delta?.content
        if (content) yield content
      } catch {
        // Skip malformed SSE lines
      }
    }
  }
}

/** Raw model entry from the API */
interface ApiModel {
  id: string
  name?: string
  context_length?: number
  pricing?: {
    prompt?: string
    completion?: string
  }
  architecture?: {
    modality?: string
  }
  top_provider?: {
    is_moderated?: boolean
  }
}

const ALWAYS_FREE_PROVIDER_IDS = new Set([
  'groq',
  'google',
  'cerebras',
  'demo',
])

/**
 * Strip the provider prefix from a compound model ID.
 * "deepseek/deepseek-chat" → "deepseek-chat"
 * OpenRouter IDs like "anthropic/claude-sonnet-4" are kept as-is.
 */
function stripProviderPrefix(compoundId: string, providerId: string): string {
  const prefix = providerId + '/'
  return compoundId.startsWith(prefix) ? compoundId.slice(prefix.length) : compoundId
}

/**
 * Fetch available models from a provider.
 * Maps the response to ModelMeta format.
 * Falls back to customModels if the /models endpoint fails or is not available.
 */
export async function fetchModels(
  provider: ProviderConfig,
  apiKey: string,
): Promise<ModelMeta[]> {
  // Mock provider — return static model list
  if (provider.type === 'mock') {
    return MOCK_MODELS
  }

  let apiModels: ModelMeta[] = []
  let fetchFailed = false

  try {
    const headers: Record<string, string> = {
      'Authorization': `Bearer ${apiKey}`,
    }

    const res = await fetch(`${provider.baseUrl}/models`, {
      headers,
    })

    if (!res.ok) {
      if (res.status === 401) {
        throw new ApiError('API Key 无效', res.status, 'invalid_key')
      }
      fetchFailed = true
    } else {
      const json = await res.json()
      const rawModels: ApiModel[] = json.data ?? json

      apiModels = rawModels
        .filter((m) => {
          // Filter by provider's model whitelist if set
          if (provider.models?.length) {
            return provider.models.some(
              (pattern) => m.id === pattern || m.id.startsWith(pattern),
            )
          }
          return true
        })
        .map((m) => mapToModelMeta(m, provider))
        .sort((a, b) => b.tier - a.tier || a.name.localeCompare(b.name))
    }
  } catch (e) {
    if (e instanceof ApiError) throw e
    fetchFailed = true
  }

  // Add custom (manually added) models that aren't already in API results
  if (provider.customModels?.length) {
    const existingIds = new Set(apiModels.map(m => m.id))
    for (const modelId of provider.customModels) {
      const compoundId = provider.type === 'openrouter' ? modelId : `${provider.id}/${modelId}`
      if (!existingIds.has(compoundId)) {
        apiModels.push({
          id: compoundId,
          name: modelId,
          provider: provider.id,
          category: deriveCategory({ id: modelId }),
          tier: 0,
          priceInput: 0,
          priceOutput: 0,
          tags: ['general'],
          contextWindow: 4096,
          free: false,
          supportsVision: false,
          supportsNativeWebSearch: false,
          supportsTools: false,
          capabilitySource: 'default',
          capabilityVerifiedAt: null,
        })
      }
    }
  }

  if (!apiModels.length && fetchFailed) {
    throw new ApiError(`获取模型列表失败`, 0)
  }

  return apiModels
}

function mapToModelMeta(raw: ApiModel, provider: ProviderConfig): ModelMeta {
  const promptPrice = parseFloat(raw.pricing?.prompt ?? '0') * 1_000_000
  const completionPrice = parseFloat(raw.pricing?.completion ?? '0') * 1_000_000

  // For OpenRouter, IDs already have provider prefix (e.g. "anthropic/claude-sonnet-4")
  // For other providers, prefix with provider.id to avoid collisions
  const id = provider.type === 'openrouter' ? raw.id : `${provider.id}/${raw.id}`
  // OpenRouter models: provider is always 'openrouter' (the actual API source)
  const providerName = provider.type === 'openrouter' ? 'openrouter' : provider.id

  // Free detection
  const hasExplicitPricing = raw.pricing?.prompt != null || raw.pricing?.completion != null
  const zeroPriced = parseFloat(raw.pricing?.prompt ?? '1') === 0 && parseFloat(raw.pricing?.completion ?? '1') === 0
  const free = provider.type === 'openrouter'
    ? zeroPriced
    : (hasExplicitPricing && zeroPriced) || ALWAYS_FREE_PROVIDER_IDS.has(provider.id)

  // Vision detection
  const supportsVision = deriveSupportsVision(raw, provider)
  const capabilities = resolveModelCapabilities({
    compoundId: id,
    rawModelId: raw.id,
    providerId: provider.id,
    supportsVision,
  })

  return {
    id,
    name: raw.name ?? raw.id,
    provider: providerName,
    category: deriveCategory(raw),
    tier: deriveTier(promptPrice),
    priceInput: Math.round(promptPrice * 100) / 100,
    priceOutput: Math.round(completionPrice * 100) / 100,
    tags: deriveTags(raw),
    contextWindow: raw.context_length ?? 4096,
    free,
    supportsVision: capabilities.supportsVision,
    supportsNativeWebSearch: capabilities.supportsNativeWebSearch,
    supportsTools: capabilities.supportsTools,
    capabilitySource: capabilities.capabilitySource,
    capabilityVerifiedAt: capabilities.capabilityVerifiedAt,
  }
}

function deriveSupportsVision(raw: ApiModel, provider: ProviderConfig): boolean {
  // OpenRouter: use architecture.modality metadata
  if (raw.architecture?.modality?.includes('image')) return true

  const id = raw.id.toLowerCase()

  // Google: Gemini models all support vision
  if (provider.id === 'google' || id.includes('gemini')) return true

  // Heuristic for model names indicating vision support
  if (/-vl\b|vision|4v|vl-|\/vl-/.test(id)) return true

  // Groq: llava models support vision
  if (id.includes('llava')) return true

  return false
}

function deriveProvider(modelId: string): string {
  const prefix = modelId.split('/')[0]
  const map: Record<string, string> = {
    anthropic: 'anthropic',
    openai: 'openai',
    google: 'google',
    'deepseek': 'deepseek',
    'meta-llama': 'meta',
    mistralai: 'mistral',
    qwen: 'qwen',
  }
  return map[prefix] ?? prefix
}

function deriveCategory(raw: ApiModel): string {
  const id = raw.id.toLowerCase()
  if (id.includes('o1') || id.includes('o3') || id.includes('o4') || id.includes('r1')) return 'reasoning'
  if (id.includes('mini') || id.includes('flash') || id.includes('haiku')) return 'fast'
  return 'frontier'
}

function deriveTier(inputPricePerMillion: number): number {
  if (inputPricePerMillion >= 3) return 2 // Premium
  if (inputPricePerMillion >= 0.5) return 1 // Standard
  return 0 // Free/cheap
}

function deriveTags(raw: ApiModel): string[] {
  const tags: string[] = []
  const id = raw.id.toLowerCase()
  const name = (raw.name ?? '').toLowerCase()

  if (id.includes('o1') || id.includes('o3') || id.includes('r1') || name.includes('reason')) {
    tags.push('reasoning')
  }
  if (id.includes('code') || name.includes('code') || name.includes('coding')) {
    tags.push('coding')
  }
  if (raw.architecture?.modality?.includes('image') || name.includes('vision')) {
    tags.push('vision')
  }
  if (id.includes('mini') || id.includes('flash') || id.includes('haiku')) {
    tags.push('fast')
  }
  if (!tags.length) tags.push('general')

  return tags
}

// ─── Mock Provider ───────────────────────────────────────────────

const MOCK_MODELS: ModelMeta[] = [
  { id: 'demo/claude-sonnet-4', name: 'Claude Sonnet 4 (Demo)', provider: 'anthropic', category: 'frontier', tier: 2, priceInput: 3, priceOutput: 15, tags: ['reasoning', 'coding', 'vision', 'recommended'], contextWindow: 200000, free: false, supportsVision: true, supportsNativeWebSearch: false, supportsTools: true, capabilitySource: 'manual', capabilityVerifiedAt: '2026-03-17' },
  { id: 'demo/gpt-4.1', name: 'GPT-4.1 (Demo)', provider: 'openai', category: 'frontier', tier: 2, priceInput: 2, priceOutput: 8, tags: ['reasoning', 'coding', 'vision', 'recommended'], contextWindow: 128000, free: false, supportsVision: true, supportsNativeWebSearch: false, supportsTools: true, capabilitySource: 'manual', capabilityVerifiedAt: '2026-03-17' },
  { id: 'demo/gemini-2.5-pro', name: 'Gemini 2.5 Pro (Demo)', provider: 'google', category: 'frontier', tier: 2, priceInput: 1.25, priceOutput: 5, tags: ['reasoning', 'vision', 'recommended'], contextWindow: 1000000, free: true, supportsVision: true, supportsNativeWebSearch: true, supportsTools: true, capabilitySource: 'manual', capabilityVerifiedAt: '2026-03-17' },
  { id: 'demo/deepseek-r1', name: 'DeepSeek R1 (Demo)', provider: 'deepseek', category: 'reasoning', tier: 1, priceInput: 0.55, priceOutput: 2.2, tags: ['reasoning', 'coding'], contextWindow: 64000, free: false, supportsVision: false, supportsNativeWebSearch: false, supportsTools: true, capabilitySource: 'manual', capabilityVerifiedAt: '2026-03-17' },
  { id: 'demo/qwen-max', name: 'Qwen Max (Demo)', provider: 'qwen', category: 'frontier', tier: 1, priceInput: 0.9, priceOutput: 3.8, tags: ['reasoning', 'coding'], contextWindow: 131072, free: false, supportsVision: false, supportsNativeWebSearch: false, supportsTools: true, capabilitySource: 'manual', capabilityVerifiedAt: '2026-03-17' },
  { id: 'demo/mistral-large', name: 'Mistral Large (Demo)', provider: 'mistral', category: 'reasoning', tier: 1, priceInput: 0.8, priceOutput: 2.8, tags: ['reasoning', 'coding', 'fast'], contextWindow: 32000, free: false, supportsVision: false, supportsNativeWebSearch: false, supportsTools: true, capabilitySource: 'manual', capabilityVerifiedAt: '2026-03-17' },
  { id: 'demo/glm-4.5', name: 'GLM-4.5 (Demo)', provider: 'zhipu', category: 'frontier', tier: 1, priceInput: 0.75, priceOutput: 2.6, tags: ['reasoning', 'fast'], contextWindow: 128000, free: true, supportsVision: false, supportsNativeWebSearch: false, supportsTools: true, capabilitySource: 'manual', capabilityVerifiedAt: '2026-03-17' },
  { id: 'demo/claude-haiku-3.5', name: 'Claude Haiku 3.5 (Demo)', provider: 'anthropic', category: 'fast', tier: 0, priceInput: 0.25, priceOutput: 1.2, tags: ['fast', 'coding'], contextWindow: 200000, free: true, supportsVision: false, supportsNativeWebSearch: false, supportsTools: true, capabilitySource: 'manual', capabilityVerifiedAt: '2026-03-17' },
  { id: 'demo/offline-strategy-agent', name: 'Strategy Agent (Offline Demo)', provider: 'openai', category: 'reasoning', tier: 1, priceInput: 0.6, priceOutput: 2.2, tags: ['reasoning'], contextWindow: 64000, free: true, supportsVision: false, supportsNativeWebSearch: false, supportsTools: false, capabilitySource: 'manual', capabilityVerifiedAt: '2026-03-17' },
  { id: 'demo/throttled-risk-agent', name: 'Risk Agent (Rate Limited Demo)', provider: 'anthropic', category: 'reasoning', tier: 1, priceInput: 0.6, priceOutput: 2.2, tags: ['reasoning'], contextWindow: 64000, free: true, supportsVision: false, supportsNativeWebSearch: false, supportsTools: false, capabilitySource: 'manual', capabilityVerifiedAt: '2026-03-17' },
]

const MOCK_UNAVAILABLE_MODEL_IDS = new Set(['demo/offline-strategy-agent'])
const MOCK_RATE_LIMIT_MODEL_IDS = new Set(['demo/throttled-risk-agent'])
const MOCK_CHAT_TRIGGER = /新对话|chat|普通问答|快速方案/i
const MOCK_COMMITTEE_TRIGGER = /锦囊团|committee|战情会|角色评审/i
const MOCK_JUDGE_TRIGGER = /Risk-Aware Decision Judge|## 决策评估/

function getMockMessageText(message: ChatMessage | undefined): string {
  if (!message) return ''
  if (typeof message.content === 'string') return message.content
  return message.content
    .filter((part): part is Extract<ContentPart, { type: 'text' }> => part.type === 'text')
    .map((part) => part.text)
    .join('\n')
}

function stableIndex(seed: string, size: number): number {
  if (size <= 1) return 0
  let hash = 0
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0
  }
  return hash % size
}

function compactText(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

function extractTopic(text: string): string {
  const cleaned = compactText(text)
  const patterns = [
    /用户的问题是[:：]\s*(.+)$/i,
    /原始问题[:：]\s*(.+)$/i,
    /议题[:：]\s*(.+)$/i,
  ]
  for (const pattern of patterns) {
    const match = cleaned.match(pattern)
    if (match?.[1]) return match[1].slice(0, 48)
  }
  return cleaned.slice(0, 48) || '当前议题'
}

function resolveMockProvider(modelId: string): string {
  if (modelId.includes('claude') || modelId.includes('haiku')) return 'anthropic'
  if (modelId.includes('gemini')) return 'google'
  if (modelId.includes('deepseek')) return 'deepseek'
  if (modelId.includes('qwen')) return 'qwen'
  if (modelId.includes('mistral')) return 'mistral'
  if (modelId.includes('glm')) return 'zhipu'
  return 'openai'
}

function buildGeneralMockResponse(provider: string, prompt: string): string {
  const topic = extractTopic(prompt)
  const providerAngles: Record<string, string[]> = {
    anthropic: ['先收边界。', '先验关键假设。'],
    openai: ['先拿短反馈。', '先定 owner+时限。'],
    google: ['先对齐指标。', '先小流量验证。'],
    deepseek: ['先做假设树。', '先定失败信号。'],
    qwen: ['先可交付。', '先拆成两步。'],
    mistral: ['先并行准备。', '先跑低成本实验。'],
    zhipu: ['先曝露依赖。', '先写约束条件。'],
  }
  const anglePool = providerAngles[provider] ?? providerAngles.openai
  const angle = anglePool[stableIndex(topic + provider, anglePool.length)]

  return [
    '<BRIEF>',
    `结论: 先做小闭环（${topic}）`,
    '风险: 口径偏差',
    '下一步: 3天验证',
    '</BRIEF>',
    '## 结论',
    `围绕“${topic}”，先做小闭环。`,
    '',
    '## 关键点',
    `- 视角：${angle}`,
    '- 指标：转化率 / 错误率 / 时延',
    '',
    '## 动作',
    '1. 先上线最小版本。',
    '2. 只看一个主指标。',
    '3. 失败就回滚。',
    '',
    '## 风险',
    '- 口径不一致会误判。',
    '- 依赖未准备会拖慢。',
  ].join('\n')
}

function buildMockPhase1Response(prompt: string): string {
  const topic = extractTopic(prompt)
  return JSON.stringify({
    approach: `先围绕“${topic}”做最小验证。`,
    reasoning: '先小后大，降低返工。',
    risks: ['口径偏差', '依赖阻塞', '回滚不完整'],
    keyDecisions: ['先上小流量', '先定回滚线'],
    nextStep: '24小时内确认 owner 和指标。',
  }, null, 2)
}

function buildMockPhase2Response(prompt: string): string {
  const topic = extractTopic(prompt)
  const strongestPoint = `优点：围绕“${topic}”能快速对齐目标。`
  const weakestAssumption = '弱点：默认关键假设成立，证据不足。'
  const missingRisk = '遗漏：失败回滚的成本与时长。'
  const betterApproach = '改进：先小流量验证，再扩量。'
  const verdict = '部分接受：方向对，但证据和风控仍不足。'

  return JSON.stringify({
    strongestPoint,
    weakestAssumption,
    missingRisk,
    betterApproach,
    verdict,
    agreement: strongestPoint,
    challenge: weakestAssumption,
    betterOption: betterApproach,
  }, null, 2)
}

function buildMockPhase3Response(prompt: string): string {
  const topic = extractTopic(prompt)
  return [
    '## 综合结论',
    `围绕“${topic}”，先验证再扩面。`,
    '',
    '### 核心共识',
    '- 先小流量验证。',
    '- 指标统一后再推进。',
    '- 必须可回滚。',
    '',
    '### 分歧与取舍',
    '- 分歧在速度与稳健。',
    '- 当前优先稳健。',
    '',
    '### 建议行动计划',
    '1. 先定 owner 与指标。',
    '2. 先做最小版本。',
    '3. 复盘后再扩量。',
  ].join('\n')
}

function buildMockRollupResponse(prompt: string): string {
  const topic = extractTopic(prompt)
  return [
    '## 行动计划',
    `围绕“${topic}”，按“小闭环 -> 复盘 -> 扩量”推进。`,
    '',
    '## 核心理由',
    '低成本、快反馈、可回滚。',
    '',
    '## 取舍',
    '牺牲首版完整度，换取更低风险。',
    '',
    '## 风险与约束',
    '- 指标口径不统一。',
    '- 依赖资源未到位。',
    '',
    '## 失效条件',
    '- 没有 owner。',
    '- 没有回滚方案。',
    '',
    '## 下一步',
    '1. 明确 owner 与截止时间。',
    '2. 先上小流量。',
    '3. 复盘后再扩量。',
  ].join('\n')
}

function buildCommitteeSummaryResponse(systemText: string, userText: string): string {
  const topic = extractTopic(userText || systemText)
  const roleName = systemText.match(/固定角色：([^\n·]+)/)?.[1]?.trim() || '该角色'
  const roleFocus = systemText.match(/你的职责：([^\n]+)/)?.[1]?.trim() || '关键职责'
  const redLine = systemText.match(/你的不可妥协点：([^\n]+)/)?.[1]?.trim() || '不能牺牲基本可交付性'

  return [
    `【判断】“${topic}”先守住 ${roleFocus}。`,
    `【观点】${roleName}建议先小范围验证，再放大。`,
    `【张力】若直接扩面，风险会先爆。`,
    `【建议】先定回滚线，并写入“${redLine}”。`,
  ].join('\n')
}

function buildCommitteeDebateResponse(systemText: string, userText: string): string {
  const topic = extractTopic(userText || systemText)
  const roleName = systemText.match(/固定角色：([^\n·]+)/)?.[1]?.trim() || '本角色'
  const targetRole = systemText.match(/回应的对象：([^\n。]+)/)?.[1]?.trim() || '对方角色'
  const redLine = systemText.match(/你的不可妥协点：([^\n]+)/)?.[1]?.trim() || '先守住关键约束'

  return [
    `【反驳】${targetRole}太快扩面，会放大“${topic}”的不确定性。`,
    `【立场】${roleName}坚持：${redLine}。`,
    `【吸收】可吸收对方的节奏建议，但先做小验证。`,
  ].join('\n')
}

function buildCommitteeModeratorResponse(systemText: string, userText: string): string {
  const topic = extractTopic(userText || systemText)
  const roleNames = Array.from(systemText.matchAll(/- ([^·\n]+)\s*·/g)).map((match) => match[1].trim())
  const roleA = roleNames[0] || '角色A'
  const roleB = roleNames[1] || '角色B'
  const roleC = roleNames[2] || '角色C'

  return [
    '## 一句话结论',
    `围绕“${topic}”，锦囊团建议先小验证再扩量。`,
    '',
    '## 共识',
    `- 先小验证，避免误判 → 来源：${roleA}, ${roleB}`,
    `- 指标统一再决策 → 来源：${roleA}, ${roleC}`,
    '',
    '## 主要分歧',
    '- 【红线冲突】速度优先 vs 风险优先。',
    '',
    '## 建议动作',
    `- 本周先上小流量并设 owner → 来源：${roleA}, ${roleB}`,
    `- 同步准备回滚与监控 → 来源：${roleB}, ${roleC}`,
    '',
    '## 少数派意见',
    `- ${roleC}：无口径统一时，不建议扩量。`,
  ].join('\n')
}

function buildJudgeResponse(lastUserText: string): string {
  const topic = extractTopic(lastUserText)
  const letters = Array.from(lastUserText.matchAll(/\[回答 ([A-Z])\]/g)).map((match) => match[1])
  const uniqueLetters = Array.from(new Set(letters))
  const scored = uniqueLetters.length ? uniqueLetters : ['A', 'B']
  const scoreLines = scored.map((letter, index) => {
    const score = 4 - (index % 2)
    const comment = score >= 4 ? '结构清晰，行动性强。' : '有价值，但风控不足。'
    return `- 回答 ${letter}: ${score}/5 — ${comment}`
  })

  return [
    '## 决策评估',
    '',
    '### 共识',
    '先小范围验证，再决定是否扩量。',
    '',
    '### 分歧',
    '主要分歧在推进节奏和风险容忍度。',
    '',
    '### 风险与盲点',
    '- 指标口径可能不一致。',
    '- 回滚条件不够明确。',
    '',
    '### 建议行动',
    '- **现在可以安全做的**：先上小流量验证关键假设。',
    '- **需要进一步验证的**：扩量阈值与回滚阈值。',
    '- **条件失效时**：若主指标连续两天恶化，立即回滚。',
    '',
    '### 各回答评分',
    ...scoreLines,
    '',
    '### 不确定性',
    `整体信心：中。原因：围绕“${topic}”的关键假设仍需真实数据验证。`,
  ].join('\n')
}

function getStructuredMockResponse(messages: ChatMessage[], provider: string): string | null {
  const lastUserText = getMockMessageText([...messages].reverse().find((message) => message.role === 'user'))
  const systemText = getMockMessageText([...messages].reverse().find((message) => message.role === 'system'))

  if (systemText.includes('你现在扮演系统主持人')) {
    return buildCommitteeModeratorResponse(systemText, lastUserText)
  }
  if (systemText.includes('输出格式（严格按下面三个字段输出') && systemText.includes('【反驳】')) {
    return buildCommitteeDebateResponse(systemText, lastUserText)
  }
  if (systemText.includes('输出格式（严格按下面四个字段输出') && systemText.includes('【判断】')) {
    return buildCommitteeSummaryResponse(systemText, lastUserText)
  }
  if (lastUserText.includes('请严格按以下 JSON 格式输出') && lastUserText.includes('"approach"')) {
    return buildMockPhase1Response(lastUserText)
  }
  if (
    lastUserText.includes('请严格按以下 JSON 格式输出')
    && (lastUserText.includes('"strongestPoint"') || lastUserText.includes('"agreement"'))
  ) {
    return buildMockPhase2Response(lastUserText)
  }
  if (lastUserText.includes('你是一个总结专家') && lastUserText.includes('## 综合结论')) {
    return buildMockPhase3Response(lastUserText)
  }
  if (systemText.includes('independent synthesis agent')) {
    return buildMockRollupResponse(lastUserText)
  }
  if (MOCK_JUDGE_TRIGGER.test(lastUserText)) {
    return buildJudgeResponse(lastUserText)
  }
  if (MOCK_COMMITTEE_TRIGGER.test(lastUserText)) {
    return buildCommitteeModeratorResponse(systemText, lastUserText)
  }
  if (MOCK_CHAT_TRIGGER.test(lastUserText)) {
    return buildGeneralMockResponse(provider, lastUserText)
  }

  if (!lastUserText) return null
  return buildGeneralMockResponse(provider, lastUserText)
}

async function* mockStreamChat(
  model: string,
  messages: ChatMessage[],
  signal?: AbortSignal,
): AsyncGenerator<string> {
  if (MOCK_UNAVAILABLE_MODEL_IDS.has(model)) {
    throw new ApiError(
      '该 Demo Agent 当前不可访问（模拟 404），请点击重试并更换模型',
      404,
      'model_unavailable',
      'mock_demo_unavailable',
    )
  }
  if (MOCK_RATE_LIMIT_MODEL_IDS.has(model)) {
    throw new ApiError(
      '该 Demo Agent 触发频率限制（模拟 429），请重试或切换模型',
      429,
      'rate_limited',
      'mock_demo_rate_limited',
    )
  }

  const provider = resolveMockProvider(model)
  const fullText = getStructuredMockResponse(messages, provider) || buildGeneralMockResponse(provider, '')

  for (let i = 0; i < fullText.length; ) {
    if (signal?.aborted) return
    const chunkSize = Math.min(1 + Math.floor(Math.random() * 3), fullText.length - i)
    yield fullText.slice(i, i + chunkSize)
    i += chunkSize
    const lastChar = fullText[i - 1]
    const delay = '，。！？\n'.includes(lastChar) ? 40 : (5 + Math.random() * 10)
    await new Promise((resolve) => setTimeout(resolve, delay))
  }
}
