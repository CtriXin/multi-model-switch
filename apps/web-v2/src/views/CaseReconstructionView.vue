<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  ClipboardCheck,
  FileSearch,
  Flag,
  FlaskConical,
  LayoutList,
  RotateCcw,
  Search,
  ShieldCheck,
  Users,
} from 'lucide-vue-next'
import { useCaseReconstructionStore } from '@/stores/caseReconstruction'

const store = useCaseReconstructionStore()

const workspaceTab = ref<'clues' | 'people'>('clues')
const culpritId = ref<string | null>(null)
const motiveId = ref<string | null>(null)
const explanation = ref('')
const timelineFactIds = ref<string[]>([])
const selectedEvidenceId = ref('')
const selectedFactId = ref('')
const evidencePairs = ref<Array<{ evidenceId: string; factId: string }>>([])

onMounted(() => {
  store.init()
  if (store.phase === 'scene_zero') return
  workspaceTab.value = 'clues'
})

const factLabelMap = computed(() =>
  new Map(store.packet.facts.map((fact) => [fact.id, fact.label])),
)

const evidenceLabelMap = computed(() =>
  new Map(store.packet.evidence.map((evidence) => [evidence.id, evidence.label])),
)

const objectiveLabelMap: Record<string, string> = {
  timeline: '时间线',
  motive: '动机',
  evidence: '关键证据',
}

const evidencePool = computed(() =>
  store.packet.evidence.map((evidence) => ({
    ...evidence,
    discovered: store.discoveredEvidenceIds.includes(evidence.id),
    highlighted: store.packet.sceneZero.startingLeads.some(
      (lead) => lead.type === 'evidence' && lead.id === evidence.id,
    ),
  })),
)

const pendingEvidence = computed(() =>
  evidencePool.value.filter((item) => !item.discovered),
)

const featuredEvidence = computed(() => pendingEvidence.value[0] ?? null)

const queuedEvidence = computed(() =>
  pendingEvidence.value.slice(1, 4),
)

const archivedEvidence = computed(() =>
  evidencePool.value
    .filter((item) => item.discovered)
    .slice(-4)
    .reverse(),
)

const witnessPool = computed(() =>
  store.unlockedWitnesses.map((witness) => ({
    ...witness,
    highlighted: store.packet.sceneZero.startingLeads.some(
      (lead) => lead.type === 'witness' && lead.id === witness.id,
    ),
  })),
)

const timelinePool = computed(() =>
  store.timelineFacts.filter((fact) => !timelineFactIds.value.includes(fact.id)),
)

const evidencePairFactPool = computed(() =>
  store.unlockedFacts.filter((fact) => fact.category !== 'context'),
)

const selectedTimelineFacts = computed(() =>
  timelineFactIds.value
    .map((factId) => store.factMap.get(factId))
    .filter((f): f is NonNullable<typeof f> => Boolean(f)),
)

const compactNotes = computed(() =>
  [...store.unlockedFacts]
    .filter((fact) => fact.category !== 'context')
    .slice(-6)
    .reverse(),
)

const recentLog = computed(() => store.investigationLog.slice(0, 5))

const currentObjective = computed(() => {
  if (store.readyForReconstruction) {
    return '证据链已经足够，可以开始交卷。'
  }

  const labels = store.checkpointHint.missingDimensions.map((item) => objectiveLabelMap[item] ?? item)
  if (!labels.length) {
    return '继续补齐更多事实，系统会自动判断何时适合交卷。'
  }

  return `当前先补强：${labels.join('、')}`
})

const canSubmit = computed(() =>
  Boolean(culpritId.value) &&
  Boolean(motiveId.value) &&
  evidencePairs.value.length >= store.packet.validation.minimumEvidencePairs &&
  timelineFactIds.value.length >= store.packet.validation.minimumTimelineFacts,
)

const gradeLabel = computed(() => {
  const grade = store.latestVerdict?.grade
  if (grade === 'optimal') return 'Optimal'
  if (grade === 'hidden') return 'Hidden'
  if (grade === 'normal') return 'Cleared'
  return 'Failed'
})

const gradeClass = computed(() => {
  const grade = store.latestVerdict?.grade
  if (grade === 'optimal') return 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'
  if (grade === 'hidden') return 'bg-cyan-500/15 text-cyan-300 ring-cyan-500/30'
  if (grade === 'normal') return 'bg-amber-500/15 text-amber-300 ring-amber-500/30'
  return 'bg-red-500/15 text-red-300 ring-red-500/30'
})

