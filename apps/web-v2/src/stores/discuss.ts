import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useToastStore } from './toast'
import { useAppStore } from './app'
import { useProviderStore } from './provider'
import { streamChat, ApiError } from '@/services/api'
import { getApiKey } from '@/services/keychain'

export type DiscussDepth = 'full' | 'panel' | 'quick'

export interface Phase1Result {
  model: string
  data: {
    approach: string
    reasoning: string
    risks: string[]
    keyDecisions: string[]
    nextStep: string
  }
}

export interface Phase2Result {
  reviewer: string
  target: string
  data: {
    agreement: string
    challenge: string
    betterOption: string
  }
}

const PHASE1_PROMPT = `你是一个技术专家。用户提出了一个技术问题，请给出你的独立分析。

请严格按以下 JSON 格式输出（不要输出其他内容）：
{
  "approach": "你推荐的方案（一句话）",
  "reasoning": "推荐理由（2-3句话）",
  "risks": ["风险1", "风险2", "风险3"],
  "keyDecisions": ["关键决策1", "关键决策2"],
  "nextStep": "建议的下一步（一句话）"
}

用户的问题是：`

const PHASE2_PROMPT = `你是一个技术审查专家。请审查另一个模型对以下问题的分析，并给出你的交叉评审意见。

请严格按以下 JSON 格式输出（不要输出其他内容）：
{
  "agreement": "你同意的部分（一句话）",
  "challenge": "你质疑的部分（一句话）",
  "betterOption": "你的改进建议（一句话）"
}

原始问题：`

const PHASE3_PROMPT = `你是一个技术总结专家。根据多个模型对以下问题的分析和交叉评审，请综合输出最终结论。

使用 Markdown 格式，包含：
## 综合结论
### 核心共识（列出所有模型达成一致的观点）
### 分歧与取舍（列出有争议的部分及最终建议）
### 建议行动计划（具体步骤）

原始问题：`

async function callModel(
  modelId: string,
  prompt: string,
  signal: AbortSignal,
): Promise<string> {
  const providerStore = useProviderStore()
  const appStore = useAppStore()

  const model = appStore.models.find((m) => m.id === modelId)
  let providerConfig = providerStore.providers.find((p) => p.id === model?.provider)
  if (!providerConfig) {
    providerConfig = providerStore.providers.find((p) => p.type === 'openrouter')
  }
  if (!providerConfig) throw new Error('未找到 API 通道')

  const apiKey = await getApiKey(providerConfig.id)
  if (!apiKey) throw new Error('API Key 未配置')

  let result = ''
  const stream = streamChat({
    provider: providerConfig,
    apiKey,
    model: modelId,
    messages: [{ role: 'user', content: prompt }],
    signal,
  })
  for await (const chunk of stream) {
    result += chunk
  }
  return result
}

function tryParseJSON<T>(text: string): T | null {
  // Extract JSON from possible markdown code block
  const jsonMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/) || text.match(/(\{[\s\S]*\})/)
  if (!jsonMatch) return null
  try {
    return JSON.parse(jsonMatch[1].trim())
  } catch {
    return null
  }
}

