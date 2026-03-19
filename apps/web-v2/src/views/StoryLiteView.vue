<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowRight, Heart, History, Pause, Play, RotateCcw, Sparkles, Target, Zap } from 'lucide-vue-next'
import {
  STORY_LITE_DEFAULT_MAX_ROUNDS,
  STORY_LITE_DEFAULT_SEED,
  type StoryLiteAgentRole,
} from '@/features/play-modes/story-lite'
import { STORY_LITE_MOCK_SCENES } from '@/features/play-modes/story-lite/mock'
import type { HistoryEntry } from '@/features/play-modes/shared'
import { toHistoryCardViewModel, toResultCardViewModel } from '@/features/play-modes/shared'

const currentSceneId = ref('start')
const paused = ref(false)
const history = ref<HistoryEntry[]>([])
const focusedRole = ref<StoryLiteAgentRole | null>(null)

const ROLE_META: Record<StoryLiteAgentRole, { label: string; icon: any; accent: string }> = {
  logic: { label: '逻辑', icon: Target, accent: 'text-cyan-400' },
  emotion: { label: '情感', icon: Heart, accent: 'text-rose-400' },
  twist: { label: '变数', icon: Zap, accent: 'text-amber-400' },
}

const currentScene = computed(() => STORY_LITE_MOCK_SCENES[currentSceneId.value])
const isCompleted = computed(() => Boolean(currentScene.value.ending))
const round = computed(() => history.value.length + 1)
const progressValue = computed(() => Math.min(100, Math.round((round.value / STORY_LITE_DEFAULT_MAX_ROUNDS) * 100)))

const resultCard = computed(() => {
  if (!currentScene.value.ending) return null
  return toResultCardViewModel(currentScene.value.ending, currentScene.value.ending.highlights)
})

const historyCards = computed(() =>
  [...history.value].reverse().map((entry) => ({
    ...toHistoryCardViewModel(entry),
    title: entry.title,
  })),
)

const focusCopy = computed(() => {
  if (!focusedRole.value) return ''
  return currentScene.value.roleFocus[focusedRole.value] ?? ''
})

function choose(role: StoryLiteAgentRole) {
  focusedRole.value = focusedRole.value === role ? null : role
}

function restartStory() {
  currentSceneId.value = 'start'
  paused.value = false
  history.value = []
  focusedRole.value = null
}

function togglePause() {
  if (isCompleted.value) return
  paused.value = !paused.value
}

function pickChoice(choiceId: string) {
  if (paused.value || isCompleted.value) return

  const choice = currentScene.value.choices.find((item) => item.id === choiceId)
  if (!choice) return

  history.value.push({
    id: `story-turn-${history.value.length + 1}`,
    round: round.value,
    type: 'story_turn',
    createdAt: new Date().toISOString(),
    title: currentScene.value.chapter,
    summary: `${currentScene.value.briefing} 你选择了：${choice.label}`,
    payload: {
      sceneId: currentScene.value.id,
      choiceId: choice.id,
      choiceLabel: choice.label,
      badge: currentScene.value.badge,
    },
    tags: currentScene.value.badge ? [currentScene.value.badge, choice.risk.toUpperCase()] : [choice.risk.toUpperCase()],
  })

  currentSceneId.value = choice.nextSceneId
  focusedRole.value = null
}

function riskTone(risk: string) {
  if (risk === 'high') return 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-100'
  if (risk === 'medium') return 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-100'
  return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-100'
}