watch(
  () => store.phase,
  (phase) => {
    if (phase !== 'final_reconstruction') return
    if (timelineFactIds.value.length) return

    timelineFactIds.value = store.timelineFacts
      .filter((fact) => fact.category === 'timeline' || fact.category === 'means')
      .slice(0, store.packet.validation.minimumTimelineFacts)
      .map((fact) => fact.id)
  },
  { immediate: true },
)

function resetForm() {
  culpritId.value = null
  motiveId.value = null
  explanation.value = ''
  timelineFactIds.value = []
  selectedEvidenceId.value = ''
  selectedFactId.value = ''
  evidencePairs.value = []
}

function restartCase() {
  store.resetCase()
  resetForm()
  workspaceTab.value = 'clues'
}

function beginOrResume() {
  if (store.phase === 'scene_zero') {
    store.beginInvestigation()
    return
  }
  store.resumeInvestigation()
}

function openVerdictForm() {
  if (!store.readyForReconstruction) {
    store.requestCheckpoint()
    return
  }
  store.openFinalReconstruction()
}

function addTimelineFact(factId: string) {
  if (!factId || timelineFactIds.value.includes(factId)) return
  timelineFactIds.value = [...timelineFactIds.value, factId]
}

function removeTimelineFact(factId: string) {
  timelineFactIds.value = timelineFactIds.value.filter((item) => item !== factId)
}

function moveTimelineFact(index: number, offset: number) {
  const nextIndex = index + offset
  if (nextIndex < 0 || nextIndex >= timelineFactIds.value.length) return
  const next = [...timelineFactIds.value]
  const [item] = next.splice(index, 1)
  next.splice(nextIndex, 0, item)
  timelineFactIds.value = next
}

function addEvidencePair() {
  if (!selectedEvidenceId.value || !selectedFactId.value) return

  const nextKey = `${selectedEvidenceId.value}::${selectedFactId.value}`
  const exists = evidencePairs.value.some((pair) => `${pair.evidenceId}::${pair.factId}` === nextKey)
  if (exists) return

  evidencePairs.value = [
    ...evidencePairs.value,
    { evidenceId: selectedEvidenceId.value, factId: selectedFactId.value },
  ]
  selectedEvidenceId.value = ''
  selectedFactId.value = ''
}

function removeEvidencePair(index: number) {
  evidencePairs.value = evidencePairs.value.filter((_, pairIndex) => pairIndex !== index)
}

function submitVerdict() {
  if (!canSubmit.value) return

  store.submitReconstruction({
    culpritId: culpritId.value,
    motiveId: motiveId.value,
    explanation: explanation.value.trim(),
    timelineFactIds: [...timelineFactIds.value],
    evidencePairs: [...evidencePairs.value],
  })
}