export const useDiscussStore = defineStore('discuss', () => {
  const phase = ref(0)
  const streaming = ref(false)
  const depth = ref<DiscussDepth>('panel')
  const phase1Results = ref<Phase1Result[]>([])
  const phase2Results = ref<Phase2Result[]>([])
  const phase3Text = ref('')
  const topic = ref('')
  const abortController = ref<AbortController | null>(null)

  const hasResults = computed(() => phase1Results.value.length > 0)

  async function startDiscussion(prompt: string, modelIds: string[], discussDepth: DiscussDepth = 'panel') {
    if (streaming.value || modelIds.length < 2) return
    const toast = useToastStore()

    topic.value = prompt
    depth.value = discussDepth
    phase.value = 1
    phase1Results.value = []
    phase2Results.value = []
    phase3Text.value = ''
    streaming.value = true
    abortController.value = new AbortController()
    const signal = abortController.value.signal

    try {
      // Phase 1: Independent analysis — parallel
      const phase1Tasks = modelIds.map(async (mid) => {
        const response = await callModel(mid, PHASE1_PROMPT + prompt, signal)
        const data = tryParseJSON<Phase1Result['data']>(response)
        if (data && data.approach) {
          phase1Results.value.push({ model: mid, data })
        } else {
          // Fallback: use raw text as approach
          phase1Results.value.push({
            model: mid,
            data: {
              approach: response.slice(0, 100),
              reasoning: response,
              risks: [],
              keyDecisions: [],
              nextStep: '',
            },
          })
        }
      })
      await Promise.allSettled(phase1Tasks)
      if (signal.aborted) return

      // Phase 2: Cross review
      phase.value = 2
      const pairs = buildReviewPairs(modelIds, discussDepth)

      const phase2Tasks = pairs.map(async ([reviewer, target]) => {
        const targetResult = phase1Results.value.find((r) => r.model === target)
        const contextStr = target === '*'
          ? phase1Results.value.map((r) => `[${r.model}]: ${r.data.approach} — ${r.data.reasoning}`).join('\n')
          : targetResult
            ? `[${target}]: ${targetResult.data.approach} — ${targetResult.data.reasoning}`
            : ''

        const fullPrompt = PHASE2_PROMPT + prompt + '\n\n被审查的分析：\n' + contextStr
        const response = await callModel(reviewer, fullPrompt, signal)
        const data = tryParseJSON<Phase2Result['data']>(response)

        phase2Results.value.push({
          reviewer,
          target,
          data: data && data.agreement
            ? data
            : { agreement: response.slice(0, 80), challenge: '', betterOption: '' },
        })
      })
      await Promise.allSettled(phase2Tasks)
      if (signal.aborted) return

      // Phase 3: Synthesis — stream the output
      phase.value = 3
      const summaryContext = phase1Results.value
        .map((r) => `[${r.model}] 方案: ${r.data.approach}; 理由: ${r.data.reasoning}`)
        .join('\n')
      const reviewContext = phase2Results.value
        .map((r) => `[${r.reviewer} → ${r.target}] 同意: ${r.data.agreement}; 质疑: ${r.data.challenge}; 建议: ${r.data.betterOption}`)
        .join('\n')

      const synthesisPrompt = PHASE3_PROMPT + prompt +
        '\n\n各模型分析：\n' + summaryContext +
        '\n\n交叉评审：\n' + reviewContext

      // Pick the first model for synthesis
      const synthesisModel = modelIds[0]
      const providerStore = useProviderStore()
      const appStore = useAppStore()
      const model = appStore.models.find((m) => m.id === synthesisModel)
      let providerConfig = providerStore.providers.find((p) => p.id === model?.provider)
      if (!providerConfig) {
        providerConfig = providerStore.providers.find((p) => p.type === 'openrouter')
      }
      if (!providerConfig) throw new Error('未找到 API 通道')

      const apiKey = await getApiKey(providerConfig.id)
      if (!apiKey) throw new Error('API Key 未配置')

      const stream = streamChat({
        provider: providerConfig,
        apiKey,
        model: synthesisModel,
        messages: [{ role: 'user', content: synthesisPrompt }],
        signal,
      })
      for await (const chunk of stream) {
        if (signal.aborted) return
        phase3Text.value += chunk
      }

      toast.success('讨论完成')
    } catch (e: any) {
      if (e.name !== 'AbortError' && !signal.aborted) {
        toast.error('讨论失败: ' + e.message)
      }
    } finally {
      streaming.value = false
      abortController.value = null
    }
  }

  function stopDiscussion() {
    abortController.value?.abort()
    streaming.value = false
    useToastStore().info('已停止讨论')
  }

  function reset() {
    phase.value = 0
    phase1Results.value = []
    phase2Results.value = []
    phase3Text.value = ''
    topic.value = ''
    streaming.value = false
  }

  return {
    phase, streaming, depth, phase1Results, phase2Results, phase3Text,
    topic, hasResults,
    startDiscussion, stopDiscussion, reset,
  }
})

function buildReviewPairs(modelIds: string[], depth: DiscussDepth): [string, string][] {
  const pairs: [string, string][] = []
  if (depth === 'full') {
    for (let i = 0; i < modelIds.length; i++) {
      for (let j = 0; j < modelIds.length; j++) {
        if (i !== j) pairs.push([modelIds[i], modelIds[j]])
      }
    }
  } else if (depth === 'panel') {
    for (const mid of modelIds) {
      pairs.push([mid, '*'])
    }
  } else {
    if (modelIds.length >= 2) {
      pairs.push([modelIds[0], modelIds[1]])
      pairs.push([modelIds[1], modelIds[0]])
    }
  }
  return pairs
}
