<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import {
  CheckCircle, ChevronLeft, Cpu, Loader2, Menu, MessageSquare, Plus, RotateCcw,
  Sparkles, Square, Users, Swords, Target, Mic, ChevronRight, UserCircle2, Crown,
  ArrowRight, X, Play, Zap, Lightbulb, Shield, TrendingUp, Code, Briefcase, Eye, Hammer,
  Radio, MessagesSquare, GitCompare, ClipboardCheck, Wand2, ArrowUpRight, Crown as CrownIcon,
  Target as TargetIcon, MessageCircleMore, CheckCheck, ChevronDown, XCircle, Compass
} from 'lucide-vue-next'
import CommitteeDebateCard from '@/components/advisors/CommitteeDebateCard.vue'
import CommitteePhaseSection from '@/components/advisors/CommitteePhaseSection.vue'
import CommitteeSummaryCard from '@/components/advisors/CommitteeSummaryCard.vue'
import CommitteeSynthesisCard from '@/components/advisors/CommitteeSynthesisCard.vue'
import IOSModelSheet from '@/components/shared/IOSModelSheet.vue'
import { startWindowDrag } from '@/utils/windowDrag'
import {
  COMMITTEE_MODE_OPTIONS,
  COMMITTEE_PACKS,
  buildRoleModelAssignments,
  type CommitteeMode,
  type CommitteePhase,
} from '@/features/committee'
import { getModelColor, useAppStore } from '@/stores/app'
import { useCommitteeStore } from '@/stores/committee'
import { useTheme } from '@/composables/useTheme'
import { CATEGORY_META, getAvatarUrl, getPixelAvatarUrl, getStanceLabels, usePersonaStore, type PersonaCategory, type PersonaDefinition } from '@/stores/persona'
import { Haptics, ImpactStyle } from '@capacitor/haptics'

const appStore = useAppStore()
const committeeStore = useCommitteeStore()
const personaStore = usePersonaStore()
const { theme } = useTheme()
const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isSmallScreen = inject<import('vue').Ref<boolean>>('isSmallScreen', ref(false))

function openDrawer() { window.dispatchEvent(new CustomEvent('open-drawer')) }

const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
const showCommitteeModelSheet = ref(false)
const currentStep = ref<1 | 2 | 3>(1)
const selectionMode = ref<'mode' | 'scene'>('mode')
const hoveredCard = ref<string | null>(null)

// 角色详情弹窗
const showRoleDetail = ref(false)
const selectedRoleForDetail = ref<PersonaDefinition | null>(null)
let longPressTimer: ReturnType<typeof setTimeout> | null = null
const LONG_PRESS_DURATION = 500 // 500ms 视为长按

// 显示角色详情
async function showRoleDetailModal(role: PersonaDefinition) {
  selectedRoleForDetail.value = role
  showRoleDetail.value = true
  // 震动反馈
  try {
    await Haptics.impact({ style: ImpactStyle.Light })
  } catch (e) {
    // 忽略错误（非 Capacitor 环境）
  }
}

function closeRoleDetail() {
  showRoleDetail.value = false
  selectedRoleForDetail.value = null
}

// 长按事件处理
let pendingRoleId: string | null = null

function onRoleTouchStart(role: PersonaDefinition, event: TouchEvent | MouseEvent) {
  if (longPressTimer) clearTimeout(longPressTimer)
  pendingRoleId = role.id
  longPressTimer = setTimeout(() => {
    pendingRoleId = null
    showRoleDetailModal(role)
    longPressTimer = null
  }, LONG_PRESS_DURATION)
}

function onRoleTouchEnd() {
  if (longPressTimer) {
    clearTimeout(longPressTimer)
    longPressTimer = null
    // 短按 → 切换角色选择
    if (pendingRoleId) {
      toggleRole(pendingRoleId)
      pendingRoleId = null
    }
  }
}

function onRoleTouchMove() {
  // 移动手指时取消长按和短按
  if (longPressTimer) {
    clearTimeout(longPressTimer)
    longPressTimer = null
  }
  pendingRoleId = null
}

const selectedPackId = ref<string | null>(null)
const selectedPreset = ref<string>('balanced')

// 职场版角色名映射
const displayNames: Record<string, string> = {
  'laochuanzhang': '战略家',
  'fengtouyan': '机会猎手',
  'chuishaoren': '风控官',
  'wuyazui': '危机预警',
  'shouyiren': '技术大牛',
  'ziyuantong': '资源调度',
  'shengyijing': '增长黑客',
  'touzijia': '财务顾问',
  'tiexinren': '用户研究员',
  'lengyankan': '挑剔用户',
  'tuijinzhe': '项目经理',
  'zhiguanyuan': '质量保障',
}

// 示例问题库
const exampleQuestions = {
  product: [
    '下周要上线新功能，帮我看看有没有遗漏的风险点？',
    '这个交互设计用户会不会觉得复杂？',
    '如果资源只能做一半，哪些功能必须保留？',
    '竞品刚上了类似功能，我们要跟吗？',
  ],
  growth: [
    '预算有限，拉新和留存应该先保哪个？',
    '这个获客渠道看起来便宜，能大规模投吗？',
    '用户说想要XX功能，做了真能提高留存吗？',
    '免费转付费怎么设计才不伤用户体验？',
  ],
  technical: [
    '技术债太多，是停下来重构还是先扛住业务？',
    '这个架构方案能支撑未来一年的增长吗？',
    '第三方服务挂了怎么办，有没有兜底方案？',
    '重构预计要2个月，业务等得起吗？',
  ],
  general: [
    '这个季度目标定了，执行计划靠谱吗？',
    '团队说要做XX，但我心里没底，帮我盘盘？',
    '老板想加需求，怎么判断该不该接？',
    '如果这个项目失败，最可能是因为什么？',
  ],
}

