import { streamChat, ApiError, type ChatMessage } from '@/services/api'
import { getApiKey } from '@/services/keychain'
import { useAppStore } from '@/stores/app'
import { useProviderStore, type ProviderAccount, type ProviderConfig } from '@/stores/provider'
import { createTimingSpan } from '@/utils/timingLogger'

export interface RuntimeCandidate {
  provider: ProviderConfig
  account: ProviderAccount | null
  apiKey: string
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === 'AbortError'
}

export function shouldRetryWithAnotherAccount(error: unknown) {
  return error instanceof ApiError
    && ['invalid_key', 'rate_limited', 'model_unavailable'].includes(error.code || '')
}

function resolveProviderForModel(modelId: string) {
  const providerStore = useProviderStore()

  // Demo models must always run on the local mock provider so showcases
  // are not blocked by real provider account configuration.
  if (modelId.startsWith('demo/')) {
    const mockProvider = providerStore.providers.find((item) => item.type === 'mock')
    if (mockProvider) return mockProvider
  }

  const appStore = useAppStore()
  const model = appStore.models.find((item) => item.id === modelId)

  let provider = providerStore.getProvider(model?.provider || '')
  if (!provider) {
    provider = providerStore.providers.find((item) => item.type === 'openrouter')
  }
  return provider || null
}

export async function getRuntimeCandidates(modelId: string): Promise<RuntimeCandidate[]> {
  const providerStore = useProviderStore()
  const provider = resolveProviderForModel(modelId)

  if (!provider) throw new Error('未找到可用的 API 通道')
  if (provider.type === 'mock') {
    return [{ provider, account: null, apiKey: 'demo' }]
  }

  const accounts = providerStore.getFallbackAccounts(provider.id)
  if (!accounts.length) {
    throw new Error(`${provider.name} 未配置可用账户`)
  }

  const candidates: RuntimeCandidate[] = []
  for (const account of accounts) {
    const apiKey = await getApiKey(account.id)
    if (!apiKey) continue
    candidates.push({ provider, account, apiKey })
  }

  if (!candidates.length) throw new Error(`${provider.name} 未配置可用账户`)
  return candidates
}

export async function getFetchRuntime(providerId: string) {
  const providerStore = useProviderStore()
  const provider = providerStore.getProvider(providerId)
  if (!provider) return null
  if (provider.type === 'mock') {
    return { provider, account: null, apiKey: 'demo' }
  }

  const account = providerStore.getRuntimeAccounts(providerId)[0]
  if (!account) return null

  const apiKey = await getApiKey(account.id)
  if (!apiKey) return null

  return { provider, account, apiKey }
}

export async function* streamModelChat(options: {
  modelId: string
  messages: ChatMessage[]
  signal?: AbortSignal
  traceLabel?: string
  traceMeta?: Record<string, unknown>
}): AsyncGenerator<string> {
  const providerStore = useProviderStore()
  const trace = createTimingSpan(options.traceLabel || `runtime:${options.modelId}`, {
    modelId: options.modelId,
    ...options.traceMeta,
  })
  const candidates = await getRuntimeCandidates(options.modelId)
  trace.mark('candidates_resolved', { candidateCount: candidates.length })
  let lastError: unknown = null
  let chunkCount = 0
  let firstChunkSeen = false

  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[index]
    trace.mark('attempt_start', {
      attempt: index + 1,
      providerId: candidate.provider.id,
      accountId: candidate.account?.id ?? null,
    })

    try {
      for await (const chunk of streamChat({
        provider: candidate.provider,
        apiKey: candidate.apiKey,
        model: options.modelId,
        messages: options.messages,
        signal: options.signal,
      })) {
        chunkCount += 1
        if (!firstChunkSeen) {
          firstChunkSeen = true
          trace.mark('first_chunk', {
            attempt: index + 1,
            providerId: candidate.provider.id,
          })
        }
        yield chunk
      }

      if (candidate.account) {
        providerStore.markAccountUsed(candidate.account.id)
      }
      trace.success({
        attempt: index + 1,
        providerId: candidate.provider.id,
        chunkCount,
      })
      return
    } catch (error) {
      if (isAbortError(error) || options.signal?.aborted) throw error
      lastError = error

      if (candidate.account && error instanceof ApiError) {
        providerStore.markAccountFailure(candidate.account.id, error.code)
      }

      if (!shouldRetryWithAnotherAccount(error) || index === candidates.length - 1) {
        trace.error(error, {
          attempt: index + 1,
          providerId: candidate.provider.id,
          chunkCount,
        })
        throw error
      }

      trace.mark('retry_next_account', {
        attempt: index + 1,
        providerId: candidate.provider.id,
        chunkCount,
      })
    }
  }

  trace.error(lastError, { chunkCount })
  throw lastError instanceof Error ? lastError : new Error('请求失败')
}
