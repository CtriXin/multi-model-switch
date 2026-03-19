<script setup lang="ts">
import type { OpinionCard } from '@/features/challenge/types'
import { CATEGORY_LABELS, CATEGORY_ICONS, AXIS_LABELS } from '@/features/challenge/types'
import { Calendar, Flame, TrendingUp, ChevronDown, Award, BrainCircuit } from 'lucide-vue-next'
import { computed, reactive } from 'vue'
import MarkdownIt from 'markdown-it'
import { sanitizeModelOutput } from '@/utils/modelOutput'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

function renderText(text: string): string {
  const { content } = sanitizeModelOutput(text)
  return md.render(content)
}

const props = defineProps<{
  cards: OpinionCard[]
  streak: number
}>()

const expanded = reactive<Record<string, boolean>>({})

const weekCards = computed(() => {
  const now = new Date()
  const weekAgo = new Date(now.getTime() - 7 * 86400000)
  return props.cards.filter(c => new Date(c.challengeDate) >= weekAgo)
})

const stanceChangeRate = computed(() => {
  if (!weekCards.value.length) return 0
  const changed = weekCards.value.filter(c => c.stance.changed).length
  return Math.round((changed / weekCards.value.length) * 100)
})

const mostDiscussedCategory = computed(() => {
  const counts: Record<string, number> = {}
  for (const c of weekCards.value) {
    counts[c.category] = (counts[c.category] || 0) + 1
  }
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1])
  return sorted[0]?.[0] || 'tech'
})

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function stanceEmoji(stance: string) {
  return stance === 'support' ? '👍' : stance === 'oppose' ? '👎' : '🤔'
}

function roundCardClass(speaker: string) {
  if (speaker === 'pro') return 'border-green-500/10 bg-green-500/5'
  if (speaker === 'con') return 'border-red-500/10 bg-red-500/5'
  return 'border-amber-500/10 bg-amber-500/5'
}

function roundTextClass(speaker: string) {
  if (speaker === 'pro') return 'text-green-600 dark:text-green-400'
  if (speaker === 'con') return 'text-red-600 dark:text-red-400'
  return 'text-amber-600 dark:text-amber-400'
}

function roundLabel(speaker: string) {
  if (speaker === 'pro') return '正方'
  if (speaker === 'con') return '反方'
  return '裁判'
}
</script>