const currentExampleIndex = ref(0)

const roleMap = computed(() =>
  Object.fromEntries(personaStore.personas.map((role) => [role.id, role]))
)

const roleGroups = computed(() => {
  const order: PersonaCategory[] = ['strategy', 'risk', 'feasibility', 'business', 'user', 'execution']
  return order.map((category) => ({
    category,
    ...CATEGORY_META[category],
    roles: personaStore.personasByCategory[category] || [],
  }))
})

const currentMode = computed<CommitteeMode>({
  get: () => personaStore.mode,
  set: (value) => { personaStore.mode = value },
})

const activeRoles = computed(() =>
  personaStore.personas.filter((role) => (
    committeeStore.isActive ? committeeStore.activeRoleIds : personaStore.activePersonaIds
  ).includes(role.id))
)

const canSubmit = computed(() =>
  inputText.value.trim().length > 0
  && personaStore.activePersonaIds.length > 0
  && appStore.committeeSelectedModelIds.length > 0
)

const currentExampleCategory = computed(() => {
  if (selectedPackId.value === 'product') return 'product'
  if (selectedPackId.value === 'growth') return 'growth'
  if (selectedPackId.value === 'technical') return 'technical'
  return 'general'
})

const currentExamples = computed(() => {
  const category = currentExampleCategory.value
  return exampleQuestions[category as keyof typeof exampleQuestions] || exampleQuestions.general
})

const inputPlaceholder = computed(() => {
  const roleCount = personaStore.activePersonaIds.length
  if (roleCount === 0) return '先选择参谋角色，再描述你想商量的事...'
  const examples = currentExamples.value
  return examples[currentExampleIndex.value % examples.length]
})

let exampleInterval: ReturnType<typeof setInterval> | null = null
function startExampleRotation() {
  exampleInterval = setInterval(() => currentExampleIndex.value++, 4000)
}
function stopExampleRotation() {
  if (exampleInterval) clearInterval(exampleInterval)
}

async function useExampleAndRun(question: string) {
  inputText.value = question
  await nextTick()
  await handleSubmit()
}

const phaseNames: Record<CommitteePhase, string> = {
  1: '各自表态',
  2: '互相挑刺',
  3: '拍板定案',
}

const modeOptions = [
  { 
    id: 'broadcast' as CommitteeMode,
    name: '各说各话', 
    tagline: '先听大家骂', 
    desc: '每个人独立表态，不互相搭理。适合快速扫一遍不同立场。',
    icon: Radio,
    gradient: 'from-blue-500 via-indigo-500 to-violet-500',
    glow: 'shadow-blue-500/20',
  },
  { 
    id: 'debate' as CommitteeMode,
    name: '针锋相对', 
    tagline: '让他们吵一架', 
    desc: '先各自表态，再让预设对手正面回应。适合看分歧是不是硬冲突。',
    icon: MessagesSquare,
    gradient: 'from-rose-500 via-pink-500 to-fuchsia-500',
    glow: 'shadow-rose-500/20',
  },
  { 
    id: 'committee' as CommitteeMode,
    name: '拍板定案', 
    tagline: '给我个结论', 
    desc: '先发言，再由主持人收敛成共识、分歧、动作和少数派意见。',
    icon: ClipboardCheck,
    gradient: 'from-amber-500 via-orange-500 to-red-500',
    glow: 'shadow-amber-500/20',
  },
]

const sceneOptions = [
  { 
    id: 'product', 
    name: '产品挑刺', 
    emoji: '🎯', 
    desc: '新功能、版本规划、用户体验',
    mode: 'debate' as CommitteeMode,
    roles: ['laochuanzhang', 'chuishaoren', 'shouyiren', 'tiexinren', 'tuijinzhe', 'zhiguanyuan'],
    gradient: 'from-emerald-400 via-teal-400 to-cyan-500',
    icon: Lightbulb
  },
  { 
    id: 'growth', 
    name: '增长避坑', 
    emoji: '🚀', 
    desc: '拉新策略、留存优化、变现模式',
    mode: 'committee' as CommitteeMode,
    roles: ['fengtouyan', 'shengyijing', 'ziyuantong', 'touzijia', 'lengyankan', 'tuijinzhe'],
    gradient: 'from-violet-400 via-purple-400 to-fuchsia-500',
    icon: TrendingUp
  },
  { 
    id: 'technical', 
    name: '技术过堂', 
    emoji: '⚙️', 
    desc: '架构选型、技术债、上线风险评估',
    mode: 'debate' as CommitteeMode,
    roles: ['shouyiren', 'ziyuantong', 'chuishaoren', 'wuyazui', 'zhiguanyuan', 'tuijinzhe'],
    gradient: 'from-orange-400 via-amber-400 to-yellow-500',
    icon: Code
  },
]

function getModelName(modelId: string) {
  return appStore.models.find((model) => model.id === modelId)?.name || modelId
}