function categoryTone(category: string) {
  if (category === 'timeline') return 'border-cyan-400/20 bg-cyan-500/[0.08] text-cyan-700 dark:text-cyan-200'
  if (category === 'motive') return 'border-rose-400/20 bg-rose-500/[0.08] text-rose-700 dark:text-rose-200'
  if (category === 'means') return 'border-amber-400/20 bg-amber-500/[0.08] text-amber-700 dark:text-amber-200'
  return 'border-white/10 bg-white/[0.04] text-text-secondary'
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-[#f4f1ec] dark:bg-[#090c14]">
    <header
      class="mx-auto mt-3 flex w-full max-w-6xl shrink-0 items-center justify-between gap-4 rounded-full border border-white/10 bg-white/75 px-4 py-2.5 shadow-2xl dark:bg-white/[0.04] sm:px-6"
    >
      <div class="min-w-0 flex items-center gap-3">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#132136] shadow-2xl shadow-[#132136]/20">
          <Search :size="16" :stroke-width="3.5" class="text-[#f7d27a]" />
        </div>
        <div class="min-w-0">
          <div class="text-[9px] font-black uppercase tracking-[0.32em] text-text-tertiary">Case Reconstruction</div>
          <div class="truncate text-sm font-black tracking-tight text-text-primary sm:text-base">
            {{ store.packet.title }}
          </div>
        </div>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <div class="hidden sm:flex flex-col items-end mr-2">
          <div class="text-[9px] font-black uppercase tracking-[0.24em] text-text-tertiary">Fictional Demo Case</div>
          <div class="text-[10px] font-black uppercase tracking-[0.18em] text-[#132136] dark:text-[#f7d27a]">
            {{ store.packet.estimatedMinutes }} min loop
          </div>
        </div>
        <button
          class="h-9 w-9 rounded-full border border-white/10 bg-white/60 text-text-secondary transition-all active:scale-90 dark:bg-white/[0.04]"
          @click="restartCase"
        >
          <RotateCcw class="mx-auto" :size="16" :stroke-width="3.5" />
        </button>
      </div>
    </header>

    <main class="mx-auto flex w-full max-w-6xl flex-1 overflow-y-auto px-3 py-3 sm:px-4 lg:px-6">
      <div class="flex w-full flex-col gap-3">
        <section class="rounded-[32px] border border-white/10 bg-[#132136] px-5 py-5 text-white shadow-2xl sm:px-6">
          <div class="flex flex-wrap items-center gap-2">
            <span class="inline-flex items-center rounded-full bg-white/10 px-3 py-1 text-[9px] font-black uppercase tracking-[0.24em] text-[#f7d27a]">
              Scene Zero
            </span>
            <span class="inline-flex items-center rounded-full bg-white/10 px-3 py-1 text-[9px] font-black uppercase tracking-[0.22em] text-white/70">
              {{ store.packet.playerRole }}
            </span>
          </div>

          <h1 class="mt-4 text-2xl font-black tracking-tight sm:text-3xl">
            {{ store.packet.sceneZero.openingMoment }}
          </h1>
          <p class="mt-3 max-w-3xl text-sm leading-relaxed text-white/75">
            这版先把流程收成单主线体验。你只需要做两件事：先在“线索 / 人物”里补齐证据链，再在最后交一份结构化 reconstruction。
          </p>

          <div class="mt-5 flex flex-wrap gap-3">
            <button
              class="rounded-full bg-[#f7d27a] px-5 py-3 text-[10px] font-black uppercase tracking-[0.22em] text-[#132136] transition-transform active:scale-[0.98]"
              @click="beginOrResume"
            >
              {{ store.phase === 'scene_zero' ? '进入调查' : '继续调查' }}
            </button>
            <button
              class="rounded-full border border-white/15 px-5 py-3 text-[10px] font-black uppercase tracking-[0.22em] text-white/75 transition-colors hover:text-white"
              :class="store.readyForReconstruction ? 'bg-white/10 text-white' : ''"
              @click="openVerdictForm"
            >
              {{ store.readyForReconstruction ? '开始交卷' : '系统自动判断交卷时机' }}
            </button>
          </div>
        </section>

        <section class="rounded-[28px] border border-white/10 bg-white/70 p-5 shadow-xl dark:bg-white/[0.04]">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div class="flex items-center gap-2">
                <ShieldCheck :size="14" :stroke-width="3.5" class="text-[#132136] dark:text-[#f7d27a]" />
                <div class="text-[10px] font-black uppercase tracking-[0.28em] text-text-tertiary">Current Objective</div>
              </div>
              <div class="mt-3 text-lg font-black tracking-tight text-text-primary">
                {{ store.readyForReconstruction ? '证据链已够，准备交卷' : currentObjective }}
              </div>
              <p class="mt-2 text-sm leading-relaxed text-text-secondary">
                {{ store.checkpointHint.message }}
              </p>
            </div>

            <div class="flex flex-wrap gap-2">
              <span class="rounded-full bg-black/5 px-3 py-1 text-[8px] font-black uppercase tracking-[0.18em] text-text-tertiary dark:bg-white/10">
                facts {{ store.unlockedFacts.length }}/{{ store.packet.facts.length }}
              </span>
              <span class="rounded-full bg-black/5 px-3 py-1 text-[8px] font-black uppercase tracking-[0.18em] text-text-tertiary dark:bg-white/10">
                evidence {{ store.discoveredEvidence.length }}/{{ store.packet.evidence.length }}
              </span>
              <span class="rounded-full bg-black/5 px-3 py-1 text-[8px] font-black uppercase tracking-[0.18em] text-text-tertiary dark:bg-white/10">
                witness {{ store.unlockedWitnesses.length }}/{{ store.packet.witnesses.length }}
              </span>
            </div>
          </div>
        </section>

        <section class="rounded-[28px] border border-white/10 bg-white/70 p-5 shadow-xl dark:bg-white/[0.04]">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-2">
              <ClipboardCheck :size="14" :stroke-width="3.5" class="text-[#132136] dark:text-[#f7d27a]" />
              <div class="text-[10px] font-black uppercase tracking-[0.28em] text-text-tertiary">Main Workspace</div>
            </div>

            <div class="inline-flex rounded-full bg-black/[0.04] p-1 dark:bg-white/[0.06]">
              <button
                class="rounded-full px-4 py-2 text-[10px] font-black uppercase tracking-[0.18em] transition-all"
                :class="workspaceTab === 'clues' ? 'bg-[#132136] text-[#f7d27a]' : 'text-text-tertiary'"
                @click="workspaceTab = 'clues'"
              >
                线索
              </button>
              <button
                class="rounded-full px-4 py-2 text-[10px] font-black uppercase tracking-[0.18em] transition-all"
                :class="workspaceTab === 'people' ? 'bg-[#132136] text-[#f7d27a]' : 'text-text-tertiary'"
                @click="workspaceTab = 'people'"
              >
                人物
              </button>
            </div>
          </div>

          <div v-if="workspaceTab === 'clues'" class="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.05fr)_320px]">
            <article class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
              <div class="flex items-center gap-2">
                <FlaskConical :size="14" :stroke-width="3.5" class="text-[#132136] dark:text-[#f7d27a]" />
                <div class="text-[9px] font-black uppercase tracking-[0.24em] text-text-tertiary">Lead Queue</div>
              </div>
              <p class="mt-2 text-xs leading-relaxed text-text-secondary">
                不再把所有线索平铺成目录。这里默认给你“下一条待排查”，让调查像推进任务，而不是扫列表。
              </p>

              <div v-if="featuredEvidence" class="mt-4 rounded-[28px] border border-[#132136]/10 bg-[#132136] p-5 text-white">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="rounded-full bg-white/10 px-3 py-1 text-[8px] font-black uppercase tracking-[0.18em] text-[#f7d27a]">
                    下一条待排查
                  </span>
                  <span class="rounded-full bg-white/10 px-3 py-1 text-[8px] font-black uppercase tracking-[0.18em] text-white/70">
                    {{ featuredEvidence.kind }}
                  </span>
                  <span
                    v-if="featuredEvidence.highlighted"
                    class="rounded-full bg-white/10 px-3 py-1 text-[8px] font-black uppercase tracking-[0.18em] text-white/70"
                  >
                    scene lead
                  </span>
                </div>
                <div class="mt-3 text-xl font-black tracking-tight">
                  {{ featuredEvidence.label }}
                </div>
                <p class="mt-2 text-sm leading-relaxed text-white/75">
                  {{ featuredEvidence.summary }}
                </p>
                <button
                  class="mt-4 rounded-full bg-[#f7d27a] px-4 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-[#132136]"
                  @click="store.inspectEvidence(featuredEvidence.id)"
                >
                  跟进这条线索
                </button>
              </div>

              <div v-else class="mt-4 rounded-3xl border border-emerald-500/20 bg-emerald-500/[0.08] p-4 text-sm font-black text-emerald-700 dark:text-emerald-300">
                当前待排查线索已经清空，可以切去人物继续问询，或者直接交卷。
              </div>

              <div v-if="queuedEvidence.length" class="mt-4">
                <div class="text-[9px] font-black uppercase tracking-[0.22em] text-text-tertiary">队列里还有</div>
                <div class="mt-3 grid gap-2">
                  <button
                    v-for="item in queuedEvidence"
                    :key="item.id"
                    class="rounded-2xl border border-white/10 bg-white px-4 py-3 text-left transition-colors hover:bg-white/90 dark:bg-white/[0.04]"
                    @click="store.inspectEvidence(item.id)"
                  >
                    <div class="flex items-center justify-between gap-3">
                      <div class="min-w-0 flex-1">
                        <div class="text-sm font-black text-text-primary">{{ item.label }}</div>
                        <div class="mt-1 text-[11px] leading-relaxed text-text-secondary">{{ item.summary }}</div>
                      </div>
                      <span class="rounded-full bg-black/5 px-3 py-1 text-[8px] font-black uppercase tracking-[0.18em] text-text-tertiary dark:bg-white/10">
                        待排查
                      </span>
                    </div>
                  </button>
                </div>
              </div>

              <div v-if="archivedEvidence.length" class="mt-4">
                <div class="text-[9px] font-black uppercase tracking-[0.22em] text-text-tertiary">已跟进</div>
                <div class="mt-3 space-y-2">
                  <div
                    v-for="item in archivedEvidence"
                    :key="item.id"
                    class="rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.08] px-4 py-3"
                  >
                    <div class="flex items-center justify-between gap-3">
                      <div class="min-w-0 flex-1">
                        <div class="text-sm font-black text-text-primary">{{ item.label }}</div>
                        <div class="mt-1 text-[11px] leading-relaxed text-text-secondary">{{ item.summary }}</div>
                      </div>
                      <span class="rounded-full bg-emerald-500/15 px-3 py-1 text-[8px] font-black uppercase tracking-[0.18em] text-emerald-600 dark:text-emerald-300">
                        collected
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </article>

            <article class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
              <div class="flex items-center gap-2">
                <LayoutList :size="14" :stroke-width="3.5" class="text-[#132136] dark:text-[#f7d27a]" />
                <div class="text-[9px] font-black uppercase tracking-[0.24em] text-text-tertiary">Case Notes</div>
              </div>
              <p class="mt-2 text-xs leading-relaxed text-text-secondary">
                这里不再单独做大块 `Fact Registry`，而是只保留最近解锁的关键笔记。
              </p>

              <div class="mt-4 space-y-3">
                <div
                  v-for="fact in compactNotes"
                  :key="fact.id"
                  class="rounded-2xl border border-white/10 bg-white p-4 dark:bg-white/[0.06]"
                >
                  <div class="flex items-center justify-between gap-2">
                    <div class="text-sm font-black text-text-primary">{{ fact.label }}</div>
                    <span class="rounded-full border px-2 py-0.5 text-[8px] font-black uppercase tracking-[0.16em]" :class="categoryTone(fact.category)">
                      {{ fact.category }}
                    </span>
                  </div>
                  <p class="mt-2 text-xs leading-relaxed text-text-secondary">{{ fact.summary }}</p>
                </div>

                <div v-if="!compactNotes.length" class="rounded-2xl border border-dashed border-white/10 p-4 text-xs leading-relaxed text-text-tertiary">
                  还没有新的案件笔记。先从上面的证据开始。
                </div>
              </div>
            </article>
          </div>

          <div v-else class="mt-4 grid gap-3">
            <article
              v-for="witness in witnessPool"
              :key="witness.id"
              class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="flex flex-wrap items-center gap-2">
                    <div class="text-sm font-black tracking-tight text-text-primary">{{ witness.name }}</div>
                    <span
                      class="rounded-full px-2 py-0.5 text-[8px] font-black uppercase tracking-[0.18em]"
                      :class="witness.highlighted ? 'bg-[#132136]/10 text-[#132136] dark:bg-[#f7d27a]/10 dark:text-[#f7d27a]' : 'bg-black/5 text-text-tertiary dark:bg-white/10'"
                    >
                      {{ witness.role }}
                    </span>
                  </div>
                  <p class="mt-1 text-xs leading-relaxed text-text-secondary">{{ witness.publicProfile }}</p>
                </div>
                <span class="rounded-full bg-black/5 px-2 py-0.5 text-[8px] font-black uppercase tracking-[0.18em] text-text-tertiary dark:bg-white/10">
                  {{ witness.demeanor }}
                </span>
              </div>

              <div class="mt-3 space-y-2">
                <button
                  v-for="testimony in witness.testimony"
                  :key="testimony.id"
                  class="w-full rounded-2xl border px-3 py-3 text-left transition-all"
                  :class="[
                    store.askedTestimonyIds.includes(testimony.id)
                      ? 'border-emerald-500/20 bg-emerald-500/[0.08]'
                      : store.isTestimonyAvailable(testimony)
                        ? 'border-white/10 bg-white hover:bg-white/90 dark:bg-white/[0.04]'
                        : 'border-dashed border-white/10 bg-black/[0.02] opacity-70 dark:bg-white/[0.02]',
                  ]"
                  :disabled="!store.isTestimonyAvailable(testimony)"
                  @click="store.askWitness(witness.id, testimony.id)"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div class="text-xs font-black text-text-primary">{{ testimony.promptLabel }}</div>
                    <span class="text-[8px] font-black uppercase tracking-[0.18em] text-text-tertiary">
                      {{ store.askedTestimonyIds.includes(testimony.id) ? 'taken' : store.isTestimonyAvailable(testimony) ? 'ask' : 'locked' }}
                    </span>
                  </div>
                  <div
                    v-if="!store.isTestimonyAvailable(testimony)"
                    class="mt-2 text-[11px] leading-relaxed text-text-tertiary"
                  >
                    {{ store.gateLabelForTestimony(testimony) }}
                  </div>
                </button>
              </div>
            </article>
          </div>
        </section>

        <section
          v-if="store.phase === 'final_reconstruction' || store.phase === 'verdict'"
          class="rounded-[28px] border border-white/10 bg-white/70 p-5 shadow-xl dark:bg-white/[0.04]"
        >
          <div class="flex items-center gap-2">
            <Flag :size="14" :stroke-width="3.5" class="text-[#132136] dark:text-[#f7d27a]" />
            <div class="text-[10px] font-black uppercase tracking-[0.28em] text-text-tertiary">Final Reconstruction</div>
          </div>

          <div v-if="store.phase === 'final_reconstruction'" class="mt-4 grid gap-4">
            <div class="grid gap-4 lg:grid-cols-2">
              <article class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
                <div class="text-[9px] font-black uppercase tracking-[0.24em] text-text-tertiary">1. 谁做的</div>
                <div class="mt-3 space-y-2">
                  <label
                    v-for="witness in store.packet.witnesses"
                    :key="witness.id"
                    class="flex cursor-pointer items-center gap-3 rounded-2xl border border-white/10 px-3 py-3"
                  >
                    <input v-model="culpritId" :value="witness.id" type="radio" class="accent-[#132136]" />
                    <div>
                      <div class="text-sm font-black text-text-primary">{{ witness.name }}</div>
                      <div class="text-[11px] text-text-secondary">{{ witness.role }}</div>
                    </div>
                  </label>
                </div>
              </article>

              <article class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
                <div class="text-[9px] font-black uppercase tracking-[0.24em] text-text-tertiary">2. 为什么</div>
                <div class="mt-3 space-y-2">
                  <label
                    v-for="motive in store.packet.motives"
                    :key="motive.id"
                    class="flex cursor-pointer items-start gap-3 rounded-2xl border border-white/10 px-3 py-3"
                  >
                    <input v-model="motiveId" :value="motive.id" type="radio" class="mt-1 accent-[#132136]" />
                    <div>
                      <div class="text-sm font-black text-text-primary">{{ motive.label }}</div>
                      <div class="text-[11px] leading-relaxed text-text-secondary">{{ motive.summary }}</div>
                    </div>
                  </label>
                </div>
              </article>
            </div>

            <article class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
              <div class="flex items-center gap-2">
                <FlaskConical :size="14" :stroke-width="3.5" class="text-[#132136] dark:text-[#f7d27a]" />
                <div class="text-[9px] font-black uppercase tracking-[0.24em] text-text-tertiary">3. 哪些关键证据能支撑事实</div>
              </div>
              <div class="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                <select v-model="selectedEvidenceId" class="h-12 rounded-2xl border border-white/10 bg-white px-4 text-sm text-text-primary outline-none dark:bg-white/[0.06]">
                  <option value="">选择证据</option>
                  <option
                    v-for="item in store.discoveredEvidence"
                    :key="item.id"
                    :value="item.id"
                  >
                    {{ item.label }}
                  </option>
                </select>
                <select v-model="selectedFactId" class="h-12 rounded-2xl border border-white/10 bg-white px-4 text-sm text-text-primary outline-none dark:bg-white/[0.06]">
                  <option value="">选择对应事实</option>
                  <option
                    v-for="fact in evidencePairFactPool"
                    :key="fact.id"
                    :value="fact.id"
                  >
                    {{ fact.label }}
                  </option>
                </select>
                <button
                  class="rounded-2xl bg-[#132136] px-5 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-[#f7d27a]"
                  @click="addEvidencePair"
                >
                  加入
                </button>
              </div>
              <div class="mt-4 space-y-2">
                <div
                  v-for="(pair, index) in evidencePairs"
                  :key="`${pair.evidenceId}-${pair.factId}`"
                  class="flex items-center gap-3 rounded-2xl border border-white/10 bg-white px-3 py-3 dark:bg-white/[0.06]"
                >
                  <div class="min-w-0 flex-1 text-sm font-black text-text-primary">
                    {{ evidenceLabelMap.get(pair.evidenceId) }}
                  </div>
                  <div class="text-[11px] font-bold text-text-tertiary">supports</div>
                  <div class="min-w-0 flex-1 text-sm font-black text-text-primary">
                    {{ factLabelMap.get(pair.factId) }}
                  </div>
                  <button class="rounded-full px-2 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-red-500" @click="removeEvidencePair(index)">
                    删除
                  </button>
                </div>
              </div>
            </article>

            <article class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
              <div class="flex items-center gap-2">
                <LayoutList :size="14" :stroke-width="3.5" class="text-[#132136] dark:text-[#f7d27a]" />
                <div class="text-[9px] font-black uppercase tracking-[0.24em] text-text-tertiary">4. 最短时间线</div>
              </div>
              <div class="mt-3 flex flex-wrap gap-2">
                <button
                  v-for="fact in timelinePool"
                  :key="fact.id"
                  class="rounded-full border border-white/10 bg-white px-3 py-2 text-[11px] font-bold text-text-primary dark:bg-white/[0.06]"
                  @click="addTimelineFact(fact.id)"
                >
                  + {{ fact.label }}
                </button>
              </div>
              <div class="mt-4 space-y-2">
                <div
                  v-for="(fact, index) in selectedTimelineFacts"
                  :key="fact.id"
                  class="flex items-center gap-2 rounded-2xl border border-white/10 bg-white px-3 py-3 dark:bg-white/[0.06]"
                >
                  <div class="flex h-7 w-7 items-center justify-center rounded-full bg-[#132136] text-[10px] font-black text-[#f7d27a]">
                    {{ index + 1 }}
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="text-sm font-black text-text-primary">{{ fact.label }}</div>
                    <div class="text-[11px] text-text-secondary">{{ fact.summary }}</div>
                  </div>
                  <button class="rounded-full p-2 text-text-tertiary" @click="moveTimelineFact(index, -1)">
                    <ArrowUp :size="14" :stroke-width="3.5" />
                  </button>
                  <button class="rounded-full p-2 text-text-tertiary" @click="moveTimelineFact(index, 1)">
                    <ArrowDown :size="14" :stroke-width="3.5" />
                  </button>
                  <button class="rounded-full px-2 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-red-500" @click="removeTimelineFact(fact.id)">
                    移除
                  </button>
                </div>
              </div>
            </article>

            <article class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
              <div class="text-[9px] font-black uppercase tracking-[0.24em] text-text-tertiary">5. 一句话解释</div>
              <textarea
                v-model="explanation"
                rows="3"
                maxlength="280"
                class="mt-4 w-full rounded-3xl border border-white/10 bg-white px-4 py-4 text-sm leading-relaxed text-text-primary outline-none dark:bg-white/[0.06]"
                placeholder="这段不计分，只是把你的推理压成一句话。"
              />
              <div class="mt-2 text-right text-[10px] font-black uppercase tracking-[0.18em] text-text-tertiary">
                {{ explanation.length }}/280
              </div>
            </article>

            <div class="flex flex-wrap gap-2">
              <button
                class="rounded-full border border-white/10 px-4 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-primary"
                @click="store.resumeInvestigation"
              >
                回到调查
              </button>
              <button
                class="rounded-full px-5 py-3 text-[10px] font-black uppercase tracking-[0.22em]"
                :class="canSubmit ? 'bg-[#132136] text-[#f7d27a]' : 'bg-black/5 text-text-tertiary dark:bg-white/10'"
                @click="submitVerdict"
              >
                提交 reconstruction
              </button>
            </div>
          </div>

          <div v-else-if="store.phase === 'verdict' && store.latestVerdict" class="mt-4 grid gap-4">
            <div class="rounded-3xl border border-white/10 bg-[#132136] p-5 text-white">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <div class="text-[9px] font-black uppercase tracking-[0.24em] text-[#f7d27a]">Verdict</div>
                  <div class="mt-2 text-2xl font-black tracking-tight">
                    {{ store.latestVerdict.success ? '交卷成立' : '交卷未通过' }}
                  </div>
                </div>
                <span class="rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] ring-1" :class="gradeClass">
                  {{ gradeLabel }}
                </span>
              </div>
              <p class="mt-3 text-sm leading-relaxed text-white/75">
                当前分数 {{ store.latestVerdict.score.total }} / {{ store.packet.validation.weights.total }}。判分来自本地 validator，不会被你的自由发挥“讲圆”。
              </p>
            </div>

            <div class="grid gap-3 lg:grid-cols-4">
              <div class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
                <div class="text-[9px] font-black uppercase tracking-[0.22em] text-text-tertiary">Culprit</div>
                <div class="mt-2 text-xl font-black text-text-primary">{{ store.latestVerdict.score.culprit }}</div>
                <div class="mt-1 text-xs text-text-secondary">{{ store.latestVerdict.culpritCorrect ? '指认正确' : '指认错误' }}</div>
              </div>
              <div class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
                <div class="text-[9px] font-black uppercase tracking-[0.22em] text-text-tertiary">Timeline</div>
                <div class="mt-2 text-xl font-black text-text-primary">{{ store.latestVerdict.score.timeline }}</div>
                <div class="mt-1 text-xs text-text-secondary">accuracy {{ Math.round(store.latestVerdict.timelineAccuracy * 100) }}%</div>
              </div>
              <div class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
                <div class="text-[9px] font-black uppercase tracking-[0.22em] text-text-tertiary">Evidence</div>
                <div class="mt-2 text-xl font-black text-text-primary">{{ store.latestVerdict.score.evidence }}</div>
                <div class="mt-1 text-xs text-text-secondary">accuracy {{ Math.round(store.latestVerdict.evidenceAccuracy * 100) }}%</div>
              </div>
              <div class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
                <div class="text-[9px] font-black uppercase tracking-[0.22em] text-text-tertiary">Motive</div>
                <div class="mt-2 text-xl font-black text-text-primary">{{ store.latestVerdict.score.motive }}</div>
                <div class="mt-1 text-xs text-text-secondary">{{ store.latestVerdict.motiveCorrect ? '动机正确' : '动机错误' }}</div>
              </div>
            </div>

            <div class="grid gap-3 lg:grid-cols-2">
              <article class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
                <div class="text-[9px] font-black uppercase tracking-[0.22em] text-text-tertiary">Missing Core Facts</div>
                <div class="mt-3 flex flex-wrap gap-2">
                  <span
                    v-for="factId in store.latestVerdict.missingCoreFactIds"
                    :key="factId"
                    class="rounded-full bg-red-500/10 px-3 py-1 text-[11px] font-bold text-red-500"
                  >
                    {{ factLabelMap.get(factId) ?? factId }}
                  </span>
                  <span
                    v-if="!store.latestVerdict.missingCoreFactIds.length"
                    class="rounded-full bg-emerald-500/10 px-3 py-1 text-[11px] font-bold text-emerald-500"
                  >
                    无缺漏
                  </span>
                </div>
                <div
                  v-if="store.latestVerdict.contradictions.length"
                  class="mt-4 rounded-2xl border border-red-500/20 bg-red-500/5 p-3 text-xs leading-relaxed text-red-500"
                >
                  <div class="flex items-center gap-2 font-black uppercase tracking-[0.18em]">
                    <AlertCircle :size="12" :stroke-width="3.5" />
                    contradictions
                  </div>
                  <div class="mt-2">{{ store.latestVerdict.contradictions.join(' ') }}</div>
                </div>
              </article>

              <article class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]">
                <div class="text-[9px] font-black uppercase tracking-[0.22em] text-text-tertiary">Ground Truth</div>
                <div class="mt-3 space-y-2 text-sm leading-relaxed text-text-secondary">
                  <div>
                    <span class="font-black text-text-primary">Culprit:</span>
                    {{ store.witnessMap.get(store.latestVerdict.revealedTruth.culpritId)?.name }}
                  </div>
                  <div>
                    <span class="font-black text-text-primary">Motive:</span>
                    {{ store.motiveMap.get(store.latestVerdict.revealedTruth.motiveId)?.label }}
                  </div>
                  <div>
                    <span class="font-black text-text-primary">Timeline:</span>
                  </div>
                  <ol class="space-y-1">
                    <li
                      v-for="factId in store.latestVerdict.revealedTruth.timelineFactIds"
                      :key="factId"
                      class="rounded-2xl border border-white/10 bg-white px-3 py-2 text-xs text-text-primary dark:bg-white/[0.06]"
                    >
                      {{ factLabelMap.get(factId) ?? factId }}
                    </li>
                  </ol>
                </div>
              </article>
            </div>

            <div class="flex flex-wrap gap-2">
              <button
                class="rounded-full border border-white/10 px-4 py-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-primary"
                @click="store.reviseSubmission"
              >
                修改后重交
              </button>
              <button
                class="rounded-full bg-[#132136] px-5 py-3 text-[10px] font-black uppercase tracking-[0.22em] text-[#f7d27a]"
                @click="restartCase"
              >
                重开此案
              </button>
            </div>
          </div>
        </section>

        <section class="rounded-[28px] border border-white/10 bg-white/70 p-5 shadow-xl dark:bg-white/[0.04]">
          <div class="flex items-center gap-2">
            <FileSearch :size="14" :stroke-width="3.5" class="text-[#132136] dark:text-[#f7d27a]" />
            <div class="text-[10px] font-black uppercase tracking-[0.28em] text-text-tertiary">Recent Moves</div>
          </div>
          <div class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <article
              v-for="item in recentLog"
              :key="item.id"
              class="rounded-3xl border border-white/10 bg-white/60 p-4 dark:bg-white/[0.03]"
            >
              <div class="text-[8px] font-black uppercase tracking-[0.18em] text-text-tertiary">
                {{ item.kind }}
              </div>
              <div class="mt-2 text-sm font-black tracking-tight text-text-primary">{{ item.title }}</div>
              <p class="mt-2 text-xs leading-relaxed text-text-secondary">{{ item.summary }}</p>
            </article>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>
