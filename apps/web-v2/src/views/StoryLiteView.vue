<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ArrowRight, Heart, Loader2, RotateCcw, ShieldCheck, Sparkles, Target, ArrowLeft } from 'lucide-vue-next'
import { useStoryLiteV2Store } from '@/stores/storyLiteV2'
import { STORY_LITE_V2_DEFAULT_MAX_ROUNDS, STORY_LITE_V2_ROLES } from '@/features/play-modes/story-lite-v2'
import type { StoryLiteV2RiskLevel, StoryLiteV2Role } from '@/features/play-modes/story-lite-v2/types'
import type { EndingGrade } from '@/features/play-modes/shared'

const router = useRouter()
const storyStore = useStoryLiteV2Store()

const {
  currentScene, round, processing, error, useMock, modelAssignment, isCompleted, isStarted,
} = storeToRefs(storyStore)

const seedInput = ref('')
const gameStarted = computed(() => isStarted.value || processing.value)

// Dynamic Placeholder Logic
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
  return risk === 'safe' ? '安全' : risk === 'risky' ? '有风险' : '危险'
}

function riskTheme(risk: StoryLiteV2RiskLevel) {
  if (risk === 'safe') return { shell: 'border-emerald-400/30 bg-emerald-300/[0.08] hover:bg-emerald-300/[0.14]', badge: 'bg-emerald-300/15 text-emerald-100 border-emerald-300/30', icon: 'bg-emerald-300/15 text-emerald-100' }
  if (risk === 'risky') return { shell: 'border-amber-400/30 bg-amber-300/[0.08] hover:bg-amber-300/[0.14]', badge: 'bg-amber-300/15 text-amber-100 border-amber-300/30', icon: 'bg-amber-300/15 text-amber-100' }
  return { shell: 'border-red-400/30 bg-red-300/[0.08] hover:bg-red-300/[0.14]', badge: 'bg-red-300/15 text-red-100 border-red-300/30', icon: 'bg-red-300/15 text-red-100' }
}

async function startGame() { 
  if (!seedInput.value.trim()) {
    seedInput.value = currentPlaceholder.value
  }
  storyStore.init(seedInput.value); 
  await storyStore.startGame() 
}
async function makeChoice(choiceId: string) { await storyStore.makeChoice(choiceId) }
function restartGame() { storyStore.restart(); seedInput.value = '' }
function goBack() { router.push('/lab') }

