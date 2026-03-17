<script setup lang="ts">
import { computed, inject, nextTick, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import {
  CheckCircle, ChevronDown, Cpu, Layers, Loader2, Menu, MessageSquare, Moon, Plus, RotateCcw,
  Sparkles, Square, Sun, Users
} from 'lucide-vue-next'
import CommitteeDebateCard from '@/components/advisors/CommitteeDebateCard.vue'
import CommitteeModelPoolPicker from '@/components/advisors/CommitteeModelPoolPicker.vue'
import CommitteePhaseSection from '@/components/advisors/CommitteePhaseSection.vue'
import CommitteeSummaryCard from '@/components/advisors/CommitteeSummaryCard.vue'
import CommitteeSynthesisCard from '@/components/advisors/CommitteeSynthesisCard.vue'
import IOSModelSheet from '@/components/shared/IOSModelSheet.vue'
import { startWindowDrag } from '@/utils/windowDrag'
import {
  COMMITTEE_MODE_OPTIONS,
  COMMITTEE_PACKS,
  COMMITTEE_PRESETS,
  buildRoleModelAssignments,
  type CommitteeMode,
  type CommitteePhase,
} from '@/features/committee'
import { getModelColor, useAppStore } from '@/stores/app'
import { useCommitteeStore } from '@/stores/committee'
import { useTheme } from '@/composables/useTheme'
import { CATEGORY_META, getAvatarUrl, getStanceLabels, usePersonaStore, type PersonaCategory } from '@/stores/persona'

const appStore = useAppStore()
const committeeStore = useCommitteeStore()
const personaStore = usePersonaStore()
const { theme, toggle: toggleTheme } = useTheme()
const platform = inject<import('vue').Ref<string>>('platform')

function openDrawer() { window.dispatchEvent(new CustomEvent('open-drawer')) }
function openModels() { window.dispatchEvent(new CustomEvent('open-models')) }

const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
const showAssignments = ref(false)
const showCommitteeModelSheet = ref(false)
const resultInspector = ref<'mode' | 'roles' | 'models'>('mode')
const activeInspectors = ref(new Set<string>(['mode']))

function toggleInspector(section: string) {
  if (activeInspectors.value.has(section)) {
    if (activeInspectors.value.size > 1) activeInspectors.value.delete(section)
  } else {
    activeInspectors.value.add(section)
  }
}

function isInspectorActive(section: string) {
  return activeInspectors.value.has(section)
}

const selectedPackId = ref(COMMITTEE_PACKS[0]?.id || 'product')

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

const currentModeOption = computed(() =>
  COMMITTEE_MODE_OPTIONS.find((mode) => mode.id === currentMode.value)
)

const activePack = computed(() =>
  COMMITTEE_PACKS.find((pack) => pack.id === selectedPackId.value) || COMMITTEE_PACKS[0]
)

const filteredCommitteePresets = computed(() =>
  COMMITTEE_PRESETS.filter((preset) => preset.packId === activePack.value.id)
)

const activePresetId = computed(() =>
  COMMITTEE_PRESETS.find((preset) =>
    preset.mode === currentMode.value
    && preset.roleIds.length === personaStore.activePersonaIds.length
    && preset.roleIds.every((roleId) => personaStore.activePersonaIds.includes(roleId))
  )?.id || null
)

const startedModeOption = computed(() =>
  COMMITTEE_MODE_OPTIONS.find((mode) => mode.id === committeeStore.sessionMode)
)

const canSubmit = computed(() =>
  inputText.value.trim().length > 0
  && personaStore.activePersonaIds.length > 0
  && appStore.committeeSelectedModelIds.length > 0
)

const previewAssignments = computed(() =>
  buildRoleModelAssignments(
    personaStore.activePersonaIds,
    personaStore.personas,
    appStore.committeeSelectedModels,
  )
)

const assignmentSource = computed(() =>
  committeeStore.isActive ? committeeStore.roleAssignments : previewAssignments.value
)

const assignmentMap = computed(() =>
  Object.fromEntries(assignmentSource.value.map((item) => [item.roleId, item]))
)

const activeRoles = computed(() =>
  personaStore.personas.filter((role) => (
    committeeStore.isActive ? committeeStore.activeRoleIds : personaStore.activePersonaIds
  ).includes(role.id))
)

const phaseNames: Record<CommitteePhase, string> = {
  1: '角色独立发言',
  2: '第二轮正面回应',
  3: '系统主持人汇总',
}

const inspectorModeText = computed(() => {
  if (committeeStore.sessionMode === 'debate') {
    return '先各自表态，再让预设对手正面回应，适合看分歧到底是不是硬冲突。'
  }
  if (committeeStore.sessionMode === 'committee') {
    return '先发言，再让系统主持人收敛成共识、分歧、动作和少数派意见。'
  }
  return '每个角色平行发言，不互相回应，适合先快速扫一遍不同站位。'
})

const phase1Status = computed(() => {
  if (committeeStore.stopped) return committeeStore.phase1Summaries.length ? 'done' : 'waiting'
  if (
    committeeStore.currentPhase > 1
    || (committeeStore.phaseStatus === 'completed' && !committeeStore.hasDebatePhase && !committeeStore.hasCommitteePhase)
  ) {
    return 'done'
  }
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

function getModelName(modelId: string) {
  return appStore.models.find((model) => model.id === modelId)?.name || modelId
}

function getModelChipStyle(modelId: string) {
  const provider = appStore.models.find((model) => model.id === modelId)?.provider || ''
  const color = getModelColor(provider)
  return {
    backgroundColor: `${color}14`,
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

function selectAllRoles() {
  personaStore.activatePreset('all')
}

function clearRoles() {
  personaStore.clearActive()
}

function selectCommitteePack(packId: string) {
  selectedPackId.value = packId
}

function applyCommitteePreset(presetId: string) {
  const preset = COMMITTEE_PRESETS.find((item) => item.id === presetId)
  if (!preset) return
  selectedPackId.value = preset.packId
  currentMode.value = preset.mode
  personaStore.activePersonaIds = [...preset.roleIds]
}

function getPresetRoleNames(roleIds: string[]) {
  return roleIds
    .map((roleId) => roleMap.value[roleId]?.name)
    .filter((name): name is string => !!name)
}

function isCategoryFullySelected(category: PersonaCategory) {
  return (roleGroups.value.find((group) => group.category === category)?.roles || [])
    .every((role) => personaStore.activePersonaIds.includes(role.id))
}

function isCategoryActive(category: PersonaCategory) {
  return (roleGroups.value.find((group) => group.category === category)?.roles || [])
    .some((role) => personaStore.activePersonaIds.includes(role.id))
}

function toggleCategory(category: PersonaCategory) {
  const ids = (roleGroups.value.find((group) => group.category === category)?.roles || [])
    .map((role) => role.id)
  if (!ids.length) return

  if (ids.every((id) => personaStore.activePersonaIds.includes(id))) {
    personaStore.activePersonaIds = personaStore.activePersonaIds.filter((id) => !ids.includes(id))
    return
  }
  personaStore.activePersonaIds = Array.from(new Set([...personaStore.activePersonaIds, ...ids]))
}

async function handleSubmit() {
  if (!canSubmit.value) return
  await committeeStore.startCommittee({
    promptText: inputText.value.trim(),
    mode: currentMode.value,
    roleIds: personaStore.activePersonaIds,
    modelPool: appStore.committeeSelectedModels,
    packId: selectedPackId.value,
    presetId: activePresetId.value,
  })
  resultInspector.value = 'mode'
}

function startNew() {
  inputText.value = ''
  committeeStore.clearSession()
  nextTick(resizeComposer)
}

function endSession() {
  inputText.value = ''
  committeeStore.clearSession()
  activeInspectors.value = new Set(['mode'])
  nextTick(resizeComposer)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSubmit()
  }
}

function resizeComposer() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

onMounted(() => {
  if (!personaStore.activePersonaIds.length) {
    personaStore.activatePreset('all')
  }
  appStore.ensureCommitteeSelection()
  nextTick(resizeComposer)
})

watch(inputText, () => {
  nextTick(resizeComposer)
})

onBeforeRouteLeave(() => {
  if (committeeStore.isStreaming) {
    committeeStore.stop()
  }
  inputText.value = ''
  committeeStore.clearSession()
  resultInspector.value = 'mode'
  showCommitteeModelSheet.value = false
})
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">
    <!-- Group 1: Floating Capsule Header (V3 SPEC Style) -->
    <div class="z-40 px-4 pt-4 pb-2 shrink-0">
      <header
        data-tauri-drag-region
        class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10"
        @mousedown.left="startWindowDrag">

        <!-- Left: Sidebar Breadcrumb & Info -->
        <div class="flex items-center gap-1 sm:gap-2 min-w-0">
          <!-- Mobile Sidebar Toggle (Mobile ONLY) -->
          <button @click="openDrawer"
            class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors sm:hidden">
            <Menu :size="18" />
          </button>

          <div class="flex items-center gap-2.5 min-w-0">
            <!-- Identity Icon (Sparkles for Advisors) -->
            <div
              class="flex items-center justify-center w-8 h-8 rounded-full bg-accent text-white shadow-lg shadow-accent/20 shrink-0">
              <Sparkles :size="16" />
            </div>
            <div class="min-w-0">
              <h1 class="text-sm font-black text-text-primary truncate tracking-tight">
                AI 锦囊团
              </h1>
              <p
                class="text-[9px] text-text-tertiary font-black uppercase tracking-widest opacity-50 hidden sm:block">
                {{ personaStore.activePersonaIds.length }} 角色 ·
                {{ appStore.committeeSelectedModels.length }} 模型
              </p>
            </div>
          </div>
        </div>

        <!-- Right: Control Suite -->
        <div class="flex items-center gap-2">
          <!-- New Session -->
          <button @click="endSession"
            class="p-2 sm:px-4 sm:py-2 rounded-full bg-accent text-white shadow-xl shadow-accent/30 hover:scale-105 active:scale-95 transition-all flex items-center gap-2">
            <Plus :size="18" :stroke-width="4" />
            <span
              class="hidden sm:inline text-[10px] font-black uppercase tracking-widest">新议题</span>
          </button>
        </div>
      </header>
    </div>

    <div class="flex-1 overflow-y-auto">
      <div v-if="!committeeStore.isActive && !committeeStore.isStreaming"
        class="mx-auto max-w-5xl px-4 py-6 md:px-6 md:py-8">
        <section class="rounded-5xl border border-border-default bg-surface-1 shadow-sm">
          <div class="grid gap-6 px-4 py-5 md:px-6 md:py-6 lg:grid-cols-[1.08fr_0.92fr] lg:px-8">
            <div>
              <div
                class="mb-4 inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-accent">
                AI 锦囊团
              </div>
              <h1
                class="max-w-3xl text-2xl font-semibold leading-tight text-text-primary md:text-[2.2rem]">
                先把这轮会议配好，再让角色正式上桌。
              </h1>
              <p class="mt-3 max-w-2xl text-sm leading-7 text-text-secondary md:mt-4 md:text-base">
                这一页只做一次性锦囊团，不做会话历史。你可以把它理解成临时战情会：
                模式决定怎么开，角色决定谁发言，模型池决定谁来扮演这些人。
              </p>

              <div id="committee-mode-section" class="mt-6 grid gap-3 sm:grid-cols-3">
                <button v-for="mode in COMMITTEE_MODE_OPTIONS" :key="mode.id"
                  @click="currentMode = mode.id"
                  class="rounded-4xl border px-4 py-4 text-left transition-all duration-200"
                  :class="currentMode === mode.id
                    ? 'border-accent/35 bg-accent/10 shadow-sm'
                    : 'border-border-default bg-surface-1 hover:border-accent/20 hover:bg-surface-2/70 hover:shadow-sm'">
                  <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-accent">
                    {{ mode.tagline }}</div>
                  <div class="mt-2 text-lg font-semibold text-text-primary">{{ mode.name }}</div>
                  <p class="mt-2 text-xs leading-6 text-text-secondary">{{ mode.description }}</p>
                </button>
              </div>
            </div>

            <div id="committee-models-section">
              <CommitteeModelPoolPicker @open-sheet="showCommitteeModelSheet = true" />
            </div>
          </div>
        </section>

        <section
          class="mt-6 rounded-5xl border border-border-default bg-surface-1 p-5 shadow-sm md:p-6">
          <div class="space-y-6">
            <div class="flex flex-col">
              <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-text-tertiary">
                Committee Packs</div>
              <div class="mt-2">
                <h2 class="text-2xl font-semibold text-text-primary">任务委员会包</h2>
                <p class="mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
                  先按问题类型选一层场景。它不替你决定答案，只是先把这轮会议该看的角度收拢到对的方向上。
                </p>
              </div>

              <div class="mt-4 grid gap-2 md:grid-cols-3">
                <button v-for="pack in COMMITTEE_PACKS" :key="pack.id"
                  @click="selectCommitteePack(pack.id)"
                  class="flex h-full flex-col rounded-3xl border px-4 py-3 text-left transition-all duration-200"
                  :class="activePack.id === pack.id
                    ? 'border-accent/35 bg-accent/8 shadow-sm'
                    : 'border-border-default bg-surface-2/40 hover:border-border-subtle hover:bg-surface-2/80'">
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <div class="text-sm font-semibold text-text-primary">{{ pack.name }}</div>
                      <div class="mt-1 text-[11px] leading-5 text-text-secondary">
                        {{ pack.subtitle }}</div>
                    </div>
                    <span
                      class="inline-flex shrink-0 whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-medium leading-none"
                      :class="activePack.id === pack.id ? 'bg-accent/12 text-accent' : 'bg-surface-1 text-text-tertiary'">
                      {{ pack.outcomes.length }} 类
                    </span>
                  </div>
                  <div class="mt-3 flex flex-wrap gap-1.5">
                    <span v-for="outcome in pack.outcomes" :key="outcome"
                      class="rounded-full border border-border-subtle bg-surface-1 px-2 py-0.5 text-[10px] text-text-tertiary">
                      {{ outcome }}
                    </span>
                  </div>
                </button>
              </div>
            </div>

            <div class="h-px bg-border-subtle" />

            <div class="flex flex-col">
              <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-text-tertiary">
                Presets</div>
              <div class="mt-2">
                <h2 class="text-2xl font-semibold text-text-primary">对症抓药</h2>
                <p class="mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
                  根据你想解决的问题，自动抓一组角色给你用。当前是
                  <span class="font-semibold text-text-primary">{{ activePack.name }}</span>
                  ：{{ activePack.focus }}。
                </p>
              </div>

              <div class="mt-4 grid gap-2 sm:grid-cols-2">
                <button v-for="preset in filteredCommitteePresets" :key="preset.id"
                  @click="applyCommitteePreset(preset.id)"
                  class="flex h-full flex-col rounded-3xl border px-4 py-3 text-left transition-all duration-200"
                  :class="activePresetId === preset.id
                    ? 'border-accent/35 bg-accent/8 shadow-sm'
                    : 'border-border-default bg-surface-2/40 hover:border-border-subtle hover:bg-surface-2/80'">
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <div class="text-sm font-semibold text-text-primary">{{ preset.name }}</div>
                      <div class="mt-1 text-[11px] leading-5 text-text-secondary">
                        {{ preset.subtitle }}</div>
                    </div>
                    <span
                      class="inline-flex shrink-0 whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-medium leading-none"
                      :class="activePresetId === preset.id ? 'bg-accent/12 text-accent' : 'bg-surface-1 text-text-tertiary'">
                      {{ COMMITTEE_MODE_OPTIONS.find((mode) => mode.id === preset.mode)?.name }}
                    </span>
                  </div>
                  <p class="mt-2 text-xs leading-6 text-text-secondary">{{ preset.description }}</p>
                  <div class="mt-auto flex flex-wrap gap-1.5 pt-3">
                    <span v-for="roleName in getPresetRoleNames(preset.roleIds)" :key="roleName"
                      class="rounded-full border border-border-subtle bg-surface-1 px-2 py-0.5 text-[10px] text-text-tertiary">
                      {{ roleName }}
                    </span>
                  </div>
                </button>
              </div>
            </div>
          </div>
        </section>

        <section id="committee-roles-section"
          class="mt-6 rounded-5xl border border-border-default bg-surface-1/95 p-5 shadow-sm md:p-6">
          <div class="flex flex-col gap-4">
            <div>
              <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-text-tertiary">
                Persona Matrix</div>
              <h2 class="mt-2 text-2xl font-semibold text-text-primary">12 个预设角色，按角度互相掐架</h2>
              <p class="mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
                普通用户不需要先学什么立场轴，直接勾角色就行。你真正要验证的是：
                同一件事，换一群不同站位的人来看，会不会得出明显不同的判断。
              </p>
            </div>
            <div class="flex flex-wrap gap-2 md:justify-end">
              <button @click="showAssignments = !showAssignments"
                class="whitespace-nowrap rounded-full border border-border-default bg-surface-1 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-subtle hover:text-text-primary">
                {{ showAssignments ? '隐藏分配' : '查看分配' }}
              </button>
              <button @click="selectAllRoles"
                class="whitespace-nowrap rounded-full border border-border-default px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-subtle hover:text-text-primary">
                全选 12 角
              </button>
              <button @click="clearRoles"
                class="whitespace-nowrap rounded-full border border-border-default px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-subtle hover:text-text-primary">
                清空
              </button>
            </div>
          </div>

          <div class="mt-6 grid gap-4 xl:grid-cols-2">
            <div v-for="group in roleGroups" :key="group.category"
              class="rounded-4xl border bg-surface-1 p-4 shadow-sm" :class="isCategoryActive(group.category)
                ? [group.borderClass, group.softClass]
                : 'border-border-default'">
              <div class="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div class="text-[11px] font-semibold uppercase tracking-[0.22em]"
                    :class="isCategoryActive(group.category) ? group.textClass : 'text-text-tertiary'">
                    {{ group.tag }}
                  </div>
                  <div class="mt-1 text-lg font-semibold text-text-primary">{{ group.label }}</div>
                  <div class="mt-1 text-xs text-text-secondary">{{ group.desc }}</div>
                </div>
                <button @click="toggleCategory(group.category)"
                  class="rounded-full border bg-surface-1 px-3 py-1.5 text-[11px] font-medium transition-colors hover:bg-surface-2"
                  :class="isCategoryActive(group.category)
                    ? [group.borderClass, group.textClass]
                    : 'border-border-default text-text-secondary'">
                  {{ isCategoryFullySelected(group.category) ? '取消整组' : '整组激活' }}
                </button>
              </div>

              <div class="grid gap-3 md:grid-cols-2">
                <button v-for="role in group.roles" :key="role.id" @click="toggleRole(role.id)"
                  class="flex h-full flex-col overflow-hidden rounded-4xl border border-border-default bg-surface-1 p-3 text-left transition-all duration-200"
                  :class="isRoleActive(role.id)
                    ? [group.borderClass, 'shadow-md']
                    : 'opacity-60 hover:bg-surface-2 hover:opacity-100'">
                  <div class="flex items-center justify-between gap-3">
                    <div class="flex min-w-0 items-center gap-3">
                      <img :src="getAvatarUrl(role, 34)" :alt="role.name"
                        class="h-8.5 w-8.5 rounded-full bg-surface-3 shrink-0"
                        :class="isRoleActive(role.id) ? '' : 'grayscale'" />
                      <div class="min-w-0">
                        <div class="truncate text-sm font-semibold text-text-primary">
                          {{ role.name }}</div>
                      </div>
                    </div>
                    <div
                      class="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold leading-none"
                      :class="isRoleActive(role.id)
                        ? group.badgeClass
                        : 'bg-surface-3 text-text-tertiary'">
                      {{ isRoleActive(role.id) ? '已激活' : '待命中' }}
                    </div>
                  </div>

                  <div class="mt-1.5 text-xs leading-5 text-text-tertiary">
                    {{ role.title }}
                  </div>

                  <div class="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                    <span class="rounded-full px-2 py-0.5"
                      :class="isRoleActive(role.id) ? 'bg-sky-500/10 text-sky-400' : 'bg-surface-3 text-text-tertiary'">
                      {{ getStanceLabels(role.stance).cognition }}
                    </span>
                    <span class="rounded-full px-2 py-0.5"
                      :class="isRoleActive(role.id) ? 'bg-amber-500/10 text-amber-400' : 'bg-surface-3 text-text-tertiary'">
                      {{ getStanceLabels(role.stance).horizon }}
                    </span>
                    <span class="rounded-full px-2 py-0.5"
                      :class="isRoleActive(role.id) ? 'bg-emerald-500/10 text-emerald-400' : 'bg-surface-3 text-text-tertiary'">
                      {{ getStanceLabels(role.stance).interest }}
                    </span>
                  </div>

                  <p class="mt-3 text-xs leading-5 text-text-secondary"
                    :class="showAssignments ? 'min-h-[64px]' : ''">
                    {{ role.coreBelief }}
                  </p>

                  <p class="mt-2 text-[11px] leading-5 text-text-tertiary">
                    不可妥协：{{ role.nonNegotiable }}
                  </p>

                  <div v-if="showAssignments"
                    class="mt-3 rounded-xl border border-border-default bg-surface-2/70 px-3 py-2.5">
                    <template v-if="assignmentMap[role.id]">
                      <div class="flex items-center justify-between gap-2">
                        <span class="text-[11px] font-medium text-accent">当前模型</span>
                        <span class="truncate text-[11px] font-semibold text-text-primary">
                          {{ getModelName(assignmentMap[role.id].modelId) }}
                        </span>
                      </div>
                      <div class="mt-2 flex flex-wrap gap-1.5">
                        <span v-for="reason in assignmentMap[role.id].reasons.slice(0, 2)"
                          :key="reason"
                          class="rounded-full border border-border-subtle bg-surface-1 px-2 py-0.5 text-[10px] text-text-tertiary">
                          {{ reason }}
                        </span>
                      </div>
                    </template>
                    <template v-else>
                      <div class="flex items-center justify-between gap-2">
                        <span class="text-[11px] font-medium text-text-tertiary">当前模型</span>
                        <span class="text-[11px] font-semibold text-text-tertiary">未分配</span>
                      </div>
                      <div class="mt-2 text-[10px] text-text-tertiary">
                        待命中的角色本轮不会占用模型。
                      </div>
                    </template>
                  </div>
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div v-else class="mx-auto max-w-5xl px-4 py-6 md:px-6">
        <div class="relative">
          <div class="absolute left-5 top-0 bottom-0 hidden w-px bg-border-subtle md:block" />

          <div class="relative mb-8 flex items-start gap-4">
            <div
              class="z-10 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-surface-1 shadow-sm border border-border-default">
              <MessageSquare class="h-4 w-4 text-accent" />
            </div>
            <div
              class="flex-1 rounded-4xl border border-border-default bg-surface-1 px-4 py-4 shadow-sm">
              <div class="flex flex-wrap items-center gap-2">
                <button
                  class="rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] transition-all"
                  :class="isInspectorActive('mode') ? 'bg-accent text-white shadow-lg scale-105' : 'bg-surface-2 text-text-tertiary hover:bg-surface-3 opacity-60'"
                  @click="toggleInspector('mode')">
                  {{ startedModeOption?.name }}
                </button>
                <button
                  class="rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] transition-all"
                  :class="isInspectorActive('roles') ? 'bg-accent text-white shadow-lg scale-105' : 'bg-surface-2 text-text-tertiary hover:bg-surface-3 opacity-60'"
                  @click="toggleInspector('roles')">
                  {{ committeeStore.activeRoleCount }} 个角色
                </button>
                <button
                  class="rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] transition-all"
                  :class="isInspectorActive('models') ? 'bg-accent text-white shadow-lg scale-105' : 'bg-surface-2 text-text-tertiary hover:bg-surface-3 opacity-60'"
                  @click="toggleInspector('models')">
                  {{ appStore.committeeSelectedModels.length }} 个模型池
                </button>
              </div>
              <p
                class="mt-4 text-base font-semibold leading-relaxed text-text-primary italic border-l-4 border-accent/20 pl-4">
                {{ committeeStore.prompt }}</p>

              <div class="mt-6 space-y-4">
                <div v-if="isInspectorActive('mode')"
                  class="rounded-3xl border border-accent/10 bg-accent/5 px-4 py-3 animate-slide-up">
                  <div class="text-[10px] font-black uppercase tracking-widest text-accent/60">当前模式
                  </div>
                  <div class="mt-1 text-sm font-black text-text-primary uppercase tracking-tight">
                    {{ startedModeOption?.name }}</div>
                  <p class="mt-1 text-xs leading-relaxed text-text-secondary font-medium">
                    {{ inspectorModeText }}</p>
                </div>

                <div v-if="isInspectorActive('roles')"
                  class="rounded-3xl border border-border-subtle bg-surface-2/40 px-4 py-3 animate-slide-up">
                  <div
                    class="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-text-tertiary">
                    <Users class="h-3 w-3" />
                    当前角色组
                  </div>
                  <div class="mt-3 flex flex-wrap gap-1.5">
                    <span v-for="role in activeRoles" :key="role.id"
                      class="rounded-full border border-white/5 bg-white/5 px-3 py-1 text-[11px] font-bold text-text-secondary">
                      {{ role.name }}
                    </span>
                  </div>
                </div>

                <div v-if="isInspectorActive('models')"
                  class="rounded-3xl border border-border-subtle bg-surface-2/40 px-4 py-3 animate-slide-up">
                  <div
                    class="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-text-tertiary">
                    <Cpu class="h-3 w-3" />
                    模型池分配
                  </div>
                  <div class="mt-3 flex flex-wrap gap-1.5">
                    <span v-for="model in appStore.committeeSelectedModels" :key="model.id"
                      class="rounded-full border px-3 py-1 text-[11px] font-bold"
                      :style="getModelChipStyle(model.id)">
                      {{ model.name }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <CommitteePhaseSection :phase="1" title="角色独立发言"
            :subtitle="`${committeeStore.activeRoleCount} 个高参并行发言`" :status="phase1Status"
            color-class="bg-accent">
            <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <CommitteeSummaryCard v-for="summary in committeeStore.phase1Summaries"
                :key="summary.roleId" :summary="summary" :role="roleMap[summary.roleId]"
                :model-name="getModelName(summary.modelId)" />
            </div>
          </CommitteePhaseSection>

          <CommitteePhaseSection v-if="committeeStore.hasDebatePhase" :phase="2" title="第二轮正面回应"
            subtitle="立场不改，但要正面接招" :status="phase2Status" color-class="bg-rose-500">
            <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <CommitteeDebateCard v-for="review in committeeStore.phase2Reviews"
                :key="`${review.roleId}-${review.targetRoleId}`" :review="review"
                :role-name="roleMap[review.roleId]?.name || review.roleId"
                :target-name="roleMap[review.targetRoleId]?.name || review.targetRoleId" />
            </div>
          </CommitteePhaseSection>

          <CommitteePhaseSection v-if="committeeStore.hasCommitteePhase" :phase="3" title="系统主持人总结"
            :subtitle="committeeStore.synthesizer || ''" :status="phase3Status"
            color-class="bg-amber-500">
            <CommitteeSynthesisCard :synthesis="committeeStore.committeeSynthesis"
              :content="committeeStore.phase3Content"
              :streaming="committeeStore.isStreaming && committeeStore.currentPhase === 3" />
          </CommitteePhaseSection>
        </div>

        <div class="h-10" />
      </div>
    </div>

    <!-- Group 3: Trinity Control Pod (Consistency with Chat/Discuss) -->
    <div class="z-30 px-4 pb-4 pt-4 shrink-0">
      <div
        class="max-w-6xl mx-auto glass-v3 rounded-[36px] shadow-[0_32px_64px_-12px_rgba(0,0,0,0.5)] transition-all duration-500 relative flex flex-col overflow-visible border border-white/10">

        <!-- Status Bar (Top of Pod) -->
        <div v-if="!committeeStore.isActive && !committeeStore.isStreaming"
          class="px-6 pt-3 pb-1 overflow-x-auto no-scrollbar">
          <div
            class="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-text-tertiary">
            <span
              class="px-2 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20">{{ currentModeOption?.name }}</span>
            <span
              class="px-2 py-0.5 rounded-full bg-white/5 border border-white/5">{{ personaStore.activePersonaIds.length }}
              个角色已激活</span>
            <span
              class="px-2 py-0.5 rounded-full bg-white/5 border border-white/5">{{ appStore.committeeSelectedModels.length }}
              个模型池</span>
          </div>
        </div>

        <!-- Input / Streaming / Done State -->
        <div class="px-4 pb-2 pt-1">
          <!-- Normal Input State -->
          <div v-if="!committeeStore.isActive && !committeeStore.isStreaming"
            class="flex items-end gap-2 px-2">
            <textarea ref="textareaRef" v-model="inputText" placeholder="输入锦囊团议题..." rows="1"
              class="flex-1 bg-transparent text-base text-text-primary placeholder:text-text-tertiary/40 resize-none py-3 px-1 outline-none max-h-40 min-h-[44px] font-medium leading-relaxed"
              @keydown="handleKeydown" />
            <button @click="handleSubmit" :disabled="!canSubmit"
              class="h-10 w-10 shrink-0 flex items-center justify-center rounded-full transition-all duration-500 mb-1"
              :class="canSubmit
                ? 'bg-accent text-white shadow-xl scale-105 hover:bg-accent-hover'
                : 'bg-white/5 text-text-tertiary'">
              <Sparkles class="h-4 w-4" />
            </button>
          </div>

          <!-- Streaming State -->
          <div v-else-if="committeeStore.isStreaming"
            class="flex items-center justify-between gap-3 px-4 py-3 text-sm text-text-secondary">
            <div class="flex items-center gap-3">
              <Loader2 class="h-4 w-4 animate-spin text-accent" />
              <span
                class="font-black uppercase tracking-widest text-xs">{{ phaseNames[committeeStore.currentPhase] }}中...</span>
              <span
                class="text-[10px] font-mono text-text-tertiary">{{ committeeStore.phaseProgress.current }}/{{ committeeStore.phaseProgress.total }}</span>
            </div>
            <button @click="committeeStore.stop()"
              class="h-9 px-4 flex items-center gap-2 rounded-full bg-red-500/10 border border-red-500/20 text-xs font-black uppercase tracking-widest text-red-400 hover:bg-red-500/20 transition-all">
              <Square class="h-3 w-3" fill="currentColor" />
              停止
            </button>
          </div>

          <!-- Done State -->
          <div v-else class="flex items-center justify-between gap-3 px-4 py-2">
            <div
              class="flex items-center gap-2 text-xs font-bold text-text-secondary uppercase tracking-tight">
              <CheckCircle v-if="committeeStore.isCompleted" class="h-4 w-4 text-green-500" />
              <Square v-else class="h-4 w-4 text-amber-400" fill="currentColor" />
              {{ committeeStore.isCompleted ? '锦囊团运行完成' : '本轮已停止' }}
            </div>
            <div class="flex items-center gap-2">
              <button @click="endSession"
                class="px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest text-text-tertiary hover:bg-white/5 transition-all">
                结束
              </button>
              <button @click="startNew"
                class="px-5 py-2 rounded-xl bg-accent text-white text-xs font-black uppercase tracking-widest shadow-lg shadow-accent/20 hover:scale-105 active:scale-95 transition-all">
                新问题
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <IOSModelSheet :open="showCommitteeModelSheet" mode="committee"
      @close="showCommitteeModelSheet = false" />
  </div>
</template>

<style scoped>
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

.no-scrollbar::-webkit-scrollbar {
  display: none;
}
</style>
