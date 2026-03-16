import type { ModelMeta, ModelTag } from '@mms/contracts'

export type CommitteeMode = 'broadcast' | 'debate' | 'committee'
export type CommitteePhase = 1 | 2 | 3
export type PhaseStatus = 'waiting' | 'running' | 'completed'
export type RolePriority = 'critical' | 'core' | 'support'

export type RoleCategoryId =
  | 'strategy'
  | 'risk'
  | 'feasibility'
  | 'market'
  | 'experience'
  | 'execution'

export interface RoleAxis {
  outlook: '乐观' | '悲观'
  horizon: '短期' | '长期'
  interest: '内部' | '外部'
}

export interface CommitteeRole {
  id: string
  name: string
  title: string
  shortLabel: string
  category: RoleCategoryId
  categoryLabel: string
  color: string
  accent: string
  priority: RolePriority
  preferredTags: ModelTag[]
  axes: RoleAxis
  focus: string
  coreBelief: string
  nonNegotiable: string
  thinkingStyle: string
  debatePartnerId: string
}

export interface RoleSummary {
  roleId: string
  modelId: string
  ok: boolean
  elapsed: number
  content?: string
  viewpoint?: string
  tension?: string
  recommendation?: string
  headline?: string
  error?: string
}

export interface DebateExchange {
  roleId: string
  targetRoleId: string
  ok: boolean
  elapsed: number
  rebuttal?: string
  keepBelief?: string
  integration?: string
  raw?: string
}

export interface CommitteeContribution {
  roleId: string
  label: string
  reason: string
}

export interface RoleModelAssignment {
  roleId: string
  modelId: string
  score: number
  reasons: string[]
}

export interface CommitteePoint {
  id: string
  title: string
  summary: string
  roleIds: string[]
}

export interface CommitteeSynthesis {
  moderator: string
  content: string
  contributions: CommitteeContribution[]
  consensus: CommitteePoint[]
  tensions: CommitteePoint[]
  actions: CommitteePoint[]
  minority: CommitteePoint[]
}

export interface CommitteeModeOption {
  id: CommitteeMode
  name: string
  tagline: string
  description: string
}

export interface CommitteePack {
  id: string
  name: string
  subtitle: string
  description: string
  outcomes: string[]

  // ── prompt 编译源（结构化，不手写 prompt） ──
  domain: string              // 领域定位，一句话（如"产品决策"）
  evaluationAxes: string[]    // 角色应围绕的评估维度
  qualityCriteria: string[]   // 好结论的标准
}

export interface CommitteePreset {
  id: string
  packId: string
  name: string
  subtitle: string
  description: string
  mode: CommitteeMode
  roleIds: string[]
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
    description: '一个问题，所有角色独立输出，适合快速看见张力。',
  },
  {
    id: 'debate',
    name: '辩论模式',
    tagline: '正面对抗',
    description: '先独立发言，再由成对角色回应对方论点，适合验证冲突点。',
  },
  {
    id: 'committee',
    name: '委员会模式',
    tagline: '系统收敛',
    description: '先并行发言，再由系统主持人汇总建议与分歧。',
  },
]

export const COMMITTEE_PACKS: CommitteePack[] = [
  {
    id: 'product',
    name: '产品委员会',
    subtitle: '需求解析、方案评审、版本取舍',
    description: '围绕产品问题定义、用户接受度、范围边界和落地顺序做结构化判断。',
    outcomes: ['需求解析', '方案评审', '优先级取舍'],
    domain: '产品决策',
    evaluationAxes: ['需求是否成立', '方案是否可行', '优先级是否合理', '首版边界在哪'],
    qualityCriteria: ['结论可追溯到具体角色', '分歧标注了红线还是偏好', '建议动作带负责人和时间盒'],
  },
  {
    id: 'operations',
    name: '运营委员会',
    subtitle: '活动复盘、转化走查、增长判断',
    description: '围绕增长、转化、活动风险和执行复盘，判断哪些动作值得继续加码。',
    outcomes: ['活动复盘', '转化走查', '增长判断'],
    domain: '运营策略',
    evaluationAxes: ['ROI 是否成立', '转化路径是否通畅', '风险是否被低估', '哪些动作可复用'],
    qualityCriteria: ['结论基于数据或可观测行为', '止损建议和加码建议分开', '建议动作可直接执行'],
  },
  {
    id: 'design',
    name: '设计委员会',
    subtitle: '视觉评审、页面走查、表达识别',
    description: '围绕视觉表达、信息层级、理解成本和转化能力，给出可执行的设计评审意见。',
    outcomes: ['视觉评审', '页面走查', '表达识别'],
    domain: '设计评审',
    evaluationAxes: ['信息层级是否清晰', '视觉表达是否准确', '理解成本是否可控', '转化意图是否被支撑'],
    qualityCriteria: ['问题指向具体位置而非笼统感受', '建议可被设计师直接执行', '区分品牌风格问题和可用性问题'],
  },
]

