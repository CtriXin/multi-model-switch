<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { 
  RotateCcw, AlertTriangle, Loader2, Shield, ChevronRight, Scale, 
  Home, Info, ChevronDown, ChevronUp, ArrowLeft, ArrowRightLeft, CheckCircle2,
  Sparkles, RefreshCw, Fingerprint, SearchCode, Target, ClipboardCheck
} from 'lucide-vue-next'
import { useMultiLifeStore } from '@/stores/multiLife'
import { listCases } from '@/features/play-modes/multi-life'

const router = useRouter()
const store = useMultiLifeStore()

const {
  caseData, processing, error, phase, currentRound, challengeRemaining, started, rounds, 
  evidenceCards, ending, streamingTexts, streamingScene, modelPicked, modelWarning,
  assignmentLabel, assignmentMode, roundStarting
} = storeToRefs(store)

const cases = listCases()
const selectedCaseId = ref<string | null>(null)
const previewCase = computed(() => cases.find(c => c.id === selectedCaseId.value))
const flippedCards = reactive<Record<string, boolean>>({})
const scrollContainer = ref<HTMLElement | null>(null)
const loadingCopy = ref('案情正在重新拼版...')
const loadingStages = [
  '案情正在重新拼版...',
  '证词的边角料还在焖煮...',
  '让下一幕先发酵一下...',
  '把矛盾重新钉回证据墙...',
]
let loadingTimer: number | null = null

function toggleCard(roundId: string, roleId: string) {
  const key = `${roundId}-${roleId}`
  flippedCards[key] = !flippedCards[key]
}

function isFlipped(roundId: string, roleId: string) {
  return flippedCards[`${roundId}-${roleId}`] || false
}

// --- Cinematic Text Flow ---
const introParagraphs = ref<string[]>([])
const introVisibleCount = ref(0)
const introDone = ref(false)

const lastRound = computed(() => rounds.value.length > 0 ? rounds.value[rounds.value.length - 1] : null)
const archivedRounds = computed(() => rounds.value.slice(0, -1).reverse())
const latestRoundHasActiveStreams = computed(() => {
  const round = lastRound.value
  if (!round) return false
  return Object.keys(streamingTexts.value).some((key) => key.startsWith(`${round.id}-`))
})
const latestSceneText = computed(() => {
  if (!lastRound.value) return ''
  if (streamingScene.value) return streamingScene.value
  if (processing.value || roundStarting.value) return ''
  return lastRound.value.scene
})
const showRoundTransition = computed(() =>
  !!lastRound.value && (roundStarting.value || (processing.value && !latestSceneText.value)),
)

const canInteractWithLatestRound = computed(() => {
  const round = lastRound.value
  if (!round) return false
  if (roundStarting.value) return false
  return round.responses.every((resp) => {
    const streamed = streamingTexts.value[`${round.id}-${resp.roleId}`] || ''
    return Boolean(streamed.trim() || resp.text.trim() || resp.status === 'error')
  })
})

async function streamIntro(text: string) {
  const paragraphs = text.split('\n').filter(p => p.trim())
  introParagraphs.value = paragraphs
  introVisibleCount.value = 0
  introDone.value = false
  await nextTick()
  for (let i = 0; i < paragraphs.length; i++) {
    introVisibleCount.value = i + 1
    await new Promise(r => setTimeout(r, 180))
  }
  introDone.value = true
}

function startLoadingTicker() {
  stopLoadingTicker()
  let idx = 0
  loadingCopy.value = loadingStages[0]
  loadingTimer = window.setInterval(() => {
    idx = (idx + 1) % loadingStages.length
    loadingCopy.value = loadingStages[idx]
  }, 1400)
}

function stopLoadingTicker() {
  if (loadingTimer == null) return
  window.clearInterval(loadingTimer)
  loadingTimer = null
}

watch(() => [phase.value, caseData.value?.id ?? ''] as const, ([nextPhase, id]) => {
  if (nextPhase === 'setup' && id && caseData.value) streamIntro(caseData.value.premise)
}, { immediate: true })

