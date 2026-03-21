<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, inject } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { 
  ArrowRight, Heart, Loader2, RotateCcw, ShieldCheck, Sparkles, 
  Target, ArrowLeft, Zap, CheckCircle2, ChevronRight, ChevronLeft
} from 'lucide-vue-next'
import { useStoryLiteV2Store } from '@/stores/storyLiteV2'
import { STORY_LITE_V2_DEFAULT_MAX_ROUNDS, STORY_LITE_V2_ROLES } from '@/features/play-modes/story-lite-v2'
import type { StoryLiteV2RiskLevel, StoryLiteV2Role } from '@/features/play-modes/story-lite-v2/types'
import type { EndingGrade } from '@/features/play-modes/shared'

const router = useRouter()
const storyStore = useStoryLiteV2Store()
const isSmallScreen = inject<import('vue').Ref<boolean>>('isSmallScreen', ref(false))

const {
  currentScene, round, processing, error, useMock, modelAssignment, isCompleted, isStarted,
  manuallyEnded, streamingPremise,
} = storeToRefs(storyStore)

const seedInput = ref('')
const gameStarted = computed(() => isStarted.value || processing.value)

// Dynamic Placeholder
const placeholders = [
  '假如我穿越到了古代，成了一名带刀侍卫...',
  '假如我醒来发现在太空船里，人工智能正在报警...',
  '假如我发现整个世界其实是一场巨大的楚门世界...',
  '假如我拥有了停止时间的能力，但每次只能停 5 秒...',
  '假如我是最后一名幸存的机械师，正面临外神入侵...'
]
const currentPlaceholder = ref(placeholders[0])
let placeholderTimer: any = null

function cyclePlaceholder() {
  let idx = 0
  placeholderTimer = setInterval(() => {
    idx = (idx + 1) % placeholders.length
    currentPlaceholder.value = placeholders[idx]
  }, 3500)
}

const resultCard = computed(() => {
  if (manuallyEnded.value && currentScene.value) {
    return {
      title: '假如暂停',
      grade: 'normal' as EndingGrade,
      summary: `你经历了 ${round.value} 轮命运抉择。最后一幕：${currentScene.value.premise}`,
      highlights: [],
    }
  }
  const ending = currentScene.value?.ending
  if (!ending) return null
  return {
    title: ending.title,
    grade: ending.kind as EndingGrade,
    summary: ending.summary,
    highlights: ending.epilogue ? [ending.epilogue] : [],
  }
})

function getRoleMeta(role: StoryLiteV2Role) { return STORY_LITE_V2_ROLES[role] }
function riskLabel(risk: StoryLiteV2RiskLevel): string {
  return risk === 'safe' ? '主线' : risk === 'risky' ? '关系' : '变数'
}

function riskTheme(risk: StoryLiteV2RiskLevel) {
  if (risk === 'safe') return { border: 'border-emerald-500/40', glow: 'shadow-emerald-500/20', text: 'text-emerald-500', bg: 'bg-emerald-500/5' }
  if (risk === 'risky') return { border: 'border-orange-500/40', glow: 'shadow-orange-500/20', text: 'text-orange-500', bg: 'bg-orange-500/5' }
  return { border: 'border-rose-500/40', glow: 'shadow-rose-500/20', text: 'text-rose-500', bg: 'bg-rose-500/5' }
}

async function startGame() { 
  if (!seedInput.value.trim()) seedInput.value = currentPlaceholder.value
  storyStore.init(seedInput.value); await storyStore.startGame() 
}
async function makeChoice(choiceId: string) { await storyStore.makeChoice(choiceId) }
function restartGame() { storyStore.restart(); seedInput.value = '' }
function endStory() { storyStore.endStory() }
function goBack() { router.push('/lab') }