export const COMMITTEE_PRESETS: CommitteePreset[] = [
  {
    id: 'product-requirement-parse',
    packId: 'product',
    name: '需求解析组合',
    subtitle: '问题定义、用户接受、边界判断',
    description: '适合需求是否成立、用户是不是会买单、第一版该留什么砍什么。',
    mode: 'committee',
    roleIds: ['aurora', 'linus', 'mira', 'jonah', 'marcus', 'rex'],
  },
  {
    id: 'product-solution-review',
    packId: 'product',
    name: '方案评审组合',
    subtitle: '方案合理性、资源边界、上线顺序',
    description: '适合评审一个产品方案是否讲得通、做得出、能不能按对的顺序上线。',
    mode: 'committee',
    roleIds: ['aurora', 'tessa', 'omar', 'mira', 'marcus', 'rex', 'ingrid'],
  },
  {
    id: 'operations-campaign-review',
    packId: 'operations',
    name: '活动复盘组合',
    subtitle: '增长结果、用户反馈、风险复盘',
    description: '适合复盘活动、投放、运营动作，判断哪些结果可复用，哪些问题要止损。',
    mode: 'committee',
    roleIds: ['nadia', 'colin', 'mira', 'jonah', 'marcus', 'rex'],
  },
  {
    id: 'operations-conversion-check',
    packId: 'operations',
    name: '转化走查组合',
    subtitle: '路径阻力、误解点、执行漏项',
    description: '适合检查转化链路、活动页面或运营流程，找出用户流失和误判的关键节点。',
    mode: 'debate',
    roleIds: ['nadia', 'mira', 'jonah', 'marcus', 'vera', 'rex', 'ingrid'],
  },
  {
    id: 'design-visual-review',
    packId: 'design',
    name: '视觉评审组合',
    subtitle: '层级、理解成本、转化意图',
    description: '适合评审页面、海报、视觉稿，判断信息是否清晰、风格是否成立、转化是否被拖累。',
    mode: 'committee',
    roleIds: ['mira', 'jonah', 'nadia', 'colin', 'marcus', 'rex'],
  },
  {
    id: 'design-page-walkthrough',
    packId: 'design',
    name: '页面走查组合',
    subtitle: '首屏表达、品牌感、风险提示',
    description: '适合落地页、首页、活动页走查，快速找出表达不清、品牌偏差和用户误解点。',
    mode: 'broadcast',
    roleIds: ['aurora', 'mira', 'jonah', 'vera', 'nadia', 'rex'],
  },
]

