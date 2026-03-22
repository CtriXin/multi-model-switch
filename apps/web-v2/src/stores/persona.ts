import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export interface StanceAxes {
  cognition: number
  horizon: number
  interest: number
}

export type PersonaCategory =
  | 'strategy'
  | 'risk'
  | 'feasibility'
  | 'business'
  | 'user'
  | 'execution'

export type RolePriority = 'critical' | 'core' | 'support'
export type AdvisorMode = 'broadcast' | 'debate' | 'committee'

export interface PersonaDefinition {
  id: string
  name: string
  title: string
  shortLabel: string
  category: PersonaCategory
  priority: RolePriority
  focus: string
  stance: StanceAxes
  preferredTags: string[]
  debatePartnerId: string
  coreBelief: string
  nonNegotiable: string
  thinkingPattern: string
  color: string
  accent: string
  avatarParams: string
  boundModelId: string | null
  builtin: boolean
}

export const CATEGORY_META: Record<PersonaCategory, {
  icon: string
  label: string
  desc: string
  tag: string
  borderClass: string
  softClass: string
  textClass: string
  badgeClass: string
}> = {
  strategy: {
    icon: '🧭',
    label: '看长远的',
    desc: '这事五年后还值不值',
    tag: '看远方',
    borderClass: 'border-sky-300/70',
    softClass: 'bg-sky-500/8',
    textClass: 'text-sky-700',
    badgeClass: 'bg-sky-500 text-white',
  },
  risk: {
    icon: '🧯',
    label: '找风险的',
    desc: '哪里可能出问题，最坏会怎样',
    tag: '找茬',
    borderClass: 'border-rose-300/70',
    softClass: 'bg-rose-500/8',
    textClass: 'text-rose-700',
    badgeClass: 'bg-rose-500 text-white',
  },
  feasibility: {
    icon: '🛠️',
    label: '看落地的',
    desc: '能不能做出来，资源够不够',
    tag: '能不能干',
    borderClass: 'border-emerald-300/70',
    softClass: 'bg-emerald-500/8',
    textClass: 'text-emerald-700',
    badgeClass: 'bg-emerald-500 text-white',
  },
  business: {
    icon: '🧮',
    label: '算账的',
    desc: '谁买单，怎么赚钱',
    tag: '算账',
    borderClass: 'border-fuchsia-300/70',
    softClass: 'bg-fuchsia-500/8',
    textClass: 'text-fuchsia-700',
    badgeClass: 'bg-fuchsia-500 text-white',
  },
  user: {
    icon: '📣',
    label: '看用户的',
    desc: '用户用着顺不顺手',
    tag: '听用户',
    borderClass: 'border-amber-300/80',
    softClass: 'bg-amber-500/8',
    textClass: 'text-amber-700',
    badgeClass: 'bg-amber-500 text-white',
  },
  execution: {
    icon: '📌',
    label: '抓执行的',
    desc: '谁来干，先干啥',
    tag: '抓落实',
    borderClass: 'border-violet-300/70',
    softClass: 'bg-violet-500/8',
    textClass: 'text-violet-700',
    badgeClass: 'bg-violet-500 text-white',
  },
}

const DICEBEAR_BASE = 'https://api.dicebear.com/9.x/pixel-art/svg'

export function getAvatarUrl(persona: PersonaDefinition, size = 64): string {
  return `${DICEBEAR_BASE}?${persona.avatarParams}&size=${size}&radius=50&backgroundColor=transparent`
}

// 像素风头像 - Dicebear pixel-art
const PIXEL_AVATAR_SEEDS: Record<string, string> = {
  'laochuanzhang': 'captain-strategy',
  'fengtouyan': 'vc-hunter',
  'chuishaoren': 'whistle-blower',
  'wuyazui': 'black-swan',
  'shouyiren': 'craftsman',
  'ziyuantong': 'resource-master',
  'shengyijing': 'growth-hacker',
  'touzijia': 'investor',
  'tiexinren': 'user-friendly',
  'lengyankan': 'cold-eye',
  'tuijinzhe': 'pusher',
  'zhiguanyuan': 'gatekeeper',
}

export function getPixelAvatarUrl(roleId: string, size = 64): string {
  const seed = PIXEL_AVATAR_SEEDS[roleId] || roleId
  return `https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(seed)}&size=${size}&radius=50`
}

