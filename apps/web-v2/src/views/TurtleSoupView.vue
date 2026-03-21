<script setup lang="ts">
import { ref, nextTick, watch, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTurtleSoupStore } from '@/stores/turtleSoup'
import {
  CATEGORY_LABELS,
  DIFFICULTY_LABELS,
  TAG_LABELS,
} from '@/features/turtle-soup'
import type { HostTag } from '@/features/turtle-soup/types'
import { useAppStore } from '@/stores/app'
import { Soup, Lightbulb, ChevronRight, Flag, Trophy, RotateCcw, Home, Loader2, Sparkles, AlertTriangle, Play, PhoneCall, ArrowLeft } from 'lucide-vue-next'

const router = useRouter()
const store = useTurtleSoupStore()
const appStore = useAppStore()
const inputText = ref('')
const chatRef = ref<HTMLElement | null>(null)

const modelSelectValue = computed({
  get: () => store.selectedHostModelId,
  set: (val: string | null) => {
    if (val) store.setModel(val)
    else store.selectPuzzle(store.currentPuzzle!)
  },
})

onMounted(() => { store.init() })

watch(
  () => store.questions.length,
  async () => {
    await nextTick()
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
  },
)

function submitQuestion() {
  const text = inputText.value.trim()
  if (!text || store.processing) return
  inputText.value = ''
  store.askQuestion(text)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submitQuestion()
  }
}

function getTagColor(tag: HostTag): string {
  const map: Record<HostTag, string> = {
    yes: 'text-emerald-400',
    no: 'text-red-400',
    yes_and_no: 'text-amber-400',
    irrelevant: 'text-zinc-400',
    close: 'text-purple-400',
  }
  return map[tag] || 'text-zinc-400'
}

function answerBody(answer: string): string {
  const cut = answer.indexOf('。')
  return cut >= 0 ? answer.slice(cut + 1).trim() : ''
}

function runtimeLabel() {
  if (store.runtimeMode === 'live') return 'Live Host'
  if (store.runtimeMode === 'demo') return 'Mock Demo'
  return 'No Models'
}

