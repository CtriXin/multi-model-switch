<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { RotateCcw, AlertTriangle, Loader2, Shield, ChevronRight, Scale, Home, Info, ChevronDown, ChevronUp } from 'lucide-vue-next'
import { useMultiLifeStore } from '@/stores/multiLife'
import { listCases } from '@/features/play-modes/multi-life'

const store = useMultiLifeStore()

const {
  caseData, processing, endingGenerating, error,
  phase, currentRound, challengeRemaining,
  lastRound, hasContradiction, started,
  evidenceCards, ending, rounds,
  modelDiverse, useMock, modelPicked, modelWarning, roundStarting,
  streamingTexts, streamingScene,
} = storeToRefs(store)

const cases = listCases()
const expandedRoundIds = ref<Set<string>>(new Set())

// --- Intro streaming (case detail page) ---
const introParagraphs = ref<string[]>([])
const introVisibleCount = ref(0)
const introDone = ref(false)
const introTitleShown = ref(false)

async function streamIntro(text: string) {
  const paragraphs = text.split('\n').filter(p => p.trim())
  introParagraphs.value = paragraphs
  introVisibleCount.value = 0
  introDone.value = false
  introTitleShown.value = false
  await nextTick()
  await new Promise(r => setTimeout(r, 400))
  introTitleShown.value = true
  await new Promise(r => setTimeout(r, 600))
  // Reveal paragraphs one by one
  for (let i = 0; i < paragraphs.length; i++) {
    introVisibleCount.value = i + 1
    await new Promise(r => setTimeout(r, 500))
  }
  introDone.value = true
}

// When caseData changes and we're in setup, start streaming
let lastStreamedCaseId = ''
watch(
  () => [phase.value, caseData.value?.id ?? ''] as const,
  ([nextPhase, caseId]) => {
    if (nextPhase !== 'setup') {
      lastStreamedCaseId = ''
      return
    }
    if (!caseId || !caseData.value) return
    if (caseId === lastStreamedCaseId && introDone.value) return
    lastStreamedCaseId = caseId
    void streamIntro(caseData.value.premise)
  },
  { immediate: true },
)

const ROLE_STYLES = [
  { border: 'border-cyan-400/20', bg: 'bg-cyan-500/[0.04]', accent: 'text-cyan-400', dot: 'bg-cyan-400' },
  { border: 'border-rose-400/20', bg: 'bg-rose-500/[0.04]', accent: 'text-rose-400', dot: 'bg-rose-400' },
  { border: 'border-amber-400/20', bg: 'bg-amber-500/[0.04]', accent: 'text-amber-400', dot: 'bg-amber-400' },
]

const TAG_COLORS: Record<string, { dot: string }> = {
  key: { dot: 'bg-emerald-400' },
  suspicious: { dot: 'bg-yellow-400' },
  debunked: { dot: 'bg-red-400' },
  ambiguous: { dot: 'bg-zinc-400' },
}

function trustDot(value: number): string {
  if (value >= 2) return 'bg-emerald-400'
  if (value >= 0) return 'bg-yellow-400'
  return 'bg-red-400'
}

function toggleRound(id: string) {
  if (expandedRoundIds.value.has(id)) {
    expandedRoundIds.value.delete(id)
  } else {
    expandedRoundIds.value.add(id)
  }
}

function isRoundExpanded(id: string): boolean {
  // Latest round is always expanded
  if (lastRound.value?.id === id) return true
  return expandedRoundIds.value.has(id)
}

const canChallenge = computed(() =>
  lastRound.value && !lastRound.value.playerChoice
  && challengeRemaining.value > 0 && !processing.value,
)

const canAccept = computed(() =>
  lastRound.value && !lastRound.value.playerChoice && !processing.value,
)

const isResolutionPhase = computed(() =>
  phase.value === 'resolution' || phase.value === 'ended',
)

onMounted(() => { store.init() })