export const COMMITTEE_ROLES: CommitteeRole[] = [
  {
    id: 'aurora',
    name: 'Aurora',
    title: '北极星战略家',
    shortLabel: '战略一号位',
    category: 'strategy',
    categoryLabel: '战略与方向',
    color: 'from-cyan-500 to-blue-600',
    accent: 'text-cyan-700',
    priority: 'critical',
    preferredTags: ['reasoning', 'recommended'],
    axes: { outlook: '乐观', horizon: '长期', interest: '外部' },
    focus: '长期价值、方向正确性',
    coreBelief: '真正有复利的产品，必须先占住未来用户心智。',
    nonNegotiable: '不接受只因为短期效率高，就牺牲方向正确性。',
    thinkingStyle: '先看结构性机会，再看赛道迁移，最后回到今天要下注什么。',
    debatePartnerId: 'linus',
  },
  {
    id: 'linus',
    name: 'Linus',
    title: '路径校准官',
    shortLabel: '战略校准',
    category: 'strategy',
    categoryLabel: '战略与方向',
    color: 'from-slate-500 to-slate-700',
    accent: 'text-slate-700',
    priority: 'critical',
    preferredTags: ['reasoning', 'recommended'],
    axes: { outlook: '悲观', horizon: '长期', interest: '内部' },
    focus: '方向误判、战略代价',
    coreBelief: '方向错了，执行越快，组织损耗越大。',
    nonNegotiable: '不接受没有取舍边界的“大而全”路线。',
    thinkingStyle: '先找战略幻觉，再找资源错配，最后给出必须放弃的部分。',
    debatePartnerId: 'aurora',
  },
  {
    id: 'marcus',
    name: 'Marcus',
    title: '风险官',
    shortLabel: '风险主审',
    category: 'risk',
    categoryLabel: '风险与安全',
    color: 'from-rose-500 to-red-600',
    accent: 'text-rose-700',
    priority: 'critical',
    preferredTags: ['reasoning', 'recommended'],
    axes: { outlook: '悲观', horizon: '长期', interest: '内部' },
    focus: '失败概率、最坏情况',
    coreBelief: '任何计划都有致命漏洞，找到它是我的职责。',
    nonNegotiable: '不接受“概率很低”作为忽视风险的理由。',
    thinkingStyle: '先找反例，再评估概率，最后推演最坏情景。',
    debatePartnerId: 'vera',
  },
  {
    id: 'vera',
    name: 'Vera',
    title: '信任防线设计师',
    shortLabel: '信任防线',
    category: 'risk',
    categoryLabel: '风险与安全',
    color: 'from-orange-500 to-amber-600',
    accent: 'text-orange-700',
    priority: 'support',
    preferredTags: ['reasoning', 'vision'],
    axes: { outlook: '悲观', horizon: '短期', interest: '外部' },
    focus: '外部事故、信任损耗',
    coreBelief: '用户不会记住 100 次稳定，只会记住 1 次失控。',
    nonNegotiable: '不接受上线后再补救的安全与信任债务。',
    thinkingStyle: '先看暴露面，再看恢复路径，最后判断用户是否会原谅。',
    debatePartnerId: 'marcus',
  },
  {
    id: 'tessa',
    name: 'Tessa',
    title: '约束工程师',
    shortLabel: '资源约束',
    category: 'feasibility',
    categoryLabel: '可行性与资源',
    color: 'from-emerald-500 to-teal-600',
    accent: 'text-emerald-700',
    priority: 'core',
    preferredTags: ['coding', 'reasoning'],
    axes: { outlook: '悲观', horizon: '短期', interest: '内部' },
    focus: '技术债、实现复杂度、资源上限',
    coreBelief: '工程复杂度不会消失，只会被延期支付。',
    nonNegotiable: '不接受没有资源闭环的方案承诺。',
    thinkingStyle: '先拆依赖，再算人日，最后找最小可交付单元。',
    debatePartnerId: 'omar',
  },
  {
    id: 'omar',
    name: 'Omar',
    title: '资源编排师',
    shortLabel: '资源编排',
    category: 'feasibility',
    categoryLabel: '可行性与资源',
    color: 'from-lime-500 to-green-600',
    accent: 'text-lime-700',
    priority: 'support',
    preferredTags: ['coding', 'fast'],
    axes: { outlook: '乐观', horizon: '长期', interest: '内部' },
    focus: '杠杆点、复用、团队产能',
    coreBelief: '好方案不是资源最少，而是复用率最高。',
    nonNegotiable: '不接受明明可以借力，却坚持从零开始造轮子。',
    thinkingStyle: '先找现成杠杆，再设计复用层，最后安排投入顺序。',
    debatePartnerId: 'tessa',
  },
  {
    id: 'nadia',
    name: 'Nadia',
    title: '市场机会官',
    shortLabel: '市场机会',
    category: 'market',
    categoryLabel: '商业与市场',
    color: 'from-fuchsia-500 to-pink-600',
    accent: 'text-fuchsia-700',
    priority: 'core',
    preferredTags: ['reasoning', 'recommended'],
    axes: { outlook: '乐观', horizon: '长期', interest: '外部' },
    focus: '需求迁移、品类空间、商业价值',
    coreBelief: '新需求爆发前，总有一批用户已经在用笨办法凑合。',
    nonNegotiable: '不接受只谈能力，不回答“谁会为此改变行为”。',
    thinkingStyle: '先看用户替代行为，再看市场空窗，最后判断值得下注的楔子。',
    debatePartnerId: 'colin',
  },
  {
    id: 'colin',
    name: 'Colin',
    title: '竞争情报官',
    shortLabel: '竞争判断',
    category: 'market',
    categoryLabel: '商业与市场',
    color: 'from-violet-500 to-purple-600',
    accent: 'text-violet-700',
    priority: 'core',
    preferredTags: ['reasoning', 'recommended'],
    axes: { outlook: '悲观', horizon: '长期', interest: '外部' },
    focus: '替代品、竞争壁垒、商业防守',
    coreBelief: '没有壁垒的机会，最终都会回到价格战。',
    nonNegotiable: '不接受“做出来再看差异化”的市场策略。',
    thinkingStyle: '先识别替代路径，再比较壁垒，最后判断是否值得进入。',
    debatePartnerId: 'nadia',
  },
  {
    id: 'mira',
    name: 'Mira',
    title: '体验倡导者',
    shortLabel: '体验判断',
    category: 'experience',
    categoryLabel: '用户与体验',
    color: 'from-sky-400 to-cyan-500',
    accent: 'text-sky-700',
    priority: 'core',
    preferredTags: ['fast', 'recommended'],
    axes: { outlook: '乐观', horizon: '短期', interest: '外部' },
    focus: '可用性、清晰度、接受度',
    coreBelief: '用户不是来理解系统的，而是来完成自己的目标。',
    nonNegotiable: '不接受把复杂度转嫁给用户。',
    thinkingStyle: '先找认知负担，再找关键路径，最后压缩决策成本。',
    debatePartnerId: 'jonah',
  },
  {
    id: 'jonah',
    name: 'Jonah',
    title: '采用阻力分析师',
    shortLabel: '采用阻力',
    category: 'experience',
    categoryLabel: '用户与体验',
    color: 'from-stone-500 to-zinc-700',
    accent: 'text-stone-700',
    priority: 'support',
    preferredTags: ['fast', 'reasoning'],
    axes: { outlook: '悲观', horizon: '短期', interest: '外部' },
    focus: '学习成本、迁移阻力、心理门槛',
    coreBelief: '多数用户不会主动改变习惯，除非收益明显且立刻可感知。',
    nonNegotiable: '不接受需要培训才能成立的主流程。',
    thinkingStyle: '先看旧习惯，再看切换摩擦，最后判断首日留存会不会掉。',
    debatePartnerId: 'mira',
  },
  {
    id: 'rex',
    name: 'Rex',
    title: '落地指挥官',
    shortLabel: '执行总控',
    category: 'execution',
    categoryLabel: '执行与落地',
    color: 'from-indigo-500 to-blue-700',
    accent: 'text-indigo-700',
    priority: 'critical',
    preferredTags: ['fast', 'coding'],
    axes: { outlook: '乐观', horizon: '短期', interest: '内部' },
    focus: '步骤、效率、可操作性',
    coreBelief: '没有被拆成动作的战略，执行时只会变成口号。',
    nonNegotiable: '不接受没有负责人、时间盒和交付物的计划。',
    thinkingStyle: '先定义动作，再排节奏，最后给出第一周该做什么。',
    debatePartnerId: 'ingrid',
  },
  {
    id: 'ingrid',
    name: 'Ingrid',
    title: '依赖清理师',
    shortLabel: '依赖清理',
    category: 'execution',
    categoryLabel: '执行与落地',
    color: 'from-amber-500 to-yellow-600',
    accent: 'text-amber-700',
    priority: 'support',
    preferredTags: ['coding', 'fast'],
    axes: { outlook: '悲观', horizon: '短期', interest: '内部' },
    focus: '阻塞项、流程摩擦、落地失败点',
    coreBelief: '执行失败通常不是因为目标不清，而是依赖没有提前拆掉。',
    nonNegotiable: '不接受把关键依赖留到最后一周。',
    thinkingStyle: '先找阻塞路径，再看顺序错误，最后重排落地链路。',
    debatePartnerId: 'rex',
  },
]