function getModelChipStyle(modelId: string) {
  const provider = appStore.models.find((model) => model.id === modelId)?.provider || ''
  const color = getModelColor(provider)
  return {
    backgroundColor: `${color}15`,
    borderColor: `${color}30`,
    color,
  }
}

function isRoleActive(roleId: string) {
  return personaStore.activePersonaIds.includes(roleId)
}

function toggleRole(roleId: string) {
  personaStore.togglePersona(roleId)
}

function selectAllInCategory(category: PersonaCategory) {
  const ids = roleGroups.value.find((g) => g.category === category)?.roles.map((r) => r.id) || []
  const allSelected = ids.every((id) => personaStore.activePersonaIds.includes(id))
  if (allSelected) {
    personaStore.activePersonaIds = personaStore.activePersonaIds.filter((id) => !ids.includes(id))
  } else {
    personaStore.activePersonaIds = Array.from(new Set([...personaStore.activePersonaIds, ...ids]))
  }
}

function applyQuickPreset(presetType: 'min' | 'balanced' | 'full') {
  selectedPreset.value = presetType
  if (presetType === 'min') {
    personaStore.activePersonaIds = ['laochuanzhang', 'chuishaoren', 'tiexinren']
  } else if (presetType === 'balanced') {
    personaStore.activePersonaIds = ['laochuanzhang', 'chuishaoren', 'shouyiren', 'tiexinren', 'tuijinzhe', 'shengyijing']
  } else {
    personaStore.activatePreset('all')
  }
}

function selectScene(sceneId: string) {
  const scene = sceneOptions.find(s => s.id === sceneId)
  if (!scene) return
  selectedPackId.value = sceneId
  currentMode.value = scene.mode
  personaStore.activePersonaIds = [...scene.roles]
  selectionMode.value = 'scene'
}

function selectMode(modeId: CommitteeMode) {
  currentMode.value = modeId
  selectedPackId.value = null
  selectionMode.value = 'mode'
}

function nextStep() {
  if (currentStep.value < 3) currentStep.value++
}

function prevStep() {
  if (currentStep.value > 1) currentStep.value--
}

function goToStep(step: 1 | 2 | 3) {
  currentStep.value = step
}

async function handleSubmit() {
  if (!canSubmit.value) return
  await committeeStore.startCommittee({
    promptText: inputText.value.trim(),
    mode: currentMode.value,
    roleIds: personaStore.activePersonaIds,
    modelPool: appStore.committeeSelectedModels,
    packId: selectedPackId.value || 'custom',
    presetId: null,
  })
}

function startNew() {
  inputText.value = ''
  committeeStore.clearSession()
  currentStep.value = 1
  selectionMode.value = 'mode'
  selectedPackId.value = null
  currentExampleIndex.value = 0
}

function endSession() {
  inputText.value = ''
  committeeStore.clearSession()
  currentStep.value = 1
  selectionMode.value = 'mode'
  selectedPackId.value = null
  currentExampleIndex.value = 0
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSubmit()
  }
}

onMounted(() => {
  if (!personaStore.activePersonaIds.length) personaStore.activatePreset('all')
  appStore.ensureCommitteeSelection()
  startExampleRotation()
})

onBeforeUnmount(() => stopExampleRotation())

onBeforeRouteLeave(() => {
  if (committeeStore.isStreaming) committeeStore.stop()
  inputText.value = ''
  committeeStore.clearSession()
  showCommitteeModelSheet.value = false
  stopExampleRotation()
})

const phase1Status = computed(() => {
  if (committeeStore.stopped) return committeeStore.phase1Summaries.length ? 'done' : 'waiting'
  if (committeeStore.currentPhase > 1 || (committeeStore.phaseStatus === 'completed' && !committeeStore.hasDebatePhase && !committeeStore.hasCommitteePhase)) return 'done'
  return 'running'
})

const phase2Status = computed(() => {
  if (committeeStore.stopped) return committeeStore.phase2Reviews.length ? 'done' : 'waiting'
  if (committeeStore.phaseStatus === 'completed') return 'done'
  if (committeeStore.currentPhase === 2) return 'running'
  return 'waiting'
})

