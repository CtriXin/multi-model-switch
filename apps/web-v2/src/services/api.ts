/**
 * Unified API layer for OpenRouter / OpenAI-compatible providers.
 * Handles streaming chat completions and model listing.
 */

import type { ProviderConfig } from '@/stores/provider'
import type { ModelMeta } from '@/stores/app'

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
  const free = provider.type === 'openrouter'
    ? (parseFloat(raw.pricing?.prompt ?? '1') === 0 && parseFloat(raw.pricing?.completion ?? '1') === 0)
    : false

  // Vision detection
  const supportsVision = deriveSupportsVision(raw, provider)

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
    supportsVision,
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
  { id: 'demo/claude-sonnet', name: 'Claude Sonnet (Demo)', provider: 'anthropic', category: 'frontier', tier: 2, priceInput: 3, priceOutput: 15, tags: ['reasoning', 'coding', 'vision'], contextWindow: 200000, free: false, supportsVision: true, supportsNativeWebSearch: false, supportsTools: false, capabilitySource: 'default', capabilityVerifiedAt: null },
  { id: 'demo/gpt-4o', name: 'GPT-4o (Demo)', provider: 'openai', category: 'frontier', tier: 2, priceInput: 2.5, priceOutput: 10, tags: ['reasoning', 'vision', 'coding'], contextWindow: 128000, free: false, supportsVision: true, supportsNativeWebSearch: false, supportsTools: false, capabilitySource: 'default', capabilityVerifiedAt: null },
  { id: 'demo/gemini-pro', name: 'Gemini Pro (Demo)', provider: 'google', category: 'frontier', tier: 2, priceInput: 1.25, priceOutput: 10, tags: ['reasoning', 'coding', 'vision'], contextWindow: 1000000, free: true, supportsVision: true, supportsNativeWebSearch: false, supportsTools: false, capabilitySource: 'default', capabilityVerifiedAt: null },
  { id: 'demo/deepseek-r1', name: 'DeepSeek R1 (Demo)', provider: 'deepseek', category: 'reasoning', tier: 1, priceInput: 0.55, priceOutput: 2.19, tags: ['reasoning', 'coding'], contextWindow: 64000, free: false, supportsVision: false, supportsNativeWebSearch: false, supportsTools: false, capabilitySource: 'default', capabilityVerifiedAt: null },
  { id: 'demo/haiku', name: 'Claude Haiku (Demo)', provider: 'anthropic', category: 'fast', tier: 0, priceInput: 0.25, priceOutput: 1.25, tags: ['fast', 'coding'], contextWindow: 200000, free: false, supportsVision: false, supportsNativeWebSearch: false, supportsTools: false, capabilitySource: 'default', capabilityVerifiedAt: null },
]

const MOCK_RESPONSES: Record<string, string[]> = {
  anthropic: [
    '这是一个很好的问题。让我从几个角度来分析：\n\n**首先**，我们需要考虑整体架构的合理性。一个好的设计应该兼顾可扩展性和易用性。\n\n**其次**，从实现层面来看，推荐使用模块化的方式来组织代码，这样便于后续的维护和迭代。\n\n**最后**，建议在实现前做好充分的技术选型评估，避免后期的重构成本。',
    '根据我的分析，这个场景适合使用事件驱动架构。核心思路是：\n\n1. 将业务流程拆分为独立的事件\n2. 通过消息队列解耦各个服务\n3. 使用幂等性设计保证数据一致性\n\n这样做的好处是系统的伸缩性更强，也更容易做故障隔离。',
  ],
  openai: [
    '好的，我来帮你解答这个问题。\n\n这个问题的关键在于理解核心概念之间的关系。我建议采用以下策略：\n\n- 使用 **分层架构** 来降低复杂度\n- 引入 **依赖注入** 提高测试覆盖率\n- 利用 **缓存策略** 优化性能\n\n具体实现上，可以参考业界的最佳实践来落地。',
    '这个需求可以通过以下方式实现：\n\n```typescript\nclass EventBus {\n  private handlers = new Map()\n  \n  on(event: string, handler: Function) {\n    this.handlers.set(event, handler)\n  }\n  \n  emit(event: string, data: any) {\n    this.handlers.get(event)?.(data)\n  }\n}\n```\n\n这个方案简洁高效，适合中小规模的应用场景。',
  ],
  google: [
    '我来综合分析一下这个问题。\n\n从技术可行性来看，有以下几种方案：\n\n| 方案 | 优势 | 劣势 | 推荐度 |\n|------|------|------|--------|\n| 方案A | 实现简单 | 扩展性差 | ★★★ |\n| 方案B | 性能好 | 复杂度高 | ★★★★ |\n| 方案C | 均衡 | 需要学习成本 | ★★★★★ |\n\n综合考虑，我推荐方案C。',
  ],
  deepseek: [
    '让我深入思考一下这个问题...\n\n经过分析，核心解决方案是：\n\n1. 使用有限状态机建模业务流程\n2. 通过状态转移表明确各状态间的跳转规则\n3. 结合响应式系统实现自动更新\n\n这个方案的时间复杂度是 O(n)，空间复杂度是 O(1)，效率很高。',
  ],
}

function getMockResponse(provider: string): string {
  const pool = MOCK_RESPONSES[provider] || MOCK_RESPONSES.openai
  return pool[Math.floor(Math.random() * pool.length)]
}

async function* mockStreamChat(
  model: string,
  messages: ChatMessage[],
  signal?: AbortSignal,
): AsyncGenerator<string> {
  const provider = model.includes('claude') || model.includes('haiku')
    ? 'anthropic'
    : model.includes('gpt') ? 'openai'
    : model.includes('gemini') ? 'google'
    : model.includes('deepseek') ? 'deepseek'
    : 'openai'

  const fullText = getMockResponse(provider)

  for (let i = 0; i < fullText.length; ) {
    if (signal?.aborted) return
    const chunkSize = Math.min(1 + Math.floor(Math.random() * 3), fullText.length - i)
    yield fullText.slice(i, i + chunkSize)
    i += chunkSize
    const lastChar = fullText[i - 1]
    const delay = '，。！？\n'.includes(lastChar) ? 40 : (5 + Math.random() * 10)
    await new Promise((r) => setTimeout(r, delay))
  }
}
