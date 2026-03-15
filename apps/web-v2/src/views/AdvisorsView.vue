<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { CheckCircle, ChevronRight, Cpu, Loader2, MessageSquare, Sparkles, Square, Users } from 'lucide-vue-next'
import CommitteeDebateCard from '@/components/advisors/CommitteeDebateCard.vue'
import CommitteeModelPoolPicker from '@/components/advisors/CommitteeModelPoolPicker.vue'
import CommitteePhaseSection from '@/components/advisors/CommitteePhaseSection.vue'
import CommitteeSummaryCard from '@/components/advisors/CommitteeSummaryCard.vue'
import CommitteeSynthesisCard from '@/components/advisors/CommitteeSynthesisCard.vue'
import { COMMITTEE_MODE_OPTIONS, buildRoleModelAssignments, type CommitteeMode, type CommitteePhase } from '@/features/committee'
import { getModelColor, useAppStore } from '@/stores/app'
import { useCommitteeStore } from '@/stores/committee'
import { CATEGORY_META, getAvatarUrl, getStanceLabels, usePersonaStore, type PersonaCategory } from '@/stores/persona'

const appStore = useAppStore()
const committeeStore = useCommitteeStore()
const personaStore = usePersonaStore()

const inputText = ref('')
const showAssignments = ref(false)
const setupStage = ref<'landing' | 'configure'>('landing')
const resultInspector = ref<'mode' | 'roles' | 'models'>('mode')

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
  })
  resultInspector.value = 'mode'
}

function startNew() {
  inputText.value = ''
  committeeStore.clearSession()
  setupStage.value = 'configure'
}

function endSession() {
  inputText.value = ''
  committeeStore.clearSession()
  setupStage.value = 'landing'
  resultInspector.value = 'mode'
}

function handleKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault()
    handleSubmit()
  }
}

