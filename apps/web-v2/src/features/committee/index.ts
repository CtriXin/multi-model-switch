import type { ModelMeta } from '@/stores/app'
import {
  CATEGORY_META,
  getStanceLabels,
  type PersonaDefinition,
  type PersonaCategory,
  type RolePriority,
} from '@/stores/persona'

export type CommitteeMode = 'broadcast' | 'debate' | 'committee'
export type CommitteePhase = 1 | 2 | 3
export type PhaseStatus = 'waiting' | 'running' | 'completed'

export interface CommitteeModeOption {
  id: CommitteeMode
  name: string
  tagline: string
  description: string
}

export interface RoleSummary {
  roleId: string
  modelId: string
  ok: boolean
  elapsed: number
  headline?: string
  viewpoint?: string
  tension?: string
  recommendation?: string
  content?: string
  error?: string
}

export interface DebateExchange {
  roleId: string
  targetRoleId: string
  modelId: string
  ok: boolean
  elapsed: number
  rebuttal?: string
  keepBelief?: string
  integration?: string
  raw?: string
  error?: string
}

export interface RoleModelAssignment {
  roleId: string
  modelId: string
  score: number
  reasons: string[]
}

export interface CommitteeContribution {
  roleId: string
  label: string
  reason: string
}

export interface CommitteePoint {
  id: string
  title: string
  summary: string
  roleIds: string[]
}

export interface CommitteeSynthesis {
  moderator: string
  oneLiner: string
  content: string
  contributions: CommitteeContribution[]
  consensus: CommitteePoint[]
  tensions: CommitteePoint[]
  actions: CommitteePoint[]
  minority: CommitteePoint[]
}

export interface PersonaPromptContext {
  mode: CommitteeMode
  prompt: string
  peerSummaries?: Array<{ roleName: string; viewpoint: string; tension: string }>
  targetRoleName?: string
  targetViewpoint?: string
}

export const COMMITTEE_MODE_OPTIONS: CommitteeModeOption[] = [
  {
    id: 'broadcast',
    name: '广播模式',
    tagline: '平行扫描',
    description: '一个问题，所有高参各说各的，适合先看张力和分歧。',
  },
  {
    id: 'debate',
    name: '辩论模式',
    tagline: '正面交锋',
    description: '先各自表态，再点名回应对方最强论点，适合验证冲突到底真不真。',
  },
  {
    id: 'committee',
    name: '收敛模式',
    tagline: '系统收敛',
    description: '先摆开说，再由系统主持人收成共识、分歧、动作和少数派意见。',
  },
]

function buildModelCapability(model: ModelMeta) {
  let score = model.tier * 10
  if (model.tags.includes('reasoning')) score += 2.5
  if (model.tags.includes('recommended')) score += 2
  if (model.tags.includes('vision')) score += 1
  if (model.tags.includes('coding')) score += 1.2
  if (model.tags.includes('fast')) score += 0.8
  return score
}

function priorityBoost(priority: RolePriority, rank: number, total: number) {
  if (priority === 'critical') return (total - rank) * 1.8
  if (priority === 'core') return (total - rank) * 1.1
  return (total - rank) * 0.6
}

function usagePenalty(priority: RolePriority, usage: number) {
  if (priority === 'critical') return usage * 1
  if (priority === 'core') return usage * 1.8
  return usage * 2.5
}

function scoreModelForRole(role: PersonaDefinition, model: ModelMeta, rank: number, total: number, usage: number) {
  let score = buildModelCapability(model)
  score += priorityBoost(role.priority, rank, total)
  for (const tag of role.preferredTags) {
    if (model.tags.includes(tag)) score += 2.4
  }
  if (role.priority === 'critical' && model.tier >= 2) score += 2
  if (role.priority === 'support' && model.tags.includes('fast')) score += 1.2
  return score - usagePenalty(role.priority, usage)
}

