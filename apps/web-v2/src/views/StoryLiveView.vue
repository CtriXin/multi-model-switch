<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { Clapperboard, Heart, RotateCcw, Send, Sparkles, Target, Wand2, Loader2 } from 'lucide-vue-next'
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
const premiseDraft = ref('一个女人倒在血泊中')

const {
  envelope,
  turns,
  draftInput,
  processing,
  error,
  wrapError,
  hydrated,
  resumed,
  premise,
  modelAssignment,
  wrapResult,
  latestDirectorCue,
  started,
  wrapBusy,
} = storeToRefs(storyLiveStore)

const ROLE_META: Record<StoryLiveRole, { label: string; title: string; accent: string; surface: string; icon: any }> = {
  logic: { label: '逻辑', title: '主镜头推进', accent: 'text-cyan-400', surface: 'border-cyan-400/20 bg-cyan-500/[0.06]', icon: Target },
  emotion: { label: '情感', title: '情绪暗流', accent: 'text-rose-400', surface: 'border-rose-400/20 bg-rose-500/[0.06]', icon: Heart },
  twist: { label: '变数', title: '异动信号', accent: 'text-amber-400', surface: 'border-amber-400/20 bg-amber-500/[0.06]', icon: Wand2 },
}

const STORY_STARTERS = [
  { label: '暴雨仓库', value: '暴雨夜，仓库门口的地面上拖出一条还没干的血线。' },
  { label: '住院部电话', value: '凌晨两点，住院部尽头的电话忽然响了第三次。' },
  { label: '空屋晚饭', value: '空屋餐桌上摆着两份还冒着热气的晚饭，却一个人都看不见。' },
] as const

const NEXT_BEAT_SUGGESTIONS = [
  { label: '先听动静', value: '我没有推门，而是贴着门缝先听里面有没有第二个人的呼吸声。' },
  { label: '假装离开', value: '我故意后退半步，装作要离开，想看里面会不会有人趁机动。' },
  { label: '检查血线', value: '我蹲下来摸那条血线，先判断它是往里拖还是往外拖。' },
] as const

const userInput = computed({
  get: () => draftInput.value,
  set: (value: string) => storyLiveStore.updateDraft(value),
})

const modelChips = computed(() => {
  if (!modelAssignment.value) return []
  return (Object.keys(modelAssignment.value) as StoryLiveRole[]).map((role) => ({
    role,
    modelId: modelAssignment.value![role],
    modelName: storyLiveStore.getModelName(modelAssignment.value![role]),
  }))
})

const roleCards = computed(() =>
  (Object.keys(ROLE_META) as StoryLiveRole[]).map((role) => {
    const assignedModelId = modelAssignment.value?.[role]
    return {
      role,
      modelName: assignedModelId ? storyLiveStore.getModelName(assignedModelId) : '开场后自动分配',
      statusLabel: assignedModelId ? '已锁定到场景' : '首轮自动分配',
      ready: Boolean(assignedModelId),
    }
  }),
)

const assignmentNote = computed(() => {
  const selected = appStore.selectedModelIds.filter((id) => appStore.getModel(id))
  if (selected.length >= 3) return '优先沿用你已经选好的 3 个模型。'
  return '如果你没先选满 3 个模型，这里会自动补齐偏免费 / 中间档的组合。'
})

const wrapTitle = computed(() => {
  if (!wrapResult.value) return '收束台'
  return wrapResult.value.mode === 'story' ? '故事整理' : '剧本草案'
})

const turnCountLabel = computed(() => `${turns.value.length} 轮`)

const resumeHint = computed(() => envelope.value.pauseState?.resumeHint || '')

const stageStatus = computed(() => {
  if (!started.value) return '准备就绪'
  if (processing.value) return '导演中'
  if (wrapBusy.value) return '收束中'
  return '演出中'
})

const sceneSummary = computed(() => {
  if (!started.value) return '先给一个失衡瞬间，Story Live 会把它接成一段正在发生的戏。'
  return '戏已经开场。现在优先看最新镜头和导演提示，再决定下一步。'
})

function renderMarkdown(text: string) {
  return md.render(sanitizeModelOutput(text).content || '')
}