function scrollToSection(section: 'mode' | 'roles' | 'models') {
  const targetMap: Record<typeof section, string> = {
    mode: 'committee-mode-section',
    roles: 'committee-roles-section',
    models: 'committee-models-section',
  }
  const target = document.getElementById(targetMap[section])
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function openSetup(section: 'mode' | 'roles' | 'models' = 'mode') {
  setupStage.value = 'configure'
  await nextTick()
  scrollToSection(section)
}

function toggleInspector(section: 'mode' | 'roles' | 'models') {
  resultInspector.value = resultInspector.value === section ? 'mode' : section
}

onMounted(() => {
  if (!personaStore.activePersonaIds.length) {
    personaStore.activatePreset('all')
  }
  appStore.ensureCommitteeSelection()
})

onBeforeRouteLeave(() => {
  if (committeeStore.isStreaming) {
    committeeStore.stop()
  }
  inputText.value = ''
  committeeStore.clearSession()
  setupStage.value = 'landing'
  resultInspector.value = 'mode'
})
</script>

<template>
  <div class="flex h-full flex-col bg-surface-0">
    <div class="flex-1 overflow-y-auto">
      <div
        v-if="!committeeStore.isActive && !committeeStore.isStreaming && setupStage === 'landing'"
        class="flex h-full items-center justify-center px-4 py-8 md:px-6"
      >
        <section class="w-full max-w-5xl rounded-[2rem] border border-border-default bg-surface-1 px-6 py-8 shadow-sm md:px-8 md:py-10">
          <div class="mx-auto max-w-3xl text-center">
              <div class="inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-accent">
              AI 锦囊团
              </div>
            <h1 class="mt-5 text-3xl font-semibold leading-tight text-text-primary md:text-[2.6rem]">
              先定这轮怎么开会，
              <br>
              再让 12 个角色上桌。
            </h1>
            <p class="mx-auto mt-4 max-w-2xl text-sm leading-7 text-text-secondary md:text-base">
              锦囊团不是连续聊天，也不是会话历史。它更像一次临时组局：
              先定模式、挑角色、绑模型，再开一轮会，结论看完就散场。
            </p>
          </div>

          <div class="mx-auto mt-8 grid max-w-4xl gap-4 md:grid-cols-3">
            <button
              class="rounded-[1.5rem] border border-border-default bg-surface-2/70 p-5 text-left transition-colors hover:border-border-subtle hover:bg-surface-1"
              @click="openSetup('mode')"
            >
              <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-text-tertiary">Step 1</div>
              <div class="mt-2 text-lg font-semibold text-text-primary">先定模式</div>
              <p class="mt-2 text-xs leading-6 text-text-secondary">广播、辩论、收敛，先决定这轮是扫一遍，还是正面交锋，还是直接收束。</p>
              <div class="mt-4 inline-flex items-center gap-1 text-xs font-medium text-accent">
                去选模式
                <ChevronRight class="h-3.5 w-3.5" />
              </div>
            </button>

            <button
              class="rounded-[1.5rem] border border-border-default bg-surface-2/70 p-5 text-left transition-colors hover:border-border-subtle hover:bg-surface-1"
              @click="openSetup('roles')"
            >
              <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-text-tertiary">Step 2</div>
              <div class="mt-2 text-lg font-semibold text-text-primary">再挑角色</div>
              <p class="mt-2 text-xs leading-6 text-text-secondary">不是默认全塞给用户。你可以整组激活，也可以只拉几类站位明确的人上桌。</p>
              <div class="mt-4 inline-flex items-center gap-1 text-xs font-medium text-accent">
                去选角色
                <ChevronRight class="h-3.5 w-3.5" />
              </div>
            </button>

            <button
              class="rounded-[1.5rem] border border-border-default bg-surface-2/70 p-5 text-left transition-colors hover:border-border-subtle hover:bg-surface-1"
              @click="openSetup('models')"
            >
              <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-text-tertiary">Step 3</div>
              <div class="mt-2 text-lg font-semibold text-text-primary">最后绑模型</div>
              <p class="mt-2 text-xs leading-6 text-text-secondary">锦囊团单独维护一套模型池，不直接复用 chat 的运行态，但可以一键导入当前聊天已选模型。</p>
              <div class="mt-4 inline-flex items-center gap-1 text-xs font-medium text-accent">
                去绑模型
                <ChevronRight class="h-3.5 w-3.5" />
              </div>
            </button>
          </div>

          <div class="mx-auto mt-8 flex max-w-3xl flex-wrap items-center justify-center gap-2 text-xs text-text-tertiary">
            <button
              class="rounded-full bg-surface-2 px-3 py-1.5 transition-colors hover:bg-surface-3"
              @click="openSetup('mode')"
            >
              {{ currentModeOption?.name || '收敛模式' }}
            </button>
            <button
              class="rounded-full bg-surface-2 px-3 py-1.5 transition-colors hover:bg-surface-3"
              @click="openSetup('roles')"
            >
              {{ personaStore.activePersonaIds.length }} 个角色已预激活
            </button>
            <button
              class="rounded-full bg-surface-2 px-3 py-1.5 transition-colors hover:bg-surface-3"
              @click="openSetup('models')"
            >
              {{ appStore.committeeSelectedModels.length }} 个模型池
            </button>
          </div>

          <div class="mt-8 flex justify-center">
            <button
              class="inline-flex items-center gap-2 rounded-[1.2rem] bg-accent px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
              @click="openSetup('mode')"
            >
              开始组局
              <ChevronRight class="h-4 w-4" />
            </button>
          </div>
        </section>
      </div>

      <div v-else-if="!committeeStore.isActive && !committeeStore.isStreaming" class="mx-auto max-w-5xl px-4 py-6 md:px-6 md:py-8">
        <section class="overflow-hidden rounded-[1.75rem] border border-border-default bg-surface-1 shadow-sm">
          <div class="grid gap-6 px-6 py-6 lg:grid-cols-[1.08fr_0.92fr] md:px-8">
            <div>
              <div class="mb-4 inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-accent">
                AI 锦囊团
              </div>
              <h1 class="max-w-3xl text-3xl font-semibold leading-tight text-text-primary md:text-[2.2rem]">
                先把这轮会议配好，
                <br>
                再让角色正式上桌。
              </h1>
              <p class="mt-4 max-w-2xl text-sm leading-7 text-text-secondary md:text-base">
                这一页只做一次性锦囊团，不做会话历史。你可以把它理解成临时战情会：
                模式决定怎么开，角色决定谁发言，模型池决定谁来扮演这些人。
              </p>

              <div id="committee-mode-section" class="mt-6 grid gap-3 sm:grid-cols-3">
                <button
                  v-for="mode in COMMITTEE_MODE_OPTIONS"
                  :key="mode.id"
                  @click="currentMode = mode.id"
                  class="rounded-[1.4rem] border px-4 py-4 text-left transition-all duration-200"
                  :class="currentMode === mode.id
                    ? 'border-accent/35 bg-accent/10 shadow-sm'
                    : 'border-border-default bg-surface-1 hover:border-accent/20 hover:bg-surface-2/70 hover:shadow-sm'"
                >
                  <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-accent">{{ mode.tagline }}</div>
                  <div class="mt-2 text-lg font-semibold text-text-primary">{{ mode.name }}</div>
                  <p class="mt-2 text-xs leading-6 text-text-secondary">{{ mode.description }}</p>
                </button>
              </div>
            </div>

            <div id="committee-models-section">
              <CommitteeModelPoolPicker />
            </div>
          </div>
        </section>

        <section id="committee-roles-section" class="mt-6 rounded-[2rem] border border-border-default bg-surface-1/95 p-5 shadow-sm md:p-6">
          <div class="flex flex-col gap-4">
            <div>
              <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-text-tertiary">Persona Matrix</div>
              <h2 class="mt-2 text-2xl font-semibold text-text-primary">12 个预设角色，按角度互相掐架</h2>
              <p class="mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
                普通用户不需要先学什么立场轴，直接勾角色就行。你真正要验证的是：
                同一件事，换一群不同站位的人来看，会不会得出明显不同的判断。
              </p>
            </div>
            <div class="flex flex-wrap gap-2 md:justify-end">
              <button
                @click="showAssignments = !showAssignments"
                class="whitespace-nowrap rounded-full border border-border-default bg-surface-1 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-subtle hover:text-text-primary"
              >
                {{ showAssignments ? '隐藏分配' : '查看分配' }}
              </button>
              <button
                @click="selectAllRoles"
                class="whitespace-nowrap rounded-full border border-border-default px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-subtle hover:text-text-primary"
              >
                全选 12 角
              </button>
              <button
                @click="clearRoles"
                class="whitespace-nowrap rounded-full border border-border-default px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-subtle hover:text-text-primary"
              >
                清空
              </button>
            </div>
          </div>

          <div class="mt-6 grid gap-4 xl:grid-cols-2">
            <div
              v-for="group in roleGroups"
              :key="group.category"
              class="rounded-[1.6rem] border bg-surface-1 p-4 shadow-sm"
              :class="isCategoryActive(group.category)
                ? [group.borderClass, group.softClass]
                : 'border-border-default'"
            >
              <div class="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div
                    class="text-[11px] font-semibold uppercase tracking-[0.22em]"
                    :class="isCategoryActive(group.category) ? group.textClass : 'text-text-tertiary'"
                  >
                    {{ group.tag }}
                  </div>
                  <div class="mt-1 text-lg font-semibold text-text-primary">{{ group.label }}</div>
                  <div class="mt-1 text-xs text-text-secondary">{{ group.desc }}</div>
                </div>
                <button
                  @click="toggleCategory(group.category)"
                  class="rounded-full border bg-surface-1 px-3 py-1.5 text-[11px] font-medium transition-colors hover:bg-surface-2"
                  :class="isCategoryActive(group.category)
                    ? [group.borderClass, group.textClass]
                    : 'border-border-default text-text-secondary'"
                >
                  {{ isCategoryFullySelected(group.category) ? '取消整组' : '整组激活' }}
                </button>
              </div>

              <div class="grid gap-3 md:grid-cols-2">
                <button
                  v-for="role in group.roles"
                  :key="role.id"
                  @click="toggleRole(role.id)"
                  class="flex h-full flex-col overflow-hidden rounded-[1.4rem] border border-border-default bg-surface-1 p-3 text-left transition-all duration-200"
                  :class="isRoleActive(role.id)
                    ? [group.borderClass, 'shadow-md']
                    : 'opacity-60 hover:bg-surface-2 hover:opacity-100'"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div class="flex min-w-0 items-center gap-3">
                      <img
                        :src="getAvatarUrl(role, 34)"
                        :alt="role.name"
                        class="h-8.5 w-8.5 rounded-full bg-surface-3 shrink-0"
                        :class="isRoleActive(role.id) ? '' : 'grayscale'"
                      />
                      <div class="min-w-0">
                        <div class="truncate text-sm font-semibold text-text-primary">{{ role.name }}</div>
                      </div>
                    </div>
                    <div
                      class="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold leading-none"
                      :class="isRoleActive(role.id)
                        ? group.badgeClass
                        : 'bg-surface-3 text-text-tertiary'"
                    >
                      {{ isRoleActive(role.id) ? '已激活' : '待命中' }}
                    </div>
                  </div>

                  <div class="mt-1.5 text-xs leading-5 text-text-tertiary">
                    {{ role.title }}
                  </div>

                  <div class="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                    <span
                      class="rounded-full px-2 py-0.5"
                      :class="isRoleActive(role.id) ? 'bg-sky-500/10 text-sky-400' : 'bg-surface-3 text-text-tertiary'"
                    >
                      {{ getStanceLabels(role.stance).cognition }}
                    </span>
                    <span
                      class="rounded-full px-2 py-0.5"
                      :class="isRoleActive(role.id) ? 'bg-amber-500/10 text-amber-400' : 'bg-surface-3 text-text-tertiary'"
                    >
                      {{ getStanceLabels(role.stance).horizon }}
                    </span>
                    <span
                      class="rounded-full px-2 py-0.5"
                      :class="isRoleActive(role.id) ? 'bg-emerald-500/10 text-emerald-400' : 'bg-surface-3 text-text-tertiary'"
                    >
                      {{ getStanceLabels(role.stance).interest }}
                    </span>
                  </div>

                  <p
                    class="mt-3 text-xs leading-5 text-text-secondary"
                    :class="showAssignments ? 'min-h-[64px]' : ''"
                  >
                    {{ role.coreBelief }}
                  </p>

                  <p class="mt-2 text-[11px] leading-5 text-text-tertiary">
                    不可妥协：{{ role.nonNegotiable }}
                  </p>

                  <div
                    v-if="showAssignments"
                    class="mt-3 rounded-xl border border-border-default bg-surface-2/70 px-3 py-2.5"
                  >
                    <template v-if="assignmentMap[role.id]">
                      <div class="flex items-center justify-between gap-2">
                        <span class="text-[11px] font-medium text-accent">当前模型</span>
                        <span class="truncate text-[11px] font-semibold text-text-primary">
                          {{ getModelName(assignmentMap[role.id].modelId) }}
                        </span>
                      </div>
                      <div class="mt-2 flex flex-wrap gap-1.5">
                        <span
                          v-for="reason in assignmentMap[role.id].reasons.slice(0, 2)"
                          :key="reason"
                          class="rounded-full border border-border-subtle bg-surface-1 px-2 py-0.5 text-[10px] text-text-tertiary"
                        >
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
            <div class="z-10 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-surface-1 shadow-sm border border-border-default">
              <MessageSquare class="h-4 w-4 text-accent" />
            </div>
            <div class="flex-1 rounded-[1.5rem] border border-border-default bg-surface-1 px-4 py-4 shadow-sm">
              <div class="flex flex-wrap items-center gap-2">
                <button
                  class="rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] transition-colors"
                  :class="resultInspector === 'mode' ? 'bg-accent text-white' : 'bg-surface-2 text-text-tertiary hover:bg-surface-3'"
                  @click="toggleInspector('mode')"
                >
                  {{ startedModeOption?.name }}
                </button>
                <button
                  class="rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors"
                  :class="resultInspector === 'roles' ? 'bg-accent text-white' : 'bg-surface-2 text-text-tertiary hover:bg-surface-3'"
                  @click="toggleInspector('roles')"
                >
                  {{ committeeStore.activeRoleCount }} 个角色
                </button>
                <button
                  class="rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors"
                  :class="resultInspector === 'models' ? 'bg-accent text-white' : 'bg-surface-2 text-text-tertiary hover:bg-surface-3'"
                  @click="toggleInspector('models')"
                >
                  {{ appStore.committeeSelectedModels.length }} 个模型池
                </button>
              </div>
              <p class="mt-3 text-base font-medium leading-7 text-text-primary">{{ committeeStore.prompt }}</p>

              <div class="mt-4 rounded-[1.2rem] border border-border-subtle bg-surface-2/70 px-4 py-3">
                <template v-if="resultInspector === 'mode'">
                  <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-text-tertiary">当前模式</div>
                  <div class="mt-2 text-sm font-semibold text-text-primary">{{ startedModeOption?.name }}</div>
                  <p class="mt-2 text-xs leading-6 text-text-secondary">{{ inspectorModeText }}</p>
                </template>

                <template v-else-if="resultInspector === 'roles'">
                  <div class="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-text-tertiary">
                    <Users class="h-3.5 w-3.5" />
                    当前角色
                  </div>
                  <div class="mt-3 flex flex-wrap gap-2">
                    <span
                      v-for="role in activeRoles"
                      :key="role.id"
                      class="rounded-full border border-border-subtle bg-surface-1 px-3 py-1 text-xs text-text-secondary"
                    >
                      {{ role.name }}
                    </span>
                  </div>
                </template>

                <template v-else>
                  <div class="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-text-tertiary">
                    <Cpu class="h-3.5 w-3.5" />
                    本次模型池
                  </div>
                  <div class="mt-3 flex flex-wrap gap-2">
                    <span
                      v-for="model in appStore.committeeSelectedModels"
                      :key="model.id"
                      class="rounded-full border px-3 py-1 text-xs"
                      :style="getModelChipStyle(model.id)"
                    >
                      {{ model.name }}
                    </span>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <CommitteePhaseSection
            :phase="1"
            title="角色独立发言"
            :subtitle="`${committeeStore.activeRoleCount} 个高参并行发言`"
            :status="phase1Status"
            color-class="bg-accent"
          >
            <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <CommitteeSummaryCard
                v-for="summary in committeeStore.phase1Summaries"
                :key="summary.roleId"
                :summary="summary"
                :role="roleMap[summary.roleId]"
                :model-name="getModelName(summary.modelId)"
              />
            </div>
          </CommitteePhaseSection>

          <CommitteePhaseSection
            v-if="committeeStore.hasDebatePhase"
            :phase="2"
            title="第二轮正面回应"
            subtitle="立场不改，但要正面接招"
            :status="phase2Status"
            color-class="bg-rose-500"
          >
            <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <CommitteeDebateCard
                v-for="review in committeeStore.phase2Reviews"
                :key="`${review.roleId}-${review.targetRoleId}`"
                :review="review"
                :role-name="roleMap[review.roleId]?.name || review.roleId"
                :target-name="roleMap[review.targetRoleId]?.name || review.targetRoleId"
              />
            </div>
          </CommitteePhaseSection>

          <CommitteePhaseSection
            v-if="committeeStore.hasCommitteePhase"
            :phase="3"
            title="系统主持人总结"
            :subtitle="committeeStore.synthesizer || ''"
            :status="phase3Status"
            color-class="bg-amber-500"
          >
            <CommitteeSynthesisCard
              :synthesis="committeeStore.committeeSynthesis"
              :content="committeeStore.phase3Content"
              :streaming="committeeStore.isStreaming && committeeStore.currentPhase === 3"
            />
          </CommitteePhaseSection>
        </div>

        <div class="h-10" />
      </div>
    </div>

    <div class="border-t border-border-subtle bg-surface-1/95 backdrop-blur-sm">
      <div v-if="!committeeStore.isActive && !committeeStore.isStreaming" class="px-4 py-3">
        <div class="mx-auto max-w-5xl">
          <div class="mb-2 flex flex-wrap items-center gap-2 text-xs text-text-tertiary">
            <span class="rounded-full bg-surface-2 px-2.5 py-1">{{ currentModeOption?.name }}</span>
            <span class="rounded-full bg-surface-2 px-2.5 py-1">{{ personaStore.activePersonaIds.length }} 个角色已激活</span>
            <span class="rounded-full bg-surface-2 px-2.5 py-1">{{ appStore.committeeSelectedModels.length }} 个模型池</span>
          </div>
          <div class="flex items-end gap-2">
            <div class="flex-1 rounded-[1.3rem] border border-border-default bg-surface-2 transition-all focus-within:border-accent/40 focus-within:bg-surface-1">
              <textarea
                v-model="inputText"
                rows="2"
                placeholder="输入要交给这群高参的问题，比如：这个产品到底该先做预设角色，还是先做角色自定义？"
                class="max-h-[120px] w-full resize-none bg-transparent px-4 py-3 text-sm leading-7 text-text-primary focus:outline-none"
                @keydown="handleKeydown"
              />
            </div>
            <button
              @click="handleSubmit"
              :disabled="!canSubmit"
              class="inline-flex items-center gap-2 rounded-[1.2rem] bg-accent px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Sparkles class="h-4 w-4" />
              启动锦囊团
            </button>
          </div>
        </div>
      </div>

      <div v-else-if="committeeStore.isStreaming" class="px-4 py-3">
        <div class="mx-auto flex max-w-5xl items-center justify-between gap-3 text-sm text-text-secondary">
          <div class="flex items-center gap-3">
            <Loader2 class="h-4 w-4 animate-spin text-accent" />
            <span>{{ phaseNames[committeeStore.currentPhase] }}中...</span>
            <span class="text-xs text-text-tertiary">{{ committeeStore.phaseProgress.current }}/{{ committeeStore.phaseProgress.total }}</span>
          </div>
          <button
            @click="committeeStore.stop()"
            class="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium text-red-300 transition-colors hover:bg-red-500/10"
          >
            <Square class="h-3.5 w-3.5" fill="currentColor" />
            停止
          </button>
        </div>
      </div>

      <div v-else class="px-4 py-3">
        <div class="mx-auto flex max-w-5xl items-center justify-between gap-3">
          <div class="flex items-center gap-2 text-sm text-text-secondary">
            <CheckCircle v-if="committeeStore.isCompleted" class="h-4 w-4 text-green-500" />
            <Square v-else class="h-4 w-4 text-amber-400" fill="currentColor" />
            {{ committeeStore.isCompleted ? '锦囊团运行完成' : '本轮已停止，保留当前结果' }}
          </div>
          <div class="flex items-center gap-2">
            <button
              @click="endSession"
              class="rounded-full px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-surface-2"
            >
              结束
            </button>
            <button
              @click="startNew"
              class="rounded-full bg-accent px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
            >
              新问题
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
