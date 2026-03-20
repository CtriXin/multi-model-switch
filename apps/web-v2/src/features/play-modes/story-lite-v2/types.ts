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
    title: '任务指引',
    accent: 'text-cyan-400',
    icon: 'Target',
    systemPrompt: `你是"假如模拟器"中的引路人角色。
职责：
- 给用户提供任务目标、方向指引、背景信息
- 语气冷静、专业、可靠
- 像游戏里的 NPC 导师或组织联络人

输出要求：
- 中文，30-60 字
- 提供清晰的目标或信息
- 不要替用户做决定`,
  },
  partner: {
    id: 'partner',
    title: '同行伙伴',
    label: '伙伴',
    accent: 'text-rose-400',
    icon: 'Heart',
    systemPrompt: `你是"假如模拟器"中的同行伙伴角色。
职责：
- 作为用户的搭档、队友、朋友
- 提供情感支持、不同视角、担忧或鼓励
- 语气亲切、有人情味

输出要求：
- 中文，20-50 字
- 表达感受、担忧、建议（但不强制）
- 不要替用户做决定`,
  },
  variable: {
    id: 'variable',
    title: '未知变量',
    label: '变量',
    accent: 'text-amber-400',
    icon: 'Sparkles',
    systemPrompt: `你是"假如模拟器"中的未知变量角色。
职责：
- 扮演神秘人、意外因素、剧情转折触发器
- 抛出悬念、暗示危险、制造不确定性
- 语气神秘、模棱两可

输出要求：
- 中文，15-40 字
- 制造悬念或不安感
- 不要直接揭示真相`,
  },
}