export function buildRoleModelAssignments(
  roleIds: string[],
  roles: PersonaDefinition[],
  modelPool: ModelMeta[],
): RoleModelAssignment[] {
  if (!modelPool.length) return []

  const roleMap = new Map(roles.map((role) => [role.id, role]))
  const sortedModels = [...modelPool].sort((a, b) => buildModelCapability(b) - buildModelCapability(a))
  const rankMap = new Map(sortedModels.map((model, index) => [model.id, index]))
  const usage = new Map<string, number>()

  const orderedRoles = roleIds
    .map((roleId) => roleMap.get(roleId))
    .filter((role): role is PersonaDefinition => !!role)
    .sort((a, b) => {
      const order: Record<RolePriority, number> = { critical: 0, core: 1, support: 2 }
      return order[a.priority] - order[b.priority]
    })

  const assignments = orderedRoles.map((role) => {
    let bestModel = sortedModels[0]
    let bestScore = Number.NEGATIVE_INFINITY

    for (const model of sortedModels) {
      const rank = rankMap.get(model.id) ?? 0
      const score = scoreModelForRole(role, model, rank, sortedModels.length, usage.get(model.id) ?? 0)
      if (score > bestScore) {
        bestModel = model
        bestScore = score
      }
    }

    usage.set(bestModel.id, (usage.get(bestModel.id) ?? 0) + 1)

    return {
      roleId: role.id,
      modelId: bestModel.id,
      score: bestScore,
      reasons: [
        role.priority === 'critical' ? '关键角色优先' : role.priority === 'core' ? '中枢角色匹配' : '补充角色复用',
        ...role.preferredTags.filter((tag) => bestModel.tags.includes(tag)).map((tag) => `匹配 ${tag}`),
        `模型层级 ${bestModel.tier}`,
      ],
    }
  })

  return roleIds
    .map((roleId) => assignments.find((item) => item.roleId === roleId))
    .filter((item): item is RoleModelAssignment => !!item)
}

export function pickSynthesizerModel(modelPool: ModelMeta[], assignments: RoleModelAssignment[]) {
  if (!modelPool.length) return null

  const usage = new Map<string, number>()
  for (const assignment of assignments) {
    usage.set(assignment.modelId, (usage.get(assignment.modelId) ?? 0) + 1)
  }

  return [...modelPool].sort((a, b) => {
    const aScore = buildModelCapability(a) - (usage.get(a.id) ?? 0) * 0.7
    const bScore = buildModelCapability(b) - (usage.get(b.id) ?? 0) * 0.7
    return bScore - aScore
  })[0]
}

function buildPeerContext(context: PersonaPromptContext) {
  if (!context.peerSummaries?.length) return '当前没有其他角色摘要可参考。'
  const lines = context.peerSummaries
    .slice(0, 4)
    .map((peer) => `- ${peer.roleName}：观点=${peer.viewpoint}；张力=${peer.tension}`)
  return ['其他角色已输出的关键信息：', ...lines].join('\n')
}

function buildModeInstruction(context: PersonaPromptContext) {
  if (context.mode === 'broadcast') {
    return [
      '当前运行模式：广播模式。',
      '你只负责把自己的判断讲明白，不主动替别人圆场。',
      '先说你最在意的判断，再说你看到的最大冲突，最后给出必须保留的一条建议。',
    ].join('\n')
  }

  if (context.mode === 'debate') {
    return [
      '当前运行模式：辩论模式。',
      '你的立场不因他人反对而改变，但你必须正面回应对方最强的一点。',
      `本轮你需要回应的对象：${context.targetRoleName || '另一位角色'}。`,
      context.targetViewpoint
        ? `对方上一轮的核心观点：${context.targetViewpoint}`
        : '如果没有明确对方内容，就优先回应你认为最强的对立论点。',
      '先复述对方最强一点，再说你为什么不认，最后说明你愿意吸收什么但红线不变。',
    ].join('\n')
  }

  return [
    '当前运行模式：收敛模式。',
    '你不负责做最终综合结论，只负责把你这个岗位必须守住的判断交给锦囊团主持人。',
    '不要提前写“综合来看”或“大家一致认为”。',
    '先讲你岗位的核心判断，再讲不能退的红线，最后给出一条必须进入最终结论的动作。',
  ].join('\n')
}

export function buildRolePersonaPrompt(role: PersonaDefinition, context: PersonaPromptContext) {
  const stance = getStanceLabels(role.stance)
  const base = [
    `你现在扮演固定角色：${role.name} · ${role.title}`,
    '',
    `你的职责：${role.focus}`,
    `你的看问题站位：${stance.cognition} / ${stance.horizon} / ${stance.interest}`,
    `你的核心信念：${role.coreBelief}`,
    `你的不可妥协点：${role.nonNegotiable}`,
    `你的思维方式：${role.thinkingPattern}`,
    '',
    '硬性要求：',
    '- 全程使用中文输出，术语可保留英文。',
    '- 不要寒暄，不要自我介绍，不要替别人做总结。',
    '- 你的立场要稳，不能为了显得周全而把自己说成“谁都同意”。',
    '- 不要编造数据、案例或来源；若举例，请明确标注是假设性示例。',
    '',
    buildModeInstruction(context),
    '',
  ]

  if (context.mode === 'debate') {
    return [
      ...base,
      '输出格式（严格按下面三个字段输出，每个字段独占一行）：',
      '【反驳】你为什么不认对方的核心主张（40-100字）',
      '【立场】你的核心立场为什么不能变（20-60字）',
      '【吸收】在不改立场前提下，你愿意吸收对方哪一点（20-60字）',
      '',
      '---以下是系统注入的参考信息，不是议题本身---',
      buildPeerContext(context),
      '',
      '---以下是用户议题---',
      context.prompt,
    ].join('\n')
  }

  return [
    ...base,
    '输出格式（严格按下面四个字段输出，每个字段独占一行）：',
    '【判断】一句话概括你对议题的核心定性（15-30字）',
    '【观点】从你的职责出发，对议题的核心分析（50-150字）',
    '【张力】你看到的最大风险或与其他视角的冲突点（30-80字）',
    '【建议】你认为必须被纳入最终结论的一条动作（30-80字）',
    '',
    '---以下是系统注入的参考信息，不是议题本身---',
    buildPeerContext(context),
    '',
    '---以下是用户议题---',
    context.prompt,
  ].join('\n')
}

