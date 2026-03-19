import type {
  DirectorOutput,
  EmotionOutput,
  LogicOutput,
  StoryLiteRoundContext,
  TwistOutput,
} from './types'
import { STORY_LITE_PROMPT_VERSION } from './constants'

function buildContextBlock(context: StoryLiteRoundContext) {
  const historyText = context.recentHistorySummary.length
    ? context.recentHistorySummary.map((item) => `- ${item}`).join('\n')
    : '- 无'

  const threadText = context.availableThreads?.length
    ? context.availableThreads.map((item) => `- ${item}`).join('\n')
    : '- 无'

  return [
    `promptVersion: ${STORY_LITE_PROMPT_VERSION}`,
    `sessionId: ${context.sessionId}`,
    `round: ${context.round}`,
    `seed: ${context.seedLabel}`,
    '',
    '当前局势：',
    context.sceneSummary,
    '',
    '近期摘要：',
    historyText,
    '',
    '活跃线索：',
    threadText,
    '',
    `上一轮选择：${context.lastPlayerChoice ?? '无'}`,
    `storyState: ${JSON.stringify(context.storyState)}`,
  ].join('\n')
}

export function buildLogicPrompt(context: StoryLiteRoundContext) {
  return `${buildContextBlock(context)}

你是 Logic Agent。
任务：
- 分析当前局势
- 给出 2-3 个可执行选择
- 至少指出一个可证伪的事实判断

严格输出 JSON：
{
  "insight": "string",
  "risk": "string",
  "choices": [
    { "id": "string", "label": "string", "risk": "low|medium|high" }
  ]
}`
}

export function buildEmotionPrompt(context: StoryLiteRoundContext) {
  return `${buildContextBlock(context)}

你是 Emotion Agent。
任务：
- 给出人物动机判断
- 给出情绪或关系张力
- 不新增客观事实

严格输出 JSON：
{
  "feeling": "string",
  "motivation": "string",
  "tension": "string"
}`
}

export function buildTwistPrompt(context: StoryLiteRoundContext) {
  return `${buildContextBlock(context)}

你是 Twist Agent。
任务：
- 提供一个可选的候选变化
- 变化必须和当前局势有因果关系
- 不要直接决定它一定发生

严格输出 JSON：
{
  "candidateEvent": "string",
  "reason": "string",
  "intensity": "low|medium|high"
}`
}

export function buildDirectorPrompt(
  context: StoryLiteRoundContext,
  logic: LogicOutput,
  emotion: EmotionOutput,
  twist: TwistOutput | null,
) {
  return `${buildContextBlock(context)}

你是 hidden Director，不对用户出面。
你要仲裁 Logic / Emotion / Twist 的候选输出，并合并成一个一致的单轮结果。

Logic:
${JSON.stringify(logic, null, 2)}

Emotion:
${JSON.stringify(emotion, null, 2)}

Twist:
${twist ? JSON.stringify(twist, null, 2) : 'null'}

要求：
- 可以拒绝 Twist
- 产出一条用户可读 summary
- 输出 history entry 所需最小字段

严格输出 JSON：
{
  "summary": "string",
  "acceptedTwist": true,
  "briefing": "string",
  "outcome": "string",
  "statePatch": {},
  "historyEntry": {
    "type": "story_turn",
    "summary": "string"
  }
}`
}

export function isLogicOutput(value: unknown): value is LogicOutput {
  return typeof value === 'object' && value !== null && 'insight' in value && 'choices' in value
}

export function isEmotionOutput(value: unknown): value is EmotionOutput {
  return typeof value === 'object' && value !== null && 'feeling' in value && 'tension' in value
}

export function isTwistOutput(value: unknown): value is TwistOutput {
  return typeof value === 'object' && value !== null && 'candidateEvent' in value && 'intensity' in value
}

export function isDirectorOutput(value: unknown): value is DirectorOutput {
  return typeof value === 'object' && value !== null && 'summary' in value && 'historyEntry' in value
}
