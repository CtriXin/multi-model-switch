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
import { useProviderStore } from '@/stores/provider'
import { Soup, Lightbulb, ChevronRight, Flag, Trophy, RotateCcw, Home, Loader2, Sparkles, AlertTriangle, Play, PhoneCall, ArrowLeft } from 'lucide-vue-next'

const router = useRouter()
const store = useTurtleSoupStore()
const appStore = useAppStore()
const providerStore = useProviderStore()
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
    yes: 'text-emerald-500 dark:text-emerald-400',
    no: 'text-red-500 dark:text-red-400',
    yes_and_no: 'text-amber-500 dark:text-amber-400',
    irrelevant: 'text-zinc-500 dark:text-zinc-400',
    close: 'text-purple-500 dark:text-purple-400',
  }
  return map[tag] || 'text-zinc-500 dark:text-zinc-400'
}

function answerBody(answer: string): string {
  const cut = answer.indexOf('。')
  return cut >= 0 ? answer.slice(cut + 1).trim() : ''
}

function goBack() { router.push('/lab') }
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-surface-0">
    
    <!-- Unified Header -->
    <div class="z-40 px-4 pt-2 sm:pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2 shadow-2xl relative flex items-center justify-between border border-black/5 dark:border-white/10 bg-white/80 dark:bg-white/[0.05]">
        <div class="flex items-center gap-2">
          <button @click="goBack" class="p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/10 text-text-secondary transition-colors" title="返回实验室">
            <ArrowLeft :size="18" stroke-width="3.5" />
          </button>
          <div class="w-8 h-8 rounded-full bg-accent/10 dark:bg-accent/20 flex items-center justify-center shadow-lg shadow-accent/10">
            <Soup :size="14" stroke-width="4" class="text-accent" />
          </div>
          <h1 class="text-xs font-black text-text-primary uppercase tracking-widest">海龟汤解密</h1>
        </div>
        <div class="flex items-center gap-2">
          <button v-if="store.phase === 'playing'" @click="store.reset()" class="p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/10 text-text-secondary transition-all">
            <RotateCcw :size="18" stroke-width="3.5" />
          </button>
        </div>
      </header>
    </div>

    <main class="flex-1 relative overflow-hidden flex flex-col px-3 sm:px-6 pb-3 sm:pb-6">
      <div class="w-full max-w-4xl mx-auto flex-1 flex flex-col glass-v3 rounded-[32px] lg:rounded-[48px] shadow-2xl border border-black/5 dark:border-white/10 overflow-hidden bg-white/95 dark:bg-[#0d0f14]/90 relative z-10">
        
        <div class="flex-1 flex flex-col overflow-hidden">

          <!-- ─── Pick Puzzle ─── -->
          <div v-if="store.phase === 'pick_puzzle'" class="flex-1 overflow-y-auto custom-scrollbar px-6 py-10">
            <div class="max-w-2xl mx-auto space-y-8">
              <template v-if="!store.currentPuzzle">
                <div class="text-center space-y-2">
                  <h2 class="text-3xl font-black text-text-primary uppercase tracking-tight">离奇案件卷宗</h2>
                  <p class="text-xs text-text-tertiary opacity-60">真相往往隐藏在最不合理的细节里</p>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <button v-for="puzzle in store.puzzles" :key="puzzle.id" @click="store.selectPuzzle(puzzle)" class="group text-left p-6 rounded-[32px] bg-white dark:bg-white/[0.04] border-2 border-black/5 dark:border-white/5 hover:border-accent/30 dark:hover:border-accent/40 transition-all duration-500 shadow-sm hover:shadow-xl active:scale-95">
                    <div class="flex items-center justify-between mb-4">
                      <span class="px-2 py-0.5 rounded-lg bg-accent/10 dark:bg-accent/20 text-[8px] font-black uppercase tracking-widest text-accent">{{ CATEGORY_LABELS[puzzle.category] }}</span>
                      <span class="text-[8px] font-black uppercase tracking-widest text-text-quaternary opacity-40">{{ DIFFICULTY_LABELS[puzzle.difficulty] }}</span>
                    </div>
                    <h3 class="text-lg font-black text-text-primary group-hover:text-accent transition-colors leading-tight">{{ puzzle.title }}</h3>
                    <p class="mt-3 text-xs text-text-tertiary leading-relaxed italic opacity-80 line-clamp-2">“{{ puzzle.surfaceText }}”</p>
                  </button>
                </div>
              </template>

              <template v-else>
                <div class="text-center space-y-10 py-10">
                  <div class="p-8 rounded-[40px] bg-accent/5 dark:bg-accent/10 border border-accent/10 dark:border-accent/20 italic text-lg text-text-primary leading-loose shadow-inner">
                    “{{ store.currentPuzzle.surfaceText }}”
                  </div>
                  <div class="max-w-xs mx-auto space-y-6">
                    <select v-model="modelSelectValue" class="w-full h-14 px-6 rounded-2xl bg-white dark:bg-white/[0.05] border-2 border-black/5 dark:border-white/10 text-sm font-black text-text-primary outline-none focus:border-accent/40 transition-all appearance-none text-center">
                      <option :value="null" class="dark:bg-surface-1">推荐：智能均衡模式</option>
                      <option v-for="m in store.availableModels" :key="m.id" :value="m.id" class="dark:bg-surface-1">{{ m.name }}</option>
                    </select>
                    <button @click="store.startGame()" class="w-full h-16 rounded-3xl bg-accent text-white font-black uppercase tracking-widest text-xs active:scale-95 shadow-2xl">开始解密</button>
                  </div>
                </div>
              </template>
            </div>
          </div>

          <!-- ─── Playing ─── -->
          <div v-else-if="store.phase === 'playing'" class="flex-1 flex flex-col overflow-hidden relative">
            <div class="px-6 py-4 border-b border-black/5 dark:border-white/5 bg-accent/5 dark:bg-accent/10 backdrop-blur-md">
              <p class="text-xs font-black text-text-primary leading-relaxed text-center opacity-80">
                <span class="text-accent uppercase tracking-widest mr-2">Current puzzle:</span>“{{ store.currentPuzzle?.surfaceText }}”
              </p>
            </div>
            
            <div ref="chatRef" class="flex-1 overflow-y-auto custom-scrollbar px-6 py-8 space-y-8 pb-32">
              <div v-for="(q, idx) in store.questions" :key="idx" class="space-y-6">
                <div class="flex justify-end">
                  <div class="max-w-[85%] px-6 py-4 rounded-[28px] rounded-br-md bg-accent text-white shadow-xl text-sm font-black leading-relaxed">{{ q.question }}</div>
                </div>
                <div class="flex justify-start">
                  <div class="max-w-[85%] px-6 py-4 rounded-[28px] rounded-bl-md bg-white dark:bg-white/[0.05] border-2 border-black/5 dark:border-white/5 shadow-sm">
                    <p class="text-base leading-loose font-medium">
                      <span :class="getTagColor(q.tags[0])" class="font-black mr-2 uppercase text-xs tracking-tighter">{{ TAG_LABELS[q.tags[0]] }}</span>
                      <span v-if="answerBody(q.answer)" class="text-text-primary whitespace-pre-wrap">{{ answerBody(q.answer) }}</span>
                    </p>
                  </div>
                </div>
              </div>
              <div v-if="store.processing" class="flex justify-start"><div class="px-6 py-4 rounded-full bg-white dark:bg-white/[0.05] border-2 border-black/5 dark:border-white/5 opacity-40">...</div></div>
            </div>

            <!-- ACTION POD -->
            <div class="absolute bottom-0 left-0 right-0 p-4 sm:p-6 bg-white/90 dark:bg-[#0d0f14]/90 backdrop-blur-xl border-t border-black/5 dark:border-white/5">
              <div class="relative max-w-3xl mx-auto group">
                <div class="relative flex items-center bg-white dark:bg-[#1a1d24] border-2 border-black/5 dark:border-white/10 rounded-[32px] p-1.5 shadow-xl transition-all group-focus-within:border-accent/40">
                  <input 
                    v-model="inputText" 
                    @keydown="handleKeydown" 
                    :disabled="store.processing" 
                    type="text" 
                    placeholder="向主持人提问细节..." 
                    class="flex-1 h-12 px-6 bg-transparent outline-none text-sm font-black placeholder:text-text-quaternary text-text-primary" 
                  />
                  <button 
                    @click="submitQuestion" 
                    :disabled="!inputText.trim() || store.processing" 
                    class="w-12 h-12 rounded-2xl bg-accent text-white flex items-center justify-center shadow-lg active:scale-95 disabled:opacity-20 transition-all"
                  >
                    <ChevronRight :size="24" stroke-width="4" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- ─── Result ─── -->
          <div v-else-if="store.phase === 'completed' || store.phase === 'abandoned'" class="flex-1 overflow-y-auto custom-scrollbar px-6 py-10 text-center">
            <div class="max-w-xl mx-auto space-y-10">
              <div class="w-24 h-24 rounded-[40px] bg-accent/10 flex items-center justify-center mx-auto shadow-2xl rotate-12">
                <component :is="store.result?.outcome === 'solved' ? Trophy : Flag" :size="40" stroke-width="3.5" class="text-accent" />
              </div>
              <h2 class="text-4xl font-black text-text-primary uppercase tracking-tight">{{ store.result?.outcome === 'solved' ? '案件告破' : '中途结案' }}</h2>
              <div class="p-10 rounded-[48px] bg-accent/5 dark:bg-accent/10 border border-accent/20 dark:border-accent/30 relative">
                <div class="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-accent rounded-full text-[10px] font-black text-white uppercase tracking-widest">最终真相</div>
                <p class="text-base text-text-primary leading-loose font-black whitespace-pre-wrap">{{ store.currentPuzzle?.truth }}</p>
              </div>
              <button @click="store.reset()" class="w-full h-16 rounded-3xl bg-text-primary text-surface-1 font-black text-sm uppercase tracking-widest active:scale-95 shadow-2xl transition-all">重返卷宗中心</button>
            </div>
          </div>

        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
:deep(svg) { stroke-width: 3.5px !important; }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }
</style>