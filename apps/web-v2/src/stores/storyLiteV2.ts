import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useAppStore } from './app'
import { streamModelChat } from '@/services/runtime'
import { sanitizeModelOutput } from '@/utils/modelOutput'
import {
  STORY_LITE_V2_ROLES,
  STORY_LITE_V2_BRANCHES,
  STORY_LITE_V2_MOCK_SCENES,
  buildStoryLiteV2SystemPrompt,
  buildStoryLiteV2UserPrompt,
  type StoryLiteV2Choice,
  type StoryLiteV2Response,
  type StoryLiteV2Role,
  type StoryLiteV2Scene,
} from '@/features/play-modes/story-lite-v2'

const ROLE_ORDER: StoryLiteV2Role[] = ['guide', 'partner', 'variable']
const DEMO_MODEL_IDS = ['demo/claude-sonnet-4', 'demo/gpt-4.1', 'demo/gemini-2.5-pro']

function isUsingDemoModels(modelIds: string[]) {
  return modelIds.length > 0 && modelIds.every((id) => id.startsWith('demo/'))
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

async function collectText(stream: AsyncGenerator<string>) {
  let text = ''
  for await (const chunk of stream) {
    text += chunk
  }
  return text.trim()
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

  const isCompleted = computed(() => currentScene.value?.ending != null)
  const isStarted = computed(() => round.value > 0 || currentScene.value != null)

  function getModelName(modelId: string) {
    if (modelId.startsWith('mock-')) return '模拟角色'
    return appStore.getModel(modelId)?.name || modelId
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
    const template = STORY_LITE_V2_MOCK_SCENES[sceneId] || STORY_LITE_V2_MOCK_SCENES.start

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
            }
          })
        : [],
      choices: template.choices.map((choice) => ({ ...choice })),
      ending: template.ending ? { ...template.ending } : undefined,
    } satisfies StoryLiteV2Scene
  }

  async function callModel(modelId: string, systemPrompt: string, userPrompt: string) {
    return collectText(streamModelChat({
      modelId,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
    }))
  }

  async function buildLiveScene(sceneId: string, lastChoice?: StoryLiteV2Choice) {
    const baseScene = buildSceneFromMock(sceneId)
    const assignment = modelAssignment.value
    if (!assignment || baseScene.responses.length === 0) return baseScene

    const responses: StoryLiteV2Response[] = []
    for (const role of ROLE_ORDER) {
      const fallback = buildFallbackResponse(role, baseScene)
      const modelId = assignment[role]

      try {
        const rawText = await callModel(
          modelId,
          buildStoryLiteV2SystemPrompt(role),
          buildStoryLiteV2UserPrompt(
            seedLabel.value,
            round.value + 1,
            baseScene.premise,
            lastChoice
              ? {
                  role: lastChoice.targetRole ? STORY_LITE_V2_ROLES[lastChoice.targetRole].label : '当前局面',
                  label: lastChoice.label,
                }
              : undefined,
          ),
        )

        const content = sanitizeModelOutput(rawText).content.trim()
        responses.push({
          ...fallback,
          modelId,
          modelName: getModelName(modelId),
          text: shouldFallbackToMock(content) ? fallback.text : content,
        })
      } catch {
        responses.push(fallback)
      }
    }

    return {
      ...baseScene,
      responses,
    } satisfies StoryLiteV2Scene
  }

  function init(seed?: string) {
    const nextSeed = seed?.trim() || '公路异变悬疑'
    const selectedIds = appStore.selectedModelIds.filter((id) => appStore.getModel(id))

    seedLabel.value = nextSeed
    round.value = 0
    currentScene.value = null
    processing.value = false
    error.value = ''
    useMock.value = selectedIds.length === 0 || isUsingDemoModels(selectedIds)
    modelAssignment.value = assignRoles(selectedIds)
  }

  async function startGame() {
    if (processing.value) return
    if (!modelAssignment.value) {
      error.value = '当前没有可用模型，请先选择模型后再开始。'
      return
    }

    processing.value = true
    error.value = ''

    try {
      currentScene.value = useMock.value
        ? buildSceneFromMock('start')
        : await buildLiveScene('start')
      round.value = 1
    } catch (e: any) {
      error.value = e?.message || '生成场景失败'
      currentScene.value = buildSceneFromMock('start')
      round.value = 1
    } finally {
      processing.value = false
    }
  }

  async function makeChoice(choiceId: string) {
    if (!currentScene.value || processing.value) return

    const choice = currentScene.value.choices.find((item) => item.id === choiceId)
    if (!choice) return

    processing.value = true
    error.value = ''

    try {
      const nextSceneId = STORY_LITE_V2_BRANCHES[currentScene.value.id]?.[choiceId] || 'ending-normal'
      currentScene.value = useMock.value
        ? buildSceneFromMock(nextSceneId)
        : await buildLiveScene(nextSceneId, choice)
      round.value += 1
    } catch (e: any) {
      error.value = e?.message || '推进剧情失败'
      currentScene.value = buildSceneFromMock('ending-normal')
      round.value += 1
    } finally {
      processing.value = false
    }
  }

  function restart() {
    init(seedLabel.value)
  }

  return {
    currentScene,
    seedLabel,
    round,
    processing,
    error,
    useMock,
    modelAssignment,
    isCompleted,
    isStarted,
    init,
    startGame,
    makeChoice,
    restart,
    getModelName,
  }
})