function scrollLatestTurnIntoView() {
  nextTick(() => {
    if (!transcriptRef.value) return
    const turnCards = transcriptRef.value.querySelectorAll<HTMLElement>('[data-story-live-turn]')
    const latestTurn = turnCards.item(turnCards.length - 1)
    if (latestTurn) {
      latestTurn.scrollIntoView({ block: 'start' })
      return
    }

    transcriptRef.value.scrollTop = 0
  })
}

async function startStory() {
  const seed = premiseDraft.value.trim()
  if (!seed) {
    toastStore.info('先写一个开场')
    return
  }

  const ok = await storyLiveStore.startStory(seed)
  if (!ok && !modelAssignment.value) {
    toastStore.error('没有可用模型，先去设置配置一下')
  }
}

async function continueStory() {
  await flowContinueStory(userInput.value)
}

function restart() {
  const nextPremise = premiseDraft.value.trim() || premise.value
  premiseDraft.value = nextPremise
  if (!nextPremise) return
  storyLiveStore.restart(nextPremise)
}

watch(
  () => turns.value.length,
  () => scrollLatestTurnIntoView(),
)

onMounted(async () => {
  await storyLiveStore.init()
  premiseDraft.value = premise.value
  storyLiveStore.markActive()
  scrollLatestTurnIntoView()
})