function handleStart() { if (cases.length > 0) store.selectCase(cases[0].id) }
function handleBegin() { store.startRound() }
function handleNextRound() { store.startRound() }
function handleAccept() { store.acceptRound() }
function handleChallenge(roleId: string) { store.challengeRole(roleId) }
function handleGenerateEnding() { store.generateEnding() }
</script>

<template>
  <div class="h-full flex flex-col items-center p-3 sm:p-4 lg:p-6 overflow-hidden relative">
    <div class="w-full max-w-5xl flex-1 flex flex-col glass-v3 rounded-[32px] shadow-2xl border border-white/10 overflow-hidden bg-white/70 dark:bg-[#0b0b18]/80 relative z-10 transition-all duration-700 lg:rounded-[40px]">

      <!-- Header -->
      <header class="flex items-center justify-between px-6 h-14 shrink-0 relative border-b border-black/[0.03] dark:border-white/5 bg-white/40 backdrop-blur-md">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center shadow-lg shadow-accent/10">
            <Shield :size="14" stroke-width="4" class="text-accent" />
          </div>
          <div class="flex flex-col">
            <h1 class="text-[10px] font-black uppercase tracking-[0.2em] text-text-primary leading-none">多重人生</h1>
            <div v-if="started" class="text-[8px] font-black text-accent uppercase tracking-widest mt-1">
              第{{ currentRound }}/{{ caseData?.totalRounds ?? '?' }} 轮
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span v-if="started" class="flex items-center gap-1 px-2.5 py-1 rounded-full bg-accent/10 text-[8px] font-black text-accent uppercase tracking-widest">
            <Scale :size="10" stroke-width="4" /> {{ challengeRemaining }}
          </span>
          <button v-if="started || caseData" @click="store.restart()"
            class="flex items-center justify-center w-8 h-8 rounded-full bg-black/[0.03] dark:bg-white/5 text-text-tertiary hover:text-text-primary transition-all active:scale-90">
            <Home :size="14" stroke-width="4" />
          </button>
        </div>
      </header>

      <main class="flex-1 relative overflow-hidden flex flex-col">
        <!-- Banners -->
        <div v-if="error" class="shrink-0 mx-4 mt-4 px-4 py-3 rounded-2xl bg-red-500/[0.06] border border-red-400/20 text-xs text-red-300">
          {{ error }}
        </div>
        <div v-if="useMock && started" class="shrink-0 mx-4 mt-3 flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-amber-500/[0.06] border border-amber-400/20">
          <Info :size="14" stroke-width="3" class="text-amber-400 shrink-0" />
          <p class="text-xs text-amber-300/80">未检测到可用模型，当前使用<strong class="text-amber-300">模拟数据</strong>运行。</p>
        </div>
        <div v-else-if="!modelDiverse && started" class="shrink-0 mx-4 mt-3 flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-amber-500/[0.06] border border-amber-400/20">
          <Info :size="14" stroke-width="3" class="text-amber-400 shrink-0" />
          <p class="text-xs text-amber-300/80">模型不足 3 个不同 provider，<strong class="text-amber-300">角色差异可能不明显</strong>。</p>
        </div>

        <transition name="ios-swap" mode="out-in">
          <div :key="phase" class="flex-1 flex flex-col overflow-hidden">

            <!-- ─── Setup: no case ─── -->
            <div v-if="phase === 'setup' && !caseData" class="flex-1 flex flex-col items-center justify-center gap-8 px-6">
              <div class="w-16 h-16 rounded-[32px] bg-accent/10 flex items-center justify-center shadow-lg">
                <Shield :size="28" stroke-width="3" class="text-accent" />
              </div>
              <div class="text-center max-w-md">
                <h2 class="text-2xl font-black tracking-tight text-text-primary mb-3">多重人生</h2>
                <p class="text-sm text-text-tertiary leading-relaxed">
                  同一个案件，3 个 AI 角色各执一词。<br>你通过质疑和信任推进叙事，最终还原属于你的真相。
                </p>
              </div>
              <button @click="handleStart"
                class="flex items-center gap-3 h-14 rounded-2xl bg-accent text-white font-black tracking-widest text-xs hover:bg-accent-hover hover:shadow-2xl hover:shadow-accent/20 transition-all active:scale-[0.98]">
                <ChevronRight :size="16" stroke-width="4" /><span>选择案件开始</span>
              </button>
            </div>

            <!-- ─── Setup: case selected ─── -->
            <div v-else-if="phase === 'setup' && caseData" class="flex-1 overflow-y-auto px-4 sm:px-10 py-8 overscroll-contain">
              <div class="mx-auto w-full max-w-2xl">
                <button @click="store.restart()" class="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-text-quaternary hover:text-text-primary transition-colors mb-10">
                  <RotateCcw :size="12" /> 返回
                </button>
                <div class="text-center mb-10">
                  <h2 class="text-2xl font-black tracking-tight text-text-primary mb-4 transition-all duration-700"
                    :class="introTitleShown ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'">
                    {{ caseData.title }}
                  </h2>
                  <div class="p-6 rounded-[32px] bg-accent/5 border border-accent/10 text-sm text-text-secondary leading-loose shadow-inner min-h-[5em]">
                    <p v-for="(p, pi) in introParagraphs" :key="pi"
                      class="transition-all duration-500"
                      :class="pi < introVisibleCount ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'">
                      {{ p }}
                    </p>
                    <span v-if="!introDone && introVisibleCount > 0" class="inline-block w-1.5 h-3.5 bg-accent/60 animate-pulse ml-0.5 align-middle" />
                  </div>
                </div>
                <!-- Meta + Roles + Button: appear after intro streaming -->
                <transition name="intro-fade">
                  <div v-if="introDone">
                    <div class="flex items-center justify-center gap-3 mb-6">
                      <span class="px-2 py-0.5 rounded-md bg-accent/10 text-[8px] font-black uppercase tracking-widest text-accent">{{ caseData.totalRounds }} 轮</span>
                      <span class="text-[8px] font-black uppercase tracking-widest text-text-quaternary">{{ caseData.challengeBudget }} 次质疑</span>
                    </div>

                    <!-- Model warning -->
                    <div v-if="modelWarning" class="mb-4 flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-amber-500/[0.06] border border-amber-400/20">
                      <Info :size="14" stroke-width="3" class="text-amber-400 shrink-0" />
                      <p class="text-xs text-amber-300/80">{{ modelWarning }}</p>
                    </div>

                    <!-- Role cards with model info -->
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
                      <div v-for="(role, idx) in caseData.roles" :key="role.id"
                        class="p-4 rounded-2xl transition-all" :class="ROLE_STYLES[idx].bg + ' ' + ROLE_STYLES[idx].border">
                        <p class="text-sm font-bold" :class="ROLE_STYLES[idx].accent">{{ role.name }}</p>
                        <p v-if="modelPicked" class="mt-1 text-xs text-text-quaternary truncate">{{ store.getAssignedModelName(role.id) }}</p>
                        <p v-else class="mt-1 text-xs text-text-tertiary">等待分配…</p>
                      </div>
                    </div>

                    <!-- Pick models button -->
                    <button v-if="!modelPicked" @click="store.pickRandomModels()"
                      class="w-full flex items-center justify-center gap-3 h-12 rounded-2xl border-2 border-dashed border-accent/30 text-accent font-black tracking-widest text-xs hover:bg-accent/5 hover:border-accent/50 transition-all active:scale-[0.98] mb-3">
                      <Shield :size="14" stroke-width="3" /><span>随机分配模型</span>
                    </button>

                    <div v-if="modelPicked" class="flex flex-col gap-3 sm:flex-row">
                      <button @click="store.pickRandomModels()"
                        class="sm:w-40 h-14 rounded-2xl border border-accent/20 bg-accent/5 text-accent font-black tracking-widest text-xs hover:bg-accent/10 transition-all active:scale-[0.98]">
                        重新随机
                      </button>
                      <button @click="handleBegin"
                        class="flex-1 flex items-center justify-center gap-3 h-14 rounded-2xl bg-accent text-white font-black tracking-widest text-xs hover:bg-accent-hover hover:shadow-2xl hover:shadow-accent/20 transition-all active:scale-[0.98]">
                        <Shield :size="16" stroke-width="4" /><span>开始调查</span>
                      </button>
                    </div>
                  </div>
                </transition>
              </div>
            </div>

            <!-- ─── Investigation: card stack ─── -->
            <div v-else-if="phase === 'investigation' && started" class="flex-1 overflow-y-auto px-4 sm:px-6 py-4 overscroll-contain scroll-smooth">
              <div class="mx-auto w-full max-w-3xl space-y-3 pb-8">

                <!-- Loading state while transition finishes -->
                <div v-if="roundStarting" class="flex flex-col items-center justify-center gap-4 py-20">
                  <Loader2 class="h-6 w-6 animate-spin text-accent/60" />
                  <p class="text-xs text-text-tertiary">进入调查现场…</p>
                </div>

                <!-- Card content (only after transition) -->
                <template v-if="!roundStarting">

                <!-- Evidence rail (sticky top) -->
                <div v-if="evidenceCards.length > 0" class="sticky top-0 z-20 py-2 bg-gradient-to-b from-white/80 via-white/60 to-transparent dark:from-[#0b0b18]/90 dark:via-[#0b0b18]/70 dark:to-transparent">
                  <div class="flex gap-2 overflow-x-auto no-scrollbar">
                    <div v-for="card in evidenceCards" :key="card.id"
                      class="flex shrink-0 items-center gap-2 rounded-xl bg-white/60 dark:bg-white/[0.04] border border-black/5 dark:border-white/5 px-3 py-1.5"
                      style="min-width: 140px; max-width: 220px">
                      <span class="h-1.5 w-1.5 shrink-0 rounded-full" :class="TAG_COLORS[card.tag]?.dot ?? 'bg-zinc-400'" />
                      <div class="min-w-0">
                        <span class="text-[8px] text-text-quaternary">R{{ card.round }}</span>
                        <p class="text-[10px] text-text-secondary truncate">{{ card.summary }}</p>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Round cards (stacked, newest on top) -->
                <div v-for="r in [...rounds].reverse()" :key="r.id">

                  <!-- Collapsed card (old rounds) -->
                  <button v-if="!isRoundExpanded(r.id)"
                    @click="toggleRound(r.id)"
                    class="flex w-full items-center gap-3 px-4 py-3 rounded-2xl text-left transition-all bg-white/50 dark:bg-white/[0.02] border border-black/5 dark:border-white/5 hover:border-accent/20 hover:shadow-md"
                  >
                    <span class="text-[10px] font-black text-text-primary tabular-nums w-10 shrink-0">R{{ r.roundNumber }}</span>
                    <span class="text-xs text-text-tertiary truncate flex-1">{{ r.scene.slice(0, 50) }}</span>
                    <span v-if="r.playerChoice?.type === 'challenge'" class="shrink-0 text-[8px] font-black text-amber-400 uppercase tracking-widest">质疑</span>
                    <span v-else-if="r.playerChoice" class="shrink-0 text-[8px] font-black text-text-quaternary uppercase tracking-widest">接受</span>
                    <ChevronDown class="h-3.5 w-3.5 text-text-quaternary shrink-0" />
                  </button>

                  <!-- Expanded card -->
                  <div v-else class="rounded-[20px] bg-white/50 dark:bg-white/[0.03] border border-black/5 dark:border-white/5 overflow-hidden transition-shadow hover:shadow-lg">

                    <!-- Card header -->
                    <div class="flex items-center justify-between px-4 py-3 border-b border-black/[0.03] dark:border-white/5">
                      <div class="flex items-center gap-2">
                        <span class="text-[10px] font-black text-text-primary tabular-nums">R{{ r.roundNumber }}</span>
                        <span class="h-1 w-1 rounded-full" :class="r.contradictions.length ? 'bg-amber-400' : 'bg-text-quaternary/30'" />
                        <span v-if="r.contradictions.length" class="text-[8px] font-black text-amber-400 uppercase tracking-widest">矛盾</span>
                      </div>
                      <button v-if="r.id !== lastRound?.id" @click="toggleRound(r.id)"
                        class="flex items-center gap-1 text-[8px] text-text-quaternary hover:text-text-primary transition-colors">
                        收起 <ChevronUp class="h-3 w-3" />
                      </button>
                      <span v-if="r.playerChoice" class="text-[8px] font-black uppercase tracking-widest"
                        :class="r.playerChoice.type === 'challenge' ? 'text-amber-400' : 'text-text-quaternary'">
                        {{ r.playerChoice.type === 'challenge' ? '已质疑' : '已接受' }}
                      </span>
                    </div>

                    <!-- Scene -->
                    <div class="px-4 pt-3 pb-2">
                      <p class="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">
                        {{ r.id === lastRound?.id ? (streamingScene || r.scene) : r.scene }}
                        <span v-if="r.id === lastRound?.id && processing && !lastRound?.playerChoice" class="inline-block w-1.5 h-3.5 bg-accent/60 animate-pulse ml-0.5 align-middle" />
                      </p>
                    </div>

                    <!-- 3 Role testimonies -->
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 px-4 pb-3">
                      <div v-for="(resp, idx) in r.responses" :key="resp.roleId"
                        class="p-3 rounded-xl border transition-all" :class="ROLE_STYLES[idx].bg + ' ' + ROLE_STYLES[idx].border">
                        <div class="flex items-center justify-between mb-1.5">
                          <p class="text-xs font-bold" :class="ROLE_STYLES[idx].accent">
                            {{ caseData?.roles.find(rl => rl.id === resp.roleId)?.name }}
                          </p>
                          <div class="flex items-center gap-1.5">
                            <span class="h-1.5 w-1.5 rounded-full" :class="trustDot(store.trustMap[resp.roleId] ?? 0)" />
                            <span class="px-1 py-0.5 rounded bg-black/5 dark:bg-white/5 text-[7px] font-black text-text-quaternary">{{ resp.modelName }}</span>
                          </div>
                        </div>
                        <p v-if="resp.status === 'done'" class="text-xs text-text-primary leading-relaxed whitespace-pre-wrap">{{ streamingTexts[`${r.id}-${resp.roleId}`] || resp.text }}</p>
                        <div v-else-if="resp.status === 'generating' && streamingTexts[`${r.id}-${resp.roleId}`]" class="text-xs text-text-primary/50 leading-relaxed whitespace-pre-wrap min-h-[3em]">{{ streamingTexts[`${r.id}-${resp.roleId}`] }}<span class="inline-block w-1.5 h-3.5 bg-accent/60 animate-pulse ml-0.5 align-middle" /></div>
                        <div v-else-if="resp.status === 'generating'" class="flex items-center gap-2 py-2 text-xs text-text-tertiary">
                          <Loader2 class="h-3 w-3 animate-spin text-accent" /> 证词生成中…
                        </div>
                        <p v-else class="text-xs text-red-400">{{ resp.error || '生成失败' }}</p>
                      </div>
                    </div>

                    <!-- Challenge response overlay card -->
                    <div v-if="r.playerChoice?.type === 'challenge' && (r.responses.some(resp => resp.isChallenged && resp.challengeResponse) || streamingTexts[`${r.id}-ch-${r.playerChoice?.challengedRoleId}`])"
                      class="mx-4 mb-4 p-3 rounded-xl border border-amber-400/25 bg-amber-500/[0.06] shadow-sm">
                      <div class="flex items-center gap-1.5 mb-2">
                        <AlertTriangle class="h-3.5 w-3.5 text-amber-400" />
                        <span class="text-[8px] font-black text-amber-400 uppercase tracking-widest">质疑后补充</span>
                        <span class="text-[8px] text-amber-400/60">
                          — {{ caseData?.roles.find(rl => rl.id === r.playerChoice!.challengedRoleId)?.name }}
                        </span>
                      </div>
                      <p class="text-xs text-text-primary leading-relaxed whitespace-pre-wrap">
                        {{ streamingTexts[`${r.id}-ch-${r.playerChoice?.challengedRoleId}`] || r.responses.find(resp => resp.challengeResponse)?.challengeResponse || '' }}
                        <span v-if="streamingTexts[`${r.id}-ch-${r.playerChoice?.challengedRoleId}`]" class="inline-block w-1.5 h-3.5 bg-amber-400/60 animate-pulse ml-0.5 align-middle" />
                      </p>
                    </div>

                    <!-- Contradiction (only if not yet decided) -->
                    <div v-if="r.contradictions.length && !r.playerChoice" class="mx-4 mb-3 flex items-start gap-2.5 p-3 rounded-xl bg-amber-500/[0.04] border border-amber-400/20">
                      <AlertTriangle class="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                      <div>
                        <p class="text-[10px] font-bold text-amber-300">发现矛盾</p>
                        <p v-for="(c, ci) in r.contradictions" :key="ci" class="text-[10px] text-text-secondary mt-0.5">{{ c.description }}</p>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Action buttons (only on latest round, not yet decided) -->
                <div v-if="lastRound && !lastRound.playerChoice" class="pt-2">
                  <div class="flex flex-wrap gap-2">
                    <button :disabled="!canAccept"
                      class="flex-1 h-12 rounded-2xl bg-accent text-white text-xs font-black uppercase tracking-widest transition-all active:scale-[0.98] disabled:opacity-40"
                      @click="handleAccept">
                      {{ hasContradiction ? '接受说法' : '继续' }}
                    </button>
                    <button v-for="resp in lastRound.responses.filter(r => r.status === 'done')"
                      v-if="canChallenge" :key="'ch-' + resp.roleId"
                      class="h-12 rounded-2xl border border-amber-400/20 bg-amber-500/[0.06] px-4 text-xs font-black text-amber-300 uppercase tracking-widest transition-all hover:bg-amber-500/[0.12]"
                      @click="handleChallenge(resp.roleId)">
                      质疑 {{ caseData?.roles.find(r => r.id === resp.roleId)?.name }}
                    </button>
                  </div>
                </div>

                <!-- Next round button -->
                <div v-if="lastRound?.playerChoice && !isResolutionPhase" class="pt-2">
                  <button :disabled="processing"
                    class="w-full h-12 rounded-2xl bg-text-primary text-surface-1 text-xs font-black uppercase tracking-widest transition-all active:scale-[0.98] disabled:opacity-40"
                    @click="handleNextRound">
                    <span v-if="processing" class="flex items-center justify-center gap-2">
                      <Loader2 class="h-3 w-3 animate-spin" /> 生成中…
                    </span>
                    <span v-else class="flex items-center justify-center gap-2">
                      下一轮 <ChevronRight :size="14" stroke-width="4" />
                    </span>
                  </button>
                </div>
                </template>
              </div>
            </div>

            <!-- ─── Resolution ─── -->
            <div v-else-if="isResolutionPhase && !ending" class="flex-1 flex flex-col items-center justify-center gap-8 px-6">
              <div class="w-16 h-16 rounded-[32px] bg-accent/10 flex items-center justify-center">
                <Shield :size="28" stroke-width="3" class="text-accent" />
              </div>
              <div class="text-center">
                <h2 class="text-2xl font-black tracking-tight text-text-primary mb-3">调查结束</h2>
                <p class="text-sm text-text-tertiary">所有轮次已完成，查看你的版本与真相对比。</p>
              </div>
              <button v-if="!endingGenerating" @click="handleGenerateEnding"
                class="flex items-center gap-3 h-14 rounded-2xl bg-accent text-white font-black tracking-widest text-xs hover:bg-accent-hover hover:shadow-2xl hover:shadow-accent/20 transition-all active:scale-[0.98]">
                <Scale :size="16" stroke-width="4" /><span>生成结局对比</span>
              </button>
              <div v-else class="flex items-center gap-2 text-sm text-text-tertiary">
                <Loader2 class="h-4 w-4 animate-spin text-accent" /> 生成中…
              </div>
            </div>

            <!-- ─── Ended ─── -->
            <div v-else-if="ending" class="flex-1 overflow-y-auto px-4 sm:px-8 py-8 overscroll-contain">
              <div class="mx-auto w-full max-w-3xl space-y-6">
                <div class="text-center">
                  <h2 class="text-2xl font-black tracking-tight text-text-primary mb-2">结局对比</h2>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div class="p-6 rounded-[28px] bg-cyan-500/[0.04] border border-cyan-400/15">
                    <p class="text-[9px] font-black uppercase tracking-[0.2em] text-cyan-400 mb-3">你的版本</p>
                    <p class="text-sm text-text-primary leading-relaxed">{{ ending.playerNarrative }}</p>
                  </div>
                  <div class="p-6 rounded-[28px] bg-emerald-500/[0.04] border border-emerald-400/15">
                    <p class="text-[9px] font-black uppercase tracking-[0.2em] text-emerald-400 mb-3">真相</p>
                    <p class="text-sm text-text-primary leading-relaxed">{{ ending.truthNarrative }}</p>
                  </div>
                </div>
                <div v-if="ending.deviationAnalysis" class="p-6 rounded-[28px] bg-white/40 dark:bg-white/[0.03] border border-black/5 dark:border-white/5">
                  <p class="text-[9px] font-black uppercase tracking-[0.2em] text-amber-400 mb-3">偏差分析</p>
                  <p class="text-sm text-text-primary leading-relaxed">{{ ending.deviationAnalysis }}</p>
                </div>
                <div v-if="ending.unexploredBranches?.length" class="p-6 rounded-[28px] bg-purple-500/[0.04] border border-purple-400/15">
                  <p class="text-[9px] font-black uppercase tracking-[0.2em] text-purple-400 mb-3">未探索的分支</p>
                  <ul class="space-y-2">
                    <li v-for="(branch, bi) in ending.unexploredBranches" :key="bi" class="text-sm text-text-secondary leading-relaxed">{{ branch }}</li>
                  </ul>
                </div>
                <button @click="store.restart()"
                  class="w-full h-14 rounded-2xl bg-text-primary text-surface-1 font-black text-xs uppercase tracking-[0.2em] hover:shadow-2xl transition-all active:scale-[0.98]">
                  再来一局
                </button>
              </div>
            </div>

          </div>
        </transition>
      </main>
    </div>
  </div>
</template>

<style scoped>
.ios-swap-enter-active { animation: iosIn 0.6s cubic-bezier(0.32, 0.72, 0, 1); }
.ios-swap-leave-active { animation: iosOut 0.5s cubic-bezier(0.32, 0.72, 0, 1); }

.intro-fade-enter-active { transition: all 0.8s cubic-bezier(0.16, 1, 0.3, 1); }
.intro-fade-leave-active { transition: all 0.3s ease-in; }
.intro-fade-enter-from, .intro-fade-leave-to { opacity: 0; transform: translateY(12px); }

@keyframes iosIn {
  from { opacity: 0; transform: translateX(40px) scale(0.98); filter: blur(15px); }
  to { opacity: 1; transform: translateX(0) scale(1); filter: blur(0); }
}
@keyframes iosOut {
  from { opacity: 1; transform: translateX(0); }
  to { opacity: 0; transform: translateX(-40px) scale(0.98); filter: blur(15px); }
}

.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
