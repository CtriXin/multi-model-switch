<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ArrowRight, Heart, Loader2, RotateCcw, Sparkles, Target, ArrowLeft, Zap, CheckCircle2 } from 'lucide-vue-next'
import { useStoryLiteV2Store } from '@/stores/storyLiteV2'
import { STORY_LITE_V2_ROLES } from '@/features/play-modes/story-lite-v2'
import type { StoryLiteV2RiskLevel, StoryLiteV2Role } from '@/features/play-modes/story-lite-v2/types'
import type { EndingGrade } from '@/features/play-modes/shared'

const router = useRouter()
const storyStore = useStoryLiteV2Store()

const {
  currentScene, round, processing, error, useMock, modelAssignment, isCompleted, isStarted,
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
const canUsePlaceholder = computed(() => !seedInput.value.trim())

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
  return risk === 'safe' ? '主线' : risk === 'risky' ? '关系' : '异常'
}

function riskTheme(risk: StoryLiteV2RiskLevel) {
  if (risk === 'safe') return { shell: 'border-emerald-400/20 bg-emerald-50 hover:border-emerald-400/40', badge: 'text-emerald-500', accent: 'bg-emerald-400' }
  if (risk === 'risky') return { shell: 'border-amber-400/20 bg-amber-50 hover:border-amber-400/40', badge: 'text-amber-500', accent: 'bg-amber-400' }
  return { shell: 'border-rose-400/20 bg-rose-50 hover:border-rose-400/40', badge: 'text-rose-500', accent: 'bg-rose-400' }
}

async function startGame() { 
  if (!seedInput.value.trim()) seedInput.value = currentPlaceholder.value
  storyStore.init(seedInput.value); await storyStore.startGame() 
}
async function startCurrentPlaceholder() {
  seedInput.value = currentPlaceholder.value
  await startGame()
}
async function makeChoice(choiceId: string) { await storyStore.makeChoice(choiceId) }
function restartGame() { storyStore.restart(); seedInput.value = '' }
function goBack() { router.push('/lab') }