watch([processing, roundStarting], ([isProcessing, isRoundStarting]) => {
  if (isProcessing || isRoundStarting) {
    startLoadingTicker()
    return
  }
  stopLoadingTicker()
}, { immediate: true })

const ROLE_STYLES = [
  { border: 'border-cyan-400/20', bg: 'bg-cyan-500/[0.04]', accent: 'text-cyan-400', icon: Fingerprint },
  { border: 'border-rose-400/20', bg: 'bg-rose-500/[0.04]', accent: 'text-rose-400', icon: SearchCode },
  { border: 'border-amber-400/20', bg: 'bg-amber-500/[0.04]', accent: 'text-amber-400', icon: Shield },
]

onMounted(() => store.init())
onUnmounted(() => {
  stopLoadingTicker()
})
function goBack() { router.push('/lab') }
function handleSelectCase(caseId: string) { selectedCaseId.value = caseId }
function handleConfirmCase() { if (selectedCaseId.value) store.selectCase(selectedCaseId.value) }
function handleBackToSelection() { selectedCaseId.value = null }
function handleAccept() { store.acceptRound() }
function handleChallenge(roleId: string) { 
  store.challengeRole(roleId)
  const roundId = lastRound.value?.id
  if (roundId) setTimeout(() => { flippedCards[`${roundId}-${roleId}`] = true }, 1000)
}

