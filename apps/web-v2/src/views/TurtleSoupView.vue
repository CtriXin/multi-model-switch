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

// Model selection: sync select dropdown with store
const modelSelectValue = computed({
  get: () => store.selectedHostModelId,
  set: (val: string | null) => {
    if (val) {
      store.setModel(val)
    } else {
      // User chose "使用推荐模型" — re-auto-pick
      store.selectPuzzle(store.currentPuzzle!)
    }
  },
})

onMounted(() => {
  store.init()
})

// Auto-scroll to bottom on new messages
watch(
  () => store.questions.length,
  async () => {
    await nextTick()
    if (chatRef.value) {
      chatRef.value.scrollTop = chatRef.value.scrollHeight
    }
  },
)

function providerName(modelId: string): string {
  const m = appStore.models.find(m => m.id === modelId)
  if (!m) return ''
  const p = providerStore.getProvider(m.provider)
  return p?.name || m.provider
}

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

function getTagBadge(tag: HostTag): string {
  const map: Record<HostTag, string> = {
    yes: 'bg-emerald-500/20 text-emerald-400 ring-emerald-500/30',
    no: 'bg-red-500/20 text-red-400 ring-red-500/30',
    yes_and_no: 'bg-amber-500/20 text-amber-400 ring-amber-500/30',
    irrelevant: 'bg-zinc-500/20 text-zinc-400 ring-zinc-500/30',
    close: 'bg-purple-500/20 text-purple-400 ring-purple-500/30',
  }
  return map[tag] || 'bg-zinc-500/20 text-zinc-400 ring-zinc-500/30'
}

function answerBody(answer: string): string {
  const cut = answer.indexOf('。')
  return cut >= 0 ? answer.slice(cut + 1).trim() : ''
}
</script>

