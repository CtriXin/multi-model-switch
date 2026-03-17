import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useChatStore, type ChatRound, type ChatMessage, type ImageAttachment, type ContextMode } from './chat'
import { useDiscussStore, type Phase1Result, type Phase2Result } from './discuss'
import { useAppStore } from './app'

export interface SerializedChatRound {
  id: string
  prompt: string
  attachments?: ImageAttachment[]
  responses: [string, ChatMessage][]
  activeModelId: string | null
  selectedModelId: string | null
  timestamp: number
  judge?: {
    content: string
    modelId: string
    isSelfEval: boolean
    timestamp: number
  }
}

export interface Session {
  id: string
  type: 'chat' | 'discuss'
  title: string
  modelIds: string[]
  createdAt: number
  updatedAt: number
  messageCount: number
  contextMode?: ContextMode
  chatData?: SerializedChatRound[]
  discussData?: {
    phase: number
    phase1Results: Phase1Result[]
    phase2Results: Phase2Result[]
    phase3Text: string
    rollupText: string
    rollupModel: string
    rollupPhase: 'idle' | 'streaming' | 'done'
    topic: string
  }
}

const STORAGE_KEY = 'mms-sessions'
const CURRENT_SESSION_KEY = 'mms-current-session'

function generateId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function serializeRounds(rounds: ChatRound[]): SerializedChatRound[] {
  return rounds.map(r => ({
    id: r.id,
    prompt: r.prompt,
    attachments: r.attachments?.length ? r.attachments : undefined,
    responses: Array.from(r.responses.entries()),
    activeModelId: r.activeModelId,
    selectedModelId: r.selectedModelId,
    timestamp: r.timestamp,
    judge: r.judge,
  }))
}

function deserializeRounds(data: SerializedChatRound[]): ChatRound[] {
  return data.map(r => ({
    id: r.id,
    prompt: r.prompt,
    attachments: r.attachments ?? [],
    responses: new Map(r.responses),
    activeModelId: r.activeModelId,
    selectedModelId: r.selectedModelId ?? null,
    timestamp: r.timestamp,
    judge: r.judge,
  }))
}

export const useSessionStore = defineStore('session', () => {
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<string | null>(null)

  const currentSession = computed(() =>
    sessions.value.find(s => s.id === currentSessionId.value) ?? null
  )

  const sortedSessions = computed(() =>
    [...sessions.value].sort((a, b) => b.updatedAt - a.updatedAt)
  )

  function loadSessions() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) sessions.value = JSON.parse(raw)
      currentSessionId.value = localStorage.getItem(CURRENT_SESSION_KEY)
    } catch { /* ignore corrupt data */ }
  }

  function persist() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions.value))
    if (currentSessionId.value) {
      localStorage.setItem(CURRENT_SESSION_KEY, currentSessionId.value)
    }
  }

  function saveCurrentSession(options: { touchUpdatedAt?: boolean } = {}) {
    if (!currentSessionId.value) return
    const session = sessions.value.find(s => s.id === currentSessionId.value)
    if (!session) return

    const appStore = useAppStore()
    session.modelIds = [...appStore.selectedModelIds]
    if (options.touchUpdatedAt !== false) {
      session.updatedAt = Date.now()
    }

    if (session.type === 'chat') {
      const chatStore = useChatStore()
      session.chatData = serializeRounds(chatStore.rounds)
      session.contextMode = chatStore.contextMode
      session.messageCount = chatStore.rounds.length
      if (chatStore.rounds.length && !session.title.startsWith('新')) {
        // keep existing title
      } else if (chatStore.rounds.length) {
        session.title = chatStore.rounds[0].prompt.slice(0, 20) || '新对话'
      }
    } else {
      const discussStore = useDiscussStore()
      session.discussData = {
        phase: discussStore.phase,
        phase1Results: [...discussStore.phase1Results],
        phase2Results: [...discussStore.phase2Results],
        phase3Text: discussStore.phase3Text,
        rollupText: discussStore.rollupText,
        rollupModel: discussStore.rollupModel,
        rollupPhase: discussStore.rollupPhase,
        topic: discussStore.topic,
      }
      session.messageCount = discussStore.phase1Results.length + discussStore.phase2Results.length
      if (discussStore.topic) {
        session.title = discussStore.topic.slice(0, 20) || '新辩论'
      }
    }

    persist()
  }

  function createSession(type: 'chat' | 'discuss'): Session {
    // If current session is already empty and same type, reuse it
    const cur = currentSession.value
    if (cur && cur.type === type && cur.messageCount === 0) {
      return cur
    }

    // Save current session first
    saveCurrentSession({ touchUpdatedAt: false })

    // Clean up stale empty sessions (no messages ever sent)
    sessions.value = sessions.value.filter(s =>
      s.id === currentSessionId.value || s.messageCount > 0
    )

    const session: Session = {
      id: generateId(),
      type,
      title: type === 'chat' ? '新对话' : '新辩论',
      modelIds: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messageCount: 0,
    }

    sessions.value.push(session)
    currentSessionId.value = session.id

    // Clear current stores
    const chatStore = useChatStore()
    const discussStore = useDiscussStore()
    chatStore.clearHistory()
    discussStore.reset()

    persist()
    return session
  }

  function switchSession(id: string) {
    if (id === currentSessionId.value) return

    // Save current
    saveCurrentSession({ touchUpdatedAt: false })

    const session = sessions.value.find(s => s.id === id)
    if (!session) return

    currentSessionId.value = id
    const appStore = useAppStore()
    const chatStore = useChatStore()
    const discussStore = useDiscussStore()

    // Restore model selection
    appStore.selectedModelIds = [...session.modelIds]

    // Restore data
    chatStore.clearHistory()
    discussStore.reset()

    if (session.type === 'chat' && session.chatData) {
      chatStore.rounds = deserializeRounds(session.chatData)
      chatStore.contextMode = session.contextMode ?? 'summary'
    } else if (session.type === 'discuss' && session.discussData) {
      discussStore.phase = session.discussData.phase
      discussStore.phase1Results = [...session.discussData.phase1Results]
      discussStore.phase2Results = [...session.discussData.phase2Results]
      discussStore.phase3Text = session.discussData.phase3Text
      discussStore.rollupText = session.discussData.rollupText ?? ''
      discussStore.rollupModel = session.discussData.rollupModel ?? ''
      discussStore.rollupPhase = session.discussData.rollupPhase ?? 'idle'
      discussStore.topic = session.discussData.topic
    }

    localStorage.setItem(CURRENT_SESSION_KEY, id)
  }

  function deleteSession(id: string) {
    const idx = sessions.value.findIndex(s => s.id === id)
    if (idx < 0) return

    sessions.value.splice(idx, 1)

    if (currentSessionId.value === id) {
      currentSessionId.value = null
      useChatStore().clearHistory()
      useDiscussStore().reset()
    }

    persist()
  }

  function formatTime(ts: number): string {
    const now = Date.now()
    const diff = now - ts
    const date = new Date(ts)

    if (diff < 60_000) return '刚刚'
    if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
    if (diff < 86400_000) return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    if (diff < 172800_000) return '昨天'
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }

  return {
    sessions, currentSessionId, currentSession, sortedSessions,
    loadSessions, saveCurrentSession, createSession, switchSession,
    deleteSession, formatTime, persist,
  }
})
