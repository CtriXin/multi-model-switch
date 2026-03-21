<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, inject, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { 
  ArrowRight, Heart, Loader2, RotateCcw, Sparkles, 
  Target, ArrowLeft, CheckCircle2, ChevronRight, X
} from 'lucide-vue-next'
import { useStoryLiteV2Store } from '@/stores/storyLiteV2'
import { STORY_LITE_V2_DEFAULT_MAX_ROUNDS, STORY_LITE_V2_ROLES } from '@/features/play-modes/story-lite-v2'
import type { StoryLiteV2RiskLevel, StoryLiteV2Role, StoryLiteV2Choice } from '@/features/play-modes/story-lite-v2/types'
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

// Phase control: 'reading' | 'choosing' | 'completed'
const phase = ref<'reading' | 'choosing' | 'completed'>('reading')

// When scene changes, reset to reading phase
watch(currentScene, (newScene, oldScene) => {
  if (newScene && newScene.id !== oldScene?.id) {
    phase.value = 'reading'
  }
}, { immediate: true })

// Auto-show choices when in choosing phase and choices are available
watch([phase, currentScene], ([p, scene]) => {
  if (p === 'choosing' && (!scene?.choices?.length || scene?.ending)) {
    phase.value = scene?.ending ? 'completed' : 'reading'
  }
}, { immediate: true })

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
  if (risk === 'safe') return { border: 'border-emerald-500/40', glow: 'shadow-emerald-500/20', text: 'text-emerald-500', bg: 'bg-emerald-500/5', dot: 'bg-emerald-500' }
  if (risk === 'risky') return { border: 'border-orange-500/40', glow: 'shadow-orange-500/20', text: 'text-orange-500', bg: 'bg-orange-500/5', dot: 'bg-orange-500' }
  return { border: 'border-rose-500/40', glow: 'shadow-rose-500/20', text: 'text-rose-500', bg: 'bg-rose-500/5', dot: 'bg-rose-500' }
}

async function startGame() { 
  if (!seedInput.value.trim()) seedInput.value = currentPlaceholder.value
  storyStore.init(seedInput.value); await storyStore.startGame() 
}

async function makeChoice(choiceId: string) { 
  phase.value = 'reading'
  await storyStore.makeChoice(choiceId) 
}

function restartGame() { 
  phase.value = 'reading'
  storyStore.restart(); 
  seedInput.value = '' 
}

function endStory() { 
  phase.value = 'completed'
  storyStore.endStory() 
}

function goBack() { router.push('/lab') }

// Keyboard shortcuts
function handleKeydown(e: KeyboardEvent) {
  if (!gameStarted.value || phase.value !== 'choosing') return
  
  const choices = currentScene.value?.choices
  if (!choices?.length) return
  
  if (e.key === '1' && choices[0]) makeChoice(choices[0].id)
  else if (e.key === '2' && choices[1]) makeChoice(choices[1].id)
  else if (e.key === '3' && choices[2]) makeChoice(choices[2].id)
  else if (e.key === 'Escape') phase.value = 'reading'
}

