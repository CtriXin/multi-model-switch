import { ref, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { useProviderStore } from '@/stores/provider'
import { streamChat } from '@/services/api'
import { getApiKey } from '@/services/keychain'
import type { Phase1Result, Phase2Result, DiscussDepth } from '@/stores/discuss'

export type { DiscussDepth }

export interface DiscussSessionOptions {
  prompt: string
  modelIds: string[]
  depth?: DiscussDepth
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
### 核心共识
### 分歧与取舍
### 建议行动计划

原始问题：`

function tryParseJSON<T>(text: string): T | null {
  const jsonMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/) || text.match(/(\{[\s\S]*\})/)
  if (!jsonMatch) return null
  try {
    return JSON.parse(jsonMatch[1].trim())
  } catch {
    return null
  }
}

async function callModelForSession(
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

export function useDiscussSession() {
  const appStore = useAppStore()

  const phase = ref(0)
  const streaming = ref(false)
  const depth = ref<DiscussDepth>('panel')
  const phase1Results = ref<Phase1Result[]>([])
  const phase2Results = ref<Phase2Result[]>([])
  const phase3Text = ref('')
  const abortController = ref<AbortController | null>(null)

  const isActive = computed(() => phase.value > 0)

  async function start(options: DiscussSessionOptions) {
    if (streaming.value) return

    const { prompt, modelIds, depth: d = 'panel' } = options
    depth.value = d
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
        const response = await callModelForSession(mid, PHASE1_PROMPT + prompt, signal)
        const data = tryParseJSON<Phase1Result['data']>(response)
        if (data && data.approach) {
          phase1Results.value.push({ model: mid, data })
        } else {
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
      const pairs = buildReviewPairs(modelIds, d)

      const phase2Tasks = pairs.map(async ([reviewer, target]) => {
        const targetResult = phase1Results.value.find((r) => r.model === target)
        const contextStr = target === '*'
          ? phase1Results.value.map((r) => `[${r.model}]: ${r.data.approach}`).join('\n')
          : targetResult ? `[${target}]: ${targetResult.data.approach}` : ''

        const fullPrompt = PHASE2_PROMPT + prompt + '\n\n被审查的分析：\n' + contextStr
        const response = await callModelForSession(reviewer, fullPrompt, signal)
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

      // Phase 3: Synthesis — stream
      phase.value = 3
      const summaryContext = phase1Results.value
        .map((r) => `[${r.model}] 方案: ${r.data.approach}`)
        .join('\n')
      const reviewContext = phase2Results.value
        .map((r) => `[${r.reviewer} → ${r.target}] 同意: ${r.data.agreement}; 质疑: ${r.data.challenge}`)
        .join('\n')

      const synthesisPrompt = PHASE3_PROMPT + prompt +
        '\n\n各模型分析：\n' + summaryContext +
        '\n\n交叉评审：\n' + reviewContext

      const synthesisModel = modelIds[0]
      const providerStore = useProviderStore()
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
    } finally {
      streaming.value = false
      abortController.value = null
    }
  }

  function stop() {
    abortController.value?.abort()
    streaming.value = false
  }

  function reset() {
    stop()
    phase.value = 0
    phase1Results.value = []
    phase2Results.value = []
    phase3Text.value = ''
  }

  return {
    phase, streaming, depth, isActive,
    phase1Results, phase2Results, phase3Text,
    start, stop, reset,
  }
}

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

function depthLabel(d: DiscussDepth): string {
  return d === 'full' ? '深度交叉' : d === 'panel' ? '全局审查' : '快速审查'
}
