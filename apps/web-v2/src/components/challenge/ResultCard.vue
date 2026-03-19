<script setup lang="ts">
import type { TopicCandidate, DebateStance, DebateTakeaway, ThinkingPatternSnapshot, DebateMessage } from '@/features/challenge/types'
import type { OpinionCard } from '@/features/challenge/types'
import { AXIS_LABELS } from '@/features/challenge/types'
import { Award, BookmarkPlus, RotateCcw, Check, History, Home, ChevronDown, Sparkles, BrainCircuit } from 'lucide-vue-next'
import { ref, reactive, computed } from 'vue'
import MarkdownIt from 'markdown-it'
import { sanitizeModelOutput } from '@/utils/modelOutput'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

function renderMsg(text: string): string {
  const { content } = sanitizeModelOutput(text)
  return md.render(content)
}

function getMsgMeta(text: string) {
  const { thinkText, briefText } = sanitizeModelOutput(text)
  return { thinkText, briefText }
}

const expandedThink = reactive<Record<string, boolean>>({})

const props = defineProps<{
  topic: TopicCandidate | null
  proText: string
  conText: string
  takeaway: DebateTakeaway | null
  snapshot: ThinkingPatternSnapshot | null
  currentCard: OpinionCard | null
  userStance: DebateStance
  userReason: string
  streak: number
  messages: DebateMessage[]
}>()

const emit = defineEmits<{
  save: [finalStance?: DebateStance]
  retry: []
  goHistory: []
  goHome: []
}>()

const saved = ref(false)
const showDebate = ref(false)

const stanceLabel = computed(() => {
  if (props.userStance === 'support') return '支持方'
  if (props.userStance === 'oppose') return '反对方'
  return '中立'
})

function getAxisPercent(axisId: string): number {
  const score = props.snapshot?.axes?.[axisId as keyof typeof props.snapshot.axes]
  return score?.score ?? 50
}

function getAxisNote(axisId: string): string {
  const score = props.snapshot?.axes?.[axisId as keyof typeof props.snapshot.axes]
  return score?.note ?? ''
}

async function handleSave() {
  emit('save')
  saved.value = true
}
</script>