<template>
  <div class="h-full flex flex-col items-center p-3 sm:p-4 lg:p-6 overflow-hidden relative">

    <!-- Cinematic Arena Container -->
    <div class="w-full max-w-4xl flex-1 flex flex-col glass-v3 rounded-[32px] shadow-2xl border border-white/10 overflow-hidden bg-white/70 dark:bg-[#0b0b18]/80 relative z-10 transition-all duration-700 lg:rounded-[40px]">

      <!-- Content Area -->
      <main class="flex-1 relative overflow-hidden flex flex-col">
        <transition name="ios-swap" mode="out-in">
          <div :key="store.phase" class="flex-1 flex flex-col overflow-hidden">

            <!-- ─── Loading ─── -->
            <div v-if="store.phase === 'loading'" class="flex-1 flex flex-col items-center justify-center gap-6">
              <div class="relative w-12 h-12">
                <div class="absolute inset-0 rounded-full border-2 border-accent/20 animate-ping"></div>
                <div class="absolute inset-0 rounded-full border-2 border-accent/40 border-t-accent animate-spin"></div>
                <div class="absolute inset-0 flex items-center justify-center">
                  <Soup :size="20" stroke-width="3.5" class="text-accent" />
                </div>
              </div>
              <div class="text-[9px] font-black uppercase tracking-[0.4em] text-text-primary animate-pulse">初始化中</div>
            </div>

            <!-- ─── Pick Puzzle ─── -->
            <div v-else-if="store.phase === 'pick_puzzle'" class="flex-1 flex flex-col overflow-hidden">
              <div class="flex-1 overflow-y-auto px-4 sm:px-10 py-8 overscroll-contain">
                <div class="mx-auto w-full max-w-2xl">
                  <!-- No puzzle selected yet -->
                  <template v-if="!store.currentPuzzle">
                    <div class="mb-10 text-center">
                      <div class="inline-block px-3 py-1 rounded-full bg-accent/10 text-[9px] font-black text-accent uppercase tracking-[0.2em] mb-4">案件卷宗</div>
                      <h2 class="text-3xl font-black tracking-tight text-text-primary mb-3">离奇案件卷宗</h2>
                      <p class="text-sm text-text-tertiary">真相往往隐藏在最不合理的细节里</p>
                    </div>

                    <div class="grid gap-4">
                      <button
                        v-for="puzzle in store.puzzles"
                        :key="puzzle.id"
                        @click="store.selectPuzzle(puzzle)"
                        :disabled="store.completedPuzzleIds.includes(puzzle.id)"
                        class="group text-left p-6 rounded-[28px] bg-white/40 dark:bg-white/[0.03] border border-black/5 dark:border-white/5 hover:border-accent/30 hover:shadow-xl transition-all duration-500 disabled:opacity-40"
                      >
                        <div class="flex items-start justify-between gap-4">
                          <div class="flex-1 min-w-0">
                            <div class="flex items-center gap-2 mb-3">
                              <span class="px-2 py-0.5 rounded-md bg-accent/10 text-[8px] font-black uppercase tracking-widest text-accent">
                                {{ CATEGORY_LABELS[puzzle.category] }}
                              </span>
                              <span class="text-[8px] font-black uppercase tracking-widest text-text-quaternary">
                                {{ DIFFICULTY_LABELS[puzzle.difficulty] }}
                              </span>
                            </div>
                            <h3 class="text-lg font-black tracking-tight text-text-primary mb-2 group-hover:text-accent transition-colors">
                              {{ puzzle.title }}
                            </h3>
                            <p class="text-sm text-text-secondary leading-relaxed line-clamp-2 italic">
                              “{{ puzzle.surfaceText }}”
                            </p>
                          </div>
                          <div class="w-10 h-10 rounded-full bg-black/5 dark:bg-white/5 flex items-center justify-center shrink-0 group-hover:bg-accent group-hover:text-white transition-all">
                            <ChevronRight :size="18" stroke-width="4" />
                          </div>
                        </div>
                      </button>
                    </div>
                  </template>

                  <!-- Puzzle selected → model selection -->
                  <template v-else>
                    <button @click="store.currentPuzzle = null; store.selectedHostModelId = null" class="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-text-quaternary hover:text-text-primary transition-colors mb-10">
                      <RotateCcw :size="12" /> 返回选谜题
                    </button>

                    <div class="text-center mb-10">
                      <h2 class="text-2xl font-black tracking-tight text-text-primary mb-4">
                        {{ store.currentPuzzle.title }}
                      </h2>
                      <div class="p-6 rounded-[32px] bg-accent/5 border border-accent/10 italic text-sm text-text-secondary leading-loose shadow-inner">
                        “{{ store.currentPuzzle.surfaceText }}”
                      </div>
                    </div>

                    <div class="space-y-6 max-w-sm mx-auto">
                      <div>
                        <div class="flex items-center gap-2 mb-3 px-1">
                          <Sparkles :size="12" stroke-width="4" class="text-accent" />
                          <span class="text-[9px] font-black uppercase tracking-widest text-text-tertiary">主持人模型</span>
                        </div>
                        <select
                          v-model="modelSelectValue"
                          class="w-full h-12 px-4 rounded-2xl bg-white/50 dark:bg-white/[0.05] border border-black/5 dark:border-white/10 text-sm text-text-primary outline-none focus:border-accent/40 focus:ring-4 focus:ring-accent/5 transition-all appearance-none"
                        >
                          <option :value="null">推荐：智能均衡模式</option>
                          <option v-for="m in store.availableModels" :key="m.id" :value="m.id">
                            {{ m.name }}
                          </option>
                        </select>
                      </div>

                      <button
                        @click="store.startGame()"
                        :disabled="store.availableModels.length === 0"
                        class="w-full flex items-center justify-center gap-3 h-14 rounded-2xl bg-accent text-white font-black tracking-widest text-xs hover:bg-accent-hover hover:shadow-2xl hover:shadow-accent/20 transition-all active:scale-[0.98] disabled:opacity-40"
                      >
                        <Play :size="16" stroke-width="4" fill="currentColor" />
                        <span>进入现场</span>
                      </button>
                    </div>
                  </template>
                </div>
              </div>
            </div>

            <!-- ─── Playing ─── -->
            <div v-else-if="store.phase === 'playing'" class="flex-1 flex flex-col overflow-hidden">
              <!-- Sticky Case Briefing -->
              <div class="shrink-0 px-4 py-4 sm:px-8">
                <div class="mx-auto w-full max-w-2xl">
                  <div class="relative overflow-hidden p-4 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/5 dark:border-white/5">
                    <div class="flex items-center justify-between gap-4 mb-2">
                      <div class="flex items-center gap-2">
                        <div class="w-1.5 h-1.5 rounded-full bg-accent"></div>
                        <span class="text-[9px] font-black uppercase tracking-widest text-text-tertiary">{{ store.currentPuzzle?.title }}</span>
                      </div>
                      <button
                        @click="store.abandon()"
                        class="text-[8px] font-black uppercase tracking-widest text-red-400/80 hover:text-red-400 transition-colors"
                      >
                        🏳️ 放弃本案
                      </button>
                    </div>
                    <p class="text-xs text-text-secondary leading-relaxed line-clamp-2 italic opacity-80">“{{ store.currentPuzzle?.surfaceText }}”</p>
                  </div>
                </div>
              </div>

              <!-- Chat Timeline -->
              <div ref="chatRef" class="flex-1 overflow-y-auto px-4 sm:px-8 py-2 overscroll-contain scroll-smooth">
                <div class="mx-auto w-full max-w-2xl space-y-6 pb-4">
                  <div class="text-center py-4">
                    <span class="px-3 py-1 rounded-full bg-black/5 dark:bg-white/5 text-[8px] font-black text-text-quaternary uppercase tracking-widest">现场勘查开始</span>
                  </div>

                  <div v-for="(q, idx) in store.questions" :key="idx" class="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
                    <!-- User -->
                    <div class="flex justify-end">
                      <div class="max-w-[85%] px-5 py-3 rounded-[24px] rounded-br-md bg-accent text-white shadow-lg shadow-accent/10">
                        <p class="text-sm font-medium leading-relaxed">{{ q.question }}</p>
                      </div>
                    </div>
                    <!-- Host -->
                    <div class="flex justify-start">
                      <div class="max-w-[85%] px-5 py-3 rounded-[24px] rounded-bl-md bg-white dark:bg-white/[0.06] border border-black/5 dark:border-white/10 shadow-sm">
                        <div class="flex items-center gap-2 mb-2">
                          <Soup :size="10" stroke-width="4" class="text-accent" />
                          <span class="text-[8px] font-black uppercase tracking-widest text-text-tertiary">主持人</span>
                        </div>
                        <p class="text-sm leading-relaxed">
                          <span :class="getTagColor(q.tags[0])" class="font-black mr-1 animate-pulse">{{ TAG_LABELS[q.tags[0]] }}</span>
                          <span v-if="answerBody(q.answer)" class="text-text-primary lab-flowing-text">{{ answerBody(q.answer) }}</span>
                        </p>
                        <p v-if="q.guidance" class="mt-2 pl-4 text-[11px] leading-relaxed text-text-secondary/80">
                          {{ q.guidance }}
                        </p>
                      </div>
                    </div>
                  </div>

                  <!-- Hint logic -->
                  <div v-if="store.callingPhase !== 'idle'" class="flex justify-center py-4">
                    <div class="max-w-sm w-full px-5 py-4 rounded-2xl bg-accent/5 border border-accent/10 flex flex-col items-center gap-3">
                      <div class="flex items-center gap-2 text-accent">
                        <PhoneCall :size="14" :class="store.callingPhase === 'ringing' ? 'animate-bounce' : ''" />
                        <span class="text-[9px] font-black uppercase tracking-[0.2em]">场外援助</span>
                      </div>
                      <p v-if="store.currentHint" class="text-xs text-text-secondary text-center leading-relaxed italic animate-in fade-in">{{ store.currentHint }}</p>
                      <Loader2 v-else class="animate-spin text-accent/40" :size="16" />
                    </div>
                  </div>

                  <!-- Typing -->
                  <div v-if="store.processing && store.callingPhase === 'idle'" class="flex justify-start">
                    <div class="px-4 py-3 rounded-full bg-black/5 dark:bg-white/5 animate-pulse">
                      <div class="flex gap-1.5">
                        <div class="w-1 h-1 rounded-full bg-accent/60"></div>
                        <div class="w-1 h-1 rounded-full bg-accent/60"></div>
                        <div class="w-1 h-1 rounded-full bg-accent/60"></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Input Area -->
              <div class="shrink-0 px-4 py-4 sm:px-8 sm:pb-8 bg-white/20 backdrop-blur-xl border-t border-black/5 dark:border-white/5">
                <div class="mx-auto w-full max-w-2xl">
                  <div class="flex items-center gap-3">
                    <button
                      v-if="store.canAskHint"
                      @click="store.requestHint()"
                      :disabled="store.processing"
                      class="relative shrink-0 flex items-center justify-center w-12 h-12 rounded-2xl bg-white dark:bg-white/5 border border-black/5 dark:border-white/10 text-accent hover:shadow-xl transition-all active:scale-90"
                    >
                      <PhoneCall :size="20" stroke-width="3" />
                      <span class="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[9px] font-black text-white ring-4 ring-surface-0">
                        {{ Math.max(0, 3 - store.hintLevel) }}
                      </span>
                    </button>

                    <div class="flex-1 relative">
                      <input
                        v-model="inputText"
                        @keydown="handleKeydown"
                        :disabled="store.processing"
                        type="text"
                        placeholder="向 GM 提问细节..."
                        class="w-full h-12 px-5 rounded-2xl bg-white dark:bg-white/10 border border-black/5 dark:border-white/10 focus:border-accent/40 focus:ring-4 focus:ring-accent/5 outline-none transition-all text-sm"
                      />
                      <button
                        @click="submitQuestion"
                        :disabled="!inputText.trim() || store.processing"
                        class="absolute right-2 top-2 w-8 h-8 rounded-xl bg-accent text-white flex items-center justify-center shadow-lg shadow-accent/20 transition-all hover:scale-105 active:scale-95 disabled:opacity-20 lab-breathing-btn"
                      >
                        <ChevronRight :size="18" stroke-width="4" />
                      </button>
                    </div>
                  </div>
                  <div class="text-center mt-3">
                    <span class="text-[8px] font-black uppercase tracking-[0.3em] text-text-quaternary opacity-50">剩余 {{ store.remainingRounds }} 次提问机会</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- ─── Result ─── -->
            <div v-else-if="store.phase === 'completed' || store.phase === 'abandoned'" class="flex-1 overflow-y-auto px-6 py-10 overscroll-contain">
              <div class="mx-auto w-full max-w-xl text-center">
                <div class="mb-8 flex justify-center">
                  <div class="w-20 h-20 rounded-[32px] flex items-center justify-center rotate-12 shadow-2xl transition-transform hover:rotate-0 duration-700"
                    :class="store.result?.outcome === 'solved' ? 'bg-emerald-500 text-white' : 'bg-zinc-200 dark:bg-white/10 text-text-tertiary'">
                    <component :is="store.result?.outcome === 'solved' ? Trophy : Flag" :size="32" stroke-width="3.5" />
                  </div>
                </div>

                <h2 class="text-3xl font-black tracking-tight text-text-primary mb-2">
                  {{ store.result?.outcome === 'solved' ? '破案成功' : '案件结案' }}
                </h2>
                <div class="flex items-center justify-center gap-2 mb-10">
                  <span class="text-[9px] font-black uppercase tracking-widest text-text-tertiary">{{ store.result?.totalRounds }} 轮</span>
                  <div class="w-1 h-1 rounded-full bg-text-quaternary"></div>
                  <span class="text-[9px] font-black uppercase tracking-widest text-text-tertiary">{{ store.result?.hintsUsed }} 次提示</span>
                </div>

                <div class="text-left space-y-8">
                  <div class="p-8 rounded-[40px] bg-accent/5 border border-accent/10 relative">
                    <div class="absolute -top-3 left-8 px-3 py-1 bg-accent rounded-full text-[9px] font-black text-white uppercase tracking-widest">真相大白</div>
                    <p class="text-base text-text-primary leading-loose font-medium">{{ store.currentPuzzle?.truth }}</p>
                  </div>

                  <div v-if="store.recap?.keyMisleads?.length" class="space-y-4">
                    <h3 class="text-[10px] font-black uppercase tracking-[0.2em] text-text-tertiary px-2">误导项分析</h3>
                    <div v-for="m in store.recap.keyMisleads" :key="m.round" class="p-5 rounded-3xl bg-red-500/[0.03] border border-red-500/10">
                      <p class="text-sm font-bold text-red-400 mb-1">{{ m.description }}</p>
                      <p class="text-xs text-text-secondary leading-relaxed">{{ m.why }}</p>
                    </div>
                  </div>

                  <button
                    @click="store.reset()"
                    class="w-full h-14 rounded-2xl bg-text-primary text-surface-1 font-black text-xs uppercase tracking-[0.2em] hover:shadow-2xl transition-all active:scale-[0.98]"
                  >
                    重返案件中心
                  </button>
                </div>
              </div>
            </div>

          </div>
        </transition>
      </main>
    </div>
  </div>
