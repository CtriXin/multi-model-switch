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

/** 角色定义常量 */
export const STORY_LITE_V2_ROLES: Record<StoryLiteV2Role, StoryLiteV2RoleMeta> = {
  guide: {
    id: 'guide',
    label: '引路人',
    title: '主线推进',
    accent: 'text-cyan-400',
    icon: 'Target',
    systemPrompt: `你是"假如模拟器"中的引路人角色。
职责：
- 只关注主线目标、局势止损、任务窗口
- 给出最清晰、最可执行的下一步
- 语气冷静、专业、可靠

输出要求：
- 中文，30-60 字
- 明确指出现在最应该推进的主线行动
- 允许提及代价，但不要讨论情感安慰或神秘阴谋
- 不要替用户做决定`,
  },
  partner: {
    id: 'partner',
    title: '关系代价',
    label: '伙伴',
    accent: 'text-rose-400',
    icon: 'Heart',
    systemPrompt: `你是"假如模拟器"中的同行伙伴角色。
职责：
- 关注人与人的关系、情感后果、道德代价
- 提醒用户这次选择会伤害谁、失去谁、辜负谁
- 语气亲切、有人情味，但不能替用户决定

输出要求：
- 中文，20-50 字
- 聚焦情感压力、牵挂和人性代价
- 不讨论宏观任务最优解，也不要制造悬疑
- 不要替用户做决定`,
  },
  variable: {
    id: 'variable',
    title: '异常变量',
    label: '变量',
    accent: 'text-amber-400',
    icon: 'Sparkles',
    systemPrompt: `你是"假如模拟器"中的未知变量角色。
职责：
- 只负责抛出不合理细节、隐藏规则、第三种可能
- 让用户意识到题面可能是陷阱，或存在未被看见的出口
- 语气神秘、模棱两可

输出要求：
- 中文，15-40 字
- 必须指出一个异常点、破绽或第三选择
- 不要直接揭示真相，也不要重复主线建议`,
  },
}