onMounted(() => { 
  storyStore.init(seedInput.value); 
  cyclePlaceholder() 
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => { 
  if (placeholderTimer) clearInterval(placeholderTimer) 
  window.removeEventListener('keydown', handleKeydown)
})
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
        
        <!-- SETUP PHASE -->
        <div v-if="!gameStarted" class="flex-1 overflow-y-auto custom-scrollbar px-6 py-8 sm:px-16 sm:py-16">
          <div class="flex flex-col items-center justify-center min-h-full max-w-lg mx-auto space-y-8 animate-in zoom-in-95 duration-700">
            <div class="text-center space-y-3">
              <h2 class="text-3xl font-black text-text-primary uppercase tracking-tight">设定命运开场</h2>
              <p class="text-xs text-text-tertiary opacity-60">让三种逻辑模型，把你的"假如"撕裂成不同结局</p>
            </div>

            <div class="w-full space-y-4">
              <div class="relative group">
                <textarea 
                  v-model="seedInput" 
                  rows="5" 
                  :placeholder="currentPlaceholder" 
                  class="w-full min-h-[160px] rounded-[36px] bg-white dark:bg-white/[0.02] border-2 border-black/5 dark:border-white/10 p-8 text-base leading-relaxed outline-none focus:border-accent/40 shadow-xl transition-all resize-none" 
                  @keydown.enter.prevent="startGame" 
                />
              </div>
              <button @click="startGame" :disabled="processing" class="w-full h-16 rounded-3xl bg-accent text-white font-black uppercase tracking-[0.2em] text-xs active:scale-95 lab-breathing-btn shadow-2xl">开启时空裂痕</button>
            </div>
          </div>
        </div>

        <!-- PLAYING PHASE -->
        <template v-else>
          <!-- Phase 1: Full Screen Reading -->
          <div v-if="phase === 'reading'" class="flex-1 flex flex-col min-h-0">
            <!-- Scrollable Content -->
            <div class="flex-1 overflow-y-auto custom-scrollbar px-6 py-8 sm:px-16 sm:py-16 relative">
              <div class="max-w-4xl mx-auto space-y-16 pb-24">
                <!-- Premise -->
                <div v-if="currentScene?.premise || streamingPremise" class="space-y-6 animate-in fade-in zoom-in-95 duration-700">
                  <div class="flex items-center gap-3 opacity-40">
                    <div class="w-1 h-1 rounded-full bg-text-primary" />
                    <span class="text-[10px] font-black uppercase tracking-[0.2em]">剧本脉络</span>
                  </div>
                  <p class="text-2xl sm:text-3xl lg:text-4xl leading-relaxed text-text-primary italic font-medium whitespace-pre-wrap lab-flowing-text">
                    {{ streamingPremise || currentScene?.premise }}
                  </p>
                </div>

                <!-- AI Responses -->
                <div v-if="currentScene?.responses?.length" class="space-y-8">
                  <div v-for="res in currentScene.responses" :key="res.role" 
                       class="relative pl-8 border-l-2 border-white/10 animate-in fade-in slide-in-from-bottom-4 duration-700"
                       :style="{ animationDelay: `${['guide', 'partner', 'variable'].indexOf(res.role) * 150}ms` }">
                    <div class="absolute -left-[5px] top-0 w-2.5 h-2.5 rounded-full border-2 border-surface-1" :class="getRoleMeta(res.role).accent.replace('text-', 'bg-')" />
                    <div class="flex items-center gap-3 mb-3">
                      <span class="text-[10px] font-black uppercase tracking-[0.3em]" :class="getRoleMeta(res.role).accent">{{ getRoleMeta(res.role).label }}决策</span>
                    </div>
                    <p class="text-base sm:text-lg leading-loose text-text-secondary whitespace-pre-wrap">{{ res.text }}</p>
                  </div>
                </div>

                <!-- Processing State -->
                <div v-if="processing" class="py-10 flex flex-col items-center gap-4 opacity-40">
                  <Loader2 :size="24" class="animate-spin text-accent" />
                  <p class="text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary">时间线坍缩中...</p>
                </div>
              </div>
            </div>

            <!-- Floating Action Button - Make Choice -->
            <div v-if="!processing && currentScene?.choices?.length && !currentScene?.ending" 
                 class="shrink-0 p-4 sm:p-6 flex flex-col items-center gap-3 bg-gradient-to-t from-surface-0 via-surface-0/95 to-transparent border-t border-white/5">
              <button @click="phase = 'choosing'" 
                      class="group relative px-8 py-4 rounded-full bg-accent text-white font-black uppercase tracking-[0.2em] text-xs shadow-2xl shadow-accent/30 active:scale-95 transition-all duration-300 hover:shadow-accent/50">
                <span class="flex items-center gap-3">
                  做出选择
                  <ArrowRight :size="16" stroke-width="4" class="group-hover:translate-x-1 transition-transform" />
                </span>
              </button>
              <button @click="endStory" class="px-4 py-1.5 rounded-full text-[8px] font-black uppercase tracking-widest text-text-quaternary opacity-30 hover:opacity-60 transition-opacity border border-black/5 dark:border-white/5">
                结束这场假如
              </button>
            </div>

            <!-- Ending Button -->
            <div v-if="!processing && currentScene?.ending" 
                 class="shrink-0 p-4 sm:p-6 flex justify-center bg-gradient-to-t from-surface-0 via-surface-0/95 to-transparent border-t border-white/5">
              <button @click="phase = 'completed'" 
                      class="px-8 py-4 rounded-full bg-text-primary text-surface-0 font-black uppercase tracking-[0.2em] text-xs shadow-2xl active:scale-95 transition-all">
                查看结局
              </button>
            </div>
          </div>

          <!-- Phase 2: Choices Panel (Slides Up) -->
          <div v-else-if="phase === 'choosing'" class="flex flex-col h-full overflow-hidden">
            <!-- Collapsed Story Preview -->
            <div class="shrink-0 px-6 py-3 sm:px-16 sm:py-4 border-b border-white/10 bg-surface-0/50 backdrop-blur-xl">
              <div class="max-w-4xl mx-auto">
                <div class="flex items-center gap-2 mb-1 opacity-40">
                  <div class="w-1 h-1 rounded-full bg-text-primary" />
                  <span class="text-[9px] font-black uppercase tracking-[0.2em]">当前情境</span>
                </div>
                <p class="text-xs sm:text-sm text-text-secondary italic line-clamp-2 leading-relaxed">
                  {{ currentScene?.premise }}
                </p>
              </div>
            </div>

            <!-- Choices Area -->
            <div class="flex-1 overflow-y-auto custom-scrollbar px-6 py-4 sm:px-16 sm:py-6">
              <div class="max-w-4xl mx-auto space-y-4 pb-20">
                <!-- Header with Risk Tags -->
                <div class="flex items-center justify-between gap-4">
                  <h3 class="text-xs font-black text-text-primary uppercase tracking-[0.3em] shrink-0">命运分叉点 · Fate Fork</h3>
                  <div class="flex items-center gap-2 shrink-0">
                    <div class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20">
                      <div class="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      <span class="text-[8px] font-black uppercase tracking-widest text-emerald-500">主线</span>
                    </div>
                    <div class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-orange-500/10 border border-orange-500/20">
                      <div class="w-1.5 h-1.5 rounded-full bg-orange-500" />
                      <span class="text-[8px] font-black uppercase tracking-widest text-orange-500">关系</span>
                    </div>
                    <div class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-rose-500/10 border border-rose-500/20">
                      <div class="w-1.5 h-1.5 rounded-full bg-rose-500" />
                      <span class="text-[8px] font-black uppercase tracking-widest text-rose-500">变数</span>
                    </div>
                    <button @click="phase = 'reading'" class="ml-2 p-2 rounded-full hover:bg-white/10 text-text-tertiary transition-colors shrink-0" title="返回阅读">
                      <X :size="16" stroke-width="3" />
                    </button>
                  </div>
                </div>

                <!-- Choice Cards - Vertical Stack -->
                <div class="space-y-3">
                  <button v-for="(choice, idx) in currentScene?.choices" :key="choice.id"
                          @click="makeChoice(choice.id)"
                          class="group w-full text-left p-5 sm:p-6 rounded-[28px] border-2 transition-all duration-300 active:scale-[0.98] hover:-translate-y-0.5 hover:shadow-xl relative"
                          :class="[riskTheme(choice.risk).border, riskTheme(choice.risk).bg, riskTheme(choice.risk).glow]"
                          :style="{ animationDelay: `${idx * 80}ms` }">
                    <!-- Top Row: Label + Risk Dot -->
                    <div class="flex items-start gap-3 mb-2">
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-1">
                          <div class="w-2 h-2 rounded-full shrink-0" :class="riskTheme(choice.risk).dot" />
                          <span class="text-[10px] font-black uppercase tracking-widest opacity-60" :class="riskTheme(choice.risk).text">{{ riskLabel(choice.risk) }}</span>
                        </div>
                        <h4 class="text-base sm:text-lg font-black text-text-primary leading-snug group-hover:text-accent transition-colors break-words">
                          {{ choice.label }}
                        </h4>
                      </div>
                      <!-- Arrow -->
                      <div class="w-9 h-9 rounded-full border-2 flex items-center justify-center shrink-0 transition-all duration-200 group-hover:bg-accent group-hover:border-accent group-hover:text-white mt-0.5"
                           :class="[riskTheme(choice.risk).border, riskTheme(choice.risk).text]">
                        <ArrowRight :size="16" stroke-width="4" class="group-hover:translate-x-0.5 transition-transform" />
                      </div>
                    </div>

                    <!-- Hint -->
                    <p class="text-xs text-text-tertiary leading-relaxed opacity-60 pl-4 break-words">
                      {{ choice.hint }}
                    </p>

                    <!-- Keyboard Hint -->
                    <div class="absolute bottom-4 left-5 sm:bottom-5 sm:left-6 opacity-0 group-hover:opacity-40 transition-opacity">
                      <span class="text-[10px] font-black text-text-tertiary">按 {{ idx + 1 }}</span>
                    </div>
                  </button>
                </div>

                <!-- End Story Option -->
                <button @click="endStory" class="w-full py-4 rounded-2xl border border-dashed border-text-quaternary/20 text-text-quaternary/40 hover:text-text-quaternary/60 hover:border-text-quaternary/40 transition-all text-[10px] font-black uppercase tracking-widest">
                  结束这场假如
                </button>

                <!-- Keyboard Shortcuts Hint -->
                <div class="flex items-center justify-center gap-4 pt-2 text-[9px] font-black uppercase tracking-widest text-text-quaternary/30">
                  <span class="flex items-center gap-1"><kbd class="px-1.5 py-0.5 rounded bg-white/5 border border-white/10">1</kbd> <kbd class="px-1.5 py-0.5 rounded bg-white/5 border border-white/10">2</kbd> <kbd class="px-1.5 py-0.5 rounded bg-white/5 border border-white/10">3</kbd> 选择</span>
                  <span class="w-1 h-1 rounded-full bg-text-quaternary/20" />
                  <span class="flex items-center gap-1"><kbd class="px-1.5 py-0.5 rounded bg-white/5 border border-white/10">Esc</kbd> 返回</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Phase 3: Completed / Ending -->
          <div v-else-if="phase === 'completed'" class="flex-1 flex flex-col items-center justify-center px-6 py-8 sm:px-16 sm:py-16 overflow-y-auto custom-scrollbar">
            <div class="max-w-2xl w-full mx-auto text-center space-y-8 animate-in zoom-in-95 duration-700">
              <!-- Result Card -->
              <div v-if="resultCard" class="p-8 sm:p-12 rounded-[48px] bg-accent/5 border border-accent/20 shadow-inner">
                <div class="text-[10px] font-black uppercase tracking-widest text-accent mb-4">
                  {{ manuallyEnded ? '假如暂歇' : '命运收束' }}
                </div>
                <h4 class="text-2xl sm:text-3xl font-black text-text-primary uppercase tracking-tight mb-6">
                  {{ resultCard.title }}
                </h4>
                <p class="text-base sm:text-lg text-text-secondary leading-loose">
                  {{ resultCard.summary }}
                </p>
                <div v-if="resultCard.highlights.length" class="mt-6 pt-6 border-t border-white/10">
                  <p v-for="(h, i) in resultCard.highlights" :key="i" class="text-sm text-text-tertiary italic">
                    {{ h }}
                  </p>
                </div>
              </div>

              <!-- Stats -->
              <div class="flex justify-center gap-8 py-4">
                <div class="text-center">
                  <div class="text-3xl font-black text-text-primary">{{ round }}</div>
                  <div class="text-[9px] font-black uppercase tracking-widest text-text-tertiary mt-1">命运轮次</div>
                </div>
                <div class="text-center">
                  <div class="text-3xl font-black text-accent">{{ manuallyEnded ? '-' : (currentScene?.ending?.kind === 'good' ? 'A' : currentScene?.ending?.kind === 'bad' ? 'C' : 'B') }}</div>
                  <div class="text-[9px] font-black uppercase tracking-widest text-text-tertiary mt-1">结局评级</div>
                </div>
              </div>

              <!-- Actions -->
              <div class="flex flex-col sm:flex-row gap-4 justify-center">
                <button @click="restartGame" class="px-8 py-4 rounded-3xl bg-text-primary text-surface-0 font-black uppercase tracking-widest text-xs active:scale-95 shadow-2xl transition-all flex items-center justify-center gap-2">
                  <RotateCcw :size="16" stroke-width="3" />
                  重返假如
                </button>
                <button @click="goBack" class="px-8 py-4 rounded-3xl border border-white/10 text-text-secondary font-black uppercase tracking-widest text-xs active:scale-95 transition-all hover:bg-white/5">
                  返回实验室
                </button>
              </div>
            </div>
          </div>
        </template>
      </div>
    </main>
  </div>
</template>

<style scoped>
:deep(svg) { stroke-width: 3.5px !important; }

.lab-flowing-text { animation: flowingText 0.8s cubic-bezier(0.215, 0.61, 0.355, 1) forwards; }
@keyframes flowingText { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

.lab-breathing-btn:not(:disabled) { animation: breathing 2.5s ease-in-out infinite; }
@keyframes breathing { 
  0% { box-shadow: 0 0 0 0 rgba(var(--color-accent-rgb, 110, 89, 255), 0.4); } 
  70% { box-shadow: 0 0 0 15px rgba(var(--color-accent-rgb, 110, 89, 255), 0); } 
  100% { box-shadow: 0 0 0 0 rgba(var(--color-accent-rgb, 110, 89, 255), 0); } 
}

.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
