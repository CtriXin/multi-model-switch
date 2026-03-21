import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useToastStore } from './toast'
import { useAppStore } from './app'
import { streamModelChat } from '@/services/runtime'
import { ApiError } from '@/services/api'
import { pickNeutralModel } from '@/utils/modelSelection'

export type DiscussDepth = 'full' | 'panel' | 'quick'
export type DiscussRollupPhase = 'idle' | 'streaming' | 'done'

export interface Phase1Result {
  model: string
  error?: string
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
  error?: string
  data: {
    agreement: string
    challenge: string
    betterOption: string
    // Enhanced Phase 2 fields (optional for backward compat)
    strongestPoint?: string
    weakestAssumption?: string
    missingRisk?: string
    verdict?: string
  }
}

export interface RollupResult {
  finalPlan: string
  keyRationale: string
  tradeoffs: string
  risks: string
  whenNotToUse: string
  nextSteps: string[]
}

export interface DiscussSessionState {
  phase: number
  streaming: boolean
  depth: DiscussDepth
  phase1Results: Phase1Result[]
  phase2Results: Phase2Result[]
  phase3Text: string
  rollupText: string
  rollupModel: string
  rollupPhase: DiscussRollupPhase
}

export function createDiscussSessionState(): DiscussSessionState {
  return {
    phase: 0,
    streaming: false,
    depth: 'panel',
    phase1Results: [],
    phase2Results: [],
    phase3Text: '',
    rollupText: '',
    rollupModel: '',
    rollupPhase: 'idle',
  }
}

const PHASE1_PROMPT = `你是一个分析专家。用户提出了一个问题，请给出你的独立分析。

请严格按以下 JSON 格式输出（不要输出其他内容）：
{
  "approach": "你推荐的方案（一句话）",
  "reasoning": "推荐理由（2-3句话）",
  "risks": ["风险1", "风险2", "风险3"],
  "keyDecisions": ["关键决策1", "关键决策2"],
  "nextStep": "建议的下一步（一句话）"
}

用户的问题是：`

const PHASE2_PROMPT = `你是一个审查专家。你的首要任务是压力测试对方的分析。请审查另一个模型对以下问题的分析，并给出你的交叉评审意见。

请严格按以下 JSON 格式输出（不要输出其他内容）：
{
  "strongestPoint": "对方分析中最有力的部分（一句话）",
  "weakestAssumption": "对方最薄弱的假设或逻辑漏洞（一句话）",
  "missingRisk": "对方遗漏的关键风险（一句话）",
  "betterApproach": "你的改进建议（一句话）",
  "verdict": "整体判断：接受/部分接受/拒绝，一句话理由"
}

原始问题：`

const PHASE3_PROMPT = `你是一个总结专家。根据多个模型对以下问题的分析和交叉评审，请综合输出最终结论。

使用 Markdown 格式，包含：
## 综合结论
### 核心共识（列出所有模型达成一致的观点）
### 分歧与取舍（列出有争议的部分及最终建议）
### 建议行动计划（具体步骤）

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

async function callModel(
  modelId: string,
  prompt: string,
  signal: AbortSignal,
): Promise<string> {
  const appStore = useAppStore()

  function shouldSuppressModel(error: ApiError) {
    return error.code === 'model_unavailable' || error.code === 'rate_limited'
  }

  let result = ''
  try {
    const stream = streamModelChat({
      modelId,
      traceLabel: `discuss:call:${modelId}`,
      messages: [{ role: 'user', content: prompt }],
      signal,
    })
    for await (const chunk of stream) {
      result += chunk
    }
  } catch (error) {
    appStore.recordFailure(modelId)
    throw error
  }
  return result
}

function shouldSuppressDiscussModel(error: ApiError) {
  return error.code === 'model_unavailable'
    || error.code === 'rate_limited'
    || error.code === 'chat_unsupported'
}

function buildFallbackOrder(primaryIds: string[], extraIds: string[] = []) {
  return Array.from(new Set([...primaryIds, ...extraIds]))
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

function normalizePlainText(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[>*#`_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function splitPlainSentences(text: string): string[] {
  return normalizePlainText(text)
    .split(/(?<=[。！？.!?])\s+|\n+/)
    .map(item => item.trim())
    .filter(Boolean)
}