</template>

<style scoped>
:deep(svg) { stroke-width: 3.5px !important; }

.lab-flowing-text {
  animation: flowingText 0.8s cubic-bezier(0.215, 0.61, 0.355, 1) forwards;
}

@keyframes flowingText {
  from { opacity: 0; transform: translateY(4px); filter: blur(4px); }
  to { opacity: 1; transform: translateY(0); filter: blur(0); }
}

.lab-breathing-btn:not(:disabled) {
  animation: breathing 2.5s ease-in-out infinite;
}

@keyframes breathing {
  0% { box-shadow: 0 0 0 0 rgba(110, 89, 255, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(110, 89, 255, 0); }
  100% { box-shadow: 0 0 0 0 rgba(110, 89, 255, 0); }
}

.ios-swap-enter-active { animation: iosIn 0.6s cubic-bezier(0.32, 0.72, 0, 1); }
.ios-swap-leave-active { animation: iosOut 0.5s cubic-bezier(0.32, 0.72, 0, 1); }

@keyframes iosIn {
  from { opacity: 0; transform: translateX(40px) scale(0.98); filter: blur(15px); }
  to { opacity: 1; transform: translateX(0) scale(1); filter: blur(0); }
}
@keyframes iosOut {
  from { opacity: 1; transform: translateX(0); }
  to { opacity: 0; transform: translateX(-40px) scale(0.98); filter: blur(15px); }
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>