onMounted(() => { storyStore.init(seedInput.value); cyclePlaceholder() })
onUnmounted(() => { if (placeholderTimer) clearInterval(placeholderTimer) })
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-surface-0">
    
    <!-- Unified V3 Capsule Header -->
    <div class="z-40 px-4 pt-2 sm:pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-2">
          <button @click="goBack" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors" title="返回实验室"><ArrowLeft :size="18" stroke-width="3.5" /></button>
          <div class="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center shadow-lg shadow-accent/10"><Sparkles :size="14" stroke-width="4" class="text-accent" /></div>
          <h1 class="text-sm font-black text-text-primary truncate uppercase tracking-tight">假如模拟器</h1>
        </div>
        <div class="flex items-center gap-2">
          <button v-if="gameStarted" @click="restartGame" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all"><RotateCcw :size="18" stroke-width="3.5" /></button>
        </div>
      </header>
    </div>

    <main class="flex-1 relative overflow-hidden flex flex-col p-3 sm:p-4 lg:p-6">
      <div class="w-full max-w-6xl mx-auto flex-1 flex flex-col glass-v3 rounded-[32px] lg:rounded-[40px] shadow-2xl border border-white/10 overflow-hidden bg-white/95 dark:bg-white/[0.03] relative z-10">
        
        <!-- MAIN CONTENT AREA -->
        <div class="flex-1 flex flex-col lg:flex-row overflow-hidden">
          
          <!-- Narrative Section -->
          <div class="flex flex-col border-white/5 lg:border-r overflow-hidden transition-all duration-700" 
            :class="[
              gameStarted ? 'h-[55%] lg:h-full lg:flex-[1.5]' : 'h-full flex-1'
            ]">
            <div class="flex-1 px-6 py-6 overflow-y-auto custom-scrollbar">
              
              <!-- SETUP VIEW -->
              <div v-if="!gameStarted" class="flex flex-col items-center justify-center h-full max-w-lg mx-auto space-y-6 animate-in zoom-in-95 duration-700">
                <div class="text-center space-y-2">
                  <h2 class="text-2xl font-black text-text-primary uppercase tracking-tight">设定开场</h2>
                  <p class="text-[11px] text-text-tertiary opacity-60">输入一个高压两难，让 AI 把命运往不同方向撕扯</p>
                </div>

                <div v-if="modelAssignment" class="w-full p-4 rounded-[24px] bg-accent/5 border border-accent/10 flex items-center gap-3">
                  <div class="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center text-accent"><Zap :size="14" stroke-width="4" /></div>
                  <div class="min-w-0 flex-1">
                    <p class="text-[10px] font-black text-text-primary uppercase leading-none">模型就绪</p>
                    <p class="text-[9px] text-text-tertiary truncate opacity-60 mt-1">已分配 3 位决策框架 AI</p>
                  </div>
                  <CheckCircle2 :size="14" class="text-emerald-500" />
                </div>

                <div class="w-full space-y-4">
                  <textarea v-model="seedInput" rows="4" :placeholder="currentPlaceholder" class="w-full rounded-[32px] bg-white border-2 border-black/5 p-6 text-sm leading-relaxed outline-none focus:border-accent/40 shadow-sm transition-all" @keydown.enter.prevent="startGame" />
                  <button
                    v-if="canUsePlaceholder"
                    @click="startCurrentPlaceholder"
                    :disabled="processing"
                    class="w-full rounded-[24px] border border-accent/15 bg-accent/[0.04] px-5 py-4 text-left transition-all hover:border-accent/30 hover:bg-accent/[0.06] active:scale-[0.99]"
                  >
                    <div class="flex items-center justify-between gap-3">
                      <div class="min-w-0">
                        <p class="text-[10px] font-black uppercase tracking-widest text-accent">直接试试当前示例</p>
                        <p class="mt-1 text-sm leading-relaxed text-text-secondary">{{ currentPlaceholder }}</p>
                      </div>
                      <div class="w-9 h-9 rounded-2xl bg-accent text-white flex items-center justify-center shrink-0 shadow-lg shadow-accent/20">
                        <ArrowRight :size="16" stroke-width="4" />
                      </div>
                    </div>
                  </button>
                  <button @click="startGame" :disabled="processing" class="w-full h-14 rounded-2xl bg-accent text-white font-black uppercase tracking-widest text-[11px] active:scale-95 lab-breathing-btn shadow-lg transition-all">开启时空裂痕</button>
                </div>
              </div>

              <!-- PLAYING VIEW -->
              <template v-else>
                <div v-if="currentScene?.premise" class="mb-10 space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-700">
                  <div class="flex items-center gap-2"><div class="w-1 h-4 bg-accent rounded-full" /><span class="text-[10px] font-black uppercase tracking-widest text-text-tertiary">场景描述</span></div>
                  <p class="text-base leading-relaxed text-text-primary italic lab-flowing-text whitespace-pre-wrap">{{ currentScene.premise }}</p>
                </div>
                <div v-if="currentScene?.responses?.length" class="space-y-6">
                  <div v-for="res in currentScene.responses" :key="res.role" class="p-6 rounded-[32px] border border-white/5 bg-white shadow-sm animate-in fade-in slide-in-from-bottom-4 duration-700">
                    <div class="flex items-center gap-3 mb-4">
                      <component :is="getRoleMeta(res.role).icon === 'Target' ? Target : Heart" :size="14" stroke-width="4" :class="getRoleMeta(res.role).accent" />
                      <span class="text-[10px] font-black uppercase tracking-widest" :class="getRoleMeta(res.role).accent">{{ getRoleMeta(res.role).label }}</span>
                    </div>
                    <p class="text-sm leading-relaxed text-text-secondary lab-flowing-text whitespace-pre-wrap">{{ res.text }}</p>
                  </div>
                </div>
                <div v-if="processing" class="py-10 flex flex-col items-center gap-3 opacity-40 animate-pulse"><Loader2 :size="24" class="animate-spin text-accent" /><p class="text-[10px] font-black uppercase tracking-widest text-text-tertiary">正在构思下一幕...</p></div>
              </template>
            </div>
          </div>

          <!-- Choices Section -->
          <transition name="action-panel">
            <div v-if="gameStarted" 
              class="flex flex-col bg-accent/[0.02] backdrop-blur-sm lg:border-l border-white/10 min-h-0"
              :class="['h-[45%] lg:h-full lg:flex-1']">
              <div class="p-4 border-b border-white/10 shrink-0">
                <h3 class="text-sm font-black text-text-primary uppercase tracking-tight">命运分叉</h3>
                <p v-if="!isCompleted" class="text-[9px] text-text-tertiary mt-0.5 opacity-60">请在三条时间线中做出你的抉择</p>
              </div>
              
              <div class="flex-1 px-4 py-4 overflow-y-auto custom-scrollbar">
                <div v-if="isCompleted && resultCard" class="space-y-6 animate-in zoom-in-95 duration-700 pb-10">
                  <div class="p-8 rounded-[40px] border border-accent/20 bg-accent/5 shadow-inner text-center">
                    <div class="text-[10px] font-black uppercase tracking-widest text-accent mb-4">结局已解锁</div>
                    <h4 class="text-2xl font-black text-text-primary uppercase tracking-tight">{{ resultCard.title }}</h4>
                    <p class="mt-6 text-sm text-text-secondary leading-loose">{{ resultCard.summary }}</p>
                  </div>
                  <button @click="restartGame" class="w-full h-14 rounded-2xl bg-text-primary text-surface-1 font-black uppercase tracking-widest text-xs active:scale-95 shadow-xl">重返假如入口</button>
                </div>

                <div v-else-if="currentScene?.choices?.length" class="grid gap-3 pb-10">
                  <button v-for="choice in currentScene.choices" :key="choice.id" 
                    @click="makeChoice(choice.id)"
                    class="group relative p-4 rounded-[24px] border-2 text-left transition-all duration-500 active:scale-[0.97] hover:shadow-xl overflow-hidden"
                    :class="riskTheme(choice.risk).shell"
                  >
                    <div class="flex items-center justify-between mb-2">
                      <div class="flex items-center gap-2">
                        <div class="w-1.5 h-1.5 rounded-full" :class="riskTheme(choice.risk).accent"></div>
                        <span class="text-[9px] font-black uppercase tracking-widest" :class="riskTheme(choice.risk).badge">{{ riskLabel(choice.risk) }}</span>
                      </div>
                      <ArrowRight :size="14" stroke-width="4" class="opacity-20 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                    </div>
                    <h4 class="text-sm font-black text-text-primary leading-tight group-hover:text-accent transition-colors">{{ choice.label }}</h4>
                    <p v-if="choice.hint" class="mt-1.5 text-[9px] text-text-tertiary opacity-60 line-clamp-2">{{ choice.hint }}</p>
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

.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }
</style>