<template>
  <div class="space-y-8 py-4 pb-20">
    
    <!-- Congratulations Header (Only for fresh result) -->
    <div v-if="takeaway && !saved" class="text-center space-y-3 animate-in fade-in zoom-in duration-700">
       <div class="relative inline-flex items-center justify-center w-20 h-20 rounded-[32px] bg-accent/10 border border-accent/20 shadow-2xl mb-2 group">
        <div class="absolute inset-0 bg-accent/20 blur-[30px] rounded-full animate-pulse"></div>
        <Award :size="40" stroke-width="3" class="text-accent relative z-10" />
      </div>
      <div class="space-y-1">
        <h2 class="text-2xl font-black uppercase tracking-[0.2em] text-text-primary">思维对决完成</h2>
        <p class="text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary opacity-60">思维整合完成</p>
      </div>
    </div>

    <!-- Already saved card state -->
    <template v-if="currentCard && !takeaway">
      <div class="text-center py-10 glass-v3 rounded-[32px] border-white/10 space-y-4">
        <div class="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center mx-auto border border-green-500/30">
          <Check :size="32" stroke-width="4" class="text-green-500" />
        </div>
        <div class="space-y-1 px-6">
          <h2 class="text-[14px] font-black uppercase tracking-[0.2em] text-text-primary">今日挑战已达成</h2>
          <p class="text-lg font-bold text-text-secondary leading-tight">{{ currentCard.topic.title }}</p>
        </div>
        <div class="px-6 py-3 bg-black/5 dark:bg-white/5 border-y border-white/5 mx-6 rounded-2xl">
           <span class="text-[10px] font-black uppercase tracking-widest text-accent">{{ currentCard.stance.final === 'support' ? '支持' : currentCard.stance.final === 'oppose' ? '反对' : '中立' }}</span>
           <p class="text-xs text-text-tertiary mt-1 italic">「{{ currentCard.stance.userReason }}」</p>
        </div>
      </div>

      <!-- Snapshot from saved card -->
      <div v-if="currentCard.thinkingSnapshot.summary" class="p-8 rounded-[32px] glass-v3 border-white/10 bg-white/5">
        <div class="flex items-center gap-3 mb-8">
          <div class="p-2 rounded-xl bg-purple-500/10 text-purple-500">
            <BrainCircuit :size="20" stroke-width="3" />
          </div>
          <div class="flex flex-col">
            <span class="text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary">认知画像</span>
            <span class="text-xs font-bold text-text-primary">{{ currentCard.thinkingSnapshot.label }}</span>
          </div>
        </div>
        
        <div class="space-y-6">
          <div v-for="(labels, axisId) in AXIS_LABELS" :key="axisId" class="space-y-2">
            <div class="flex justify-between text-[9px] font-black uppercase tracking-widest text-text-tertiary">
              <span>{{ labels[0] }}</span>
              <span>{{ labels[1] }}</span>
            </div>
            <div class="h-1.5 rounded-full bg-black/10 dark:bg-white/5 overflow-hidden border border-white/5">
              <div
                class="h-full rounded-full bg-gradient-to-r from-accent to-purple-500 transition-all duration-1000"
                :style="{ width: `${currentCard.thinkingSnapshot.axes[axisId]?.score ?? 50}%` }"
              />
            </div>
          </div>
        </div>
        <div class="mt-8 pt-6 border-t border-white/5">
          <p class="text-sm text-text-secondary leading-relaxed font-medium">{{ currentCard.thinkingSnapshot.summary }}</p>
        </div>
      </div>
    </template>

    <!-- Fresh result -->
    <template v-else-if="takeaway">
      <!-- Verdict Area -->
      <div class="p-8 rounded-[32px] glass-v3 border-white/10 bg-accent/5 relative overflow-hidden">
        <div class="absolute -top-20 -right-20 w-64 h-64 bg-accent/10 blur-[100px] rounded-full"></div>
        
        <div class="flex items-center gap-3 mb-6 relative z-10">
          <div class="p-2 rounded-xl bg-accent text-white shadow-xl shadow-accent/20">
            <Sparkles :size="20" stroke-width="3" />
          </div>
          <span class="text-[11px] font-black uppercase tracking-[0.3em] text-accent">协议综合</span>
        </div>

        <div class="space-y-6 relative z-10">
          <p class="text-xl font-black text-text-primary leading-tight">{{ takeaway.oneLineVerdict }}</p>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div class="p-4 rounded-2xl bg-green-500/5 border border-green-500/10">
              <span class="text-[9px] font-black uppercase tracking-widest text-green-600 dark:text-green-400 block mb-2">最强支持论点</span>
              <p class="text-xs text-text-secondary leading-relaxed font-medium">{{ takeaway.strongestPointFor }}</p>
            </div>
            <div class="p-4 rounded-2xl bg-red-500/5 border border-red-500/10">
              <span class="text-[9px] font-black uppercase tracking-widest text-red-600 dark:text-red-400 block mb-2">最强反对论点</span>
              <p class="text-xs text-text-secondary leading-relaxed font-medium">{{ takeaway.strongestPointAgainst }}</p>
            </div>
          </div>
          
          <div class="pt-4 border-t border-white/5">
            <p class="text-[11px] text-accent font-black uppercase tracking-widest mb-1">最终提问：</p>
            <p class="text-sm text-text-primary italic font-bold">「{{ takeaway.decisiveQuestion }}」</p>
          </div>
        </div>
      </div>

      <!-- User Stance Recap -->
      <div class="p-6 rounded-2xl bg-black/5 dark:bg-white/5 border border-white/5 flex items-start gap-4">
        <div class="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center shrink-0 border border-white/10">
           <User :size="20" stroke-width="3" class="text-text-secondary" />
        </div>
        <div class="flex-1 space-y-1">
          <p class="text-[10px] font-black uppercase tracking-widest text-text-tertiary">最终立场：<span class="text-text-primary">{{ stanceLabel }}</span></p>
          <p class="text-sm text-text-secondary font-medium leading-relaxed italic">「{{ userReason }}」</p>
        </div>
      </div>

      <!-- Toggle Full Log -->
      <button
        @click="showDebate = !showDebate"
        class="w-full flex items-center justify-center gap-3 py-4 rounded-2xl border border-dashed border-white/10 text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary hover:text-text-secondary transition-all"
      >
        <span>{{ showDebate ? '收起记录' : '查看辩论档案' }}</span>
        <ChevronDown :size="14" stroke-width="4" class="transition-transform duration-300" :class="showDebate ? 'rotate-180' : ''" />
      </button>

      <transition name="collapse">
        <div v-if="showDebate" class="space-y-4 overflow-hidden">
          <div
            v-for="msg in messages.filter(m => m.status === 'done')"
            :key="msg.id"
            class="rounded-2xl p-5 border bg-white/5 dark:bg-black/20 border-white/5"
          >
            <div class="flex items-center gap-3 mb-3">
              <span class="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded"
                :class="{
                  'bg-green-500 text-white': msg.side === 'pro',
                  'bg-red-500 text-white': msg.side === 'con',
                  'bg-amber-500 text-white': msg.side === 'judge',
                }"
              >{{ msg.side === 'pro' ? '正方' : msg.side === 'con' ? '反方' : '裁判' }}</span>
              <span class="text-[10px] font-bold text-text-tertiary uppercase tracking-tighter">{{ msg.label }}</span>
            </div>
            <div class="text-[13px] text-text-primary leading-relaxed md-body prose-invert prose-xs" v-html="renderMsg(msg.text)" />
          </div>
        </div>
      </transition>

      <!-- Thinking Snapshot Visualization -->
      <div v-if="snapshot" class="p-8 rounded-[32px] glass-v3 border-white/10 bg-white/5">
        <div class="flex items-center gap-3 mb-8">
          <div class="p-2 rounded-xl bg-purple-500/10 text-purple-500 shadow-lg shadow-purple-500/5">
            <BrainCircuit :size="20" stroke-width="3" />
          </div>
          <div class="flex flex-col">
            <span class="text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary">认知画像矩阵</span>
            <span class="text-sm font-black text-text-primary">{{ snapshot.label }}</span>
          </div>
        </div>

        <div class="space-y-6">
          <div v-for="(labels, axisId) in AXIS_LABELS" :key="axisId" class="space-y-2.5">
            <div class="flex justify-between text-[9px] font-black uppercase tracking-widest text-text-tertiary">
              <span class="opacity-60">{{ labels[0] }}</span>
              <span class="opacity-60">{{ labels[1] }}</span>
            </div>
            <div class="h-2 rounded-full bg-black/10 dark:bg-black/40 overflow-hidden border border-white/5 p-[1px]">
              <div
                class="h-full rounded-full bg-gradient-to-r from-accent via-indigo-500 to-purple-600 transition-all duration-1500 ease-out shadow-[0_0_10px_rgba(var(--accent-rgb),0.3)]"
                :style="{ width: `${getAxisPercent(axisId)}%` }"
              />
            </div>
            <p v-if="getAxisNote(axisId)" class="text-[9px] text-text-tertiary font-bold uppercase tracking-tighter opacity-40">
              {{ getAxisNote(axisId) }}
            </p>
          </div>
        </div>
        <div v-if="snapshot.summary" class="mt-8 pt-8 border-t border-white/5">
          <p class="text-sm text-text-secondary leading-relaxed font-medium">{{ snapshot.summary }}</p>
        </div>
      </div>

      <!-- Terminal Actions -->
      <div v-if="!saved" class="flex gap-4 pt-4">
        <button
          @click="handleSave"
          class="flex-1 flex items-center justify-center gap-3 py-4 rounded-2xl
                 bg-accent text-white font-black uppercase tracking-[0.2em] text-[10px]
                 shadow-2xl shadow-accent/30 hover:shadow-accent/50 hover:-translate-y-1 transition-all active:scale-95"
        >
          <BookmarkPlus :size="16" stroke-width="4" /> 保存观点卡
        </button>
        <button
          @click="emit('retry')"
          class="p-4 rounded-2xl bg-white/5 border border-white/10 text-text-tertiary hover:text-text-primary hover:bg-white/10 transition-all active:scale-90"
        >
          <RotateCcw :size="18" stroke-width="3" />
        </button>
      </div>

      <!-- Post-save Final CTA -->
      <div v-else class="space-y-4 pt-4 animate-in fade-in slide-in-from-bottom-4">
        <div class="flex flex-col items-center py-8 rounded-[32px] bg-green-500/5 border border-green-500/20 shadow-2xl">
          <div class="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center mb-4">
             <Check :size="28" stroke-width="4" class="text-green-500" />
          </div>
          <p class="text-[12px] font-black uppercase tracking-[0.2em] text-text-primary">Observation Archived</p>
          <p v-if="streak > 0" class="text-[10px] font-black text-accent mt-2 uppercase tracking-[0.3em] animate-pulse">
            {{ streak }} DAY STREAK MAINTAINED
          </p>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <button
            @click="emit('goHistory')"
            class="flex items-center justify-center gap-3 py-4 rounded-2xl
                   bg-white/5 border border-white/10 text-text-primary font-black uppercase tracking-widest text-[10px] hover:bg-white/10 transition-all active:scale-95"
          >
            <History :size="16" stroke-width="3" /> Archive
          </button>
          <button
            @click="emit('goHome')"
            class="flex items-center justify-center gap-3 py-4 rounded-2xl
                   bg-accent text-white font-black uppercase tracking-widest text-[10px] shadow-xl shadow-accent/20 hover:shadow-accent/40 hover:-translate-y-1 transition-all active:scale-95"
          >
            <Home :size="16" stroke-width="4" /> Terminal
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.collapse-enter-active, .collapse-leave-active { transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); max-height: 2000px; }
.collapse-enter-from, .collapse-leave-to { max-height: 0; opacity: 0; }
</style>