onBeforeUnmount(() => {
  storyLiveStore.markPaused()
})
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden bg-surface-0">
    <!-- Header: Fixed -->
    <header
      class="glass-v3 mx-auto mt-3 flex w-full max-w-6xl shrink-0 items-center justify-between gap-4 rounded-full border border-black/5 bg-white/72 px-4 py-3 shadow-2xl dark:border-white/10 dark:bg-white/[0.04] sm:px-6"
    >
      <div class="min-w-0 flex items-center gap-3">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent shadow-2xl shadow-accent/20">
          <Clapperboard :size="16" :stroke-width="3.5" class="text-white" />
        </div>
        <div class="min-w-0">
          <div class="text-[9px] font-black uppercase tracking-[0.32em] text-text-tertiary">Director Co-Play</div>
          <div class="truncate text-sm font-black tracking-tight text-text-primary sm:text-base">剧情共演</div>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <div v-if="started" class="hidden items-center gap-2 sm:flex">
          <span class="inline-flex items-center rounded-full bg-accent/10 px-3 py-1 text-[9px] font-black uppercase tracking-[0.24em] text-accent">
            {{ stageStatus }}
          </span>
        </div>
        <button
          class="glass-v3 flex h-10 w-10 items-center justify-center rounded-full border border-white/10 text-text-secondary transition-all hover:text-text-primary active:scale-90"
          title="重新开始"
          @click="restart"
        >
          <RotateCcw :size="16" :stroke-width="3.5" />
        </button>
      </div>
    </header>

    <!-- Main Content: Flex container -->
    <main class="mx-auto flex w-full max-w-6xl flex-1 overflow-hidden py-3 px-3 sm:px-4 lg:px-6">
      <section class="glass-v3 relative flex w-full flex-1 flex-col overflow-hidden rounded-[32px] border border-black/5 bg-white/70 shadow-2xl dark:border-white/10 dark:bg-white/[0.04] lg:rounded-[40px]">
        <!-- Background Accents -->
        <div class="pointer-events-none absolute inset-0 overflow-hidden">
          <div class="absolute inset-x-0 top-0 h-40 bg-[radial-gradient(circle_at_top,rgba(99,102,241,0.12),transparent_72%)]"></div>
          <div class="absolute -left-16 top-24 h-56 w-56 rounded-full bg-cyan-400/[0.06] blur-3xl"></div>
          <div class="absolute right-[-6rem] top-1/3 h-72 w-72 rounded-full bg-accent/[0.08] blur-3xl"></div>
        </div>

        <div class="relative flex flex-1 overflow-hidden">
          <!-- Left: Main Stage (Scrollable Transcript + Fixed Input) -->
          <div class="flex flex-1 flex-col min-w-0 border-white/10 xl:border-r">
            
            <!-- Context Banner (Sticky) -->
            <div v-if="!started" class="px-4 pt-5 sm:px-6 sm:pt-6">
              <div class="flex flex-wrap items-center gap-2">
                <span class="inline-flex items-center rounded-full bg-accent/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.24em] text-accent">
                  Director-Led
                </span>
                <span class="inline-flex items-center rounded-full bg-white/5 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-text-tertiary">
                  输入一句，故事就往前演半步
                </span>
              </div>
              
              <div class="mt-5 overflow-hidden rounded-[28px] border border-black/5 bg-white/82 p-5 shadow-sm dark:border-white/10 dark:bg-white/[0.05]">
                <div class="text-[10px] font-black uppercase tracking-[0.26em] text-text-tertiary mb-3">Opening Premise</div>
                <textarea
                  v-model="premiseDraft"
                  rows="3"
                  class="w-full rounded-[20px] border border-white/10 bg-black/[0.03] px-4 py-3 text-sm leading-relaxed text-text-primary outline-none transition-all placeholder:text-text-quaternary focus:border-accent/40 focus:ring-2 focus:ring-accent/10 dark:bg-white/[0.04]"
                  placeholder="输入你的故事开场，比如：凌晨两点，住院部尽头的电话忽然响了第三次。"
                />
                <div class="mt-4 flex flex-wrap gap-2">
                  <button
                    class="rounded-full bg-text-primary px-5 py-2.5 text-[10px] font-black uppercase tracking-[0.22em] text-surface-1 transition-all hover:shadow-xl active:scale-[0.98] disabled:opacity-40"
                    :disabled="processing || wrapBusy"
                    @click="startStory"
                  >
                    开始共演
                  </button>
                  <button
                    class="rounded-full bg-white/5 px-4 py-2.5 text-[10px] font-black uppercase tracking-[0.22em] text-text-secondary transition-all hover:bg-white/10"
                    @click="premiseDraft = STORY_STARTERS[Math.floor(Math.random() * STORY_STARTERS.length)].value"
                  >
                    换个开场
                  </button>
                </div>
              </div>
            </div>

            <!-- Transcript: The core scrolling area -->
            <div ref="transcriptRef" class="flex-1 overflow-y-auto overscroll-contain px-4 py-5 scroll-smooth sm:px-6">
              <div v-if="!turns.length" class="relative overflow-hidden rounded-[28px] border border-dashed border-black/10 bg-white/68 p-6 dark:border-white/10 dark:bg-white/[0.03] sm:p-8">
                <div class="relative z-10">
                  <div class="text-[10px] font-black uppercase tracking-[0.28em] text-text-tertiary">Stage Blocking</div>
                  <div class="mt-4 max-w-2xl text-2xl font-black tracking-tight text-text-primary sm:text-3xl">
                    给一个失衡瞬间，<br/>让镜头动起来。
                  </div>
                  <p class="mt-4 max-w-2xl text-sm leading-relaxed text-text-secondary">
                    这不是分支选择器，而是持续接戏。你负责下一步动作，导演组把局势往前顶。
                  </p>
                  
                  <div class="mt-8 grid gap-4 lg:grid-cols-3">
                    <div v-for="role in (['logic', 'emotion', 'twist'] as const)" :key="role" class="rounded-2xl border p-4 transition-colors" :class="ROLE_META[role].surface">
                      <div class="flex items-center gap-2 mb-2">
                        <component :is="ROLE_META[role].icon" :size="14" :stroke-width="4" :class="ROLE_META[role].accent" />
                        <span class="text-[10px] font-black uppercase tracking-widest" :class="ROLE_META[role].accent">{{ ROLE_META[role].label }}</span>
                      </div>
                      <p class="text-xs text-text-secondary leading-relaxed">{{ ROLE_META[role].title }}</p>
                    </div>
                  </div>
                </div>
              </div>

              <template v-else>
                <div class="relative space-y-6 pl-4 sm:pl-6">
                  <!-- Timeline line -->
                  <div class="absolute bottom-6 left-[7px] top-4 w-px bg-gradient-to-b from-accent/40 via-cyan-400/20 to-transparent sm:left-[9px]"></div>

                  <div v-for="turn in turns" :key="turn.id" class="relative" data-story-live-turn>
                    <!-- Dot -->
                    <div class="absolute left-[-15px] top-4 h-3 w-3 rounded-full border border-accent/30 bg-surface-0 shadow-[0_0_0_4px_rgba(99,102,241,0.08)] sm:left-[-18px]"></div>

                    <article class="overflow-hidden rounded-[24px] border border-black/5 bg-white/80 p-4 shadow-sm dark:border-white/10 dark:bg-white/5 sm:p-6">
                      <div class="mb-4 flex items-start justify-between gap-4">
                        <div class="min-w-0 flex-1">
                          <div class="text-[9px] font-black uppercase tracking-[0.28em] text-accent mb-1">你的回合</div>
                          <p class="text-base font-black tracking-tight text-text-primary">{{ turn.userText }}</p>
                        </div>
                      </div>

                      <div class="grid gap-4">
                        <!-- Logic Column -->
                        <div class="rounded-2xl border border-cyan-400/20 bg-cyan-500/[0.06] p-4">
                          <div class="flex items-center gap-2 mb-2">
                            <Target :size="14" :stroke-width="4" class="text-cyan-400" />
                            <span class="text-[10px] font-black uppercase tracking-widest text-cyan-400">导演指令</span>
                          </div>
                          <div class="md-body text-sm text-text-primary" v-html="turn.responses.logic.text ? renderMarkdown(turn.responses.logic.text) : '...'" />
                        </div>

                        <!-- Emotion -->
                        <div class="rounded-2xl border border-rose-400/20 bg-rose-500/[0.06] p-4">
                          <div class="flex items-center gap-2 mb-2">
                            <Heart :size="14" :stroke-width="4" class="text-rose-400" />
                            <span class="text-[10px] font-black uppercase tracking-widest text-rose-400">氛围</span>
                          </div>
                          <div class="md-body text-sm text-text-primary" v-html="turn.responses.emotion.text ? renderMarkdown(turn.responses.emotion.text) : '...'" />
                        </div>
                        <!-- Twist (only when triggered) -->
                        <div v-if="turn.responses.twist.text" class="rounded-2xl border border-amber-400/20 bg-amber-500/[0.06] p-4">
                          <div class="flex items-center gap-2 mb-2">
                            <Wand2 :size="14" :stroke-width="4" class="text-amber-400" />
                            <span class="text-[10px] font-black uppercase tracking-widest text-amber-400">信号</span>
                          </div>
                          <div class="md-body text-sm text-text-primary" v-html="renderMarkdown(turn.responses.twist.text)" />
                        </div>
                      </div>
                    </article>
                  </div>
                </div>
              </template>
            </div>

            <!-- Input Bar: Fixed at bottom of stage -->
            <div v-if="started" class="shrink-0 border-t border-black/[0.03] bg-white/40 p-4 backdrop-blur-md dark:border-white/5 sm:px-6 sm:pb-6">
              <div class="mx-auto max-w-3xl">
                <div v-if="latestDirectorCue" class="mb-3 flex items-center gap-2 px-1">
                  <div class="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse"></div>
                  <span class="text-[10px] font-black uppercase tracking-[0.2em] text-cyan-500/80">{{ latestDirectorCue }}</span>
                </div>

                <!-- Ending confirmation -->
                <div v-if="pendingEndingText" class="mb-3 flex items-center justify-between gap-2 rounded-xl bg-red-500/[0.06] border border-red-500/20 px-3 py-2">
                  <span class="text-xs text-red-400 font-medium">确认结束这个故事？</span>
                  <div class="flex gap-1.5">
                    <button
                      @click="confirmEnding"
                      class="rounded-lg bg-red-500 px-3 py-1 text-[9px] font-black uppercase tracking-widest text-white transition-all hover:bg-red-600 active:scale-95"
                    >
                      确认
                    </button>
                    <button
                      @click="dismissEnding"
                      class="rounded-lg bg-white/10 px-3 py-1 text-[9px] font-black uppercase tracking-widest text-text-secondary transition-all hover:bg-white/20 active:scale-95"
                    >
                      继续
                    </button>
                  </div>
                </div>

                <div class="relative">
                  <textarea
                    v-model="userInput"
                    rows="2"
                    class="w-full rounded-[24px] border border-black/5 bg-black/[0.03] px-5 py-4 pr-14 text-sm leading-relaxed text-text-primary outline-none transition-all placeholder:text-text-quaternary focus:border-accent/40 focus:ring-2 focus:ring-accent/10 dark:border-white/10 dark:bg-white/[0.05]"
                    :disabled="processing || wrapBusy"
                    placeholder="决定下一步动作..."
                    @keydown.enter.prevent="continueStory"
                  />
                  <button
                    class="absolute bottom-3 right-3 flex h-10 w-10 items-center justify-center rounded-full bg-accent text-white shadow-lg transition-all hover:scale-105 active:scale-95 disabled:opacity-40"
                    :disabled="processing || wrapBusy || !userInput.trim()"
                    @click="continueStory"
                  >
                    <Send v-if="!processing" :size="18" :stroke-width="3.5" />
                    <Loader2 v-else class="animate-spin" :size="18" :stroke-width="3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Right Sidebar: Stats & Wraps (Desktop only or Drawer on mobile) -->
          <aside class="hidden w-80 shrink-0 flex-col overflow-y-auto border-white/10 bg-black/[0.01] p-6 xl:flex dark:bg-white/[0.01]">
            <div class="space-y-6">
              <!-- Models -->
              <div class="rounded-3xl border border-black/5 bg-white/60 p-5 dark:border-white/10 dark:bg-white/[0.03]">
                <div class="text-[10px] font-black uppercase tracking-[0.28em] text-text-tertiary mb-4">导演组</div>
                <div class="space-y-3">
                  <div v-for="card in roleCards" :key="card.role" class="rounded-2xl border p-3 transition-all" :class="card.ready ? ROLE_META[card.role].surface : 'border-dashed border-black/10 opacity-50'">
                    <div class="flex items-center gap-2 mb-1.5">
                      <component :is="ROLE_META[card.role].icon" :size="12" :stroke-width="4" :class="ROLE_META[card.role].accent" />
                      <span class="text-[9px] font-black uppercase tracking-widest" :class="ROLE_META[card.role].accent">{{ ROLE_META[card.role].label }}</span>
                    </div>
                    <div class="text-xs font-black tracking-tight text-text-primary">{{ card.modelName }}</div>
                    <div class="text-[9px] font-black text-text-tertiary">{{ card.ready ? '已锁定场景' : '首轮锁定' }}</div>
                  </div>
                </div>
              </div>

              <!-- Wrap -->
              <div class="rounded-3xl border border-black/5 bg-white/60 p-5 dark:border-white/10 dark:bg-white/[0.03]">
                <div class="flex items-center justify-between mb-4">
                  <div class="text-[10px] font-black uppercase tracking-[0.28em] text-text-tertiary">制作</div>
                  <Sparkles v-if="wrapBusy" class="animate-pulse text-accent" :size="14" />
                </div>
                <div class="grid grid-cols-2 gap-2">
                  <button @click="storyLiveStore.generateWrap('story')" :disabled="!turns.length || wrapBusy" class="rounded-xl bg-black/[0.03] py-2 text-[9px] font-black uppercase tracking-widest text-text-secondary hover:bg-accent/10 hover:text-accent transition-colors disabled:opacity-40">故事</button>
                  <button @click="storyLiveStore.generateWrap('script')" :disabled="!turns.length || wrapBusy" class="rounded-xl bg-black/[0.03] py-2 text-[9px] font-black uppercase tracking-widest text-text-secondary hover:bg-accent/10 hover:text-accent transition-colors disabled:opacity-40">剧本</button>
                </div>
                <div v-if="wrapResult" class="mt-4 max-h-60 overflow-y-auto rounded-xl bg-black/[0.02] p-3 text-xs leading-relaxed text-text-secondary dark:bg-white/[0.02]">
                  <div class="md-body text-xs" v-html="renderMarkdown(wrapResult.text || '')"></div>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
/* V3 Industrial Stroke Enforcement */
:deep(svg) { stroke-width: 3.5px !important; }

.page-enter-active, .page-leave-active { transition: all 0.4s cubic-bezier(0.32, 0.72, 0, 1); }
.page-enter-from { opacity: 0; transform: translateY(10px); }
.page-leave-to { opacity: 0; transform: translateY(-10px); }

.no-scrollbar::-webkit-scrollbar { display: none; }
</style>