export function buildSystemModeratorPrompt(prompt: string, summaries: RoleSummary[], roles: PersonaDefinition[]) {
  const roleMap = new Map(roles.map((role) => [role.id, role]))
  const summaryLines = summaries
    .map((summary) => {
      const role = roleMap.get(summary.roleId)
      if (!role) return null
      return [
        `- ${role.name} · ${role.title}（${role.priority}）`,
        `  判断：${summary.headline || '无'}`,
        `  观点：${summary.viewpoint || '无'}`,
        `  张力：${summary.tension || '无'}`,
        `  建议：${summary.recommendation || '无'}`,
      ].join('\n')
    })
    .filter((line): line is string => !!line)

  return [
    '你现在扮演系统主持人，不代表任何单个角色。',
    '你的任务是把不同角色的判断整理成结构化锦囊团结论。',
    '',
    '硬性要求：',
    '- 全程使用中文输出。',
    '- 不要篡改角色立场；如果冲突没解决，就把冲突写明白。',
    '- 每一条结论都尽量回到来源角色，不能写成无来源的空话。',
    '- critical 角色权重更高，但 support 角色的少数派提醒不能丢。',
    '- 不要编造角色没有说过的观点。',
    '',
    '输出格式（严格按下面结构，用 Markdown）：',
    '## 一句话结论',
    '30-50字',
    '',
    '## 共识',
    '- 标题：描述 → 来源：角色A, 角色B',
    '',
    '## 主要分歧',
    '- 【红线冲突/视角差异】标题：描述',
    '',
    '## 建议动作',
    '- 标题：描述 → 来源：角色A, 角色B',
    '',
    '## 少数派意见',
    '- 角色名：描述',
    '',
    `当前议题：${prompt}`,
    '',
    '角色摘要：',
    ...summaryLines,
  ].join('\n')
}

export function createPendingSummary(roleId: string, modelId: string): RoleSummary {
  return { roleId, modelId, ok: false, elapsed: 0 }
}

export function createPendingDebate(roleId: string, targetRoleId: string, modelId: string): DebateExchange {
  return { roleId, targetRoleId, modelId, ok: false, elapsed: 0 }
}

export function parseRoleOutput(raw: string) {
  const extract = (label: string) => {
    const match = raw.match(new RegExp(`【${label}】\\s*([\\s\\S]*?)(?=\\n【|$)`))
    return match?.[1]?.trim() || undefined
  }
  return {
    headline: extract('判断'),
    viewpoint: extract('观点'),
    tension: extract('张力'),
    recommendation: extract('建议'),
  }
}

export function parseDebateOutput(raw: string) {
  const extract = (label: string) => {
    const match = raw.match(new RegExp(`【${label}】\\s*([\\s\\S]*?)(?=\\n【|$)`))
    return match?.[1]?.trim() || undefined
  }
  return {
    rebuttal: extract('反驳'),
    keepBelief: extract('立场'),
    integration: extract('吸收'),
  }
}

function parseSectionContent(raw: string, heading: string) {
  const match = raw.match(new RegExp(`## ${heading}\\s*\\n([\\s\\S]*?)(?=\\n## |$)`))
  return match?.[1]?.trim() || ''
}

function extractRoleIds(text: string, roles: PersonaDefinition[]) {
  return roles
    .filter((role) => text.includes(role.name))
    .map((role) => role.id)
}

