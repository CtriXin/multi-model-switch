<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { Clapperboard, Heart, RotateCcw, Send, Sparkles, Target, Wand2, Loader2, ArrowLeft } from 'lucide-vue-next'
import MarkdownIt from 'markdown-it'
import { useAppStore } from '@/stores/app'
import { useStoryLiveStore } from '@/stores/storyLive'
import { useToastStore } from '@/stores/toast'
import { sanitizeModelOutput } from '@/utils/modelOutput'
import { useStoryFlow } from '@/features/play-modes/story-live/useStoryFlow'
import type { StoryLiveRole } from '@/features/play-modes/story-live'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const router = useRouter()
const appStore = useAppStore()
const toastStore = useToastStore()
const storyLiveStore = useStoryLiveStore()
const { pendingEndingText, continueStory: flowContinueStory, confirmEnding, dismissEnding } = useStoryFlow()
const transcriptRef = ref<HTMLElement | null>(null)
const premiseDraft = ref('')
const inputRef = ref<HTMLTextAreaElement | null>(null)
const inputHeight = ref(48) // min height

const { turns, draftInput, processing, started, latestDirectorCue, modelAssignment, assignmentMode, assignmentLabel } = storeToRefs(storyLiveStore)

// Auto-resize textarea
function resizeInput() {
  nextTick(() => {
    if (!inputRef.value) return
    inputRef.value.style.height = 'auto'
    const scrollHeight = inputRef.value.scrollHeight
    inputHeight.value = Math.min(144, Math.max(48, scrollHeight)) // max 144px (6 rows)
    inputRef.value.style.height = inputHeight.value + 'px'
  })
}