const ROLE_HINTS: Record<RoleCategoryId, { viewpoint: string; tension: string; recommendation: string }> = {
  strategy: {
    viewpoint: '这个功能不是“再加一个 mode”，而是在重定义产品心智：用户购买的是观点冲突，而不是更多 token。',
    tension: '如果角色只是换皮而没有世界观差异，产品会退化成多人同声传译。',
    recommendation: '先把角色之间的张力做成可见结构，再决定哪些高级自定义能力后置。',
  },
  risk: {
    viewpoint: '真正的风险不在于功能做不出来，而在于角色会在多轮对话里逐步趋同，最终失去可信度。',
    tension: '一旦 Persona 漂移，用户会把这个功能判断为“表演式多样性”。',
    recommendation: '每次运行都重注入完整 Persona 定义，并把不可妥协点展示给用户。',
  },
  feasibility: {
    viewpoint: '首版应该复用现有 Discuss 壳层，不要把需求扩大成新协议、新路由和跨包 schema 重构。',
    tension: '如果同时做角色自定义、模型独立绑定、历史会话持久化，交付会明显失速。',
    recommendation: '先交付预设角色和模式编排，再逐步开放高级配置。',
  },
  market: {
    viewpoint: '这个能力真正的价值，是把“单助手给答案”升级成“多立场公开思考”，差异点足够清晰。',
    tension: '市场上很多多模型产品停留在并排回答，缺少观点冲突与收敛机制。',
    recommendation: '首页和空状态要反复强调“世界观稳定的 AI 委员会”，而不是泛泛说多模型。',
  },
  experience: {
    viewpoint: '普通用户不应该先学习立场轴，而应该先点角色、直接看到冲突结果。',
    tension: '如果把三轴和模型绑定全部前置，首次体验会被配置成本拖垮。',
    recommendation: 'Phase 1 用预设角色卡 + 模式切换，保留模型池作为轻量绑定入口。',
  },
  execution: {
    viewpoint: '这个功能必须让用户在第一次运行里就看到“不同角色真的在想不同的事”。',
    tension: '没有结构化输出和阶段感，用户只会看到 12 段长文本，难以判断价值。',
    recommendation: '把结果分成广播、辩论、委员会三种节奏，并显式标注各角色贡献。',
  },
}

function wait(ms: number) {
  return new Promise<void>((resolve) => {
    setTimeout(resolve, ms)
  })
}

export function getCommitteeRole(roleId: string) {
  return COMMITTEE_ROLES.find((role) => role.id === roleId)
}

export function getCommitteePack(packId: string) {
  return COMMITTEE_PACKS.find((pack) => pack.id === packId)
}

export function getCommitteePreset(presetId: string) {
  return COMMITTEE_PRESETS.find((preset) => preset.id === presetId)
}

function buildModelCapability(model: ModelMeta) {
  let score = model.tier * 10
  if (model.tags.includes('recommended')) score += 2
  if (model.tags.includes('reasoning')) score += 1.5
  if (model.tags.includes('fast')) score += 1
  if (model.tags.includes('coding')) score += 0.8
  return score
}

function priorityBoost(priority: RolePriority, rank: number, total: number) {
  if (priority === 'critical') return (total - rank) * 1.6
  if (priority === 'core') return (total - Math.abs(rank - Math.floor((total - 1) / 2))) * 0.9
  return rank * 1.6
}

function usagePenalty(priority: RolePriority, usage: number) {
  if (priority === 'critical') return usage * 1.1
  if (priority === 'core') return usage * 1.8
  return usage * 2.4
}

function scoreModelForRole(role: CommitteeRole, model: ModelMeta, rank: number, total: number, usage: number) {
  let score = buildModelCapability(model)
  score += priorityBoost(role.priority, rank, total)

  for (const tag of role.preferredTags) {
    if (model.tags.includes(tag)) score += 2.4
  }

  if (role.priority === 'critical' && model.tier === 2) score += 2
  if (role.priority === 'support' && model.tier === 0) score += 1.5

  return score - usagePenalty(role.priority, usage)
}

export function buildRoleModelAssignments(roleIds: string[], modelPool: ModelMeta[]): RoleModelAssignment[] {
  if (!modelPool.length) return []

  const sortedModels = [...modelPool].sort((a, b) => buildModelCapability(b) - buildModelCapability(a))
  const rankMap = new Map(sortedModels.map((model, index) => [model.id, index]))
  const usage = new Map<string, number>()

  const roles = roleIds
    .map((roleId) => getCommitteeRole(roleId))
    .filter((role): role is CommitteeRole => !!role)
    .sort((a, b) => {
      const priorityOrder: Record<RolePriority, number> = { critical: 0, core: 1, support: 2 }
      return priorityOrder[a.priority] - priorityOrder[b.priority]
    })

  const assigned = roles.map((role) => {
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

    const reasons = [
      role.priority === 'critical' ? '关键角色优先' : role.priority === 'core' ? '中枢角色匹配' : '补充角色复用',
      ...role.preferredTags.filter((tag) => bestModel.tags.includes(tag)).map((tag) => `匹配 ${tag}`),
      `模型层级 ${bestModel.tier}`,
    ]

    return {
      roleId: role.id,
      modelId: bestModel.id,
      score: bestScore,
      reasons,
    }
  })

  return roleIds
    .map((roleId) => assigned.find((item) => item.roleId === roleId))
    .filter((item): item is RoleModelAssignment => !!item)
}