function roleCardClass(role: StoryLiteAgentRole) {
  if (role === 'logic') return 'border-cyan-400/20 bg-cyan-500/[0.05]'
  if (role === 'emotion') return 'border-rose-400/20 bg-rose-500/[0.05]'
  return 'border-amber-400/20 bg-amber-500/[0.05]'
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-surface-0">
    <!-- Header -->
    <header
      class="glass-v3 mx-auto mt-3 flex w-full max-w-6xl shrink-0 items-center justify-between gap-4 rounded-full border border-white/10 bg-white/72 px-4 py-2.5 shadow-2xl dark:bg-white/[0.04] sm:px-6"
    >
      <div class="min-w-0 flex items-center gap-3">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent shadow-2xl shadow-accent/20">
          <Sparkles :size="16" :stroke-width="3.5" class="text-white" />
        </div>
        <div class="min-w-0">
          <div class="text-[9px] font-black uppercase tracking-[0.32em] text-text-tertiary">互动剧情</div>
          <div class="truncate text-sm font-black tracking-tight text-text-primary sm:text-base">{{ STORY_LITE_DEFAULT_SEED }}</div>
        </div>
      </div>

      <div class="flex items-center gap-2 shrink-0">
        <div class="hidden sm:flex flex-col items-end mr-2">
          <div class="text-[9px] font-black uppercase tracking-[0.24em] text-text-tertiary">第{{ Math.min(round, STORY_LITE_DEFAULT_MAX_ROUNDS) }}轮</div>
          <div class="text-[10px] font-black uppercase tracking-[0.18em] text-accent">{{ currentScene.chapter }}</div>
        </div>
        <button
          class="h-9 w-9 rounded-full glass-v3 border border-white/10 flex items-center justify-center text-text-secondary hover:text-text-primary transition-all active:scale-90"
          @click="togglePause"
        >
          <Play v-if="paused" :size="16" :stroke-width="3.5" />
          <Pause v-else :size="16" :stroke-width="3.5" />
        </button>
        <button
          class="h-9 w-9 rounded-full glass-v3 border border-white/10 flex items-center justify-center text-text-secondary hover:text-text-primary transition-all active:scale-90"
          @click="restartStory"
        >
          <RotateCcw :size="16" :stroke-width="3.5" />
        </button>
      </div>
    </header>

    <main class="mx-auto flex w-full max-w-6xl flex-1 overflow-hidden py-3 px-3 sm:px-4 lg:px-6">
      <section
        class="glass-v3 relative flex w-full flex-1 flex-col overflow-hidden rounded-[32px] border border-white/10 bg-white/70 shadow-2xl dark:bg-white/[0.04]"
      >
        <div class="flex flex-1 overflow-hidden">
          <!-- Main Scenario Area -->
          <div class="flex flex-1 flex-col overflow-y-auto overscroll-contain border-white/10 xl:border-r">
            <!-- Scene Intro -->
            <div class="px-4 pt-5 sm:px-6 sm:pt-6">
              <div class="flex flex-wrap items-center gap-2">
                <span class="inline-flex items-center rounded-full bg-accent/10 px-3 py-1 text-[9px] font-black uppercase tracking-[0.24em] text-accent">
                  {{ currentScene.badge ?? 'Story Lite' }}
                </span>
                <span class="inline-flex items-center rounded-full bg-white/5 px-3 py-1 text-[9px] font-black uppercase tracking-[0.22em] text-text-tertiary">
                  {{ currentScene.chapter }}
                </span>
              </div>

              <div class="mt-4 rounded-[28px] border border-white/10 bg-white/82 p-5 shadow-sm dark:bg-white/5">
                <div class="flex items-center justify-between gap-4 mb-3">
                  <div class="text-[9px] font-black uppercase tracking-[0.26em] text-text-tertiary">当前简报</div>
                  <div class="text-[9px] font-black uppercase tracking-[0.22em] text-accent">{{ progressValue }}%</div>
                </div>
                <div class="h-1 rounded-full bg-white/5 overflow-hidden">
                  <div class="h-full rounded-full bg-gradient-to-r from-accent to-cyan-400 transition-all duration-500" :style="{ width: `${progressValue}%` }"></div>
                </div>
                <p class="mt-5 text-lg font-black tracking-tight text-text-primary leading-tight sm:text-xl">
                  {{ currentScene.briefing }}
                </p>
                <p class="mt-3 text-sm leading-relaxed text-text-secondary">
                  {{ currentScene.payload.sceneSummary }}
                </p>
              </div>
            </div>

            <!-- Agent Insights -->
            <div class="px-4 py-5 sm:px-6">
              <div class="text-[9px] font-black uppercase tracking-[0.28em] text-text-tertiary mb-3">智囊团</div>
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <button
                  v-for="role in (['logic', 'emotion', 'twist'] as const)"
                  :key="role"
                  class="rounded-3xl border p-4 text-left transition-all duration-300 hover:shadow-lg active:scale-[0.98]"
                  :class="[roleCardClass(role), focusedRole === role ? 'ring-2 ring-accent/40 ring-offset-2 ring-offset-surface-0' : '']"
                  @click="choose(role)"
                >
                  <div class="flex items-center gap-2 mb-3">
                    <component :is="ROLE_META[role].icon" :size="14" :stroke-width="4" :class="ROLE_META[role].accent" />
                    <span class="text-[9px] font-black uppercase tracking-widest" :class="ROLE_META[role].accent">{{ ROLE_META[role].label }}</span>
                  </div>
                  <p class="text-xs font-bold leading-tight text-text-primary line-clamp-2">
                    {{ role === 'logic' ? currentScene.payload.logic.insight : role === 'emotion' ? currentScene.payload.emotion.feeling : (currentScene.payload.twist.triggered ? currentScene.payload.twist.event : '保持克制') }}
                  </p>
                </button>
              </div>

              <transition name="page">
                <div v-if="focusedRole && focusCopy" class="mt-4 rounded-2xl border border-accent/20 bg-accent/5 p-4 text-xs leading-relaxed text-text-secondary">
                  <span class="font-black text-accent uppercase tracking-widest mr-2">{{ focusedRole === 'logic' ? '逻辑' : focusedRole === 'emotion' ? '情感' : '变数' }}视角：</span>
                  {{ focusCopy }}
                </div>
              </transition>
            </div>

            <!-- Choices Area -->
            <div class="mt-auto px-4 pb-6 sm:px-6">
              <div class="glass-v3 rounded-[32px] border border-white/10 bg-white/40 p-3 sm:p-5 backdrop-blur-md">
                <div class="flex items-center justify-between gap-4 mb-3 px-2">
                  <div class="text-[9px] font-black uppercase tracking-[0.28em] text-text-tertiary">可选行动</div>
                  <div class="text-[9px] font-black uppercase tracking-[0.2em] text-text-tertiary italic">
                    {{ isCompleted ? '已到达结局' : paused ? '已暂停' : `${currentScene.choices.length} 条路径` }}
                  </div>
                </div>

                <div v-if="isCompleted && resultCard" class="grid gap-3">
                  <div class="rounded-2xl border border-accent/20 bg-accent/5 p-4">
                    <div class="text-[9px] font-black uppercase tracking-[0.28em] text-accent mb-1">结局解锁</div>
                    <div class="text-base font-black tracking-tight text-text-primary mb-2">{{ resultCard.title }}</div>
                    <p class="text-xs leading-relaxed text-text-secondary">{{ resultCard.summary }}</p>
                  </div>
                  <button class="w-full rounded-2xl bg-text-primary py-3.5 text-[10px] font-black uppercase tracking-widest text-surface-1" @click="restartStory">再跑一局</button>
                </div>

                <div v-else class="grid gap-2">
                  <button
                    v-for="choice in currentScene.choices"
                    :key="choice.id"
                    class="group flex items-center gap-3 rounded-2xl border px-4 py-3 text-left transition-all hover:bg-white/5 disabled:opacity-40"
                    :class="riskTone(choice.risk)"
                    :disabled="paused"
                    @click="pickChoice(choice.id)"
                  >
                    <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-black/5 dark:bg-white/10">
                      <ArrowRight :size="14" :stroke-width="4" />
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="text-[8px] font-black uppercase tracking-widest opacity-60">{{ choice.risk === 'high' ? '高' : choice.risk === 'medium' ? '中' : '低' }}风险</div>
                      <div class="truncate text-xs font-black text-current">{{ choice.label }}</div>
                    </div>
                  </button>
                </div>
              </div>
            </div>
          </div>

            <aside class="hidden w-80 shrink-0 flex-col overflow-y-auto bg-black/[0.01] p-6 xl:flex dark:bg-white/[0.01]">
            <div class="flex items-center justify-between mb-6 px-1">
              <div class="flex items-center gap-2">
                <History :size="16" :stroke-width="3.5" class="text-accent" />
                <span class="text-[10px] font-black uppercase tracking-[0.28em] text-text-tertiary">路径历史</span>
              </div>
              <span class="text-[9px] font-black text-text-tertiary bg-white/5 px-2 py-0.5 rounded-full">{{ history.length }}</span>
            </div>

            <div class="space-y-3">
              <div v-if="!historyCards.length" class="rounded-2xl border border-dashed border-white/10 p-6 text-center text-[10px] text-text-tertiary">
                尚未开始记录路径
              </div>
              <div v-for="item in historyCards" :key="item.id" class="rounded-2xl border border-white/5 bg-white/60 p-4 dark:bg-white/5">
                <div class="flex items-center justify-between mb-2">
                  <span class="text-[9px] font-black uppercase tracking-widest text-accent">{{ item.roundLabel }}</span>
                  <span class="text-[8px] font-black uppercase tracking-widest text-text-tertiary opacity-60">{{ item.typeLabel }}</span>
                </div>
                <div class="text-xs font-black text-text-primary mb-1">{{ item.title }}</div>
                <p class="text-[11px] leading-relaxed text-text-secondary">{{ item.summary }}</p>
              </div>
            </div>
            </aside>
        </div>
      </section>
    </main>
  </div>
</template>
