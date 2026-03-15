/**
 * Unified API layer for OpenRouter / OpenAI-compatible providers.
 * Handles streaming chat completions and model listing.
 */

import type { ProviderConfig } from '@/stores/provider'
import type { ModelMeta } from '@/stores/app'

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
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
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Stream chat completions from an OpenAI-compatible endpoint.
 * Yields text chunks as they arrive.
 */
export async function* streamChat(options: StreamChatOptions): AsyncGenerator<string> {
  const { provider, apiKey, model, messages, signal } = options

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
      model,
      messages,
      stream: true,
    }),
    signal,
  })

  if (!res.ok) {
    const body = await res.text().catch(() => '')
    if (res.status === 401) {
      throw new ApiError('API Key 无效，请检查配置', res.status, 'invalid_key')
    }
    if (res.status === 429) {
      throw new ApiError('请求过于频繁，请稍后重试', res.status, 'rate_limited')
    }
    throw new ApiError(
      `API 请求失败 (${res.status}): ${body.slice(0, 200)}`,
      res.status,
    )
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
 * Fetch available models from a provider.
 * Maps the response to ModelMeta format.
 */
export async function fetchModels(
  provider: ProviderConfig,
  apiKey: string,
): Promise<ModelMeta[]> {
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
    throw new ApiError(`获取模型列表失败 (${res.status})`, res.status)
  }

  const json = await res.json()
  const rawModels: ApiModel[] = json.data ?? json

  return rawModels
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

function mapToModelMeta(raw: ApiModel, provider: ProviderConfig): ModelMeta {
  const promptPrice = parseFloat(raw.pricing?.prompt ?? '0') * 1_000_000
  const completionPrice = parseFloat(raw.pricing?.completion ?? '0') * 1_000_000

  // Derive provider name from model ID for OpenRouter
  const providerName = deriveProvider(raw.id)

  return {
    id: raw.id,
    name: raw.name ?? raw.id,
    provider: providerName,
    category: deriveCategory(raw),
    tier: deriveTier(promptPrice),
    priceInput: Math.round(promptPrice * 100) / 100,
    priceOutput: Math.round(completionPrice * 100) / 100,
    tags: deriveTags(raw),
    contextWindow: raw.context_length ?? 4096,
  }
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