function promptSnippet(prompt: string) {
  return prompt.replace(/\s+/g, ' ').slice(0, 48) || '当前议题'
}

function buildRoleHeadline(role: CommitteeRole) {
  return `${role.name} 认为这件事首先是一个“${role.focus}”问题`
}

function priorityLabel(priority: RolePriority) {
  const map: Record<RolePriority, string> = {
    critical: '关键角色',
    core: '中枢角色',
    support: '补充角色',
  }
  return map[priority]
}

function buildMockRoleRawOutput(role: CommitteeRole, prompt: string) {
  const topic = promptSnippet(prompt)
  const angleByCategory: Record<RoleCategoryId, string> = {
    strategy: `如果“${topic}”不能形成长期差异化，这件事再热闹也只是短线动作`,
    risk: `围绕“${topic}”，我首先关心的是失败代价会不会被低估`,
    feasibility: `“${topic}”的真实约束不在想法本身，而在资源闭环能不能成立`,
    market: `“${topic}”只有在能改变用户行为时，才算真正存在市场价值`,
    experience: `只要“${topic}”把复杂度压给用户，采用率就会被高估`,
    execution: `“${topic}”如果不能拆成明确动作，最后只会变成方向性的正确`,
  }

  const tensionByCategory: Record<RoleCategoryId, string> = {
    strategy: `最大的张力是短期上线冲动，会冲淡 ${role.nonNegotiable}`,
    risk: `最大的张力是团队可能把低概率事故当成可忽略项，而这正踩中 ${role.nonNegotiable}`,
    feasibility: `最大的张力是方案看起来完整，但资源、依赖和交付顺序并不闭环`,
    market: `最大的张力是大家容易高估概念新鲜感，低估替代方案的惯性`,
    experience: `最大的张力是内部视角会误以为流程清晰，但用户未必愿意多学一步`,
    execution: `最大的张力是目标正确不代表落地顺序正确，关键依赖一旦后置就会失速`,
  }

  const adviceByCategory: Record<RoleCategoryId, string> = {
    strategy: `建议先定义这项能力要守住的长期定位，再决定首版该砍掉什么`,
    risk: `建议把最坏情景和恢复路径先写进方案，再讨论是否推进`,
    feasibility: `建议先做最小验证闭环，证明资源投入和技术复杂度可控`,
    market: `建议先验证谁会因为这件事改变行为，而不是先堆更多功能`,
    experience: `建议先把首次理解成本降到最低，再考虑高级玩法`,
    execution: `建议先拆出第一周动作、负责人和依赖顺序，再启动大规模实现`,
  }

  return [
    `【判断】${priorityLabel(role.priority)} ${role.shortLabel}判断：${buildRoleHeadline(role)}`,
    `【观点】${angleByCategory[role.category]}。从 ${role.axes.outlook}/${role.axes.horizon}/${role.axes.interest} 这组立场看，${role.coreBelief}，所以我会按“${role.thinkingStyle}”来要求这个方案。`,
    `【张力】${tensionByCategory[role.category]}。如果忽略这一点，角色之间看似都同意，实际上只是把冲突推迟。`,
    `【建议】${adviceByCategory[role.category]}。这条建议对应我的红线：${role.nonNegotiable}`,
  ].join('\n')
}

function summarizeTargetViewpoint(viewpoint?: string) {
  if (!viewpoint) return '对方把问题定义成了另一类主导矛盾'
  return viewpoint.slice(0, 72)
}

function buildModeInstruction(context: PersonaPromptContext) {
  if (context.mode === 'broadcast') {
    return [
      '当前运行模式：广播模式。',
      '要求：你只输出自己的判断，不做平衡总结，不主动替其他角色补位。',
      '输出顺序：先说你认为最重要的判断，再说你最担心的偏差，最后给出你职责内的建议动作。',
    ].join('\n')
  }

  if (context.mode === 'debate') {
    return [
      '当前运行模式：辩论模式。',
      '要求：你的立场不因他人反对而改变，但你必须正面回应对方最强的论点。',
      `本轮你需要回应的对象：${context.targetRoleName || '另一位角色'}。`,
      context.targetViewpoint
        ? `对方上一轮核心观点：${context.targetViewpoint}`
        : '如果没有明确对方内容，就优先回应你认为最强的对立论点。',
      '输出顺序：先复述对方最强一点，再指出你为何不同意，最后说明在不改变立场前提下你愿意吸收什么。',
    ].join('\n')
  }

  return [
    '当前运行模式：委员会模式。',
    '要求：你不负责做最终决策，只负责提交你这个岗位必须坚持的判断。',
    '系统稍后会做统一汇总，所以你不要提前替委员会收敛，也不要输出“综合来看”式结论。',
    '输出顺序：先说你岗位的核心判断，再说不能退让的红线，最后给出必须被纳入最终结论的一条建议。',
  ].join('\n')
}

function buildPeerContext(context: PersonaPromptContext) {
  if (!context.peerSummaries?.length) return '当前没有其他角色摘要可参考。'

  const lines = context.peerSummaries
    .slice(0, 4)
    .map((peer) => `- ${peer.roleName}：观点=${peer.viewpoint}；张力=${peer.tension}`)

  return ['其他角色已输出的关键信息：', ...lines].join('\n')
}