export function getStanceLabels(stance: StanceAxes) {
  return {
    cognition: stance.cognition > 0.3 ? '押注型' : stance.cognition < -0.3 ? '避险型' : '中间派',
    horizon: stance.horizon > 0.3 ? '看长远' : stance.horizon < -0.3 ? '看眼前' : '看阶段',
    interest: stance.interest > 0.3 ? '局外人' : stance.interest < -0.3 ? '自己人' : '两边看',
  }
}

const BUILTIN_PERSONAS: PersonaDefinition[] = [
  {
    id: 'laochuanzhang',
    name: '老船长',
    title: '方向不能错的掌舵人',
    shortLabel: '掌舵',
    category: 'strategy',
    priority: 'critical',
    focus: '长期定位、方向取舍、组织下注',
    stance: { cognition: -0.7, horizon: 1, interest: -0.6 },
    preferredTags: ['reasoning', 'recommended'],
    debatePartnerId: 'fengtouyan',
    coreBelief: '船不能沉，方向比速度更重要。',
    nonNegotiable: '不接受“先做着看”式战略，除非已经说明白退路和终局。',
    thinkingPattern: '先看终局和航线，再反推今天该舍掉什么。',
    color: 'from-sky-500 to-cyan-600',
    accent: 'text-sky-700',
    avatarParams: 'seed=laochuanzhang&clothingColor=1e88e5&skinColor=f5d0a9',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'fengtouyan',
    name: '风投眼',
    title: '敢押未来的下注手',
    shortLabel: '下注',
    category: 'strategy',
    priority: 'critical',
    focus: '未来空间、赛道势能、非线性机会',
    stance: { cognition: 0.9, horizon: 1, interest: 0.8 },
    preferredTags: ['reasoning', 'vision'],
    debatePartnerId: 'laochuanzhang',
    coreBelief: '赌的是未来，不看当下盈亏，关键是值不值得一把梭。',
    nonNegotiable: '不接受只因为眼前省事，就错过大机会。',
    thinkingPattern: '先看未来增量，再看下注窗口，最后看今天要不要重仓。',
    color: 'from-violet-500 to-fuchsia-600',
    accent: 'text-violet-700',
    avatarParams: 'seed=fengtouyan&clothingColor=8e24aa&skinColor=e8d5b7',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'chuishaoren',
    name: '吹哨人',
    title: '现在就敢喊停的防线官',
    shortLabel: '喊停',
    category: 'risk',
    priority: 'critical',
    focus: '当前风险、事故防线、止损预案',
    stance: { cognition: -0.9, horizon: -0.6, interest: -0.7 },
    preferredTags: ['reasoning', 'recommended'],
    debatePartnerId: 'wuyazui',
    coreBelief: '真出事的时候，没人会夸你大胆，只会问你为什么没提前踩刹车。',
    nonNegotiable: '不接受“先上再说、出事再补”的推进方式。',
    thinkingPattern: '先找今天就会炸的点，再看怎么止血和兜底。',
    color: 'from-rose-500 to-red-600',
    accent: 'text-rose-700',
    avatarParams: 'seed=chuishaoren&clothingColor=e53935&skinColor=ffcc80',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'wuyazui',
    name: '乌鸦嘴',
    title: '专想黑天鹅的坏消息制造机',
    shortLabel: '黑天鹅',
    category: 'risk',
    priority: 'support',
    focus: '长期脆弱点、黑天鹅、信任坍塌',
    stance: { cognition: -1, horizon: 0.8, interest: 0.7 },
    preferredTags: ['reasoning', 'vision'],
    debatePartnerId: 'chuishaoren',
    coreBelief: '所有看起来光鲜的计划，时间一拉长，都可能露出要命的缝。',
    nonNegotiable: '不接受拿“小概率”当借口跳过风险准备。',
    thinkingPattern: '先想最坏能坏到哪，再看这个坑值不值得现在补。',
    color: 'from-stone-500 to-zinc-700',
    accent: 'text-stone-700',
    avatarParams: 'seed=wuyazui&clothingColor=455a64&skinColor=d7ccc8',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'shouyiren',
    name: '手艺人',
    title: '给材料就能立刻开干的老师傅',
    shortLabel: '开干',
    category: 'feasibility',
    priority: 'core',
    focus: '实现路径、技术闭环、最小可行解',
    stance: { cognition: 0.5, horizon: -0.8, interest: -0.8 },
    preferredTags: ['coding', 'fast'],
    debatePartnerId: 'ziyuantong',
    coreBelief: '先跑起来再说，能落地的方案才算方案。',
    nonNegotiable: '不接受只有概念图没有可验证原型的方案。',
    thinkingPattern: '先做最小闭环，再补结构和护栏。',
    color: 'from-emerald-500 to-teal-600',
    accent: 'text-emerald-700',
    avatarParams: 'seed=shouyiren&clothingColor=43a047&skinColor=d7ccc8',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'ziyuantong',
    name: '资源通',
    title: '会借力的资源编排师',
    shortLabel: '借力',
    category: 'feasibility',
    priority: 'support',
    focus: '资源复用、外部杠杆、长期产能',
    stance: { cognition: 0.6, horizon: 0.6, interest: 0.8 },
    preferredTags: ['coding', 'reasoning'],
    debatePartnerId: 'shouyiren',
    coreBelief: '不会借力的人，迟早会被资源成本拖死。',
    nonNegotiable: '不接受明明能复用，还要从零开始造轮子。',
    thinkingPattern: '先盘现成杠杆，再决定哪些部分值得自己扛。',
    color: 'from-lime-500 to-green-600',
    accent: 'text-lime-700',
    avatarParams: 'seed=ziyuantong&clothingColor=7cb342&skinColor=ffcc80',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'shengyijing',
    name: '生意精',
    title: '先看钱从哪来的生意脑',
    shortLabel: '来钱',
    category: 'business',
    priority: 'core',
    focus: '用户买单、增长窗口、短期回报',
    stance: { cognition: 0.9, horizon: -0.8, interest: 0.9 },
    preferredTags: ['reasoning', 'fast'],
    debatePartnerId: 'touzijia',
    coreBelief: '有风口就上，能先赚到钱才有资格谈理想。',
    nonNegotiable: '不接受没有明确买单路径的“好产品”。',
    thinkingPattern: '先看谁付钱，再看钱多久能回来。',
    color: 'from-fuchsia-500 to-pink-600',
    accent: 'text-fuchsia-700',
    avatarParams: 'seed=shengyijing&clothingColor=d81b60&skinColor=ffcc80',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'touzijia',
    name: '投资家',
    title: '盯复利而不是盯热闹的老钱',
    shortLabel: '复利',
    category: 'business',
    priority: 'core',
    focus: '长期复利、商业壁垒、资本效率',
    stance: { cognition: -0.3, horizon: 0.9, interest: 0.8 },
    preferredTags: ['reasoning', 'recommended'],
    debatePartnerId: 'shengyijing',
    coreBelief: '一锤子买卖不值钱，能复利的生意才配重投。',
    nonNegotiable: '不接受为了短期数据，把长期壁垒换掉。',
    thinkingPattern: '先看壁垒，再看现金流，最后看值不值得长期押注。',
    color: 'from-amber-500 to-yellow-600',
    accent: 'text-amber-700',
    avatarParams: 'seed=touzijia&clothingColor=f9a825&skinColor=d7ccc8',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'tiexinren',
    name: '贴心人',
    title: '替用户先把难受劲感受一遍的人',
    shortLabel: '顺手',
    category: 'user',
    priority: 'core',
    focus: '顺手程度、理解成本、用户情绪',
    stance: { cognition: 0.4, horizon: -0.7, interest: -0.3 },
    preferredTags: ['fast', 'recommended'],
    debatePartnerId: 'lengyankan',
    coreBelief: '用户不是来理解你的系统的，是来赶紧把事办了的。',
    nonNegotiable: '不接受把复杂度甩给用户，说一句“他们会习惯”。',
    thinkingPattern: '先走一遍用户路径，再删掉所有没必要的拐弯。',
    color: 'from-sky-400 to-cyan-500',
    accent: 'text-sky-700',
    avatarParams: 'seed=tiexinren&clothingColor=29b6f6&skinColor=ffcc80',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'lengyankan',
    name: '冷眼看',
    title: '一言不合就不用的挑剔用户',
    shortLabel: '挑刺',
    category: 'user',
    priority: 'support',
    focus: '采用阻力、迁移门槛、真实反感点',
    stance: { cognition: -0.7, horizon: -0.5, interest: 0.9 },
    preferredTags: ['fast', 'reasoning'],
    debatePartnerId: 'tiexinren',
    coreBelief: '用户没义务配合你成长，稍微麻烦一点他就走了。',
    nonNegotiable: '不接受需要解释三分钟才能成立的主流程。',
    thinkingPattern: '先想用户为什么会懒得用，再想怎么让他连犹豫都省掉。',
    color: 'from-slate-500 to-zinc-700',
    accent: 'text-slate-700',
    avatarParams: 'seed=lengyankan&clothingColor=6d4c41&skinColor=d7ccc8',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'tuijinzhe',
    name: '推进者',
    title: '死线当前照样往前拱的人',
    shortLabel: '推表',
    category: 'execution',
    priority: 'critical',
    focus: '动作拆解、节奏推进、第一周落地',
    stance: { cognition: 0.8, horizon: -1, interest: -0.5 },
    preferredTags: ['fast', 'coding'],
    debatePartnerId: 'zhiguanyuan',
    coreBelief: '再好的方案，不拆成动作，也只是会上说得漂亮。',
    nonNegotiable: '不接受没有负责人、时间盒和交付物的计划。',
    thinkingPattern: '先定动作，再定顺序，最后定谁来背结果。',
    color: 'from-indigo-500 to-blue-700',
    accent: 'text-indigo-700',
    avatarParams: 'seed=tuijinzhe&clothingColor=3949ab&skinColor=ffcc80',
    boundModelId: null,
    builtin: true,
  },
  {
    id: 'zhiguanyuan',
    name: '质管员',
    title: '宁可延期也不放垃圾上线的人',
    shortLabel: '守门',
    category: 'execution',
    priority: 'support',
    focus: '上线质量、依赖清理、验收门槛',
    stance: { cognition: -0.8, horizon: -0.7, interest: -0.6 },
    preferredTags: ['coding', 'reasoning'],
    debatePartnerId: 'tuijinzhe',
    coreBelief: '赶出来的垃圾，最后都会十倍返工。',
    nonNegotiable: '不接受把关键依赖留到最后一周再处理。',
    thinkingPattern: '先找阻塞，再设验收门，最后判断能不能放行。',
    color: 'from-orange-500 to-amber-600',
    accent: 'text-orange-700',
    avatarParams: 'seed=zhiguanyuan&clothingColor=fb8c00&skinColor=d7ccc8',
    boundModelId: null,
    builtin: true,
  },
]

