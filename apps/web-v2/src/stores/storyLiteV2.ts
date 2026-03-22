import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useAppStore } from './app'
import { streamModelChat } from '@/services/runtime'
import { sanitizeModelOutput } from '@/utils/modelOutput'
import {
  STORY_LITE_V2_ROLES,
  STORY_LITE_V2_BRANCHES,
  buildStoryLiteV2SeededScene,
  buildStoryLiteV2SystemPrompt,
  buildStoryLiteV2UserPrompt,
  buildDirectorSystemPrompt,
  buildDirectorUserPrompt,
  extractDirectorJson,
  buildFallbackChoices,
  buildFallbackPremise,
  type StoryLiteV2ConnectionMode,
  type StoryLiteV2Choice,
  type StoryLiteV2Response,
  type StoryLiteV2Role,
  type StoryLiteV2Scene,
  type SceneHistoryEntry,
} from '@/features/play-modes/story-lite-v2'

const ROLE_ORDER: StoryLiteV2Role[] = ['guide', 'partner', 'variable']
const DEMO_MODEL_IDS = ['demo/claude-sonnet-4', 'demo/gpt-4.1', 'demo/gemini-2.5-pro']
const STORAGE_KEY = 'mms-story-lite-v2-session'

interface SavedSession {
  seedLabel: string
  round: number
  sceneHistory: SceneHistoryEntry[]
  currentScene: StoryLiteV2Scene | null
  isCompleted: boolean
  manuallyEnded: boolean
  timestamp: number
}

function saveSession(state: SavedSession) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch { /* ignore */ }
}

function loadSession(): SavedSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return null
}

function clearSession() {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch { /* ignore */ }
}

async function collectText(stream: AsyncGenerator<string>): Promise<string> {
  let text = ''
  for await (const chunk of stream) {
    text += chunk
  }
  return text.trim()
}

function isUsingDemoModels(modelIds: string[]) {
  return modelIds.length > 0 && modelIds.every((id) => id.startsWith('demo/'))
}

function isLiveModelId(modelId: string) {
  return !modelId.startsWith('demo/')
}

function fillModelIds(modelIds: string[]) {
  const source = modelIds.length ? [...modelIds] : [...DEMO_MODEL_IDS]
  if (!source.length) return null

  const picked = source.slice(0, 3)
  while (picked.length < 3) {
    picked.push(source[picked.length % source.length])
  }
  return picked as [string, string, string]
}

function assignRoles(modelIds: string[]) {
  const picked = fillModelIds(modelIds)
  if (!picked) return null

  return {
    guide: picked[0],
    partner: picked[1],
    variable: picked[2],
  } satisfies Record<StoryLiteV2Role, string>
}

function shouldFallbackToMock(text: string) {
  const normalized = text.trim()
  if (!normalized) return true

  return [
    '<BRIEF>',
    '## 结论',
    '转化率 / 错误率 / 时延',
    '先做小闭环',
    '先上线最小版本',
  ].some((marker) => normalized.includes(marker))
}

function createRoleState(status: 'idle' | 'loading' | 'done' = 'idle') {
  return {
    guide: status,
    partner: status,
    variable: status,
  } satisfies Record<StoryLiteV2Role, 'idle' | 'loading' | 'done'>
}