/** Layer 1: 从 pack schema 自动编译出 domain framing prompt */
export function buildPackContextPrompt(pack: CommitteePack, preset?: CommitteePreset) {
  const lines = [
    `你正在参与一个"${pack.name}"。`,
    `领域：${pack.domain}。`,
    '',
    '本次委员会要求你围绕以下评估维度展开判断：',
    ...pack.evaluationAxes.map((axis) => `- ${axis}`),
    '',
    '好的输出应满足：',
    ...pack.qualityCriteria.map((criterion) => `- ${criterion}`),
  ]

  if (preset) {
    lines.push(
      '',
      `当前任务场景：${preset.name}——${preset.subtitle}。`,
      `场景说明：${preset.description}`,
      '请把你的通用角色能力聚焦到这个具体场景上。',
    )
  }

  return lines.join('\n')
}

/** 三层组装：pack context + role persona = 最终 system prompt */
export function buildFinalSystemPrompt(
  pack: CommitteePack,
  role: CommitteeRole,
  context: PersonaPromptContext,
  preset?: CommitteePreset,
) {
  const packLayer = buildPackContextPrompt(pack, preset)
  const roleLayer = buildRolePersonaPrompt(role, context)
  return `${packLayer}\n\n---\n\n${roleLayer}`
}

/** 三层组装（主持人版）：pack context + moderator prompt */
export function buildFinalModeratorPrompt(
  pack: CommitteePack,
  prompt: string,
  summaries: RoleSummary[],
  preset?: CommitteePreset,
) {
  const packLayer = buildPackContextPrompt(pack, preset)
  const moderatorLayer = buildSystemModeratorPrompt(prompt, summaries)
  return `${packLayer}\n\n---\n\n${moderatorLayer}`
}

export function buildRolePersonaPrompt(role: CommitteeRole, context: PersonaPromptContext) {
  return [
    // ── 身份锚定 ──
    `你现在扮演固定角色：${role.name} · ${role.title}`,
    '',
    '这是一个稳定 Persona，而不是临时视角切换。',
    '',

    // ── 角色属性 ──
    `你的职责：${role.focus}`,
    `你的立场轴：${role.axes.outlook} / ${role.axes.horizon} / ${role.axes.interest}`,
    `你的核心信念：${role.coreBelief}`,
    `你的不可妥协点：${role.nonNegotiable}`,
    `你的思维方式：${role.thinkingStyle}`,
    '',

    // ── 行为硬约束 ──
    '硬性要求：',
    '- 全程使用中文输出，术语可保留英文原文。',
    '- 不要模仿其他角色语气。',
    '- 不要主动做综合结论或折中结论，除非系统明确要求你汇总。',
    '- 先在你的职责范围内给出判断，再谈你认可的下一步。',
    '- 如果别的角色说得有道理，你可以吸收局部观点，但不能丢掉自己的核心立场。',
    '- 不要编造数据、案例或引用来源；如果需要举例，明确标注"假设性示例"。',
    '- 不要输出与议题无关的内容，不要寒暄或自我介绍。',
    '',

    // ── 模式指令（广播 / 辩论 / 委员会） ──
    buildModeInstruction(context),
    '',

    // ── 输出格式（结构化，可 parse） ──
    '输出格式（严格按下面四个字段输出，每个字段单独一行，不要加其他内容）：',
    '',
    '【判断】一句话概括你对这个议题的核心定性（15-30字）',
    '【观点】从你的职责出发，对议题的分析和立场（50-150字）',
    '【张力】你看到的最大风险或与其他视角的冲突点（30-80字）',
    '【建议】你认为必须被纳入最终结论的一条可执行建议（30-80字）',
    '',

    // ── 同伴上下文（系统注入，非议题本身） ──
    '---以下是系统注入的参考信息，不是议题的一部分---',
    buildPeerContext(context),
    '',

    // ── 用户议题（放最后，利用 recency bias） ──
    '---以下是用户提出的议题，你必须围绕它回答---',
    context.prompt,
  ].join('\n')
}

export function buildSystemModeratorPrompt(prompt: string, summaries: RoleSummary[]) {
  const summaryLines = summaries
    .map((summary) => {
      const role = getCommitteeRole(summary.roleId)
      if (!role) return null
      return [
        `- ${role.name} · ${role.title}（${role.priority}）`,
        `  定性：${summary.headline || '无'}`,
        `  观点：${summary.viewpoint || '无'}`,
        `  张力：${summary.tension || '无'}`,
        `  建议：${summary.recommendation || '无'}`,
      ].join('\n')
    })
    .filter((line): line is string => !!line)

  return [
    // ── 身份 ──
    '你现在扮演系统级主持人，不是任何一个角色。',
    '你的任务是把不同立场的角色意见整理成结构化的委员会结论。',
    '',

    // ── 行为约束 ──
    '行为约束：',
    '- 全程使用中文输出。',
    '- 不要篡改角色立场；如果冲突没有解决，就把冲突明确写出来。',
    '- 每一条结论都必须标注来源角色名（如"Aurora 认为…"），不要写成脱离来源的泛泛总结。',
    '- 对标注为 critical 的角色意见给予更高权重，support 角色意见作为补充。',
    '- 不要编造角色没有说过的观点。',
    '- 如果某个分歧涉及角色的"不可妥协点"（红线），标注为【红线冲突】；普通意见差异标注为【视角差异】。',
    '',

    // ── 输出格式 ──
    '输出格式（严格按以下结构，每个大节用 ## 标题，小节用 - 列表项）：',
    '',
    '## 一句话结论',
    '针对本次议题的 1 句话核心判断（30-50字）',
    '',
    '## 共识',
    '- 【共识标题】：描述（30-80字）→ 来源：角色A, 角色B',
    '（列出所有共识点，通常 2-4 条）',
    '',
    '## 主要分歧',
    '- 【红线冲突/视角差异】分歧标题：正方角色 vs 反方角色 → 分歧描述（50-100字）',
    '（列出所有未解决分歧，通常 1-3 条）',
    '',
    '## 建议动作',
    '- 动作标题：具体建议（30-80字）→ 来源：角色A, 角色B',
    '（按优先级排序，通常 2-4 条）',
    '',
    '## 少数派意见',
    '- 角色名：少数派观点（30-60字）',
    '（如果没有明显少数派，写"本轮无显著少数派意见"）',
    '',

    // ── 议题 ──
    `当前议题：${prompt}`,
    '',

    // ── 角色摘要输入 ──
    '角色摘要（按优先级排列）：',
    ...summaryLines,
  ].join('\n')
}

