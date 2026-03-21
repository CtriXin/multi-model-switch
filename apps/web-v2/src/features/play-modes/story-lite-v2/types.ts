/**
 * StoryLite V2 - 多 AI 共演版剧情冒险
 *
 * 设计原则：
 * - 3 个 AI 扮演不同角色（类似 Story Live 但更轻量）
 * - 用户选择回应哪个 AI，驱动剧情分支
 * - 无复杂状态机，纯角色对话驱动
 */

import type { HistoryEntry, PlayModeSessionEnvelope } from '../shared'

export const STORY_LITE_V2_MODE_ID = 'story-lite-v2'
export const STORY_LITE_V2_ROUTE_ID = 'story-lite'
export const STORY_LITE_V2_DEFAULT_MAX_ROUNDS = 5

/** 三个 AI 角色定位 */
export type StoryLiteV2Role = 'guide' | 'partner' | 'variable'
export type StoryLiteV2ConnectionMode = 'demo' | 'selected-live' | 'auto-live'

export type StoryLiteV2Phase = 'seed' | 'assigning' | 'narrating' | 'player_choice' | 'resolving' | 'ended'

export type StoryLiteV2RiskLevel = 'safe' | 'risky' | 'dangerous'

/** 每个 AI 角色的元信息 */
export interface StoryLiteV2RoleMeta {
  id: StoryLiteV2Role
  label: string           // 显示名称，如"引路人"
  title: string           // 职责描述，如"任务指引"
  accent: string          // 主题色 class
  icon: string            // icon 名称
  systemPrompt: string    // 角色 system prompt
}

/** AI 回复内容 */
export interface StoryLiteV2Response {
  role: StoryLiteV2Role
  modelId: string
  modelName: string
  text: string
  tone?: string           // 语气提示，如"冷静"、"焦虑"、"神秘"
  status?: 'pending' | 'streaming' | 'done' | 'error'
}

/** 玩家选择项 */
export interface StoryLiteV2Choice {
  id: string
  label: string           // 选项文案
  targetRole?: StoryLiteV2Role  // 回应哪个 AI（可选）
  risk: StoryLiteV2RiskLevel
  hint?: string
}

/** 场景数据结构 */
export interface StoryLiteV2Scene {
  id: string
  chapter: string
  title: string
  premise: string         // 当前情境
  responses: StoryLiteV2Response[]  // 3 个 AI 的回复
  choices: StoryLiteV2Choice[]
  ending?: {
    kind: 'good' | 'normal' | 'bad' | 'mystery'
    title: string
    summary: string
    epilogue?: string
  }
}

/** Session Meta */
export interface StoryLiteV2SessionMeta {
  phase: StoryLiteV2Phase
  seedLabel: string       // 用户输入的"假如 XXX"
  currentSceneId: string
  round: number
  maxRounds: number
  modelAssignment: Record<StoryLiteV2Role, string>  // 角色→模型绑定
  historySummary: string[]
}

export interface StoryLiteV2SessionEnvelope extends PlayModeSessionEnvelope {
  mode: 'story-lite'
  meta: StoryLiteV2SessionMeta & Record<string, unknown>
  history: Array<HistoryEntry & { type: 'story_turn' | 'ending' }>
}

/** Prompt 构建所需上下文 */
export interface StoryLiteV2PromptContext {
  sessionId: string
  seedLabel: string
  round: number
  premise: string
  lastResponses?: StoryLiteV2Response[]
  lastChoice?: { role: StoryLiteV2Role; label: string }
  modelAssignment: Record<StoryLiteV2Role, string>
}

/** 导演 AI 生成的场景结构（JSON 解析后） */
export interface DirectorSceneOutput {
  premise: string
  choices: Array<{
    id: string
    label: string
    risk: StoryLiteV2RiskLevel
    hint?: string
  }>
}

/** 导演 AI 的上下文积累条目 */
export interface SceneHistoryEntry {
  round: number
  premise: string
  choiceLabel?: string
}

/** 角色定义常量 */
export const STORY_LITE_V2_ROLES: Record<StoryLiteV2Role, StoryLiteV2RoleMeta> = {
  guide: {
    id: 'guide',
    label: '引路人',
    title: '主线推进',
    accent: 'text-cyan-400',
    icon: 'Target',
    systemPrompt: `你是"假如模拟器"中的引路人。你代表理性、效率和目标导向。

【核心视角】
- 当前局势中最紧迫的任务是什么？
- 资源、时间、信息，哪个是瓶颈？
- 如果不立即行动，最坏的结果是什么？

【表达风格】
- 冷静、直接、不带情绪
- 像经验丰富的指挥官或项目经理
- 承认代价，但不沉溺于情感

【输出要求】
- 中文，25-50 字
- 直接点明：现在最该做什么，为什么
- 禁止：安慰、道德评判、阴谋论
- 例："先封锁消息。一旦失控，你手头的筹码会瞬间归零。"`,
  },
  partner: {
    id: 'partner',
    title: '关系代价',
    label: '伙伴',
    accent: 'text-rose-400',
    icon: 'Heart',
    systemPrompt: `你是"假如模拟器"中的同行者。你代表人情、羁绊和道德重量。

【核心视角】
- 这个选择会伤害谁？辜负谁？
- 谁正在等待、信任、或恐惧地看着你？
- 如果只看结果不看人心，你会失去什么？

【表达风格】
- 有温度，但不煽情
- 像真正关心你的朋友，说出你不想听的真话
- 提醒代价，但不绑架决定

【输出要求】
- 中文，25-50 字
- 聚焦具体的人或关系，而非抽象概念
- 禁止：空谈道德、替用户选择、冷静分析
- 例："你母亲还在等你电话。赢了全世界，输了她，你真的能面对吗？"`,
  },
  variable: {
    id: 'variable',
    title: '异常变量',
    label: '变量',
    accent: 'text-amber-400',
    icon: 'Sparkles',
    systemPrompt: `你是"假如模拟器"中的异常观察者。你代表质疑、隐藏真相和打破框架。

【核心视角】
- 这个情境中有什么"太合理"到可疑的地方？
- 谁在受益？谁在引导你的注意力？
- 如果前提本身就是错的，真正的出口在哪？

【表达风格】
- 神秘但不故弄玄虚
- 抛出线索而非答案
- 像知情者暗示，而非旁观者猜测

【输出要求】
- 中文，20-40 字
- 必须指出一个具体的不合理细节或隐藏关联
- 禁止：重复主线建议、直接揭底、无依据猜测
- 例："监控时间戳比事件早7秒。有人提前知道你会来这里。"`,
  },
}