// AUTO-SCROLL TO TOP ON NEXT ROUND
async function handleNextRound() { 
  await store.startRound()
  await nextTick()
  if (scrollContainer.value) {
    scrollContainer.value.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

function handleBegin() {
  if (!modelPicked.value) store.pickRandomModels()
  store.startRound()
}

function handleGenerateEnding() {
  store.generateEnding()
}
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-surface-0">
    
    <!-- Unified Header -->
    <div class="z-40 px-4 pt-2 sm:pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-2">
          <button @click="goBack" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors" title="返回实验室"><ArrowLeft :size="18" stroke-width="3.5" /></button>
          <div class="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center shadow-lg shadow-accent/10"><Shield :size="14" stroke-width="4" class="text-accent" /></div>
          <div class="min-w-0"><h1 class="text-sm font-black text-text-primary truncate uppercase">多重人生</h1></div>
        </div>
        <div class="flex items-center gap-1.5 sm:gap-2">
          <div v-if="started" class="flex sm:hidden items-center justify-center min-w-7 h-7 px-2 rounded-full bg-accent/10 text-[10px] font-black text-accent">{{ challengeRemaining }}</div>
          <div v-if="started" class="hidden sm:flex items-center gap-1 px-2.5 py-1 rounded-full bg-accent/10 text-[8px] font-black text-accent uppercase tracking-widest"><Scale :size="10" stroke-width="4" /> {{ challengeRemaining }}</div>
          <div v-if="modelPicked" class="hidden sm:flex items-center gap-1 px-2.5 py-1 rounded-full text-[8px] font-black uppercase tracking-widest"
            :class="assignmentMode === 'live' ? 'bg-emerald-500/10 text-emerald-500' : assignmentMode === 'demo' ? 'bg-amber-500/10 text-amber-500' : 'bg-white/10 text-text-tertiary'">
            {{ assignmentLabel }}
          </div>
          <button v-if="started || caseData" @click="store.restart()" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all"><RotateCcw :size="18" stroke-width="3.5" /></button>
        </div>
      </header>
    </div>

    <main class="flex-1 relative overflow-hidden flex flex-col p-3 sm:p-4 lg:p-6">
      <div class="w-full max-w-5xl mx-auto flex-1 flex flex-col glass-v3 rounded-[32px] lg:rounded-[40px] shadow-2xl border border-white/10 overflow-hidden bg-white/95 dark:bg-white/[0.03] relative z-10">
        
        
          <div :key="phase" class="flex-1 flex flex-col overflow-hidden relative">

            <!-- Phase: Case Selection -->
            <div v-if="phase === 'setup' && !caseData && !selectedCaseId" class="flex-1 flex flex-col overflow-hidden">
              <div class="flex-1 overflow-y-auto custom-scrollbar px-6 py-8 sm:px-10 sm:py-10">
                <div class="max-w-4xl mx-auto space-y-8">
                  <div class="text-center space-y-2">
                    <h2 class="text-3xl font-black text-text-primary uppercase tracking-tight">多重人生</h2>
                    <p class="text-sm text-text-tertiary opacity-60">谎言与真相交织。找出矛盾，还原当晚。</p>
                    <p class="text-xs text-text-quaternary">共 {{ cases.length }} 个案件可选</p>
                  </div>

                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <button
                      v-for="c in cases"
                      :key="c.id"
                      @click="handleSelectCase(c.id)"
                      class="group text-left p-5 rounded-[24px] border border-white/10 bg-white/50 hover:bg-white hover:border-accent/30 transition-all duration-300 shadow-sm hover:shadow-xl"
                    >
                      <div class="flex items-start justify-between mb-3">
                        <h3 class="text-sm font-black text-text-primary uppercase tracking-tight group-hover:text-accent transition-colors">{{ c.title }}</h3>
                        <span class="text-[9px] font-black text-text-quaternary uppercase tracking-widest opacity-40">{{ c.totalRounds }} 轮</span>
                      </div>
                      <p class="text-xs text-text-secondary leading-relaxed line-clamp-2 opacity-70">{{ c.premise }}</p>
                      <div class="mt-4 flex items-center gap-2">
                        <div class="flex -space-x-1">
                          <div v-for="(role, i) in c.roles.slice(0, 3)" :key="role.id" class="w-6 h-6 rounded-full bg-surface-1 border border-white/10 flex items-center justify-center text-[8px] font-black text-text-tertiary">{{ role.name.charAt(0) }}</div>
                        </div>
                        <span class="text-[9px] text-text-quaternary">{{ c.roles.length }} 个角色</span>
                      </div>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Phase: Case Detail Preview -->
            <div v-else-if="phase === 'setup' && !caseData && selectedCaseId" class="flex-1 flex flex-col overflow-hidden"
            >
              <div class="flex-1 overflow-y-auto custom-scrollbar px-6 py-8 sm:px-10 sm:py-10">
                <div class="max-w-2xl mx-auto space-y-8" v-if="previewCase">
                  <div class="text-center space-y-2">
                    <span class="text-[10px] font-black uppercase tracking-widest text-text-quaternary">案件预览</span>
                    <h2 class="text-3xl font-black text-text-primary uppercase tracking-tight">{{ previewCase.title }}</h2>
                  </div>

                  <div class="p-8 rounded-[40px] bg-accent/5 border border-accent/10 text-base text-text-primary leading-loose shadow-inner">
                    <p class="italic opacity-80">{{ previewCase.premise }}</p>
                  </div>

                  <div class="space-y-3">
                    <h3 class="text-[10px] font-black uppercase tracking-widest text-text-quaternary px-2">涉案角色</h3>
                    <div class="grid grid-cols-1 gap-3">
                      <div v-for="(role, idx) in previewCase.roles" :key="role.id" class="p-4 rounded-[24px] border border-white/10 bg-white/50 flex items-center gap-4">
                        <div class="w-10 h-10 rounded-2xl bg-white/5 flex items-center justify-center shadow-inner" :class="ROLE_STYLES[idx].accent">
                          <component :is="ROLE_STYLES[idx].icon" :size="18" stroke-width="3.5" />
                        </div>
                        <div>
                          <p class="text-sm font-black text-text-primary">{{ role.name }}</p>
                          <p class="text-[10px] text-text-tertiary line-clamp-1">{{ role.personality.slice(0, 40) }}...</p>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div class="flex items-center justify-center gap-6 text-center">
                    <div>
                      <div class="text-2xl font-black text-text-primary">{{ previewCase.totalRounds }}</div>
                      <div class="text-[9px] font-black uppercase tracking-widest text-text-quaternary">调查轮次</div>
                    </div>
                    <div class="w-px h-8 bg-white/10"></div>
                    <div>
                      <div class="text-2xl font-black text-accent">{{ previewCase.challengeBudget }}</div>
                      <div class="text-[9px] font-black uppercase tracking-widest text-text-quaternary">质疑次数</div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="p-6 bg-white/90 dark:bg-white/[0.05] backdrop-blur-2xl border-t border-white/10">
                <div class="max-w-md mx-auto space-y-3">
                  <button @click="handleConfirmCase" class="w-full h-14 rounded-2xl bg-accent text-white font-black tracking-widest text-[11px] active:scale-95 shadow-xl transition-all">确认选择此案件</button>
                  <button @click="handleBackToSelection" class="w-full h-12 rounded-2xl border border-white/10 text-text-tertiary font-black tracking-widest text-[11px] active:scale-95 transition-all hover:bg-white/5">返回案件列表</button>
                </div>
              </div>
            </div>

            <!-- Phase: Case Detail -->
            <div v-else-if="phase === 'setup' && caseData" class="flex-1 flex flex-col overflow-hidden relative">
              <div class="flex-1 overflow-y-auto custom-scrollbar px-6 pt-10 pb-60">
                <div class="max-w-2xl mx-auto space-y-10">
                  <div class="text-center space-y-6">
                    <h2 class="text-3xl font-black text-text-primary uppercase tracking-tight">{{ caseData.title }}</h2>
                    <div class="p-8 rounded-[40px] bg-accent/5 border border-accent/10 text-base text-text-primary leading-loose shadow-inner min-h-[10em] text-left">
                      <p v-for="(p, pi) in introParagraphs" :key="pi" class="mb-4 last:mb-0 transition-all duration-700" :class="pi < introVisibleCount ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'">{{ p }}</p>
                      <span v-if="!introDone && introVisibleCount > 0" class="inline-block w-1.5 h-4 bg-accent animate-pulse align-middle" />
                    </div>
                  </div>
                  <div v-if="introDone" class="grid grid-cols-1 gap-3 animate-in fade-in duration-1000">
                    <div v-if="modelPicked || modelWarning" class="p-4 rounded-[24px] border border-white/10 bg-white/70 text-left shadow-sm">
                      <div class="flex items-center justify-between gap-3">
                        <span class="text-[10px] font-black uppercase tracking-widest"
                          :class="assignmentMode === 'live' ? 'text-emerald-500' : assignmentMode === 'demo' ? 'text-amber-500' : 'text-text-tertiary'">
                          {{ assignmentLabel }}
                        </span>
                        <span v-if="modelWarning" class="text-[10px] text-amber-500 font-medium">{{ modelWarning }}</span>
                      </div>
                    </div>
                    <div v-for="(role, idx) in caseData.roles" :key="role.id" class="p-5 rounded-[32px] border border-white/5 bg-white shadow-sm flex items-center justify-between" :class="ROLE_STYLES[idx].border">
                      <div class="flex items-center gap-4">
                        <div class="w-10 h-10 rounded-2xl bg-white/5 flex items-center justify-center shadow-inner" :class="ROLE_STYLES[idx].accent"><component :is="ROLE_STYLES[idx].icon" :size="20" stroke-width="3.5" /></div>
                        <div>
                          <p class="text-sm font-black text-text-primary uppercase">{{ role.name }}</p>
                          <p v-if="modelPicked" class="text-[10px] text-text-tertiary font-medium">代理 AI: {{ store.getAssignedModelName(role.id) }}</p>
                        </div>
                      </div>
                      <div v-if="modelPicked" class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></div>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="introDone" class="absolute bottom-0 left-0 right-0 p-6 bg-white/90 dark:bg-white/[0.05] backdrop-blur-2xl border-t border-white/10">
                <div class="max-w-md mx-auto space-y-3">
                  <button @click="store.pickRandomModels()" class="w-full h-14 rounded-2xl border-2 border-accent/20 text-accent font-black tracking-widest text-[11px] active:scale-95 transition-all flex items-center justify-center gap-3">随机分配</button>
                  <button @click="handleBegin" class="w-full h-14 rounded-2xl bg-accent text-white font-black tracking-widest text-[11px] active:scale-95 shadow-xl flex items-center justify-center gap-3 transition-all">开始调查</button>
                  <button @click="handleBackToSelection" class="w-full h-12 rounded-2xl border border-white/10 text-text-tertiary font-black tracking-widest text-[11px] active:scale-95 transition-all hover:bg-white/5">返回案件列表</button>
                </div>
              </div>
            </div>

            <!-- Phase: Investigation -->
            <div v-else-if="(phase === 'investigation' || phase === 'resolution') && started" class="flex-1 flex flex-col overflow-hidden relative">
              <div ref="scrollContainer" class="flex-1 overflow-y-auto custom-scrollbar px-4 sm:px-8 py-6 space-y-10 scroll-smooth pb-60">
                <div v-if="archivedRounds.length" class="space-y-4 animate-in fade-in slide-in-from-top-2 duration-500">
                  <div class="flex items-center gap-2 px-2 opacity-50">
                    <div class="w-1 h-1 rounded-full bg-text-primary" />
                    <span class="text-[10px] font-black uppercase tracking-[0.2em] text-text-tertiary">前情档案</span>
                  </div>
                  <div class="relative px-2 pt-4 pb-2">
                    <article
                      v-for="(r, idx) in archivedRounds.slice(0, 3)"
                      :key="`archive-${r.id}`"
                      class="relative rounded-[28px] border border-white/10 bg-white/80 shadow-sm backdrop-blur-md p-4 sm:p-5"
                      :style="{
                        transform: `translateY(${idx * 16}px) rotate(${idx % 2 === 0 ? -1.2 : 1.2}deg) scale(${1 - idx * 0.03})`,
                        zIndex: String(30 - idx),
                        marginBottom: idx === archivedRounds.slice(0, 3).length - 1 ? `${idx * 16}px` : '0px',
                      }"
                    >
                      <div class="flex items-center justify-between gap-3">
                        <span class="text-[10px] font-black uppercase tracking-[0.2em] text-text-tertiary">回合 R{{ r.roundNumber }}</span>
                        <span class="text-[9px] text-text-quaternary truncate">
                          {{ r.playerChoice?.type === 'challenge' ? '已质疑角色' : r.playerChoice ? '已锁定版本' : '处理中' }}
                        </span>
                      </div>
                      <p class="mt-3 text-xs leading-relaxed text-text-secondary line-clamp-3">
                        {{ r.scene }}
                      </p>
                    </article>
                  </div>
                </div>

                <div v-if="lastRound" :key="lastRound.id" class="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
                  <div class="p-6 rounded-[32px] bg-accent/5 border border-accent/10 space-y-4 shadow-sm relative min-h-[148px]">
                    <div class="flex items-center justify-between">
                      <span class="text-[10px] font-black text-text-tertiary uppercase tracking-[0.2em]">回合 R{{ lastRound.roundNumber }}</span>
                      <div v-if="lastRound.contradictions.length && !showRoundTransition" class="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-amber-500/10 text-[8px] font-black text-amber-500 uppercase tracking-widest animate-pulse"><AlertTriangle :size="10" /> 发现核心疑点</div>
                    </div>
                    <div v-if="showRoundTransition" class="min-h-[88px] flex flex-col justify-center gap-3">
                      <div class="flex items-center gap-2 text-accent">
                        <span class="w-2 h-2 rounded-full bg-current animate-pulse" />
                        <span class="w-2 h-2 rounded-full bg-current animate-pulse" style="animation-delay:.2s" />
                        <span class="w-2 h-2 rounded-full bg-current animate-pulse" style="animation-delay:.4s" />
                      </div>
                      <p class="text-sm font-black tracking-[0.14em] uppercase text-accent">{{ loadingCopy }}</p>
                      <p class="text-xs text-text-tertiary">上一回合已归档，正在抬出新证词与新场景。</p>
                    </div>
                    <p v-else class="text-sm leading-relaxed text-text-primary italic opacity-90 whitespace-pre-wrap">{{ latestSceneText }}</p>
                  </div>

                  <div class="grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
                    <div v-for="(resp, idx) in lastRound.responses" :key="resp.roleId" class="group relative perspective-1000">
                      <div class="relative w-full transition-all duration-700 preserve-3d" :class="isFlipped(lastRound.id, resp.roleId) ? 'rotate-y-180' : ''">
                        <div class="backface-hidden relative p-6 rounded-[32px] border border-white/10 bg-white shadow-sm flex flex-col h-full" :class="ROLE_STYLES[idx].border">
                          <div class="flex items-center justify-between mb-4 shrink-0">
                            <span class="text-[10px] font-black uppercase tracking-widest" :class="ROLE_STYLES[idx].accent">{{ caseData?.roles.find(rl => rl.id === resp.roleId)?.name }}</span>
                            <button v-if="resp.isChallenged && resp.challengeResponse" @click="toggleCard(lastRound.id, resp.roleId)" class="p-2 rounded-xl bg-accent/10 text-accent active:scale-90 transition-all shadow-sm"><ArrowRightLeft :size="14" stroke-width="3.5" /></button>
                          </div>
                          <p class="text-[13px] text-text-secondary leading-loose whitespace-pre-wrap lab-flowing-text">{{ streamingTexts[`${lastRound.id}-${resp.roleId}`] || resp.text }}</p>
                          <div v-if="resp.isChallenged" class="mt-4 shrink-0"><div class="px-2.5 py-1 inline-block rounded-lg bg-amber-500/10 text-amber-500 text-[8px] font-black uppercase tracking-[0.2em]">已深度质疑</div></div>
                        </div>
                        <div v-if="resp.challengeResponse || streamingTexts[`${lastRound.id}-ch-${resp.roleId}`]" class="absolute inset-0 backface-hidden rotate-y-180 p-6 rounded-[32px] border border-amber-500/30 bg-amber-50 shadow-xl flex flex-col h-full overflow-hidden">
                          <div class="flex items-center justify-between mb-4 shrink-0">
                            <div class="flex items-center gap-2 text-amber-600 font-black"><CheckCircle2 :size="16" /><span class="text-[10px] uppercase tracking-widest">补充调查</span></div>
                            <button @click="toggleCard(lastRound.id, resp.roleId)" class="p-2 rounded-xl bg-amber-500/10 text-amber-600 active:scale-90 transition-all"><ArrowRightLeft :size="14" stroke-width="3.5" /></button>
                          </div>
                          <p class="text-[13px] text-text-primary leading-loose whitespace-pre-wrap lab-flowing-text">{{ streamingTexts[`${lastRound.id}-ch-${resp.roleId}`] || resp.challengeResponse }}</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Sticky Actions -->
              <div v-if="lastRound && !lastRound.playerChoice" 
                class="shrink-0 p-4 sm:p-6 border-t border-white/10 bg-white/90 backdrop-blur-2xl absolute bottom-0 left-0 right-0 shadow-2xl transition-all duration-500">
                <div class="max-w-3xl mx-auto space-y-4">
                  <button
                    @click="handleAccept"
                    :disabled="!canInteractWithLatestRound"
                    class="w-full h-14 sm:h-16 rounded-2xl bg-accent text-white shadow-xl active:scale-95 transition-all flex items-center justify-center gap-3 font-black uppercase tracking-widest text-sm disabled:opacity-45 disabled:shadow-none disabled:cursor-not-allowed"
                    :class="canInteractWithLatestRound ? 'lab-breathing-btn' : ''"
                  >
                    {{ canInteractWithLatestRound ? '接受当前版本' : '证词整理中...' }}
                  </button>
                  <div class="grid grid-cols-3 gap-2">
                    <button
                      v-for="resp in lastRound.responses"
                      :key="'ch-' + resp.roleId"
                      @click="handleChallenge(resp.roleId)"
                      :disabled="!canInteractWithLatestRound"
                      class="flex-1 h-12 rounded-xl bg-white border-2 border-black/5 text-amber-500 active:scale-95 transition-all flex items-center justify-center disabled:opacity-45 disabled:cursor-not-allowed"
                    >
                      <span class="text-[9px] font-black truncate uppercase px-1">质疑 {{ caseData?.roles.find(r => r.id === resp.roleId)?.name }}</span>
                    </button>
                  </div>
                </div>
              </div>

              <!-- Next Round or Resolution -->
              <div v-else-if="lastRound && lastRound.playerChoice" class="shrink-0 p-4 sm:p-6 border-t border-white/10 bg-white/90 absolute bottom-0 left-0 right-0">
                <button v-if="currentRound < (caseData?.totalRounds || 0)" @click="handleNextRound" :disabled="processing" class="w-full h-14 rounded-2xl bg-text-primary text-surface-1 font-black uppercase tracking-widest text-[11px] active:scale-95 disabled:opacity-40 flex items-center justify-center gap-3 shadow-xl"><span v-if="processing" class="flex items-center gap-2"><Loader2 :size="16" class="animate-spin" /> 分析中...</span><span v-else>进入下一幕</span></button>
                <button v-else @click="handleGenerateEnding" :disabled="processing" class="w-full h-14 rounded-2xl bg-emerald-500 text-white font-black uppercase tracking-widest text-[11px] active:scale-95 shadow-xl flex items-center justify-center gap-3 transition-all"><span v-if="processing" class="flex items-center gap-2"><Loader2 :size="16" class="animate-spin" /> 生成报告中...</span><span v-else>生成终局报告</span></button>
              </div>
            </div>

            <!-- Phase: Results -->
            <div v-else-if="ending" class="flex-1 overflow-y-auto custom-scrollbar px-6 py-10 animate-in zoom-in-95 duration-700">
              <div class="max-w-4xl mx-auto space-y-10 text-center">
                <div class="w-20 h-20 rounded-[32px] bg-accent/10 flex items-center justify-center mx-auto shadow-xl"><Shield :size="32" stroke-width="3.5" class="text-accent" /></div>
                <h2 class="text-4xl font-black text-text-primary uppercase tracking-tight">调查报告</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6 text-left">
                  <div class="p-8 rounded-[40px] bg-cyan-50 border border-cyan-400/10 space-y-4 shadow-sm"><span class="text-[10px] font-black text-cyan-600 uppercase tracking-widest">你的叙事版本</span><p class="text-sm leading-loose text-text-primary whitespace-pre-wrap">{{ ending.playerNarrative }}</p></div>
                  <div class="p-8 rounded-[40px] bg-emerald-50 border border-emerald-400/10 space-y-4 shadow-sm"><span class="text-[10px] font-black text-emerald-600 uppercase tracking-widest">最终真相</span><p class="text-sm leading-loose text-text-primary whitespace-pre-wrap">{{ ending.truthNarrative }}</p></div>
                </div>
                <button @click="store.restart()" class="w-full h-16 rounded-2xl bg-text-primary text-surface-1 font-black text-sm uppercase tracking-widest active:scale-95 shadow-xl">重返主案中心</button>
              </div>
            </div>

          </div>
        
      </div>
    </main>
  </div>
</template>

<style scoped>
:deep(svg) { stroke-width: 3.5px !important; }
.lab-flowing-text { animation: flowingText 0.8s cubic-bezier(0.215, 0.61, 0.355, 1) forwards; }
@keyframes flowingText { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.lab-breathing-btn:not(:disabled) { animation: breathing 2.5s ease-in-out infinite; }
@keyframes breathing { 0% { box-shadow: 0 0 0 0 rgba(110, 89, 255, 0.4); } 70% { box-shadow: 0 0 0 12px rgba(110, 89, 255, 0); } 100% { box-shadow: 0 0 0 0 rgba(110, 89, 255, 0); } }
.perspective-1000 { perspective: 1000px; }
.preserve-3d { transform-style: preserve-3d; transition: transform 0.7s cubic-bezier(0.4, 0, 0.2, 1); }
.backface-hidden { backface-visibility: hidden; }
.rotate-y-180 { transform: rotateY(180deg); }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
</style>