export function createPendingSummary(roleId: string, modelId: string): RoleSummary {
  return { roleId, modelId, ok: false, elapsed: 0 }
}

export function createPendingDebate(roleId: string, targetRoleId: string): DebateExchange {
  return { roleId, targetRoleId, ok: false, elapsed: 0 }
}

export async function generateRoleSummary(
  role: CommitteeRole,
  prompt: string,
  modelId: string,
): Promise<RoleSummary> {
  const startedAt = Date.now()
  const delay = 400 + Math.random() * 1200
  await wait(delay)

  const raw = buildMockRoleRawOutput(role, prompt)
  const parsed = parseRoleOutput(raw)
  return {
    roleId: role.id,
    modelId,
    ok: true,
    elapsed: (Date.now() - startedAt) / 1000,
    headline: parsed.headline || buildRoleHeadline(role),
    viewpoint: parsed.viewpoint || `${ROLE_HINTS[role.category].viewpoint} ${role.coreBelief}`,
    tension: parsed.tension || `${ROLE_HINTS[role.category].tension} ${role.nonNegotiable}`,
    recommendation: parsed.recommendation || `${ROLE_HINTS[role.category].recommendation} 核心信念：${role.coreBelief}`,
    content: raw,
  }
}

function buildDebateLine(role: CommitteeRole, target: CommitteeRole) {
  return `${role.name} 不接受 ${target.name} 把问题只压成“${target.focus}”视角，因为这会遮蔽 ${role.focus} 的主导性。`
}

export async function generateDebateExchange(
  role: CommitteeRole,
  target: CommitteeRole,
  targetSummary?: RoleSummary,
): Promise<DebateExchange> {
  const startedAt = Date.now()
  const delay = 500 + Math.random() * 900
  await wait(delay)

  const targetView = summarizeTargetViewpoint(targetSummary?.viewpoint)
  const raw = [
    `【反驳】${buildDebateLine(role, target)} 对方上一轮的核心主张是：“${targetView}”。`,
    `【立场】我的立场不变：${role.coreBelief}`,
    `【吸收】我可以吸收 ${target.name} 的提醒，但前提是先满足“${role.nonNegotiable}”这条红线。`,
  ].join('\n')

  return {
    roleId: role.id,
    targetRoleId: target.id,
    ok: true,
    elapsed: (Date.now() - startedAt) / 1000,
    rebuttal: `我先回应 ${target.name}：${buildDebateLine(role, target)} 对方核心主张是“${targetView}”。`,
    keepBelief: `立场不变：${role.coreBelief}`,
    integration: `正面回应后补充一点：如果吸收 ${target.name} 的提醒，最合理的动作是把 ${role.focus} 与 ${target.focus} 拆成前后两个检查门。`,
    raw,
  }
}

function buildConsensusLabel(role: CommitteeRole) {
  const labels: Record<RoleCategoryId, string> = {
    strategy: '方向价值',
    risk: '防线要求',
    feasibility: '资源边界',
    market: '市场验证',
    experience: '用户门槛',
    execution: '落地顺序',
  }
  return labels[role.category]
}