onMounted(() => { 
  storyStore.init(seedInput.value)
  cyclePlaceholder()
})
onUnmounted(() => {
  if (placeholderTimer) clearInterval(placeholderTimer)
})
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">
    
    <!-- Unified V3 Capsule Header -->
    <div class="z-40 px-4 pt-2 sm:pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-2">
          <button @click="goBack" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors" title="返回实验室">
            <ArrowLeft :size="18" stroke-width="3.5" />
          </button>
          <div class="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center shadow-lg shadow-accent/10">
            <Sparkles :size="14" stroke-width="4" class="text-accent" />
          </div>
          <div class="min-w-0">
            <h1 class="text-sm font-black text-text-primary truncate tracking-tight uppercase">假如模拟器</h1>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button v-if="gameStarted" @click="restartGame" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all">
            <RotateCcw :size="18" stroke-width="3.5" />
          </button>
        </div>
      </header>
    </div>

    <main class="flex-1 relative overflow-hidden flex flex-col p-3 sm:p-4 lg:p-6">
      <div class="w-full max-w-6xl mx-auto flex-1 flex flex-col glass-v3 rounded-[32px] lg:rounded-[40px] shadow-2xl border border-white/10 overflow-hidden relative">
        <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(74,222,128,0.05),transparent_28%)]" />

        <div class="relative grid flex-1 overflow-hidden transition-all duration-700" :class="gameStarted ? 'lg:grid-cols-[1fr_0.9fr]' : 'lg:grid-cols-1'">
          <!-- Left: Narrative -->
          <div class="flex flex-col border-b border-white/5 lg:border-b-0 lg:border-r overflow-hidden transition-all duration-700" :class="gameStarted ? '' : 'lg:border-r-0'">
            <div class="flex-1 px-6 py-8 overflow-y-auto custom-scrollbar">
              <div v-if="!gameStarted" class="flex flex-col items-center justify-center h-full max-w-lg mx-auto space-y-8">
                <div class="w-20 h-20 rounded-[32px] bg-accent/10 flex items-center justify-center rotate-3 shadow-2xl">
                  <Sparkles :size="32" stroke-width="3.5" class="text-accent" />
                </div>
                <div class="text-center space-y-2">
                  <h2 class="text-3xl font-black text-text-primary uppercase tracking-tight">设定开场</h2>
                  <p class="text-xs text-text-tertiary opacity-60">发挥你的想象力，输入一个不可能的瞬间</p>
                </div>
                <div class="w-full space-y-4">
                  <div class="relative">
                    <textarea v-model="seedInput" rows="3" :placeholder="currentPlaceholder" class="w-full rounded-[28px] glass-v3 border border-white/10 p-6 text-sm leading-relaxed outline-none focus:border-accent/40 transition-all placeholder:transition-opacity placeholder:duration-500" @keydown.enter.prevent="startGame" />
                  </div>
                  <button @click="startGame" :disabled="processing" class="w-full h-14 rounded-2xl bg-accent text-white font-black uppercase tracking-widest text-xs active:scale-95 lab-breathing-btn shadow-lg shadow-accent/20">开启时空裂痕</button>
                </div>
              </div>

              <template v-else>
                <div v-if="currentScene?.premise" class="mb-10 space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-700">
                  <div class="flex items-center gap-2"><div class="w-1 h-4 bg-accent rounded-full" /><span class="text-[10px] font-black uppercase tracking-widest text-text-tertiary">场景描述</span></div>
                  <p class="text-base leading-relaxed text-text-primary italic lab-flowing-text opacity-90">{{ currentScene.premise }}</p>
                </div>
                <div v-if="currentScene?.responses?.length" class="space-y-6">
                  <div v-for="res in currentScene.responses" :key="res.role" class="p-6 rounded-[32px] border border-white/5 bg-white/[0.02] shadow-sm animate-in fade-in slide-in-from-bottom-4 duration-700">
                    <div class="flex items-center gap-3 mb-4">
                      <component :is="getRoleMeta(res.role).icon === 'Target' ? Target : Heart" :size="14" stroke-width="4" :class="getRoleMeta(res.role).accent" />
                      <span class="text-[10px] font-black uppercase tracking-widest" :class="getRoleMeta(res.role).accent">{{ getRoleMeta(res.role).label }}</span>
                    </div>
                    <p class="text-sm leading-relaxed text-text-secondary lab-flowing-text">{{ res.text }}</p>
                  </div>
                </div>
                <div v-if="processing" class="py-10 flex flex-col items-center gap-3 opacity-40"><Loader2 :size="24" class="animate-spin text-accent" /><p class="text-[10px] font-black uppercase tracking-widest text-text-tertiary">正在构思下一幕...</p></div>
              </template>
            </div>
          </div>

          <!-- Right: Choices (Delayed Display) -->
          <transition name="action-panel">
            <div v-if="gameStarted" class="flex flex-col bg-white/[0.02] backdrop-blur-sm transition-all duration-700">
              <div class="p-6 border-b border-white/5"><h3 class="text-lg font-black text-text-primary uppercase tracking-tight">{{ isCompleted ? '命定结局' : '下一步动作' }}</h3></div>
              <div class="flex-1 px-6 py-6 overflow-y-auto custom-scrollbar">
                <div v-if="isCompleted && resultCard" class="space-y-6 animate-in zoom-in-95 duration-700">
                  <div class="p-8 rounded-[40px] border border-accent/20 bg-accent/5 shadow-inner">
                    <div class="text-[10px] font-black uppercase tracking-widest text-accent mb-4">结局已解锁</div>
                    <h4 class="text-2xl font-black text-text-primary uppercase tracking-tight">{{ resultCard.title }}</h4>
                    <p class="mt-6 text-sm text-text-secondary leading-relaxed">{{ resultCard.summary }}</p>
                  </div>
                  <button @click="restartGame" class="w-full h-14 rounded-2xl bg-text-primary text-surface-1 font-black uppercase tracking-widest text-xs active:scale-95 shadow-xl">重返假如</button>
                </div>
                <div v-else-if="currentScene?.choices?.length" class="grid gap-4">
                  <button v-for="choice in currentScene.choices" :key="choice.id" class="group p-6 rounded-[32px] border text-left transition-all duration-300 active:scale-95 shadow-sm" :class="riskTheme(choice.risk).shell" @click="makeChoice(choice.id)">
                    <div class="flex items-center justify-between mb-4">
                      <span class="px-2 py-1 rounded-lg border text-[8px] font-black uppercase tracking-widest" :class="riskTheme(choice.risk).badge">{{ riskLabel(choice.risk) }}</span>
                    </div>
                    <div class="flex items-start gap-4">
                      <div class="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center group-hover:bg-accent group-hover:text-white transition-all shrink-0"><ArrowRight :size="18" stroke-width="3.5" /></div>
                      <div class="min-w-0"><h4 class="text-lg font-black text-text-primary uppercase tracking-tight">{{ choice.label }}</h4><p class="mt-1 text-[11px] text-text-tertiary opacity-60 truncate">{{ choice.hint }}</p></div>
                    </div>
                  </button>
                </div>
              </div>
            </div>
          </transition>
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

/* Action Panel Transition */
.action-panel-enter-active { transition: all 0.8s cubic-bezier(0.32, 0.72, 0, 1); }
.action-panel-enter-from { transform: translateX(100%); opacity: 0; }

.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }
</style>