export function buildPersonaSystemPrompt(persona: PersonaDefinition): string {
  const stance = getStanceLabels(persona.stance)
  return [
    `你现在扮演固定角色：${persona.name} · ${persona.title}`,
    '',
    `你的职责：${persona.focus}`,
    `你的站位：${stance.cognition} / ${stance.horizon} / ${stance.interest}`,
    `你的核心信念：${persona.coreBelief}`,
    `你的不可妥协点：${persona.nonNegotiable}`,
    `你的思维方式：${persona.thinkingPattern}`,
    '',
    '要求：',
    '- 全程用中文输出，先给判断，再给理由。',
    '- 立场要稳，不要为了显得全面而把自己说成和稀泥的人。',
    '- 如果你反对，就直接说反对，不要打圆场。',
  ].join('\n')
}

export const usePersonaStore = defineStore('persona', () => {
  const personas = ref<PersonaDefinition[]>([...BUILTIN_PERSONAS])
  const activePersonaIds = ref<string[]>([])
  const mode = ref<AdvisorMode>('broadcast')

  const activePersonas = computed(() =>
    activePersonaIds.value
      .map((id) => personas.value.find((p) => p.id === id))
      .filter(Boolean) as PersonaDefinition[],
  )

  const personasByCategory = computed(() => {
    const map: Record<string, PersonaDefinition[]> = {}
    for (const persona of personas.value) {
      ;(map[persona.category] ??= []).push(persona)
    }
    return map
  })

  function togglePersona(id: string) {
    const idx = activePersonaIds.value.indexOf(id)
    if (idx >= 0) {
      activePersonaIds.value.splice(idx, 1)
      return
    }
    activePersonaIds.value.push(id)
  }

  function activateCategory(category: PersonaCategory) {
    const next = personas.value
      .filter((persona) => persona.category === category)
      .map((persona) => persona.id)
    activePersonaIds.value = Array.from(new Set([...activePersonaIds.value, ...next]))
  }

  function clearActive() {
    activePersonaIds.value = []
  }

  function activatePreset(preset: 'tech' | 'business' | 'all') {
    if (preset === 'tech') {
      activePersonaIds.value = personas.value
        .filter((persona) => ['feasibility', 'risk', 'execution'].includes(persona.category))
        .map((persona) => persona.id)
      return
    }
    if (preset === 'business') {
      activePersonaIds.value = personas.value
        .filter((persona) => ['strategy', 'business', 'user'].includes(persona.category))
        .map((persona) => persona.id)
      return
    }
    activePersonaIds.value = personas.value.map((persona) => persona.id)
  }

  return {
    personas,
    activePersonaIds,
    activePersonas,
    personasByCategory,
    mode,
    togglePersona,
    activateCategory,
    clearActive,
    activatePreset,
  }
})
