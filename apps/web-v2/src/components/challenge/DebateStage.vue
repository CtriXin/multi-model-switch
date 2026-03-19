<script setup lang="ts">
import type { TopicCandidate, UserDebateRole, DebateMessage } from '@/features/challenge/types'
import { Loader2, Swords, User, Send, ChevronDown, ArrowRight, Scale, Quote } from 'lucide-vue-next'
import { ref, reactive, nextTick, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { sanitizeModelOutput } from '@/utils/modelOutput'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const props = defineProps<{
  topic: TopicCandidate
  messages: DebateMessage[]
  debating: boolean
  error: string | null
  userRole: UserDebateRole
  awaitingUserInput: boolean
  awaitingDecision: boolean
  currentRound: number
}>()

const emit = defineEmits<{
  submitTurn: [text: string]
  continue: []
  finish: []
}>()

const replyText = ref('')
const chatContainer = ref<HTMLElement | null>(null)

function submit() {
  if (!replyText.value.trim()) return
  emit('submitTurn', replyText.value.trim())
  replyText.value = ''
}

// Auto-scroll on new messages
watch(() => props.messages.length, async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTo({
      top: chatContainer.value.scrollHeight,
      behavior: 'smooth'
    })
  }
})

watch(() => props.messages[props.messages.length - 1]?.text, async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTo({
      top: chatContainer.value.scrollHeight,
      behavior: 'smooth'
    })
  }
})

function sideColor(side: string, isUser: boolean) {
  if (side === 'pro') return isUser ? 'border-green-500/30 bg-green-500/10 shadow-lg shadow-green-500/5' : 'border-green-500/10 bg-green-500/5'
  if (side === 'con') return isUser ? 'border-red-500/30 bg-red-500/10 shadow-lg shadow-red-500/5' : 'border-red-500/10 bg-red-500/5'
  return isUser ? 'border-amber-500/30 bg-amber-500/10 shadow-lg shadow-amber-500/5' : 'border-amber-500/10 bg-amber-500/5'
}

function sideIconColor(side: string) {
  if (side === 'pro') return 'bg-green-500 text-white'
  if (side === 'con') return 'bg-red-500 text-white'
  return 'bg-amber-500 text-white'
}

function sideTextColor(side: string) {
  if (side === 'pro') return 'text-green-600 dark:text-green-400'
  if (side === 'con') return 'text-red-600 dark:text-red-400'
  return 'text-amber-600 dark:text-amber-400'
}

function currentTurnLabel(): string {
  const roleSide = props.userRole === 'pro' ? 'pro' : props.userRole === 'con' ? 'con' : 'judge'
  if (roleSide === 'judge') return '裁判总结'
  
  const roundLabels = ['一辩', '二辩', '三辩', '四辩', '五辩', '六辩']
  const doneCount = props.messages.filter(m => m.side === roleSide && m.isUser && m.status === 'done').length
  const nextRound = doneCount + 1
  const sideLabel = roleSide === 'pro' ? '正方' : '反方'
  const roundLabel = roundLabels[nextRound - 1] || `第${nextRound}轮`
  return `${sideLabel}${roundLabel}`
}

function renderMsg(text: string): string {
  const { content } = sanitizeModelOutput(text)
  return md.render(content)
}

function getMsgMeta(text: string) {
  const { thinkText, briefText } = sanitizeModelOutput(text)
  return { thinkText, briefText }
}

function decisionHint(): string {
  if (props.userRole === 'judge') {
    return '裁判视角不走无限追辩，完成总结后直接收口。'
  }
  if (props.currentRound >= 4) {
    return '已经进入深水区了，建议准备收口；如果还有新论点，再继续一轮也可以。'
  }
  return '这一场的模型阵容会保持不变。你可以继续追辩一轮，或者现在进入总结。'
}

const expandedThink = reactive<Record<string, boolean>>({})
</script>