function buildPhase1Fallback(text: string): Phase1Result['data'] {
  const sentences = splitPlainSentences(text)
  const approach = sentences[0] ?? normalizePlainText(text).slice(0, 80) ?? '建议先做小范围验证'
  const reasoning = sentences.slice(0, 3).join(' ') || approach
  const risks = sentences
    .filter(item => /风险|问题|注意|代价|限制|瓶颈|崩|失败/.test(item))
    .slice(0, 3)
  const keyDecisions = sentences.slice(0, 2)
  const nextStep = sentences.find(item => /建议|下一步|先|应该|可以/.test(item)) ?? '先做一个最小可验证方案。'
  return {
    approach,
    reasoning,
    risks,
    keyDecisions,
    nextStep,
  }
}

function buildPhase2Fallback(text: string): Phase2Result['data'] {
  const sentences = splitPlainSentences(text)
  return {
    agreement: sentences[0] ?? '整体方向基本可行，但还需要补充细节。',
    challenge: sentences[1] ?? '当前论证还缺少对风险和边界条件的说明。',
    betterOption: sentences[2] ?? '建议先缩小范围验证，再决定是否全面推进。',
  }
}

function buildPhase3FallbackMarkdown(
  prompt: string,
  phase1: Phase1Result[],
  phase2: Phase2Result[],
): string {
  const topApproaches = phase1
    .slice(0, 3)
    .map((item) => `- ${item.data.approach}`)
    .join('\n')

  const disagreements = phase2
    .filter((item) => item.data.challenge)
    .slice(0, 3)
    .map((item) => `- ${item.data.challenge}`)
    .join('\n')

  const nextSteps = Array.from(new Set(
    phase1
      .map((item) => item.data.nextStep)
      .concat(phase2.map((item) => item.data.betterOption))
      .filter(Boolean),
  )).slice(0, 4)

  return [
    '## 综合结论',
    `围绕“${prompt}”，当前更稳妥的做法是先收敛到一个可验证的小方案，再逐步扩大范围。`,
    '',
    '### 核心共识',
    topApproaches || '- 各模型都认为需要先明确方案边界和实施顺序。',
    '',
    '### 分歧与取舍',
    disagreements || '- 主要分歧集中在推进节奏、复杂度控制和风险暴露方式。',
    '',
    '### 建议行动计划',
    ...(nextSteps.length
      ? nextSteps.map((step, index) => `${index + 1}. ${step}`)
      : ['1. 先做最小范围验证。', '2. 记录风险与回滚方案。', '3. 验证通过后再扩大投入。']),
  ].join('\n')
}