// Dynamic Placeholder Logic
const placeholders = [
  '输入故事开场，如：暴雨夜，门口地上的血迹...',
  '凌晨两点，住院部尽头的电话响了第三次...',
  '空屋餐桌上摆着两份热饭，却一个人都没有...',
  '假如我醒来发现在太空船里，AI 正在报警...',
  '身为最后一名机械师，正面临外神入侵...'
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

const ROLE_META = {
  logic: { label: '逻辑', accent: 'text-cyan-400', icon: Target },
  emotion: { label: '情感', accent: 'text-rose-400', icon: Heart },
}

const userInput = computed({ get: () => draftInput.value, set: (v) => { storyLiveStore.updateDraft(v); resizeInput() } })

// Watch input changes for auto-resize
watch(userInput, () => {
  resizeInput()
})
function renderMarkdown(text: string) {
  return md.render(sanitizeModelOutput(text).visibleContent || '')
}
function scrollLatest() { nextTick(() => { if (transcriptRef.value) transcriptRef.value.scrollTop = transcriptRef.value.scrollHeight }) }
function roleModelName(role: StoryLiveRole) {
  const assignment = modelAssignment.value
  if (!assignment) return ''
  return storyLiveStore.getModelName(assignment[role])
}

async function startStory() { 
  const seed = premiseDraft.value.trim() || currentPlaceholder.value
  await storyLiveStore.startStory(seed) 
}
async function continueStory() { await flowContinueStory(userInput.value) }
function restart() { storyLiveStore.restart(premiseDraft.value); premiseDraft.value = '' }
function goBack() { router.push('/lab') }

watch(() => turns.value.length, () => scrollLatest())
onMounted(async () => { await storyLiveStore.init(); storyLiveStore.markActive(); scrollLatest(); cyclePlaceholder() })
onUnmounted(() => { if (placeholderTimer) clearInterval(placeholderTimer) })
onBeforeUnmount(() => storyLiveStore.markPaused())
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">
    
    <!-- Unified V3 Capsule Header -->
    <div class="z-40 px-4 pt-2 sm:pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-2">
          <button @click="goBack" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors" title="返回实验室"><ArrowLeft :size="18" stroke-width="3.5" /></button>
          <div class="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center shadow-lg shadow-accent/10"><Clapperboard :size="14" stroke-width="4" class="text-accent" /></div>
          <h1 class="text-sm font-black text-text-primary truncate uppercase">剧情共演</h1>
        </div>
        <div class="flex items-center gap-2">
          <button v-if="started" @click="restart" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all"><RotateCcw :size="18" stroke-width="3.5" /></button>
        </div>
      </header>
    </div>

    <main class="flex-1 relative overflow-hidden flex flex-col px-3 sm:px-6 pb-3 sm:pb-6">
      <div class="w-full max-w-6xl mx-auto flex-1 flex flex-col glass-v3 rounded-[32px] lg:rounded-[48px] shadow-2xl border border-white/10 overflow-hidden bg-white/95 dark:bg-white/[0.03] relative">
        
        <div ref="transcriptRef" class="flex-1 overflow-y-auto custom-scrollbar px-6 py-8 space-y-8">
          <!-- Setup Phase -->
          <div v-if="!started" class="max-w-xl mx-auto py-10 space-y-10">
            <div class="text-center space-y-4">
              <div class="w-20 h-20 rounded-[32px] bg-accent/10 flex items-center justify-center mx-auto shadow-xl"><Clapperboard :size="32" stroke-width="3.5" class="text-accent" /></div>
              <h2 class="text-3xl font-black text-text-primary uppercase tracking-tight">开启你的剧本</h2>
              <p class="text-sm text-text-tertiary opacity-60">实时接戏，与导演组共同推进剧情</p>
              <div class="flex flex-wrap items-center justify-center gap-2 text-[10px] font-black uppercase tracking-widest">
                <span class="px-2.5 py-1 rounded-full border" :class="assignmentMode === 'live' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-500' : assignmentMode === 'demo' ? 'border-amber-500/20 bg-amber-500/10 text-amber-500' : 'border-white/10 bg-white/5 text-text-tertiary'">
                  {{ assignmentLabel }}
                </span>
                <span v-if="modelAssignment" class="text-text-tertiary normal-case tracking-normal">
                  逻辑 {{ roleModelName('logic') }} / 情感 {{ roleModelName('emotion') }} / 异动 {{ roleModelName('twist') }}
                </span>
              </div>
            </div>
            <div class="space-y-4">
              <textarea v-model="premiseDraft" rows="3" class="w-full rounded-[28px] glass-v3 border border-white/10 p-6 text-sm leading-relaxed outline-none focus:border-accent/40 transition-all placeholder:transition-opacity placeholder:duration-500" :placeholder="currentPlaceholder" />
              <button @click="startStory" :disabled="processing" class="w-full h-14 rounded-2xl bg-accent text-white font-black uppercase tracking-widest text-xs active:scale-95 lab-breathing-btn shadow-lg shadow-accent/20">开始共演</button>
            </div>
          </div>

          <!-- Play Phase -->
          <template v-else>
            <div v-for="turn in turns" :key="turn.id" class="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
              <div class="flex justify-end"><div class="max-w-[85%] px-6 py-4 rounded-[28px] rounded-br-md bg-accent text-white shadow-lg text-sm font-black">{{ turn.userText }}</div></div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div v-for="role in (['logic', 'emotion'] as const)" :key="role" class="p-6 rounded-[32px] border border-white/5 bg-white/[0.02] space-y-3 shadow-sm">
                  <div class="flex items-center gap-2"><component :is="ROLE_META[role].icon" :size="14" stroke-width="4" :class="ROLE_META[role].accent" /><span class="text-[10px] font-black uppercase tracking-widest" :class="ROLE_META[role].accent">{{ ROLE_META[role].label }}</span></div>
                  <div class="md-body text-sm leading-relaxed text-text-secondary lab-flowing-text" v-html="renderMarkdown(turn.responses[role].text)" />
                </div>
              </div>
            </div>
            <div v-if="processing" class="flex justify-start opacity-40 animate-pulse"><div class="px-6 py-4 rounded-full glass-v3">AI 导演组正在接戏...</div></div>
          </template>
        </div>

        <div v-if="started" class="p-4 sm:p-6 bg-white/5 border-t border-white/5 backdrop-blur-md">
          <div class="max-w-3xl mx-auto space-y-3">
            <!-- Info Tags Row -->
            <div class="flex items-center justify-between gap-2">
              <div v-if="latestDirectorCue" class="px-3 py-1.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-[10px] font-black text-cyan-500 uppercase tracking-widest">{{ latestDirectorCue }}</div>
              <div v-else class="w-px"></div>
              <div class="px-3 py-1.5 rounded-full border text-[10px] font-black uppercase tracking-widest shrink-0"
                :class="assignmentMode === 'live' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-500' : assignmentMode === 'demo' ? 'border-amber-500/20 bg-amber-500/10 text-amber-500' : 'border-white/10 bg-white/5 text-text-tertiary'">
                {{ assignmentLabel }}
              </div>
            </div>
            <div class="relative">
              <textarea 
                ref="inputRef"
                v-model="userInput" 
                :style="{ height: inputHeight + 'px' }"
                class="w-full rounded-[28px] glass-v3 border border-white/10 p-5 pr-16 text-sm leading-relaxed outline-none focus:border-accent/40 transition-all resize-none overflow-y-auto" 
                placeholder="接下去演..." 
                @keydown.enter.prevent="continueStory" 
              />
              <button @click="continueStory" :disabled="processing || !userInput.trim()" class="absolute right-3 bottom-3 w-12 h-12 rounded-2xl bg-accent text-white flex items-center justify-center shadow-lg active:scale-95 disabled:opacity-20 lab-breathing-btn"><Send :size="20" stroke-width="4" /></button>
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
</style>