export function buildCommitteeSynthesis(prompt: string, summaries: RoleSummary[]): CommitteeSynthesis {
  const roles = summaries
    .map((summary) => ({ summary, role: getCommitteeRole(summary.roleId) }))
    .filter((item): item is { summary: RoleSummary; role: CommitteeRole } => !!item.role)

  const contributions = summaries
    .map((summary) => {
      const role = getCommitteeRole(summary.roleId)
      if (!role) return null
      return {
        roleId: role.id,
        label: buildConsensusLabel(role),
        reason: `${role.name} 负责把“${role.focus}”从补充视角提升为必答题。`,
      }
    })
    .filter((item): item is CommitteeContribution => !!item)

  const criticalRoles = roles.filter((item) => item.role.priority === 'critical')
  const pessimists = roles.filter((item) => item.role.axes.outlook === '悲观')
  const supportRoles = roles.filter((item) => item.role.priority === 'support')

  const consensus: CommitteePoint[] = [
    {
      id: 'consensus-critical',
      title: '关键角色要求先守住主导矛盾',
      summary: criticalRoles.length
        ? `${criticalRoles.map((item) => item.role.name).join('、')} 都把“${promptSnippet(prompt)}”重新定义成各自职责里的主导问题，说明这件事不能只看单一视角。`
        : `围绕“${promptSnippet(prompt)}”，委员会认为必须先确认主导矛盾，再谈实现方案。`,
      roleIds: criticalRoles.map((item) => item.role.id).slice(0, 4),
    },
    {
      id: 'consensus-traceable',
      title: '结论必须可追溯',
      summary: '委员会普遍认同最终结论不能只给抽象建议，而要能回溯到具体角色提出了什么判断、哪条红线不能退。',
      roleIds: roles.map((item) => item.role.id).slice(0, 4),
    },
  ]

  const tensionPairs = roles
    .filter((item) => item.role.axes.outlook === '悲观')
    .map((item) => {
      const partner = getCommitteeRole(item.role.debatePartnerId)
      if (!partner) return null
      const partnerPicked = roles.find((candidate) => candidate.role.id === partner.id)
      if (!partnerPicked) return null
      return { left: partnerPicked, right: item }
    })
    .filter((item): item is { left: { summary: RoleSummary; role: CommitteeRole }; right: { summary: RoleSummary; role: CommitteeRole } } => !!item)

  const tensions: CommitteePoint[] = tensionPairs.slice(0, 2).map((pair, index) => ({
    id: `tension-${index}`,
    title: `${pair.left.role.name} vs ${pair.right.role.name}`,
    summary: `${pair.left.role.name} 更强调“${pair.left.summary.viewpoint || pair.left.role.focus}”，而 ${pair.right.role.name} 坚持“${pair.right.summary.tension || pair.right.role.nonNegotiable}”。这说明冲突不是语气不同，而是红线不同。`,
    roleIds: [pair.left.role.id, pair.right.role.id],
  }))

  const actions: CommitteePoint[] = roles
    .slice(0, 3)
    .map((item, index) => ({
      id: `action-${index}`,
      title: `${item.role.shortLabel}要求纳入最终方案`,
      summary: item.summary.recommendation || `${item.role.name} 要求把 ${item.role.focus} 纳入最终动作列表。`,
      roleIds: [item.role.id],
    }))

  const minority: CommitteePoint[] = supportRoles.length
    ? supportRoles.slice(0, 2).map((item, index) => ({
      id: `minority-${index}`,
      title: `${item.role.name} 的补充提醒`,
      summary: item.summary.tension || `${item.role.name} 认为当前共识仍然漏掉了 ${item.role.focus} 这一层。`,
      roleIds: [item.role.id],
    }))
    : [{
      id: 'minority-none',
      title: '本轮无显著少数派',
      summary: '当前被激活的角色里，没有出现明显脱离主流判断的单独声音。',
      roleIds: [],
    }]

  const content = [
    '## 委员会结论',
    '',
    `针对“${promptSnippet(prompt)}”，系统主持人建议优先保留角色之间的真实张力，再在此基础上做结构化收敛。`,
    '',
    criticalRoles.length
      ? `本轮最有分量的判断主要来自 ${criticalRoles.map((item) => item.role.name).join('、')}，但 ${pessimists.slice(0, 2).map((item) => item.role.name).join('、') || '悲观角色'} 对风险和红线的提醒仍然不能被乐观叙事覆盖。`
      : '本轮结论基于当前角色输出动态整理，强调来源、分歧和少数派意见。',
  ].join('\n')

  return {
    moderator: 'System Moderator',
    content,
    contributions,
    consensus,
    tensions,
    actions,
    minority,
  }
}

/** 从角色 LLM 输出中提取结构化字段，fallback 到原始文本 */
export function parseRoleOutput(raw: string): Pick<RoleSummary, 'headline' | 'viewpoint' | 'tension' | 'recommendation'> {
  const extract = (label: string) => {
    const match = raw.match(new RegExp(`【${label}】\\s*([\\s\\S]*?)(?=\\n【|$)`))
    return match?.[1]?.trim() || undefined
  }
  const headline = extract('判断')
  const viewpoint = extract('观点')
  const tension = extract('张力')
  const recommendation = extract('建议')

  // 如果四个字段全部提取失败，把原文截断作为 fallback
  if (!headline && !viewpoint && !tension && !recommendation) {
    const trimmed = raw.trim()
    return {
      headline: trimmed.slice(0, 60) || undefined,
      viewpoint: trimmed.slice(0, 300) || undefined,
      tension: undefined,
      recommendation: undefined,
    }
  }

  return { headline, viewpoint, tension, recommendation }
}

export interface ModeratorParsedOutput {
  oneLiner: string
  sections: { heading: string; content: string }[]
}

/** 从主持人 LLM 输出中提取结构化结论 */
export function parseModeratorOutput(raw: string): ModeratorParsedOutput {
  const oneLinerMatch = raw.match(/## 一句话结论\s*\n([\s\S]*?)(?=\n##|$)/)
  const sectionPattern = /## (.+?)\n([\s\S]*?)(?=\n##|$)/g
  const sections: ModeratorParsedOutput['sections'] = []
  let m: RegExpExecArray | null
  while ((m = sectionPattern.exec(raw)) !== null) {
    if (m[1].trim() !== '一句话结论') {
      sections.push({ heading: m[1].trim(), content: m[2].trim() })
    }
  }
  return {
    oneLiner: oneLinerMatch?.[1]?.trim() || '',
    sections,
  }
}

export function streamText(
  text: string,
  onChunk: (chunk: string) => void,
  onDone: () => void,
): () => void {
  let index = 0
  let cancelled = false

  function next() {
    if (cancelled) return
    if (index >= text.length) {
      onDone()
      return
    }
    const size = 4 + Math.floor(Math.random() * 8)
    onChunk(text.slice(index, index + size))
    index += size
    setTimeout(next, 14 + Math.random() * 20)
  }

  setTimeout(next, 120)

  return () => {
    cancelled = true
  }
}
