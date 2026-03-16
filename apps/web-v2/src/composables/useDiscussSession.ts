import { ref, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { streamModelChat } from '@/services/runtime'
import type { Phase1Result, Phase2Result, DiscussDepth, RollupResult } from '@/stores/discuss'

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

const ROLLUP_SYSTEM_PROMPT = `You are an independent synthesis agent.

GOAL:
Produce a single, actionable plan that integrates the most reliable elements of the discussion.

RULES:
- Do NOT summarize opinions.
- Do NOT list viewpoints.
- Produce ONE coherent solution.
- Prefer practicality over theoretical optimality.
- Resolve conflicts explicitly.
- If uncertainty exists, propose a safe default.
- The result must be immediately usable.

OUTPUT REQUIREMENTS (use Markdown):

## 行动计划
A concrete, actionable solution.

## 核心理由
Why this plan is preferred.

## 取舍
What is sacrificed and why it's acceptable.

## 风险与约束
Situations where this may fail.

## 失效条件
When this plan should NOT be used.

## 下一步
Clear actions the user can take now (numbered list).

If no viable plan exists, say so and explain what information is missing.`

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
  let result = ''
  const stream = streamModelChat({
    modelId,
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
  const rollupText = ref('')
  const rollupModel = ref('')
  const rollupPhase = ref<'idle' | 'streaming' | 'done'>('idle')
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
      const stream = streamModelChat({
        modelId: synthesisModel,
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

  async function startRollup(prompt: string, modelIds: string[], overrideModelId?: string) {
    if (streaming.value || rollupPhase.value === 'streaming') return
    if (phase1Results.value.length === 0) return

    rollupPhase.value = 'streaming'
    rollupText.value = ''
    abortController.value = new AbortController()
    const signal = abortController.value.signal

    // Pick rollup model: prefer non-participating, highest tier
    const participating = new Set(modelIds)
    const candidates = appStore.models
      .filter((m) => !participating.has(m.id))
      .sort((a, b) => b.tier - a.tier)
    const rollupModelId = overrideModelId || (candidates.length ? candidates[0].id : modelIds[0])
    const modelMeta = appStore.models.find((m) => m.id === rollupModelId)
    rollupModel.value = modelMeta?.name ?? rollupModelId

    const analysisContext = phase1Results.value
      .map((r) => `[${r.model}] 方案: ${r.data.approach}; 理由: ${r.data.reasoning}; 风险: ${r.data.risks.join(', ')}`)
      .join('\n')
    const reviewContext = phase2Results.value
      .map((r) => `[${r.reviewer} → ${r.target}] 同意: ${r.data.agreement}; 质疑: ${r.data.challenge}; 建议: ${r.data.betterOption}`)
      .join('\n')
    const synthesisContext = phase3Text.value ? `\n\n综合结论：\n${phase3Text.value}` : ''

    const userPrompt = `原始问题：${prompt}\n\n各模型独立分析：\n${analysisContext}\n\n交叉审查：\n${reviewContext}${synthesisContext}\n\n请根据以上讨论内容，生成一份统一的行动计划。`

    try {
      const stream = streamModelChat({
        modelId: rollupModelId,
        messages: [
          { role: 'system', content: ROLLUP_SYSTEM_PROMPT },
          { role: 'user', content: userPrompt },
        ],
        signal,
      })
      for await (const chunk of stream) {
        if (signal.aborted) return
        rollupText.value += chunk
      }
    } catch (e: any) {
      if (e.name !== 'AbortError' && !signal.aborted) {
        if (!rollupText.value) {
          rollupText.value = `> Rollup 失败: ${e.message}`
        }
      }
    } finally {
      rollupPhase.value = 'done'
      abortController.value = null
    }
  }

  function reset() {
    stop()
    phase.value = 0
    phase1Results.value = []
    phase2Results.value = []
    phase3Text.value = ''
    rollupText.value = ''
    rollupModel.value = ''
    rollupPhase.value = 'idle'
  }

  return {
    phase, streaming, depth, isActive,
    phase1Results, phase2Results, phase3Text,
    rollupText, rollupModel, rollupPhase,
    start, startRollup, stop, reset,
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