onMounted(() => { storyStore.init(seedInput.value); cyclePlaceholder() })
onUnmounted(() => { if (placeholderTimer) clearInterval(placeholderTimer) })
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-surface-0">
    
    <!-- Unified Header -->
    <div class="z-40 px-4 pt-2 sm:pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-2">
          <button @click="goBack" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors" title="返回实验室"><ArrowLeft :size="18" stroke-width="3.5" /></button>
          <div class="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center shadow-lg shadow-accent/10"><Sparkles :size="14" stroke-width="4" class="text-accent" /></div>
          <h1 class="text-xs font-black text-text-primary uppercase tracking-widest">假如模拟器</h1>
        </div>
        <div class="flex items-center gap-2">
          <button v-if="gameStarted" @click="restartGame" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all"><RotateCcw :size="18" stroke-width="3.5" /></button>
        </div>
      </header>
    </div>

    <main class="flex-1 relative overflow-hidden flex flex-col p-3 sm:p-4 lg:p-6">
      <!-- MAIN STAGE -->
      <div class="w-full max-w-6xl mx-auto flex-1 flex flex-col glass-v3 rounded-[32px] lg:rounded-[48px] shadow-2xl border border-white/10 overflow-hidden relative z-10">
        
        <!-- NARRATIVE STAGE -->
        <div class="flex-1 overflow-y-auto custom-scrollbar relative px-6 py-8 sm:px-16 sm:py-16" :class="gameStarted ? 'pb-40 lg:pb-16' : ''">
          
          <!-- Setup Phase -->
          <div v-if="!gameStarted" class="flex flex-col items-center justify-center h-full max-w-lg mx-auto space-y-8 animate-in zoom-in-95 duration-700">
            <div class="text-center space-y-3">
              <h2 class="text-3xl font-black text-text-primary uppercase tracking-tight">设定命运开场</h2>
              <p class="text-xs text-text-tertiary opacity-60">让三种逻辑模型，把你的“假如”撕裂成不同结局</p>
            </div>

            <div class="w-full space-y-4">
              <div class="relative group">
                <textarea v-model="seedInput" rows="4" :placeholder="currentPlaceholder" class="w-full rounded-[36px] bg-white dark:bg-white/[0.02] border-2 border-black/5 dark:border-white/10 p-8 text-base leading-relaxed outline-none focus:border-accent/40 shadow-xl transition-all" @keydown.enter.prevent="startGame" />
              </div>
              <button @click="startGame" :disabled="processing" class="w-full h-16 rounded-3xl bg-accent text-white font-black uppercase tracking-[0.2em] text-xs active:scale-95 lab-breathing-btn shadow-2xl">开启时空裂痕</button>
            </div>
          </div>

          <!-- Playing Phase -->
          <template v-else>
            <div class="max-w-4xl mx-auto space-y-16">
              <div v-if="currentScene?.premise || streamingPremise" class="space-y-4">
                <div class="flex items-center gap-3 opacity-40"><div class="w-1 h-1 rounded-full bg-text-primary" /><span class="text-[10px] font-black uppercase tracking-[0.2em]">剧本脉络</span></div>
                <p class="text-xl sm:text-2xl leading-relaxed text-text-primary italic font-medium whitespace-pre-wrap">{{ streamingPremise || currentScene?.premise }}</p>
              </div>

              <div v-if="currentScene?.responses?.length" class="space-y-12">
                <div v-for="res in currentScene.responses" :key="res.role" class="relative pl-8 border-l border-white/10 animate-in fade-in slide-in-from-bottom-4 duration-700">
                  <div class="absolute -left-1.5 top-0 w-3 h-3 rounded-full border-2 border-surface-1" :class="getRoleMeta(res.role).accent.replace('text-', 'bg-')" />
                  <div class="flex items-center gap-3 mb-4">
                    <span class="text-[10px] font-black uppercase tracking-[0.3em]" :class="getRoleMeta(res.role).accent">{{ getRoleMeta(res.role).label }}决策</span>
                  </div>
                  <p class="text-base sm:text-lg leading-loose text-text-secondary lab-flowing-text whitespace-pre-wrap">{{ res.text }}</p>
                </div>
              </div>

              <div v-if="processing" class="py-10 flex flex-col items-center gap-4 opacity-40">
                <Loader2 :size="24" class="animate-spin text-accent" />
                <p class="text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary">时间线坍缩中...</p>
              </div>
            </div>
          </template>
        </div>

        <!-- FATE CONTROLLER -->
        
          <div v-if="gameStarted && !processing" class="shrink-0 relative z-20 border-t border-black/5 dark:border-white/10 bg-white/95 dark:bg-[#0d0f14]/95 backdrop-blur-3xl shadow-[0_-20px_50px_rgba(0,0,0,0.15)]">
            
            <!-- Result State -->
            <div v-if="isCompleted && resultCard" class="p-8 max-w-4xl mx-auto animate-in zoom-in-95 duration-700 text-center">
              <div class="p-10 rounded-[48px] bg-accent/5 border border-accent/20 shadow-inner mb-6">
                <div class="text-[10px] font-black uppercase tracking-widest text-accent mb-4">假如暂歇</div>
                <h4 class="text-3xl font-black text-text-primary uppercase tracking-tight">{{ resultCard.title }}</h4>
                <p class="mt-6 text-base text-text-secondary leading-loose">{{ resultCard.summary }}</p>
              </div>
              <button @click="restartGame" class="w-full max-w-xs h-16 rounded-3xl bg-text-primary text-surface-1 font-black uppercase tracking-widest text-xs active:scale-95 shadow-2xl transition-all">重返假如</button>
            </div>

            <!-- CHOICE CONTROLLER -->
            <template v-else-if="currentScene?.choices?.length">
              
              <!-- 1. PC VIEW: Pillars of Fate -->
              <div v-if="!isSmallScreen" class="p-8 flex flex-col gap-6">
                <div class="flex items-center justify-between px-2">
                  <h3 class="text-xs font-black text-text-primary uppercase tracking-[0.3em]">命运分叉点 · Fate Fork</h3>
                  <span class="text-[9px] font-black text-text-tertiary uppercase tracking-widest opacity-40">选择一条因果律推进剧情</span>
                </div>
                <div class="grid grid-cols-3 gap-6">
                  <button v-for="choice in currentScene.choices" :key="choice.id" 
                    @click="makeChoice(choice.id)"
                    class="group relative flex flex-col p-8 rounded-[40px] border-2 transition-all duration-500 active:scale-[0.98] hover:-translate-y-1 hover:shadow-2xl text-left bg-white dark:bg-white/[0.02]"
                    :class="[riskTheme(choice.risk).border, riskTheme(choice.risk).glow]"
                  >
                    <div class="flex items-center gap-2 mb-6">
                      <div class="w-2 h-2 rounded-full shadow-[0_0_10px_currentColor]" :class="riskTheme(choice.risk).text" />
                      <span class="text-[10px] font-black uppercase tracking-widest" :class="riskTheme(choice.risk).text">{{ riskLabel(choice.risk) }}</span>
                    </div>
                    <h4 class="text-lg font-black text-text-primary leading-tight group-hover:text-accent transition-colors flex-1 mb-4">{{ choice.label }}</h4>
                    <p class="text-[11px] text-text-tertiary leading-relaxed opacity-60">{{ choice.hint }}</p>
                    <div class="mt-8 flex justify-end"><ChevronRight :size="20" stroke-width="4" class="opacity-20 group-hover:opacity-100 group-hover:translate-x-1 transition-all" :class="riskTheme(choice.risk).text" /></div>
                  </button>
                </div>
              </div>

              <!-- 2. MOBILE VIEW: Card Deck (Optimized for Peeking) -->
              <div v-else class="flex flex-col">
                <div class="px-6 py-4 flex items-center justify-between border-b border-black/5 dark:border-white/5">
                  <h3 class="text-[10px] font-black text-text-primary uppercase tracking-[0.2em]">命运卡组</h3>
                  <span class="text-[8px] font-black text-text-tertiary uppercase tracking-widest opacity-40 italic">Slide to explore</span>
                </div>
                <!-- FIXED: snap-start + card width adjustments for peeking next card -->
                <div class="flex overflow-x-auto snap-x snap-mandatory no-scrollbar p-6 gap-4">
                  <!-- First card spacer to handle snap-start with padding correctly if needed, but snap-center is often easier for peeking -->
                  <button v-for="choice in currentScene.choices" :key="choice.id" 
                    @click="makeChoice(choice.id)"
                    class="snap-center shrink-0 w-[280px] p-6 rounded-[32px] border-2 bg-white dark:bg-white/[0.02] shadow-xl flex flex-col text-left transition-all active:scale-[0.97]"
                    :class="[riskTheme(choice.risk).border, riskTheme(choice.risk).bg]"
                  >
                    <div class="flex items-center gap-2 mb-4">
                      <div class="w-1.5 h-1.5 rounded-full" :class="riskTheme(choice.risk).text.replace('text-', 'bg-')" />
                      <span class="text-[10px] font-black uppercase tracking-widest" :class="riskTheme(choice.risk).text">{{ riskLabel(choice.risk) }}</span>
                    </div>
                    <h4 class="text-lg font-black text-text-primary leading-tight mb-3 whitespace-pre-wrap">{{ choice.label }}</h4>
                    <p class="text-xs text-text-tertiary leading-relaxed opacity-70">{{ choice.hint }}</p>
                    <div class="mt-6 flex items-center justify-between">
                      <ArrowRight :size="18" stroke-width="4" :class="riskTheme(choice.risk).text" />
                    </div>
                  </button>
                  <!-- End spacer to ensure last card can center properly -->
                  <div class="shrink-0 w-4" />
                </div>
                <div class="flex justify-center pb-4"><div class="w-12 h-1 bg-text-quaternary/10 rounded-full" /></div>
              </div>

            </template>

            <!-- END STORY BUTTON -->
            <div v-if="!isCompleted" class="flex justify-center pb-4">
              <button @click="endStory" class="px-4 py-1.5 rounded-full text-[8px] font-black uppercase tracking-widest text-text-quaternary opacity-30 hover:opacity-60 transition-opacity border border-black/5 dark:border-white/5">
                结束这场假如
              </button>
            </div>
          </div>
        

      </div>
    </main>
  </div>
</template>

<style scoped>
:deep(svg) { stroke-width: 3.5px !important; }

/* Deck Slide Animation */

.lab-flowing-text { animation: flowingText 0.8s cubic-bezier(0.215, 0.61, 0.355, 1) forwards; }
@keyframes flowingText { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

.lab-breathing-btn:not(:disabled) { animation: breathing 2.5s ease-in-out infinite; }
@keyframes breathing { 
  0% { box-shadow: 0 0 0 0 rgba(var(--color-accent-rgb, 110, 89, 255), 0.4); } 
  70% { box-shadow: 0 0 0 15px rgba(var(--color-accent-rgb, 110, 89, 255), 0); } 
  100% { box-shadow: 0 0 0 0 rgba(var(--color-accent-rgb, 110, 89, 255), 0); } 
}

.no-scrollbar::-webkit-scrollbar { display: none; }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }

.snap-x { scroll-snap-type: x mandatory; scroll-behavior: smooth; }
.snap-center { scroll-snap-align: center; }
</style>