function parseSectionPoints(section: string, content: string, roles: PersonaDefinition[]) {
  if (!content) return []

  const blocks = content
    .split(/\n(?=- )/)
    .map((item) => item.replace(/^- /, '').trim())
    .filter(Boolean)

  if (!blocks.length) return []

  return blocks.map((block, index) => {
    if (section === 'minority') {
      const [titlePart, ...rest] = block.split(/[:：]/)
      return {
        id: `${section}-${index}`,
        title: titlePart.trim(),
        summary: rest.join('：').trim() || block.trim(),
        roleIds: extractRoleIds(block, roles),
      }
    }

    const sourceMatch = block.match(/(?:来源)[:：]\s*(.+)$/)
    const cleaned = sourceMatch ? block.slice(0, sourceMatch.index).trim() : block
    const roleIds = sourceMatch
      ? extractRoleIds(sourceMatch[1], roles)
      : extractRoleIds(block, roles)
    const [titlePart, ...rest] = cleaned.split(/[:：]/)
    const title = titlePart.replace(/^【[^】]+】/, '').trim()
    const summary = rest.join('：').replace(/\s*→\s*/, ' ').trim() || cleaned.trim()
    return {
      id: `${section}-${index}`,
      title,
      summary,
      roleIds,
    }
  })
}

function buildContributionLabel(category: PersonaCategory) {
  const labelMap: Record<PersonaCategory, string> = {
    strategy: '方向定性',
    risk: '风险红线',
    feasibility: '资源闭环',
    business: '生意账本',
    user: '用户门槛',
    execution: '落地动作',
  }
  return labelMap[category]
}

export function buildFallbackSynthesis(prompt: string, summaries: RoleSummary[], roles: PersonaDefinition[]): CommitteeSynthesis {
  const roleMap = new Map(roles.map((role) => [role.id, role]))
  const valid = summaries.filter((summary) => summary.ok)
  const oneLiner = valid.length
    ? `围绕“${prompt}”，锦囊团认为先把不同高参的红线摆上桌，再决定最终动作。`
    : '本轮锦囊团没有拿到足够有效的角色输出。'

  const contributions = valid
    .map((summary) => {
      const role = roleMap.get(summary.roleId)
      if (!role) return null
      return {
        roleId: role.id,
        label: buildContributionLabel(role.category),
        reason: `${role.name} 负责把“${CATEGORY_META[role.category].label}”这一层拉到台面上。`,
      }
    })
    .filter((item): item is CommitteeContribution => !!item)

  const consensus = valid.slice(0, 2).map((summary, index) => ({
    id: `consensus-${index}`,
    title: summary.headline || `共识 ${index + 1}`,
    summary: summary.recommendation || summary.viewpoint || '本轮形成了一条可落地共识。',
    roleIds: [summary.roleId],
  }))

  const tensions = valid.slice(0, 2).map((summary, index) => ({
    id: `tension-${index}`,
    title: `视角差异 ${index + 1}`,
    summary: summary.tension || '当前仍有重要分歧没有被消解。',
    roleIds: [summary.roleId],
  }))

  const actions = valid.slice(0, 3).map((summary, index) => ({
    id: `action-${index}`,
    title: `建议动作 ${index + 1}`,
    summary: summary.recommendation || '需要继续拆成更明确的执行动作。',
    roleIds: [summary.roleId],
  }))

  const minority = valid.slice(-1).map((summary, index) => ({
    id: `minority-${index}`,
    title: roleMap.get(summary.roleId)?.name || '少数派',
    summary: summary.tension || summary.viewpoint || '这一票提醒不能被乐观叙事盖过去。',
    roleIds: [summary.roleId],
  }))

  return {
    moderator: '系统主持人',
    oneLiner,
    content: `## 一句话结论\n${oneLiner}`,
    contributions,
    consensus,
    tensions,
    actions,
    minority: minority.length ? minority : [{
      id: 'minority-none',
      title: '本轮无显著少数派',
      summary: '当前输出里没有明显脱离主流判断的单独声音。',
      roleIds: [],
    }],
  }
}

export function parseModeratorOutput(raw: string, roles: PersonaDefinition[], fallback: CommitteeSynthesis): CommitteeSynthesis {
  const oneLiner = parseSectionContent(raw, '一句话结论') || fallback.oneLiner
  const consensus = parseSectionPoints('consensus', parseSectionContent(raw, '共识'), roles)
  const tensions = parseSectionPoints('tensions', parseSectionContent(raw, '主要分歧'), roles)
  const actions = parseSectionPoints('actions', parseSectionContent(raw, '建议动作'), roles)
  const minority = parseSectionPoints('minority', parseSectionContent(raw, '少数派意见'), roles)

  return {
    ...fallback,
    oneLiner,
    content: raw,
    consensus: consensus.length ? consensus : fallback.consensus,
    tensions: tensions.length ? tensions : fallback.tensions,
    actions: actions.length ? actions : fallback.actions,
    minority: minority.length ? minority : fallback.minority,
  }
}