<template>
  <div class="space-y-8 py-4">
    <!-- Weekly Summary Dashboard -->
    <div class="p-6 rounded-[32px] glass-v3 border-white/10 bg-accent/5 relative overflow-hidden">
      <div class="absolute -top-10 -right-10 w-32 h-32 bg-accent/10 blur-[60px] rounded-full"></div>
      
      <div class="flex items-center gap-3 mb-6 relative z-10">
        <div class="p-2 rounded-xl bg-accent text-white shadow-xl shadow-accent/20">
          <TrendingUp :size="18" stroke-width="3" />
        </div>
        <span class="text-[11px] font-black uppercase tracking-[0.3em] text-accent">Performance Metrics</span>
      </div>

      <div class="grid grid-cols-3 gap-6 relative z-10">
        <div class="space-y-1">
          <div class="text-2xl font-black text-text-primary tracking-tight">{{ weekCards.length }}</div>
          <div class="text-[9px] font-black uppercase tracking-widest text-text-tertiary">Mission Complete</div>
        </div>
        <div class="space-y-1">
          <div class="text-2xl font-black text-accent tracking-tight flex items-center gap-1.5">
            <Flame :size="20" stroke-width="3.5" /> {{ streak }}
          </div>
          <div class="text-[9px] font-black uppercase tracking-widest text-text-tertiary">Active Streak</div>
        </div>
        <div class="space-y-1">
          <div class="text-2xl font-black text-text-primary tracking-tight">{{ stanceChangeRate }}<span class="text-sm opacity-40">%</span></div>
          <div class="text-[9px] font-black uppercase tracking-widest text-text-tertiary">Opinion Shift</div>
        </div>
      </div>

      <div class="mt-6 pt-5 border-t border-white/5 flex items-center justify-between relative z-10">
        <div class="flex items-center gap-2">
           <span class="text-[9px] font-black uppercase tracking-widest text-text-tertiary opacity-60">Focus Domain:</span>
           <span class="text-[10px] font-bold text-text-secondary">
              {{ CATEGORY_ICONS[mostDiscussedCategory as keyof typeof CATEGORY_ICONS] }}
              {{ CATEGORY_LABELS[mostDiscussedCategory as keyof typeof CATEGORY_LABELS] }}
           </span>
        </div>
        <div class="w-1.5 h-1.5 rounded-full bg-accent animate-pulse"></div>
      </div>
    </div>

    <!-- Historical Archive -->
    <div class="space-y-4">
      <div class="flex items-center gap-3 px-2">
        <Calendar :size="14" stroke-width="3" class="text-text-tertiary" />
        <h3 class="text-[11px] font-black uppercase tracking-[0.3em] text-text-tertiary">Historical Archive ({{ cards.length }})</h3>
        <div class="h-px flex-1 bg-gradient-to-r from-white/5 to-transparent"></div>
      </div>

      <div v-if="!cards.length" class="text-center py-20 glass-v3 rounded-[32px] border-dashed border-white/10">
        <p class="text-[11px] font-black uppercase tracking-widest text-text-tertiary opacity-40 italic">Archives Empty. Begin your first challenge.</p>
      </div>

      <div
        v-for="card in cards"
        :key="card.id"
        class="group rounded-3xl border border-white/5 bg-black/[0.02] dark:bg-white/[0.02] hover:bg-black/[0.04] dark:hover:bg-white/[0.05] transition-all duration-500 overflow-hidden"
      >
        <!-- Card Entry -->
        <button
          @click="expanded[card.id] = !expanded[card.id]"
          class="w-full p-5 text-left active:scale-[0.99] transition-all"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-3 mb-2">
                <span class="text-[9px] font-black uppercase tracking-widest text-text-tertiary opacity-60">{{ formatDate(card.challengeDate) }}</span>
                <span class="text-[9px] px-2 py-0.5 rounded bg-accent/10 text-accent font-black uppercase tracking-widest">
                  {{ CATEGORY_LABELS[card.category] }}
                </span>
              </div>
              <h4 class="text-[15px] font-bold text-text-primary leading-tight group-hover:text-accent transition-colors">{{ card.topic.title }}</h4>
              <div class="mt-2 flex items-center gap-2">
                <span class="text-sm">{{ stanceEmoji(card.stance.final) }}</span>
                <p class="text-[11px] font-medium text-text-secondary leading-relaxed italic line-clamp-1 opacity-70">
                  「{{ card.stance.userReason }}」
                </p>
              </div>
              <p v-if="card.debate.takeaway?.oneLineVerdict" class="mt-2 text-[11px] text-text-secondary line-clamp-2 opacity-80">
                {{ card.debate.takeaway.oneLineVerdict }}
              </p>
            </div>
            <div class="p-2 rounded-xl bg-white/5 border border-white/5 group-hover:border-accent/20 transition-all">
               <ChevronDown :size="14" stroke-width="4" class="text-text-tertiary transition-transform duration-500"
                :class="expanded[card.id] ? 'rotate-180 text-accent' : ''" />
            </div>
          </div>
        </button>

        <!-- Expanded Intelligence Report -->
        <transition name="report">
          <div v-if="expanded[card.id]" class="px-5 pb-6 space-y-5 border-t border-white/5 bg-black/5 dark:bg-black/20 overflow-hidden">
            <!-- Takeaway Summary -->
            <div v-if="card.debate.takeaway" class="mt-5 p-5 rounded-2xl glass-v3 border-white/10 bg-accent/5">
              <div class="flex items-center gap-2 mb-4">
                 <Award :size="14" stroke-width="3" class="text-accent" />
                 <span class="text-[10px] font-black uppercase tracking-[0.2em] text-accent">Protocol Synthesis</span>
              </div>
              <p class="text-sm font-bold text-text-primary leading-tight">{{ card.debate.takeaway.oneLineVerdict }}</p>
              
              <div class="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                 <div class="space-y-1">
                    <span class="text-[9px] font-black text-green-600 dark:text-green-400 uppercase tracking-widest block">PRO Edge</span>
                    <p class="text-[11px] text-text-secondary font-medium leading-snug">{{ card.debate.takeaway.strongestPointFor }}</p>
                 </div>
                 <div class="space-y-1">
                    <span class="text-[9px] font-black text-red-600 dark:text-red-400 uppercase tracking-widest block">CON Edge</span>
                    <p class="text-[11px] text-text-secondary font-medium leading-snug">{{ card.debate.takeaway.strongestPointAgainst }}</p>
                 </div>
              </div>
            </div>

            <!-- Debate Log Mini -->
            <div class="space-y-3">
              <div class="text-[9px] font-black uppercase tracking-[0.2em] text-text-tertiary px-1">Engagement Log</div>
              <div v-for="(round, idx) in card.debate.rounds" :key="idx"
                class="p-4 rounded-xl border transition-all duration-300"
                :class="roundCardClass(round.speaker)"
              >
                <div class="flex items-center gap-2 mb-2">
                  <span class="text-[9px] font-black uppercase tracking-widest"
                    :class="roundTextClass(round.speaker)"
                  >{{ roundLabel(round.speaker) }}</span>
                  <span v-if="round.modelId === 'user'" class="text-[8px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded bg-accent/10 text-accent">USER</span>
                </div>
                <div class="text-[12px] text-text-secondary leading-relaxed md-body prose-invert prose-xs opacity-80" v-html="renderText(round.text)" />
              </div>
            </div>

            <!-- Cognitive Trace -->
            <div v-if="card.thinkingSnapshot.summary" class="pt-4 border-t border-white/5">
              <div class="flex items-center gap-2 mb-4">
                 <BrainCircuit :size="14" stroke-width="3" class="text-purple-500" />
                 <span class="text-[9px] font-black uppercase tracking-[0.2em] text-text-tertiary">Cognitive Profile</span>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
                <div v-for="(labels, axisId) in AXIS_LABELS" :key="axisId" class="space-y-1.5">
                  <div class="flex justify-between text-[8px] font-black uppercase tracking-tighter text-text-tertiary opacity-40">
                    <span>{{ labels[0].slice(0, 3) }}</span>
                    <span>{{ labels[1].slice(0, 3) }}</span>
                  </div>
                  <div class="h-1 rounded-full bg-white/5 overflow-hidden border border-white/5">
                    <div
                      class="h-full rounded-full bg-accent/40"
                      :style="{ width: `${card.thinkingSnapshot.axes[axisId]?.score ?? 50}%` }"
                    />
                  </div>
                </div>
              </div>
              <p class="text-[11px] text-text-tertiary font-medium leading-relaxed opacity-60 italic">{{ card.thinkingSnapshot.summary }}</p>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.report-enter-active, .report-leave-active { transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1); max-height: 2000px; }
.report-enter-from, .report-leave-to { max-height: 0; opacity: 0; transform: translateY(-10px); }
</style>