const phase3Status = computed(() => {
  if (committeeStore.stopped) return committeeStore.phase3Content ? 'done' : 'waiting'
  return committeeStore.phaseStatus === 'completed' ? 'done' : 'running'
})
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent relative">
    <!-- 背景装饰 -->
    <div class="fixed inset-0 overflow-hidden pointer-events-none">
      <div class="absolute -top-[20%] -left-[10%] w-[50%] h-[50%] rounded-full bg-accent/5 blur-[120px]"></div>
      <div class="absolute top-[40%] -right-[10%] w-[40%] h-[40%] rounded-full bg-violet-500/5 blur-[100px]"></div>
    </div>

    <!-- 顶部导航 - 与原版一致 -->
    <div class="z-40 px-4 pt-4 pb-2 shrink-0">
      <header data-tauri-drag-region
        class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10"
        @mousedown.left="startWindowDrag">

        <!-- 左侧：菜单按钮 + Logo -->
        <div class="flex items-center gap-2.5">
          <button v-if="isSmallScreen" @click="openDrawer" class="p-2 -ml-1 rounded-full hover:bg-white/10 text-text-secondary transition-colors">
            <Menu :size="20" stroke-width="3" />
          </button>
          <div class="flex items-center justify-center w-8 h-8 rounded-full bg-accent text-white shadow-lg shadow-accent/20 shrink-0">
            <Compass :size="16" stroke-width="3.5" />
          </div>
          <div>
            <h1 class="text-sm font-black text-text-primary tracking-tight">锦囊参谋</h1>
            <p class="text-[9px] text-text-tertiary font-black uppercase tracking-widest opacity-50">
              {{ personaStore.activePersonaIds.length }} 角色 · {{ appStore.committeeSelectedModelIds.length }} 模型
            </p>
          </div>
        </div>

        <!-- 右侧：新议题按钮 -->
        <button v-if="!committeeStore.isActive && !committeeStore.isStreaming" @click="endSession"
          class="flex items-center gap-1.5 px-4 py-2 rounded-full bg-accent text-white text-xs font-black uppercase tracking-widest shadow-lg shadow-accent/30 hover:scale-105 active:scale-95 transition-all">
          <Plus :size="16" stroke-width="3.5" />
          <span class="hidden sm:inline">新议题</span>
        </button>
      </header>
    </div>

    <div class="flex-1 overflow-y-auto relative z-10">
      <!-- 配置阶段 -->
      <div v-if="!committeeStore.isActive && !committeeStore.isStreaming" class="mx-auto max-w-4xl px-4 py-6 sm:py-10">
        
        <!-- 步骤1：定打法 -->
        <div v-if="currentStep === 1" class="animate-in fade-in slide-in-from-bottom-6 duration-500">
          <div class="text-center mb-10">
            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 border border-accent/20 text-accent text-[10px] font-bold mb-4">
              STEP 1
            </div>
            <h2 class="text-3xl font-bold text-text-primary mb-2">选择讨论方式</h2>
            <p class="text-sm text-text-tertiary">三种模式，适合不同决策场景</p>
          </div>

          <!-- 切换 -->
          <div class="flex justify-center mb-8">
            <div class="flex p-1 bg-black/20 rounded-2xl">
              <button @click="selectionMode = 'mode'" 
                class="px-6 py-2.5 rounded-xl text-sm font-semibold transition-all"
                :class="selectionMode === 'mode' ? 'bg-accent text-white shadow-lg' : 'text-text-secondary hover:text-text-primary'">
                按打法选
              </button>
              <button @click="selectionMode = 'scene'" 
                class="px-6 py-2.5 rounded-xl text-sm font-semibold transition-all"
                :class="selectionMode === 'scene' ? 'bg-accent text-white shadow-lg' : 'text-text-secondary hover:text-text-primary'">
                按场景选
              </button>
            </div>
          </div>

          <!-- 按打法选 -->
          <div v-if="selectionMode === 'mode'" class="grid gap-4 sm:grid-cols-3">
            <button v-for="mode in modeOptions" :key="mode.id" @click="selectMode(mode.id)"
              @mouseenter="hoveredCard = mode.id" @mouseleave="hoveredCard = null"
              class="group relative p-6 rounded-3xl transition-all duration-500 text-left"
              :class="currentMode === mode.id && !selectedPackId ? 'bg-white/[0.08] border-2 border-accent/50 scale-[1.02]' : 'bg-white/[0.03] border-2 border-transparent hover:bg-white/[0.06] hover:border-white/10'">
              
              <!-- 选中光晕 -->
              <div v-if="currentMode === mode.id && !selectedPackId" 
                class="absolute inset-0 rounded-3xl opacity-30 blur-xl transition-opacity"
                :class="mode.glow.replace('shadow', 'bg')"></div>
              
              <div class="relative">
                <div class="w-14 h-14 rounded-2xl bg-gradient-to-br flex items-center justify-center text-white mb-5 transition-transform duration-500 group-hover:scale-110"
                  :class="[mode.gradient, currentMode === mode.id && !selectedPackId ? 'shadow-lg' : '']">
                  <component :is="mode.icon" :size="28" stroke-width="2" />
                </div>
                
                <h3 class="text-lg font-bold text-text-primary mb-1">{{ mode.name }}</h3>
                <p class="text-xs font-medium text-accent/80 mb-3">{{ mode.tagline }}</p>
                <p class="text-sm text-text-secondary leading-relaxed">{{ mode.desc }}</p>
              </div>
            </button>
          </div>

          <!-- 按场景选 -->
          <div v-else class="grid gap-4 sm:grid-cols-3">
            <button v-for="scene in sceneOptions" :key="scene.id" @click="selectScene(scene.id)"
              class="group relative p-6 rounded-3xl bg-white/[0.03] border-2 transition-all duration-500 text-left overflow-hidden"
              :class="selectedPackId === scene.id ? 'border-accent/50 bg-white/[0.06] scale-[1.02]' : 'border-transparent hover:bg-white/[0.05] hover:border-white/10'">
              
              <div class="absolute top-0 right-0 w-32 h-32 opacity-20 blur-3xl rounded-full transition-opacity group-hover:opacity-40"
                :class="`bg-gradient-to-br ${scene.gradient}`"></div>
              
              <div class="relative">
                <div class="w-14 h-14 rounded-2xl bg-gradient-to-br flex items-center justify-center text-white mb-5 text-2xl"
                  :class="scene.gradient">
                  <component :is="scene.icon" :size="28" class="text-white" stroke-width="2" v-if="scene.icon" />
                  <span v-else>{{ scene.emoji }}</span>
                </div>
                
                <h3 class="text-lg font-bold text-text-primary mb-1">{{ scene.name }}</h3>
                <p class="text-xs text-text-tertiary mb-3">{{ scene.desc }}</p>
                <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/5 text-[10px] text-text-secondary">
                  <component :is="modeOptions.find(m => m.id === scene.mode)?.icon" :size="10" />
                  {{ modeOptions.find(m => m.id === scene.mode)?.name }}
                </span>
              </div>
            </button>
          </div>
        </div>

        <!-- 步骤2：选帮手 -->
        <div v-if="currentStep === 2" class="animate-in fade-in slide-in-from-bottom-6 duration-500 max-w-xl mx-auto">
          <div class="text-center mb-10">
            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 border border-accent/20 text-accent text-[10px] font-bold mb-4">
              STEP 2
            </div>
            <h2 class="text-3xl font-bold text-text-primary mb-2">选择 AI 模型</h2>
            <p class="text-sm text-text-tertiary">选择扮演参谋的模型</p>
          </div>

          <!-- 模型卡片 -->
          <div class="p-6 rounded-3xl bg-white/[0.03] border border-white/[0.08] mb-6">
            <div class="flex items-center justify-between mb-4">
              <span class="text-sm font-semibold text-text-primary">已选择</span>
              <span class="px-2 py-0.5 rounded-full bg-accent/20 text-accent text-xs font-bold">
                {{ appStore.committeeSelectedModels.length }}
              </span>
            </div>
            
            <div v-if="appStore.committeeSelectedModels.length > 0" class="flex flex-wrap gap-2">
              <span v-for="model in appStore.committeeSelectedModels" :key="model.id"
                class="px-3 py-1.5 rounded-xl text-sm font-medium border"
                :style="getModelChipStyle(model.id)">
                {{ model.name }}
              </span>
            </div>
            <div v-else class="text-center py-10 text-text-tertiary">
              <Cpu :size="40" class="mx-auto mb-3 opacity-30" />
              <p>还没有选择模型</p>
            </div>
          </div>

          <button @click="showCommitteeModelSheet = true"
            class="w-full group relative py-4 rounded-2xl bg-accent text-white font-semibold overflow-hidden">
            <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700"></div>
            <span class="relative flex items-center justify-center gap-2">
              <Plus :size="20" />
              {{ appStore.committeeSelectedModels.length > 0 ? '调整模型配置' : '选择 AI 模型' }}
            </span>
          </button>
        </div>

        <!-- 步骤3：请参谋 -->
        <div v-if="currentStep === 3" class="animate-in fade-in slide-in-from-bottom-6 duration-500">
          <div class="text-center mb-8">
            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 border border-accent/20 text-accent text-[10px] font-bold mb-4">
              STEP 3
            </div>
            <h2 class="text-3xl font-bold text-text-primary mb-2">配置参谋团</h2>
            <p class="text-sm text-text-tertiary">选择参谋，提出你的问题</p>
          </div>

          <div class="grid lg:grid-cols-2 gap-6">
            <!-- 左侧：角色选择 -->
            <div class="space-y-4">
              <!-- 已选择预览 -->
              <div v-if="activeRoles.length > 0" class="p-4 rounded-2xl bg-white/[0.03] border border-white/[0.08]">
                <div class="flex items-center justify-between mb-3">
                  <span class="text-xs font-semibold text-text-primary">已选择参谋</span>
                  <button @click="personaStore.clearActive()" class="text-[10px] text-text-tertiary hover:text-rose-400">清空</button>
                </div>
                <div class="flex flex-wrap gap-2">
                  <span v-for="role in activeRoles" :key="role.id" class="px-2 py-1 rounded-lg bg-accent/10 text-accent text-xs">
                    {{ displayNames[role.id] || role.name }}
                  </span>
                </div>
              </div>

              <!-- 快速预设 -->
              <div class="flex gap-2">
                <button v-for="preset in [
                  { key: 'min', label: '精简', count: '3人' },
                  { key: 'balanced', label: '均衡', count: '6人' },
                  { key: 'full', label: '全席', count: '12人' }
                ]" :key="preset.key" @click="applyQuickPreset(preset.key as any)"
                  class="flex-1 py-3 rounded-xl text-xs font-bold border transition-all"
                  :class="selectedPreset === preset.key ? 'bg-accent text-white border-accent shadow-lg shadow-accent/25' : 'bg-surface-2 border-white/10 text-text-secondary hover:bg-surface-3'">
                  {{ preset.label }}
                  <span class="block text-[9px] opacity-80 mt-0.5 font-medium">{{ preset.count }}</span>
                </button>
              </div>

              <!-- 角色列表 -->
              <div class="space-y-5">
                <div v-for="group in roleGroups" :key="group.category">
                  <div class="flex items-center gap-2 mb-3">
                    <span class="text-lg">{{ group.icon }}</span>
                    <span class="text-sm font-semibold text-text-primary">{{ group.label }}</span>
                    <span class="text-[10px] text-text-tertiary">{{ group.roles.filter(r => isRoleActive(r.id)).length }}/{{ group.roles.length }}</span>
                    <button @click="selectAllInCategory(group.category)" class="ml-auto text-xs text-accent hover:opacity-80">
                      {{ group.roles.every(r => isRoleActive(r.id)) ? '全撤' : '全选' }}
                    </button>
                  </div>
                  
                  <div class="grid grid-cols-2 gap-2">
                    <button v-for="role in group.roles" :key="role.id" 
                      @click="toggleRole(role.id)"
                      @touchstart.prevent="onRoleTouchStart(role, $event)"
                      @touchend="onRoleTouchEnd"
                      @touchmove="onRoleTouchMove"
                      @mousedown="onRoleTouchStart(role, $event)"
                      @mouseup="onRoleTouchEnd"
                      @mouseleave="onRoleTouchEnd"
                      class="flex items-center gap-3 p-2.5 rounded-xl transition-all text-left select-none"
                      :class="isRoleActive(role.id) ? 'bg-accent/10 ring-1 ring-accent/30' : 'bg-white/[0.03] hover:bg-white/[0.06]'">
                      <img :src="getPixelAvatarUrl(role.id, 40)" 
                        :alt="displayNames[role.id] || role.name"
                        class="w-9 h-9 rounded-full shrink-0 ring-2 transition-all bg-surface-2 pointer-events-none"
                        :class="isRoleActive(role.id) ? 'ring-accent/50' : 'ring-transparent opacity-60'"
                        @error="$event.target.src = getAvatarUrl(role, 40)" />
                      <div class="min-w-0 flex-1 pointer-events-none">
                        <div class="text-xs font-semibold text-text-primary">{{ displayNames[role.id] || role.name }}</div>
                        <div class="text-[10px] text-text-tertiary truncate">{{ role.shortLabel }}</div>
                      </div>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 右侧：问题输入 -->
            <div class="flex flex-col">
              <!-- 示例问题 -->
              <div class="mb-4 space-y-2">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-semibold text-text-secondary">示例问题</span>
                  <span class="text-[10px] text-text-tertiary">点击直接运行</span>
                </div>
                <button v-for="(q, idx) in currentExamples.slice(0, 3)" :key="idx" @click="useExampleAndRun(q)"
                  class="w-full flex items-center gap-3 p-3 rounded-xl bg-white/[0.03] hover:bg-accent/10 border border-transparent hover:border-accent/20 transition-all text-left group">
                  <div class="w-7 h-7 rounded-lg bg-accent/20 flex items-center justify-center text-accent shrink-0">
                    <Play :size="12" :fill="'currentColor'" />
                  </div>
                  <span class="text-sm text-text-secondary group-hover:text-text-primary line-clamp-1 flex-1">{{ q }}</span>
                </button>
              </div>

              <!-- 输入框 -->
              <div class="flex-1 flex flex-col min-h-[240px]">
                <div class="flex-1 relative rounded-2xl bg-surface-1 border border-white/10 shadow-inner">
                  <textarea ref="textareaRef" v-model="inputText" 
                    :placeholder="inputPlaceholder"
                    class="w-full h-full p-4 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary/50 resize-none outline-none leading-relaxed"
                    @keydown="handleKeydown"></textarea>
                </div>

                <button @click="handleSubmit" :disabled="!canSubmit"
                  class="mt-3 py-3.5 rounded-xl font-semibold text-sm transition-all flex items-center justify-center gap-2 border"
                  :class="canSubmit ? 'bg-accent text-white shadow-lg shadow-accent/25 hover:shadow-accent/40 border-transparent' : 'bg-white/5 text-text-tertiary border-white/10'">
                  <Sparkles :size="16" />
                  {{ canSubmit ? '开始商议' : '请输入问题' }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部导航 -->
        <div class="flex items-center justify-between mt-12 pt-6 border-t border-white/5">
          <button v-if="currentStep > 1" @click="prevStep"
            class="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-text-secondary hover:bg-white/5 transition-colors">
            <ChevronLeft :size="18" />
            返回
          </button>
          <div v-else></div>

          <button v-if="currentStep < 3" @click="nextStep"
            class="flex items-center gap-2 px-8 py-3 rounded-xl bg-accent text-white font-semibold shadow-lg shadow-accent/25 hover:scale-105 transition-transform">
            下一步
            <ArrowRight :size="18" />
          </button>
        </div>
      </div>

      <!-- 运行结果 -->
      <div v-else class="mx-auto max-w-3xl px-4 py-6">
        <!-- 主题卡片 -->
        <div class="mb-8 p-6 rounded-3xl bg-white/[0.03] border border-white/[0.08] relative overflow-hidden">
          <div class="absolute top-0 right-0 w-64 h-64 bg-accent/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2"></div>
          <div class="relative">
            <div class="flex items-center gap-3 mb-4">
              <div class="px-3 py-1.5 rounded-full bg-accent/20 border border-accent/30 text-accent text-xs font-semibold flex items-center gap-1.5">
                <component :is="modeOptions.find(m => m.id === committeeStore.sessionMode)?.icon" :size="12" />
                {{ modeOptions.find(m => m.id === committeeStore.sessionMode)?.name }}
              </div>
              <div class="h-px flex-1 bg-gradient-to-r from-white/10 to-transparent"></div>
              <div class="flex items-center gap-3 text-[11px] text-text-tertiary">
                <span class="flex items-center gap-1"><Users :size="12" /> {{ committeeStore.activeRoleCount }}</span>
                <span class="flex items-center gap-1"><Cpu :size="12" /> {{ appStore.committeeSelectedModels.length }}</span>
              </div>
            </div>
            <p class="text-lg text-text-primary leading-relaxed">{{ committeeStore.prompt }}</p>
          </div>
        </div>

        <!-- 时间线 -->
        <div class="relative">
          <div class="absolute left-6 top-0 bottom-0 w-px bg-gradient-to-b from-accent via-rose-500 to-amber-500 opacity-30"></div>

          <!-- Phase 1 -->
          <div class="relative mb-8 pl-16">
            <div class="absolute left-0 top-0 w-12 h-12 rounded-2xl border-2 flex items-center justify-center backdrop-blur-sm transition-all"
              :class="phase1Status === 'done' ? 'bg-accent border-accent shadow-lg shadow-accent/30' : phase1Status === 'running' ? 'bg-surface-1 border-accent' : 'bg-surface-1 border-white/20'">
              <UserCircle2 :size="20" :class="phase1Status === 'done' ? 'text-white' : 'text-accent'" />
            </div>
            <div class="flex items-center justify-between mb-4">
              <div>
                <h4 class="text-base font-semibold text-text-primary">各自表态</h4>
                <p class="text-xs text-text-tertiary">{{ committeeStore.activeRoleCount }} 位参谋参与讨论</p>
              </div>
              <span v-if="phase1Status === 'running'" class="flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 text-accent text-xs">
                <Loader2 :size="12" class="animate-spin" /> 进行中
              </span>
              <span v-else-if="phase1Status === 'done'" class="flex items-center gap-1 px-3 py-1 rounded-full bg-accent/20 text-accent text-xs">
                <CheckCircle :size="12" /> 完成
              </span>
            </div>
            <div v-if="committeeStore.phase1Summaries.length > 0" class="space-y-3">
              <CommitteeSummaryCard v-for="summary in committeeStore.phase1Summaries" :key="summary.roleId"
                :summary="summary" :role="roleMap[summary.roleId]" :model-name="getModelName(summary.modelId)" />
            </div>
          </div>

          <!-- Phase 2 -->
          <div v-if="committeeStore.hasDebatePhase" class="relative mb-8 pl-16">
            <div class="absolute left-0 top-0 w-12 h-12 rounded-2xl border-2 flex items-center justify-center backdrop-blur-sm transition-all"
              :class="phase2Status === 'done' ? 'bg-rose-500 border-rose-500' : phase2Status === 'running' ? 'bg-surface-1 border-rose-500' : 'bg-surface-1 border-white/20'">
              <MessagesSquare :size="20" :class="phase2Status === 'done' ? 'text-white' : 'text-rose-500'" />
            </div>
            <div class="flex items-center justify-between mb-4">
              <div>
                <h4 class="text-base font-semibold text-text-primary">互相挑刺</h4>
                <p class="text-xs text-text-tertiary">观点交锋，发现分歧</p>
              </div>
              <span v-if="phase2Status === 'running'" class="flex items-center gap-2 px-3 py-1 rounded-full bg-rose-500/10 text-rose-500 text-xs">
                <Loader2 :size="12" class="animate-spin" /> 进行中
              </span>
            </div>
            <div v-if="committeeStore.phase2Reviews.length > 0" class="space-y-3">
              <CommitteeDebateCard v-for="review in committeeStore.phase2Reviews" :key="`${review.roleId}-${review.targetRoleId}`"
                :review="review" :role-name="displayNames[review.roleId] || roleMap[review.roleId]?.name" :target-name="displayNames[review.targetRoleId] || roleMap[review.targetRoleId]?.name" />
            </div>
          </div>

          <!-- Phase 3 -->
          <div v-if="committeeStore.hasCommitteePhase" class="relative pl-16">
            <div class="absolute left-0 top-0 w-12 h-12 rounded-2xl border-2 flex items-center justify-center backdrop-blur-sm transition-all"
              :class="phase3Status === 'done' ? 'bg-amber-500 border-amber-500' : phase3Status === 'running' ? 'bg-surface-1 border-amber-500' : 'bg-surface-1 border-white/20'">
              <Crown :size="20" :class="phase3Status === 'done' ? 'text-white' : 'text-amber-500'" />
            </div>
            <div class="flex items-center justify-between mb-4">
              <div>
                <h4 class="text-base font-semibold text-text-primary">拍板定案</h4>
                <p class="text-xs text-text-tertiary">综合各方观点，形成结论</p>
              </div>
              <span v-if="phase3Status === 'running'" class="flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 text-amber-500 text-xs">
                <Loader2 :size="12" class="animate-spin" /> 整理中
              </span>
            </div>
            <CommitteeSynthesisCard v-if="committeeStore.phase3Content || committeeStore.isStreaming"
              :synthesis="committeeStore.committeeSynthesis" :content="committeeStore.phase3Content"
              :streaming="committeeStore.isStreaming && committeeStore.currentPhase === 3" />
          </div>
        </div>

        <div class="h-24"></div>
      </div>
    </div>

    <!-- 运行时底部栏 -->
    <div v-if="committeeStore.isStreaming || (committeeStore.isActive && !committeeStore.isStreaming)" class="relative z-40 px-4 pb-6 pt-2">
      <div class="max-w-2xl mx-auto p-4 rounded-2xl bg-white/[0.05] backdrop-blur-xl border border-white/[0.1] shadow-2xl flex items-center justify-between">
        <div class="flex items-center gap-4">
          <div v-if="committeeStore.isStreaming" class="w-10 h-10 rounded-xl bg-accent/20 flex items-center justify-center">
            <Loader2 class="h-5 w-5 animate-spin text-accent" />
          </div>
          <div v-else class="w-10 h-10 rounded-xl bg-accent/20 flex items-center justify-center">
            <CheckCircle v-if="committeeStore.isCompleted" class="h-5 w-5 text-accent" />
            <XCircle v-else class="h-5 w-5 text-amber-500" />
          </div>
          <div>
            <div class="text-sm font-semibold text-text-primary">
              {{ committeeStore.isStreaming ? phaseNames[committeeStore.currentPhase] : committeeStore.isCompleted ? '商议完成' : '已中止' }}
            </div>
            <div v-if="committeeStore.isStreaming" class="text-[10px] text-text-tertiary">
              {{ committeeStore.phaseProgress.current }} / {{ committeeStore.phaseProgress.total }}
            </div>
          </div>
        </div>
        
        <div class="flex items-center gap-2">
          <button v-if="committeeStore.isStreaming" @click="committeeStore.stop()"
            class="px-4 py-2 rounded-xl bg-rose-500/10 text-rose-400 text-sm font-semibold hover:bg-rose-500/20 transition-colors">
            散会
          </button>
          <button v-else @click="startNew"
            class="px-5 py-2.5 rounded-xl bg-accent text-white text-sm font-semibold shadow-lg shadow-accent/30 hover:scale-105 transition-transform">
            再开一局
          </button>
        </div>
      </div>
    </div>

    <!-- 角色详情弹窗 -->
    <Transition name="fade">
      <div v-if="showRoleDetail && selectedRoleForDetail" 
        class="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
        @click="closeRoleDetail">
        <div class="w-full max-w-sm bg-surface-1 rounded-3xl border border-white/10 shadow-2xl overflow-hidden"
          @click.stop>
          <!-- 头部 -->
          <div class="relative p-6 bg-gradient-to-br from-accent/20 to-transparent">
            <button @click="closeRoleDetail" class="absolute top-4 right-4 p-2 rounded-full hover:bg-white/10 transition-colors">
              <X :size="18" />
            </button>
            <div class="flex items-center gap-4">
              <img :src="getPixelAvatarUrl(selectedRoleForDetail.id, 64)" 
                class="w-16 h-16 rounded-full ring-2 ring-accent/50 bg-surface-2"
                @error="$event.target.src = getAvatarUrl(selectedRoleForDetail, 64)" />
              <div>
                <h3 class="text-lg font-bold text-text-primary">{{ displayNames[selectedRoleForDetail.id] || selectedRoleForDetail.name }}</h3>
                <p class="text-xs text-accent mt-1">{{ selectedRoleForDetail.title }}</p>
              </div>
            </div>
          </div>
          
          <!-- 内容 -->
          <div class="p-6 space-y-4">
            <!-- 立场标签 -->
            <div class="flex flex-wrap gap-2">
              <span v-for="(label, key) in getStanceLabels(selectedRoleForDetail.stance)" :key="key"
                class="px-2.5 py-1 rounded-full bg-white/5 text-[10px] text-text-secondary border border-white/10">
                {{ label }}
              </span>
            </div>
            
            <!-- 核心信念 -->
            <div>
              <div class="text-[10px] font-bold text-text-tertiary uppercase tracking-wider mb-1">核心信念</div>
              <p class="text-sm text-text-primary leading-relaxed">{{ selectedRoleForDetail.coreBelief }}</p>
            </div>
            
            <!-- 不可妥协 -->
            <div>
              <div class="text-[10px] font-bold text-text-tertiary uppercase tracking-wider mb-1">绝不退让</div>
              <p class="text-sm text-text-secondary leading-relaxed">{{ selectedRoleForDetail.nonNegotiable }}</p>
            </div>
            
            <!-- 职责 -->
            <div class="pt-3 border-t border-white/10">
              <div class="text-[10px] font-bold text-text-tertiary uppercase tracking-wider mb-1">职责</div>
              <p class="text-xs text-text-tertiary">{{ selectedRoleForDetail.focus }}</p>
            </div>
          </div>
          
          <!-- 底部 -->
          <div class="p-4 bg-white/5 border-t border-white/10">
            <button @click="closeRoleDetail" class="w-full py-3 rounded-xl bg-accent text-white text-sm font-semibold shadow-lg shadow-accent/30 active:scale-95 transition-transform">
              知道了
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <IOSModelSheet :open="showCommitteeModelSheet" mode="committee" @close="showCommitteeModelSheet = false" />
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}
.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.animate-in {
  animation-fill-mode: both;
}
.fade-in {
  animation: fadeIn 0.5s ease-out;
}
.slide-in-from-bottom-6 {
  animation: slideInBottom 0.5s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes slideInBottom {
  from { 
    opacity: 0;
    transform: translateY(24px);
  }
  to { 
    opacity: 1;
    transform: translateY(0);
  }
}

/* 弹窗动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.fade-enter-active .bg-surface-1,
.fade-leave-active .bg-surface-1 {
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.fade-enter-from .bg-surface-1,
.fade-leave-to .bg-surface-1 {
  transform: scale(0.9) translateY(20px);
}
</style>