export const useDiscussStore = defineStore('discuss', () => {
  const phase = ref(0)
  const streaming = ref(false)
  const depth = ref<DiscussDepth>('panel')
  const phase1Results = ref<Phase1Result[]>([])
  const phase2Results = ref<Phase2Result[]>([])
  const phase3Text = ref('')
  const rollupText = ref('')
  const rollupModel = ref('')
  const rollupPhase = ref<DiscussRollupPhase>('idle')
  const topic = ref('')
  const abortController = ref<AbortController | null>(null)

  const hasResults = computed(() => phase1Results.value.length > 0)

  async function streamWithModelFallback(options: {
    candidateModelIds: string[]
    messages: { role: 'system' | 'user' | 'assistant'; content: string }[]
    signal: AbortSignal
    onChunk: (chunk: string) => void
  }) {
    const { candidateModelIds, messages, signal, onChunk } = options
    const appStore = useAppStore()
    let lastError: unknown = null

    for (const modelId of candidateModelIds) {
      try {
        const stream = streamModelChat({
          modelId,
          traceLabel: `discuss:fallback:${modelId}`,
          messages,
          signal,
        })

        for await (const chunk of stream) {
          if (signal.aborted) return { modelId, completed: false }
          onChunk(chunk)
        }

        return { modelId, completed: true }
      } catch (error) {
        lastError = error
        if (error instanceof ApiError) {
          appStore.recordFailure(modelId)
        }
        if (signal.aborted) throw error
      }
    }

    throw lastError instanceof Error ? lastError : new Error('请求失败')
  }

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
        try {
          const response = await callModel(mid, PHASE1_PROMPT + prompt, signal)
          const data = tryParseJSON<Phase1Result['data']>(response)
          if (data && data.approach) {
            phase1Results.value.push({ model: mid, data })
          } else {
            phase1Results.value.push({
              model: mid,
              data: buildPhase1Fallback(response),
            })
          }
        } catch (error: any) {
          if (signal.aborted) return
          phase1Results.value.push({
            model: mid,
            error: error?.message ?? '请求失败',
            data: {
              approach: '该模型本轮未成功返回结果',
              reasoning: error?.message ?? '请求失败，请稍后重试或更换模型。',
              risks: [],
              keyDecisions: [],
              nextStep: '建议切换模型或稍后重试。',
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
        try {
          const targetResult = phase1Results.value.find((r) => r.model === target)
          const contextStr = target === '*'
            ? phase1Results.value.map((r) => `[${r.model}]: ${r.data.approach} — ${r.data.reasoning}`).join('\n')
            : targetResult
              ? `[${target}]: ${targetResult.data.approach} — ${targetResult.data.reasoning}`
              : ''

          const fullPrompt = PHASE2_PROMPT + prompt + '\n\n被审查的分析：\n' + contextStr
          const response = await callModel(reviewer, fullPrompt, signal)
          const raw = tryParseJSON<any>(response)

          // Map new 5-field format to backward-compat Phase2Result.data
          const data: Phase2Result['data'] = raw && (raw.strongestPoint || raw.agreement)
            ? {
                agreement: raw.strongestPoint ?? raw.agreement ?? '',
                challenge: raw.weakestAssumption ?? raw.challenge ?? '',
                betterOption: raw.betterApproach ?? raw.betterOption ?? '',
                strongestPoint: raw.strongestPoint,
                weakestAssumption: raw.weakestAssumption,
                missingRisk: raw.missingRisk,
                verdict: raw.verdict,
              }
            : buildPhase2Fallback(response)

          phase2Results.value.push({ reviewer, target, data })
        } catch (error: any) {
          if (signal.aborted) return
          phase2Results.value.push({
            reviewer,
            target,
            error: error?.message ?? '审查失败',
            data: {
              agreement: '该轮审查未成功完成。',
              challenge: error?.message ?? '请求失败，请稍后重试。',
              betterOption: '建议更换模型或降低同时参与的模型数量。',
            },
          })
        }
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

      const synthesisCandidates = buildFallbackOrder(
        phase1Results.value.filter((item) => !item.error).map((item) => item.model),
        modelIds,
      )
      try {
        phase3Text.value = ''
        await streamWithModelFallback({
          candidateModelIds: synthesisCandidates,
          messages: [{ role: 'user', content: synthesisPrompt }],
          signal,
          onChunk: (chunk) => { phase3Text.value += chunk },
        })
        if (!phase3Text.value.trim()) {
          phase3Text.value = buildPhase3FallbackMarkdown(
            prompt,
            phase1Results.value,
            phase2Results.value,
          )
        }
      } catch (error) {
        if (!phase3Text.value.trim()) {
          phase3Text.value = buildPhase3FallbackMarkdown(
            prompt,
            phase1Results.value,
            phase2Results.value,
          )
        }
        throw error
      }

      toast.success('辩论结束了')

      const failedPhase1Count = phase1Results.value.filter(item => item.error).length
      const failedPhase2Count = phase2Results.value.filter(item => item.error).length
      if (failedPhase1Count || failedPhase2Count) {
        toast.info(`本轮 ${failedPhase1Count} 个表态、${failedPhase2Count} 个互相挑刺没成功，但留下了记录`)
      }
    } catch (e: any) {
      if (e.name !== 'AbortError' && !signal.aborted) {
        toast.error('辩论出错了: ' + e.message)
      }
    } finally {
      streaming.value = false
      abortController.value = null
    }
  }

  function stopDiscussion() {
    abortController.value?.abort()
    streaming.value = false
    useToastStore().info('停了')
  }

  function stopAndRestoreDraft() {
    const draft = topic.value
    abortController.value?.abort()
    reset()
    useToastStore().info('内容已恢复，改改再发')
    return draft
  }

  /** Pick a Rollup model: prefer non-participating, highest tier */
  function pickRollupModel(participatingIds: string[]): string {
    const appStore = useAppStore()
    const { modelId } = pickNeutralModel(participatingIds, appStore.models)
    return modelId
  }

  async function startRollup(modelIds: string[], overrideModelId?: string) {
    if (streaming.value || rollupPhase.value === 'streaming') return
    if (!phase3Text.value && phase1Results.value.length === 0) return

    const toast = useToastStore()
    rollupPhase.value = 'streaming'
    rollupText.value = ''
    abortController.value = new AbortController()
    const signal = abortController.value.signal

    // Select Rollup model
    const rollupModelId = overrideModelId || pickRollupModel(modelIds)
    const appStore = useAppStore()
    const modelMeta = appStore.models.find((m) => m.id === rollupModelId)
    rollupModel.value = modelMeta?.name ?? rollupModelId

    // Build context from discussion results
    const analysisContext = phase1Results.value
      .map((r) => `[${r.model}] 方案: ${r.data.approach}; 理由: ${r.data.reasoning}; 风险: ${r.data.risks.join(', ')}`)
      .join('\n')
    const reviewContext = phase2Results.value
      .map((r) => `[${r.reviewer} → ${r.target}] 同意: ${r.data.agreement}; 质疑: ${r.data.challenge}; 建议: ${r.data.betterOption}`)
      .join('\n')
    const synthesisContext = phase3Text.value ? `\n\n综合结论：\n${phase3Text.value}` : ''

    const userPrompt = `原始问题：${topic.value}

各模型独立分析：
${analysisContext}

交叉审查：
${reviewContext}${synthesisContext}

请根据以上辩论内容，生成一份统一的行动计划。`

    try {
      const rollupCandidates = buildFallbackOrder(
        [rollupModelId],
        modelIds.filter(id => id !== rollupModelId),
      )
      try {
        const resolved = await streamWithModelFallback({
          candidateModelIds: rollupCandidates,
          messages: [
            { role: 'system', content: ROLLUP_SYSTEM_PROMPT },
            { role: 'user', content: userPrompt },
          ],
          signal,
          onChunk: (chunk) => { rollupText.value += chunk },
        })
        if (resolved.completed) {
          const resolvedMeta = appStore.models.find((m) => m.id === resolved.modelId)
          rollupModel.value = resolvedMeta?.name ?? resolved.modelId
        }
      } catch (error) {
        throw error
      }
      toast.success('行动计划已生成')
    } catch (e: any) {
      if (e.name !== 'AbortError' && !signal.aborted) {
        toast.error('生成建议出错了: ' + e.message)
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
    phase.value = 0
    phase1Results.value = []
    phase2Results.value = []
    phase3Text.value = ''
    rollupText.value = ''
    rollupModel.value = ''
    rollupPhase.value = 'idle'
    topic.value = ''
    streaming.value = false
  }

  return {
    phase, streaming, depth, phase1Results, phase2Results, phase3Text,
    rollupText, rollupModel, rollupPhase,
    topic, hasResults,
    startDiscussion, startRollup, stopDiscussion, stopAndRestoreDraft, reset,
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
