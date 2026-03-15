import type {
  BootstrapConfig,
  ModelMeta,
  Session,
  ChatRequest,
  ChatResponse,
  DiscussRequest,
  DiscussSessionState,
} from '@mms/contracts'

const API_BASE = '/api'

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...options,
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }

  return response.json()
}

export async function fetchBootstrap(): Promise<BootstrapConfig> {
  return fetchApi('/bootstrap')
}

export async function fetchModels(provider?: string): Promise<ModelMeta[]> {
  const params = provider ? `?provider=${provider}` : ''
  const result = await fetchApi<{ models: ModelMeta[] }>(`/models${params}`)
  return result.models
}

export async function fetchSessions(): Promise<Session[]> {
  const result = await fetchApi<{ sessions: Session[] }>('/sessions')
  return result.sessions
}

export function streamChat(
  request: ChatRequest,
  onEvent: (type: string, data: unknown) => void,
  onError: (error: Error) => void,
  onComplete: () => void
): () => void {
  const abortController = new AbortController()

  fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal: abortController.signal,
  })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      if (!response.body) {
        throw new Error('No response body')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEventType = 'unknown'

      function read(): Promise<void> {
        return reader.read().then(({ done, value }) => {
          if (done) {
            onComplete()
            return
          }

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmed = line.trim()
            if (trimmed.startsWith('event: ')) {
              currentEventType = trimmed.slice(7).trim()
            } else if (trimmed.startsWith('data: ')) {
              try {
                const data = JSON.parse(trimmed.slice(6))
                onEvent(currentEventType, data)
              } catch {
                // Ignore parse errors for malformed lines
              }
            }
          }

          return read()
        })
      }

      return read()
    })
    .catch(error => {
      if (error.name !== 'AbortError') {
        onError(error)
      }
    })

  return () => abortController.abort()
}

export function streamDiscuss(
  request: DiscussRequest,
  onEvent: (type: string, data: unknown) => void,
  onError: (error: Error) => void,
  onComplete: () => void
): () => void {
  const abortController = new AbortController()

  fetch(`${API_BASE}/discuss/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal: abortController.signal,
  })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      if (!response.body) {
        throw new Error('No response body')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEventType = 'unknown'

      function read(): Promise<void> {
        return reader.read().then(({ done, value }) => {
          if (done) {
            onComplete()
            return
          }

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmed = line.trim()
            if (trimmed.startsWith('event: ')) {
              currentEventType = trimmed.slice(7).trim()
            } else if (trimmed.startsWith('data: ')) {
              try {
                const data = JSON.parse(trimmed.slice(6))
                onEvent(currentEventType, data)
              } catch {
                // Ignore parse errors
              }
            }
          }

          return read()
        })
      }

      return read()
    })
    .catch(error => {
      if (error.name !== 'AbortError') {
        onError(error)
      }
    })

  return () => abortController.abort()
}