function goBack() { router.push('/lab') }
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
            <Soup :size="14" stroke-width="4" class="text-accent" />
          </div>
          <div class="min-w-0">
            <h1 class="text-sm font-black text-text-primary truncate tracking-tight uppercase">海龟汤</h1>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button v-if="store.phase === 'playing'" @click="store.reset()" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all">
            <RotateCcw :size="18" stroke-width="3.5" />
          </button>
        </div>
      </header>
    </div>

    <main class="flex-1 relative overflow-hidden flex flex-col p-3 sm:p-4 lg:p-6">
      <div class="w-full max-w-4xl mx-auto flex-1 flex flex-col glass-v3 rounded-[32px] lg:rounded-[40px] shadow-2xl border border-white/10 overflow-hidden relative">
        
        <div class="flex-1 flex flex-col overflow-hidden">

            <!-- ─── Pick Puzzle ─── -->
            <div v-if="store.phase === 'pick_puzzle'" class="flex-1 overflow-y-auto custom-scrollbar px-6 py-10">
              <div class="max-w-2xl mx-auto space-y-8">
                <template v-if="!store.currentPuzzle">
                  <div class="text-center space-y-2">
                    <h2 class="text-3xl font-black text-text-primary uppercase tracking-tight">离奇案件卷宗</h2>
                    <p class="text-xs text-text-tertiary opacity-60">真相往往隐藏在最不合理的细节里</p>
                  </div>
                  <div class="grid gap-4">
                    <button v-for="puzzle in store.puzzles" :key="puzzle.id" @click="store.selectPuzzle(puzzle)" class="group text-left p-6 rounded-[32px] glass-v3 border border-white/5 hover:border-accent/30 transition-all duration-500 shadow-xl active:scale-95">
                      <div class="flex items-center justify-between mb-4">
                        <span class="px-2.5 py-1 rounded-lg bg-accent/10 text-[8px] font-black uppercase tracking-widest text-accent">{{ CATEGORY_LABELS[puzzle.category] }}</span>
                        <span class="text-[8px] font-black uppercase tracking-widest text-text-quaternary opacity-40">{{ DIFFICULTY_LABELS[puzzle.difficulty] }}</span>
                      </div>
                      <h3 class="text-lg font-black text-text-primary group-hover:text-accent transition-colors">{{ puzzle.title }}</h3>
                      <p class="mt-2 text-sm text-text-tertiary leading-relaxed italic opacity-80">“{{ puzzle.surfaceText }}”</p>
                    </button>
                  </div>
                </template>

                <template v-else>
                  <div class="text-center space-y-10 py-10 animate-in fade-in duration-700">
                    <div class="p-8 rounded-[40px] bg-accent/5 border border-accent/10 italic text-lg text-text-primary leading-loose shadow-inner">
                      “{{ store.currentPuzzle.surfaceText }}”
                    </div>
                    <div class="max-w-xs mx-auto space-y-6">
                      <div class="flex items-center justify-center gap-2 text-[10px] font-black uppercase tracking-widest">
                        <span class="px-2.5 py-1 rounded-full border" :class="store.runtimeMode === 'live' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-500' : 'border-amber-500/20 bg-amber-500/10 text-amber-500'">
                          {{ runtimeLabel() }}
                        </span>
                        <span v-if="store.selectedHostModel" class="text-text-tertiary normal-case tracking-normal truncate max-w-[180px]">
                          {{ store.selectedHostModel.name }}
                        </span>
                      </div>
                      <select v-model="modelSelectValue" class="w-full h-12 px-5 rounded-2xl bg-white/5 border border-white/10 text-sm text-text-primary outline-none focus:border-accent/40 focus:ring-4 focus:ring-accent/5 appearance-none">
                        <option :value="null">推荐：智能均衡模式</option>
                        <option v-for="m in store.availableModels" :key="m.id" :value="m.id">{{ m.name }}</option>
                      </select>
                      <p class="text-[11px] text-text-tertiary leading-relaxed opacity-70">
                        {{ store.runtimeMode === 'live' ? '当前会优先使用真实主持模型。' : '当前没有 live 主持模型，会走 Demo 或本地兜底。' }}
                      </p>
                      <button @click="store.startGame()" class="w-full h-14 rounded-2xl bg-accent text-white font-black uppercase tracking-widest text-xs hover:opacity-90 active:scale-95 lab-breathing-btn shadow-lg shadow-accent/20">开始解密</button>
                    </div>
                  </div>
                </template>
              </div>
            </div>

            <!-- ─── Playing ─── -->
            <div v-else-if="store.phase === 'playing'" class="flex-1 flex flex-col overflow-hidden">
              <!-- Case Briefing Visibility Improved -->
              <div class="p-5 border-b border-white/10 bg-accent/10 backdrop-blur-xl">
                <div class="space-y-2">
                  <p class="text-sm font-black text-text-primary leading-relaxed text-center drop-shadow-sm">
                    <span class="text-accent mr-2">当前谜面：</span>“{{ store.currentPuzzle?.surfaceText }}”
                  </p>
                  <div class="flex items-center justify-center gap-2 text-[10px] font-black uppercase tracking-widest">
                    <span class="px-2 py-1 rounded-full border" :class="store.runtimeMode === 'live' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-500' : 'border-amber-500/20 bg-amber-500/10 text-amber-500'">
                      {{ runtimeLabel() }}
                    </span>
                    <span v-if="store.selectedHostModel" class="text-text-tertiary normal-case tracking-normal truncate max-w-[180px]">
                      {{ store.selectedHostModel.name }}
                    </span>
                  </div>
                </div>
              </div>
              
              <div ref="chatRef" class="flex-1 overflow-y-auto custom-scrollbar px-6 py-6 space-y-6">
                <div v-for="(q, idx) in store.questions" :key="idx" class="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
                  <div class="flex justify-end">
                    <div class="max-w-[85%] px-5 py-3 rounded-[24px] rounded-br-md bg-accent text-white shadow-lg text-sm font-black">{{ q.question }}</div>
                  </div>
                  <div class="flex justify-start">
                    <div class="max-w-[85%] px-5 py-3 rounded-[24px] rounded-bl-md glass-v3 border border-white/10 shadow-sm">
                      <p class="text-sm leading-relaxed font-medium">
                        <span :class="getTagColor(q.tags[0])" class="font-black mr-2 animate-pulse uppercase">{{ TAG_LABELS[q.tags[0]] }}</span>
                        <span v-if="answerBody(q.answer)" class="text-text-primary lab-flowing-text">{{ answerBody(q.answer) }}</span>
                      </p>
                    </div>
                  </div>
                </div>
                <div v-if="store.processing" class="flex justify-start"><div class="px-4 py-3 rounded-full glass-v3 animate-pulse opacity-40">...</div></div>
              </div>

              <div class="p-6 bg-white/5 border-t border-white/5">
                <div class="relative max-w-2xl mx-auto">
                  <input v-model="inputText" @keydown="handleKeydown" :disabled="store.processing" type="text" placeholder="向主持人提问细节..." class="w-full h-14 px-6 rounded-2xl glass-v3 border border-white/10 focus:border-accent/40 outline-none transition-all text-sm font-black" />
                  <button @click="submitQuestion" :disabled="!inputText.trim() || store.processing" class="absolute right-2 top-2 w-10 h-10 rounded-xl bg-accent text-white flex items-center justify-center shadow-lg active:scale-95 disabled:opacity-20 lab-breathing-btn">
                    <ChevronRight :size="20" stroke-width="4" />
                  </button>
                </div>
              </div>
            </div>

            <!-- ─── Result ─── -->
            <div v-else-if="store.phase === 'completed' || store.phase === 'abandoned'" class="flex-1 overflow-y-auto custom-scrollbar px-6 py-10 text-center">
              <div class="max-w-xl mx-auto space-y-10 animate-in zoom-in-95 duration-700">
                <div class="w-24 h-24 rounded-[40px] bg-accent/10 flex items-center justify-center mx-auto shadow-2xl rotate-12">
                  <component :is="store.result?.outcome === 'solved' ? Trophy : Flag" :size="40" stroke-width="3.5" class="text-accent" />
                </div>
                <h2 class="text-4xl font-black text-text-primary uppercase tracking-tight">{{ store.result?.outcome === 'solved' ? '案件告破' : '中途结案' }}</h2>
                <div class="p-10 rounded-[48px] glass-v3 border border-accent/20 relative">
                  <div class="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-accent rounded-full text-[10px] font-black text-white uppercase tracking-widest">最终真相</div>
                  <p class="text-base text-text-primary leading-loose font-black">{{ store.currentPuzzle?.truth }}</p>
                </div>
                <button @click="store.reset()" class="w-full h-16 rounded-2xl bg-text-primary text-surface-1 font-black text-sm uppercase tracking-widest hover:opacity-90 active:scale-95 transition-all">重返卷宗中心</button>
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
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }
</style>