export const useStoryLiteV2Store = defineStore('storyLiteV2', () => {
  const appStore = useAppStore()

  const currentScene = ref<StoryLiteV2Scene | null>(null)
  const seedLabel = ref('')
  const round = ref(0)
  const processing = ref(false)
  const error = ref('')
  const useMock = ref(false)
  const modelAssignment = ref<Record<StoryLiteV2Role, string> | null>(null)
  const connectionMode = ref<StoryLiteV2ConnectionMode>('demo')
  const activeChoiceLabel = ref('')
  const responseStates = ref(createRoleState())
  const requestNonce = ref(0)
  const sceneHistory = ref<SceneHistoryEntry[]>([])
  const manuallyEnded = ref(false)
  const streamingPremise = ref('')

  /** 流式显示 premise，像讲故事一样逐字出现 */
  async function streamPremise(fullText: string, speed = 12): Promise<void> {
    streamingPremise.value = ''
    const chars = fullText.split('')
    for (let i = 0; i < chars.length; i++) {
      streamingPremise.value = fullText.slice(0, i + 1)
      await new Promise((r) => setTimeout(r, speed))
    }
  }

  const isCompleted = computed(() => currentScene.value?.ending != null || manuallyEnded.value)
  const isStarted = computed(() => round.value > 0 || currentScene.value != null)
  const usesLiveModels = computed(() => connectionMode.value !== 'demo')
  const readyResponseCount = computed(() =>
    Object.values(responseStates.value).filter((status) => status === 'done').length,
  )

  function getModelName(modelId: string) {
    if (modelId.startsWith('mock-')) return '模拟角色'
    if (modelId.startsWith('demo/')) {
      const raw = modelId.split('/')[1] || modelId
      return raw
        .split('-')
        .map((part) => part.toUpperCase() === 'GPT' ? 'GPT' : part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
    }
    return appStore.getModel(modelId)?.name || modelId
  }

  function syncModelAssignment() {
    const selectedIds = appStore.selectedModelIds.filter((id) => appStore.getModel(id))
    const selectedLiveIds = selectedIds.filter(isLiveModelId)
    const availableLiveIds = appStore.getLabAutoPool(
      appStore.models.filter((model) => isLiveModelId(model.id)),
    )
      .map((model) => model.id)

    let resolvedIds: string[] = selectedIds

    if (selectedLiveIds.length) {
      connectionMode.value = 'selected-live'
      resolvedIds = selectedLiveIds
    } else if (availableLiveIds.length) {
      connectionMode.value = 'auto-live'
      resolvedIds = availableLiveIds
    } else {
      connectionMode.value = 'demo'
      resolvedIds = selectedIds.length ? selectedIds : DEMO_MODEL_IDS
    }

    useMock.value = connectionMode.value === 'demo' || isUsingDemoModels(resolvedIds)
    modelAssignment.value = assignRoles(resolvedIds)
  }

  function resetResponseState(status: 'idle' | 'loading' | 'done' = 'idle') {
    responseStates.value = createRoleState(status)
  }

  function setResponseState(role: StoryLiteV2Role, status: 'idle' | 'loading' | 'done') {
    responseStates.value = {
      ...responseStates.value,
      [role]: status,
    }
  }

  function updateSceneResponse(role: StoryLiteV2Role, patch: Partial<StoryLiteV2Response>) {
    const scene = currentScene.value
    if (!scene) return
    const nextResponses = scene.responses.map((response) =>
      response.role === role ? { ...response, ...patch } : response,
    )
    currentScene.value = {
      ...scene,
      responses: nextResponses,
    }
  }

  function buildFallbackResponse(role: StoryLiteV2Role, scene: StoryLiteV2Scene): StoryLiteV2Response {
    const assignment = modelAssignment.value
    const fallback = scene.responses.find((item) => item.role === role)
    const modelId = assignment?.[role] || fallback?.modelId || DEMO_MODEL_IDS[0]

    return {
      role,
      modelId,
      modelName: getModelName(modelId),
      text: fallback?.text || `${STORY_LITE_V2_ROLES[role].label}暂时没有新的判断，但气氛已经开始变化。`,
      tone: fallback?.tone,
    }
  }

  function buildSceneFromMock(sceneId: string) {
    const assignment = modelAssignment.value
    const template = buildStoryLiteV2SeededScene(seedLabel.value, sceneId)

    return {
      ...template,
      responses: template.responses.length
        ? ROLE_ORDER.map((role) => {
            const fallback = template.responses.find((item) => item.role === role)
            const modelId = assignment?.[role] || fallback?.modelId || DEMO_MODEL_IDS[0]

            return {
              role,
              modelId,
              modelName: getModelName(modelId),
              text: fallback?.text || `${STORY_LITE_V2_ROLES[role].label}正在观察局势。`,
              tone: fallback?.tone,
              status: 'done',
            }
          })
        : [],
      choices: template.choices.map((choice) => ({ ...choice })),
      ending: template.ending ? { ...template.ending } : undefined,
    } satisfies StoryLiteV2Scene
  }

  function buildPendingScene(sceneId: string) {
    const baseScene = buildSceneFromMock(sceneId)
    const assignment = modelAssignment.value
    if (!assignment || baseScene.responses.length === 0) return baseScene

    return {
      ...baseScene,
      responses: ROLE_ORDER.map((role) => ({
        ...buildFallbackResponse(role, baseScene),
        text: '',
        status: 'pending',
      })),
      choices: [],
    } satisfies StoryLiteV2Scene
  }

  async function streamRoleResponse(sceneId: string, role: StoryLiteV2Role, sceneRound: number, requestId: number, lastChoice?: StoryLiteV2Choice) {
    const assignment = modelAssignment.value
    const baseScene = buildSceneFromMock(sceneId)
    if (!assignment) return

    const fallback = buildFallbackResponse(role, baseScene)
    const modelId = assignment[role]

    setResponseState(role, 'loading')
    updateSceneResponse(role, { status: 'streaming' })

    try {
      let rawText = ''
      for await (const chunk of streamModelChat({
        modelId,
        traceLabel: `story-lite:${sceneId}:${role}`,
        traceMeta: {
          round: sceneRound,
          seed: seedLabel.value,
          connectionMode: connectionMode.value,
        },
        messages: [
          { role: 'system', content: buildStoryLiteV2SystemPrompt(role) },
          {
            role: 'user',
            content: buildStoryLiteV2UserPrompt(
              seedLabel.value,
              sceneRound,
              baseScene.premise,
              lastChoice
                ? {
                    role: lastChoice.targetRole ? STORY_LITE_V2_ROLES[lastChoice.targetRole].label : '当前局面',
                    label: lastChoice.label,
                  }
                : undefined,
            ),
          },
        ],
      })) {
        if (requestNonce.value !== requestId) return

        rawText += chunk
        const cleaned = sanitizeModelOutput(rawText).content.trim()
        if (cleaned && !shouldFallbackToMock(cleaned)) {
          updateSceneResponse(role, {
            text: cleaned,
            status: 'streaming',
          })
        }
      }

      if (requestNonce.value !== requestId) return

      const finalContent = sanitizeModelOutput(rawText).content.trim()
      updateSceneResponse(role, {
        text: finalContent && !shouldFallbackToMock(finalContent) ? finalContent : fallback.text,
        status: 'done',
      })
    } catch {
      if (requestNonce.value !== requestId) return
      updateSceneResponse(role, {
        ...fallback,
        status: 'error',
      })
    } finally {
      if (requestNonce.value === requestId) {
        setResponseState(role, 'done')
      }
    }
  }

  async function generateDirectorScene(
    lastChoice?: StoryLiteV2Choice,
  ): Promise<{ premise: string; choices: StoryLiteV2Choice[] }> {
    const assignment = modelAssignment.value
    if (!assignment) return { premise: buildFallbackPremise(), choices: buildFallbackChoices() }

    const directorModelId = assignment.guide

    try {
      const rawText = await collectText(
        streamModelChat({
          modelId: directorModelId,
          traceLabel: 'story-lite:director',
          traceMeta: { round: round.value, seed: seedLabel.value },
          messages: [
            { role: 'system', content: buildDirectorSystemPrompt() },
            { role: 'user', content: buildDirectorUserPrompt(seedLabel.value, sceneHistory.value, lastChoice ? { label: lastChoice.label } : undefined) },
          ],
        }),
      )

      if (!rawText) return { premise: buildFallbackPremise(), choices: buildFallbackChoices() }

      const result = extractDirectorJson(rawText)
      if (result) return result
    } catch { /* fallback below */ }

    return { premise: buildFallbackPremise(), choices: buildFallbackChoices() }
  }

  async function buildLiveSceneDynamic(sceneRound: number, lastChoice?: StoryLiteV2Choice) {
    const assignment = modelAssignment.value
    if (!assignment) return buildSceneFromMock('start')

    // Phase 1: 导演 AI 生成 premise + choices
    const directorResult = await generateDirectorScene(lastChoice)

    const sceneId = `round-${sceneRound}`
    const requestId = requestNonce.value + 1
    requestNonce.value = requestId

    // 先开始流式显示 premise
    const premisePromise = streamPremise(directorResult.premise, 25)

    // 创建 pending scene
    currentScene.value = {
      id: sceneId,
      chapter: `第 ${sceneRound} 幕`,
      title: '',
      premise: directorResult.premise,
      responses: ROLE_ORDER.map((role) => ({
        role,
        modelId: assignment[role],
        modelName: getModelName(assignment[role]),
        text: '',
        status: 'pending',
      })),
      choices: [],
    }
    resetResponseState('loading')

    // 等待 premise 流式完成
    await premisePromise

    // Phase 2: 并行 streaming 3 个角色回应
    await Promise.allSettled(
      ROLE_ORDER.map((role) =>
        streamRoleResponseDynamic(sceneId, role, sceneRound, requestId, directorResult.premise, lastChoice),
      ),
    )

    if (requestNonce.value !== requestId || !currentScene.value) return currentScene.value!

    // 写入 choices（等角色回应完成后再展示选择按钮）
    currentScene.value = {
      ...currentScene.value,
      choices: directorResult.choices,
    }

    return currentScene.value
  }

  async function streamRoleResponseDynamic(
    sceneId: string,
    role: StoryLiteV2Role,
    sceneRound: number,
    requestId: number,
    premise: string,
    lastChoice?: StoryLiteV2Choice,
  ) {
    const assignment = modelAssignment.value
    if (!assignment) return

    const modelId = assignment[role]
    const fallbackText = `${STORY_LITE_V2_ROLES[role].label}正在观察局势。`

    setResponseState(role, 'loading')
    updateSceneResponse(role, { status: 'streaming' })

    try {
      let rawText = ''
      for await (const chunk of streamModelChat({
        modelId,
        traceLabel: `story-lite:${sceneId}:${role}`,
        traceMeta: { round: sceneRound, seed: seedLabel.value },
        messages: [
          { role: 'system', content: buildStoryLiteV2SystemPrompt(role) },
          {
            role: 'user',
            content: buildStoryLiteV2UserPrompt(
              seedLabel.value,
              sceneRound,
              premise,
              lastChoice
                ? {
                    role: lastChoice.targetRole
                      ? STORY_LITE_V2_ROLES[lastChoice.targetRole].label
                      : '当前局面',
                    label: lastChoice.label,
                  }
                : undefined,
            ),
          },
        ],
      })) {
        if (requestNonce.value !== requestId) return

        rawText += chunk
        const cleaned = sanitizeModelOutput(rawText).content.trim()
        if (cleaned && !shouldFallbackToMock(cleaned)) {
          updateSceneResponse(role, { text: cleaned, status: 'streaming' })
        }
      }

      if (requestNonce.value !== requestId) return

      const finalContent = sanitizeModelOutput(rawText).content.trim()
      updateSceneResponse(role, {
        text: finalContent && !shouldFallbackToMock(finalContent) ? finalContent : fallbackText,
        status: 'done',
      })
    } catch {
      if (requestNonce.value !== requestId) return
      updateSceneResponse(role, {
        text: fallbackText,
        status: 'error',
      })
    } finally {
      if (requestNonce.value === requestId) setResponseState(role, 'done')
    }
  }

  async function buildLiveScene(sceneId: string, sceneRound: number, lastChoice?: StoryLiteV2Choice) {
    const baseScene = buildSceneFromMock(sceneId)
    const assignment = modelAssignment.value
    if (!assignment || baseScene.responses.length === 0) return baseScene

    const requestId = requestNonce.value + 1
    requestNonce.value = requestId
    currentScene.value = buildPendingScene(sceneId)
    resetResponseState('loading')

    await Promise.allSettled(
      ROLE_ORDER.map((role) => streamRoleResponse(sceneId, role, sceneRound, requestId, lastChoice)),
    )

    if (requestNonce.value !== requestId || !currentScene.value) return baseScene

    currentScene.value = {
      ...currentScene.value,
      choices: baseScene.choices.map((choice) => ({ ...choice })),
      ending: baseScene.ending ? { ...baseScene.ending } : undefined,
    }

    return currentScene.value
  }

  function init(seed?: string, restoredSession?: SavedSession | null) {
    // If no restored session provided, try to load from localStorage
    if (!restoredSession) {
      restoredSession = loadSession()
    }

    if (restoredSession && Date.now() - restoredSession.timestamp < 24 * 60 * 60 * 1000) {
      // Restore from saved session (valid for 24 hours)
      seedLabel.value = restoredSession.seedLabel
      round.value = restoredSession.round
      sceneHistory.value = restoredSession.sceneHistory
      currentScene.value = restoredSession.currentScene
      manuallyEnded.value = restoredSession.manuallyEnded
      streamingPremise.value = ''
      syncModelAssignment()
      return
    }

    // New game initialization
    const nextSeed = seed?.trim() || '公路异变悬疑'
    seedLabel.value = nextSeed
    round.value = 0
    currentScene.value = null
    processing.value = false
    error.value = ''
    activeChoiceLabel.value = ''
    requestNonce.value += 1
    resetResponseState()
    sceneHistory.value = []
    manuallyEnded.value = false
    streamingPremise.value = ''
    syncModelAssignment()
    clearSession()
  }

  async function startGame() {
    if (processing.value) return

    await appStore.ensureModelsLoaded()
    syncModelAssignment()

    if (!modelAssignment.value) {
      error.value = '当前没有可用模型，请先选择模型后再开始。'
      return
    }

    processing.value = true
    error.value = ''
    activeChoiceLabel.value = ''

    try {
      const nextRound = 1
      round.value = nextRound

      if (useMock.value) {
        const scene = buildSceneFromMock('start')
        currentScene.value = scene
        resetResponseState('done')
        await streamPremise(scene.premise, 12)
      } else {
        currentScene.value = await buildLiveSceneDynamic(nextRound)
        if (currentScene.value) {
          sceneHistory.value = [{ round: nextRound, premise: currentScene.value.premise }]
        }
      }
    } catch (e: any) {
      error.value = e?.message || '生成场景失败'
      const scene = buildSceneFromMock('start')
      currentScene.value = scene
      round.value = 1
      resetResponseState('done')
      await streamPremise(scene.premise, 12)
    } finally {
      processing.value = false
      persist()
    }
  }

  async function makeChoice(choiceId: string) {
    if (!currentScene.value || processing.value) return

    const choice = currentScene.value.choices.find((item) => item.id === choiceId)
    if (!choice) return

    processing.value = true
    error.value = ''
    activeChoiceLabel.value = choice.label

    try {
      const nextRound = round.value + 1
      round.value = nextRound

      if (useMock.value) {
        const nextSceneId = STORY_LITE_V2_BRANCHES[currentScene.value.id]?.[choiceId] || 'ending-normal'
        const scene = buildSceneFromMock(nextSceneId)
        currentScene.value = scene
        resetResponseState('done')
        await streamPremise(scene.premise, 12)
      } else {
        currentScene.value = await buildLiveSceneDynamic(nextRound, choice)
        if (currentScene.value) {
          sceneHistory.value = [
            ...sceneHistory.value,
            { round: nextRound, premise: currentScene.value.premise, choiceLabel: choice.label },
          ]
        }
      }
    } catch (e: any) {
      error.value = e?.message || '推进剧情失败'
      if (useMock.value) {
        const scene = buildSceneFromMock('ending-normal')
        currentScene.value = scene
        round.value += 1
        resetResponseState('done')
        await streamPremise(scene.premise, 25)
      }
    } finally {
      processing.value = false
      activeChoiceLabel.value = ''
      persist()
    }
  }

  function persist() {
    if (!isStarted.value) return
    const state: SavedSession = {
      seedLabel: seedLabel.value,
      round: round.value,
      sceneHistory: sceneHistory.value,
      currentScene: currentScene.value,
      isCompleted: isCompleted.value,
      manuallyEnded: manuallyEnded.value,
      timestamp: Date.now(),
    }
    saveSession(state)
  }

  function restart() {
    clearSession()
    init(seedLabel.value)
  }

  function endStory() {
    manuallyEnded.value = true
    persist()
  }

  return {
    currentScene,
    seedLabel,
    round,
    processing,
    error,
    useMock,
    modelAssignment,
    connectionMode,
    activeChoiceLabel,
    responseStates,
    sceneHistory,
    streamingPremise,
    isCompleted,
    isStarted,
    usesLiveModels,
    readyResponseCount,
    manuallyEnded,
    init,
    startGame,
    makeChoice,
    restart,
    endStory,
    persist,
    getModelName,
  }
})