<template>
  <div class="flex flex-col h-full -mx-4 sm:-mx-8">
    
    <!-- Top Progress Indicator -->
    <div class="px-6 py-4 flex items-center justify-between border-b border-white/5 bg-black/[0.01] dark:bg-white/[0.01]">
       <div class="flex items-center gap-2">
         <div class="p-1.5 rounded-lg bg-accent/10 text-accent">
           <Swords :size="14" stroke-width="3" />
         </div>
         <span class="text-[10px] font-black uppercase tracking-[0.2em] text-text-secondary">Round {{ Math.max(currentRound, 1) }} Arena</span>
       </div>
       <div class="flex items-center gap-1.5">
          <div v-for="i in 5" :key="i" 
            class="w-8 h-1 rounded-full transition-all duration-500"
            :class="i <= (messages.length / 2) + 1 ? 'bg-accent shadow-[0_0_8px_rgba(var(--accent-rgb),0.5)]' : 'bg-white/10'">
          </div>
       </div>
    </div>

    <!-- Messages Waterfall -->
    <div ref="chatContainer" class="flex-1 overflow-y-auto no-scrollbar px-6 py-8 space-y-6">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="group relative flex flex-col max-w-[90%] transition-all duration-500 animate-in fade-in slide-in-from-bottom-4"
        :class="msg.isUser ? 'ml-auto items-end' : 'mr-auto items-start'"
      >
        <!-- Message Header / Role Badge -->
        <div class="flex items-center gap-2 mb-2 px-1">
          <span v-if="!msg.isUser" class="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md" :class="sideIconColor(msg.side)">
             {{ msg.side === 'pro' ? '正方' : msg.side === 'con' ? '反方' : '裁判' }}
          </span>
          <span class="text-[10px] font-bold text-text-tertiary uppercase tracking-tighter">{{ msg.label }}</span>
          <span
            v-if="!msg.isUser && msg.modelId"
            class="text-[9px] font-medium text-text-tertiary/70 truncate max-w-[120px]"
          >
            · {{ msg.modelId.split('/').pop() }}
          </span>
          <span v-if="msg.isUser" class="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md bg-white/10 text-text-primary">
            YOU
          </span>
        </div>

        <!-- Card Content -->
        <div 
          class="relative p-5 rounded-[24px] border transition-all duration-500 group-hover:shadow-2xl"
          :class="[sideColor(msg.side, msg.isUser), msg.isUser ? 'rounded-tr-none' : 'rounded-tl-none']"
        >
          <!-- Thinking / Brief Section (AI Only) -->
          <div v-if="!msg.isUser && (getMsgMeta(msg.text).thinkText || getMsgMeta(msg.text).briefText)" class="mb-4">
            <button
              @click="expandedThink[msg.id] = !expandedThink[msg.id]"
              class="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-text-tertiary hover:text-accent transition-colors group/think"
            >
              <div class="p-1 rounded bg-black/5 dark:bg-white/5 group-hover/think:bg-accent/10 transition-colors">
                <ChevronDown :size="10" stroke-width="4" class="transition-transform duration-300" :class="expandedThink[msg.id] ? '' : '-rotate-90'" />
              </div>
              <span>协议分析</span>
            </button>
            <transition name="collapse">
              <div v-if="expandedThink[msg.id]" class="mt-3 overflow-hidden">
                <div class="p-4 rounded-xl bg-black/5 dark:bg-black/20 border border-white/5 space-y-4">
                  <div v-if="getMsgMeta(msg.text).briefText">
                    <div class="text-[9px] font-black text-text-tertiary uppercase tracking-[0.2em] mb-2 flex items-center gap-2">
                      <span class="w-1.5 h-1.5 rounded-full bg-accent"></span> 简报
                    </div>
                    <div class="text-[11px] text-text-secondary leading-relaxed md-body prose-invert prose-xs" v-html="md.render(getMsgMeta(msg.text).briefText)" />
                  </div>
                  <div v-if="getMsgMeta(msg.text).thinkText">
                    <div class="text-[9px] font-black text-text-tertiary uppercase tracking-[0.2em] mb-2 flex items-center gap-2">
                      <span class="w-1.5 h-1.5 rounded-full bg-purple-500"></span> 神经路径
                    </div>
                    <div class="text-[11px] text-text-tertiary whitespace-pre-wrap leading-relaxed opacity-60">{{ getMsgMeta(msg.text).thinkText }}</div>
                  </div>
                </div>
              </div>
            </transition>
          </div>

          <!-- Main Content -->
          <div v-if="msg.status === 'generating'" class="flex items-center gap-3 py-2">
            <Loader2 :size="16" stroke-width="3" class="animate-spin text-accent" />
            <span class="text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary animate-pulse">构建论点中...</span>
          </div>
          <div v-else class="text-[14px] text-text-primary leading-relaxed md-body prose-invert prose-sm max-w-none" v-html="renderMsg(msg.text)" />
          
          <!-- Decorative Quote Mark -->
          <Quote v-if="!msg.isUser" class="absolute -bottom-2 -right-2 text-text-tertiary/10 rotate-180" :size="32" />
        </div>
      </div>

      <!-- Error State -->
      <div v-if="error" class="p-4 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center gap-3 text-red-500">
        <Scale :size="18" stroke-width="3" />
        <span class="text-xs font-bold">{{ error }}</span>
      </div>

      <!-- Scroll Buffer -->
      <div class="h-20"></div>
    </div>

    <!-- Floating Action / Input Bar -->
    <div class="absolute bottom-6 left-6 right-6 z-20">
      <transition name="pop" mode="out-in">
        
        <!-- User Input Mode -->
        <div v-if="awaitingUserInput" class="glass-v3 rounded-[28px] p-2 shadow-2xl border-white/10 bg-white/50 dark:bg-black/40 backdrop-blur-2xl">
          <div class="px-4 py-2 flex items-center justify-between border-b border-white/5 mb-1">
             <span class="text-[10px] font-black uppercase tracking-[0.2em] text-accent animate-pulse">你的回合：{{ currentTurnLabel() }}</span>
             <span class="text-[9px] font-bold text-text-tertiary uppercase tracking-widest opacity-40">⌘+Enter 发送</span>
          </div>
          <div class="flex items-end gap-2 px-2 pb-2 pt-1">
            <textarea
              v-model="replyText"
              :placeholder="userRole === 'judge' ? '起草最终裁决...' : '构建你的反驳论点...'"
              rows="1"
              class="flex-1 bg-transparent border-none focus:ring-0 text-sm text-text-primary placeholder:text-text-tertiary/40 py-3 px-2 resize-none no-scrollbar max-h-32"
              @input="e => { 
                const target = e.target as HTMLTextAreaElement;
                target.style.height = 'auto';
                target.style.height = Math.min(target.scrollHeight, 128) + 'px';
              }"
              @keydown.meta.enter="submit"
            />
            <button
              @click="submit"
              :disabled="!replyText.trim()"
              class="p-4 rounded-2xl transition-all duration-500 shadow-xl active:scale-90 shrink-0"
              :class="replyText.trim()
                ? 'bg-accent text-white shadow-accent/20 hover:shadow-accent/40 hover:-translate-y-1'
                : 'bg-white/5 text-text-tertiary cursor-not-allowed opacity-20'"
            >
              <Send :size="18" stroke-width="3" />
            </button>
          </div>
        </div>

        <!-- Decision Mode -->
        <div v-else-if="awaitingDecision" class="glass-v3 rounded-[32px] p-6 shadow-2xl border-white/10 bg-white/80 dark:bg-[#1a1a24]/90">
          <div class="flex flex-col sm:flex-row items-center gap-6">
            <div class="flex-1 text-center sm:text-left space-y-1">
              <h4 class="text-[14px] font-black uppercase tracking-widest text-text-primary">本轮总结已达成</h4>
              <p class="text-[10px] font-medium text-text-tertiary leading-relaxed">
                {{ decisionHint() }}
              </p>
            </div>
            <div class="flex gap-3 shrink-0">
               <button
                @click="emit('continue')"
                class="flex items-center gap-3 px-6 py-4 rounded-2xl bg-white/5 border border-white/10 text-text-primary font-black uppercase tracking-widest text-[10px] hover:bg-white/10 transition-all active:scale-95 shadow-xl"
              >
                <span>延续冲突</span>
                <ArrowRight :size="14" stroke-width="4" />
              </button>
              <button
                @click="emit('finish')"
                class="flex items-center gap-3 px-6 py-4 rounded-2xl bg-amber-500 text-white font-black uppercase tracking-widest text-[10px] shadow-xl shadow-amber-500/20 hover:shadow-amber-500/40 hover:-translate-y-1 transition-all active:scale-95"
              >
                <span>发布裁决</span>
                <Scale :size="14" stroke-width="4" />
              </button>
            </div>
          </div>
        </div>

        <!-- AI Working State -->
        <div v-else-if="debating" class="glass-v3 rounded-full px-8 py-4 shadow-2xl border-white/10 bg-black/40 backdrop-blur-xl flex items-center gap-4 mx-auto w-fit">
           <Loader2 :size="18" stroke-width="3" class="animate-spin text-accent" />
           <span class="text-[11px] font-black uppercase tracking-[0.4em] text-text-primary animate-pulse italic">AI 正在构建响应...</span>
        </div>

      </transition>
    </div>

  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

.collapse-enter-active, .collapse-leave-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); max-height: 400px; }
.collapse-enter-from, .collapse-leave-to { max-height: 0; opacity: 0; transform: translateY(-10px); }

.pop-enter-active { animation: popIn 0.5s cubic-bezier(0.17, 0.67, 0.12, 1); }
.pop-leave-active { animation: popOut 0.3s ease-in; }

@keyframes popIn {
  from { opacity: 0; transform: translateY(30px) scale(0.9); filter: blur(10px); }
  to { opacity: 1; transform: translateY(0) scale(1); filter: blur(0); }
}

@keyframes popOut {
  from { opacity: 1; transform: translateY(0); }
  to { opacity: 0; transform: translateY(20px) scale(0.95); }
}
</style>
