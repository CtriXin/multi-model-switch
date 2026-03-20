<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ArrowRight, Heart, Loader2, RotateCcw, ShieldCheck, Sparkles, Target } from 'lucide-vue-next'
import { useStoryLiteV2Store } from '@/stores/storyLiteV2'
import { STORY_LITE_V2_DEFAULT_MAX_ROUNDS, STORY_LITE_V2_ROLES } from '@/features/play-modes/story-lite-v2'
import type { StoryLiteV2RiskLevel, StoryLiteV2Role } from '@/features/play-modes/story-lite-v2/types'
import type { EndingGrade } from '@/features/play-modes/shared'

const storyStore = useStoryLiteV2Store()

const {
  currentScene,
  round,
  processing,
  error,
  useMock,
  modelAssignment,
  isCompleted,
  isStarted,
} = storeToRefs(storyStore)

const seedInput = ref('公路异变悬疑')
const gameStarted = computed(() => isStarted.value || processing.value)

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

function getRoleMeta(role: StoryLiteV2Role) {
  return STORY_LITE_V2_ROLES[role]
}

function riskLabel(risk: StoryLiteV2RiskLevel): string {
  return risk === 'safe' ? '安全' : risk === 'risky' ? '有风险' : risk === 'dangerous' ? '危险' : risk
}

function riskTheme(risk: StoryLiteV2RiskLevel) {
  if (risk === 'safe') {
    return {
      shell: 'border-emerald-400/30 bg-emerald-300/[0.08] hover:bg-emerald-300/[0.14]',
      badge: 'bg-emerald-300/15 text-emerald-100 border-emerald-300/30',
      icon: 'bg-emerald-300/15 text-emerald-100',
    }
  }
  if (risk === 'risky') {
    return {
      shell: 'border-amber-400/30 bg-amber-300/[0.08] hover:bg-amber-300/[0.14]',
      badge: 'bg-amber-300/15 text-amber-100 border-amber-300/30',
      icon: 'bg-amber-300/15 text-amber-100',
    }
  }
  return {
    shell: 'border-red-400/30 bg-red-300/[0.08] hover:bg-red-300/[0.14]',
    badge: 'bg-red-300/15 text-red-100 border-red-300/30',
    icon: 'bg-red-300/15 text-red-100',
  }
}

async function startGame() {
  storyStore.init(seedInput.value)
  await storyStore.startGame()
}

async function makeChoice(choiceId: string) {
  await storyStore.makeChoice(choiceId)
}

function restartGame() {
  storyStore.restart()
}

onMounted(() => {
  storyStore.init(seedInput.value)
})
</script>

<template>
  <div class="h-full overflow-y-auto bg-surface-0 px-3 py-3 sm:px-4 lg:px-6">
    <section
      class="relative mx-auto flex min-h-[calc(100vh-2rem)] w-full max-w-6xl flex-col overflow-hidden rounded-[36px] border border-[#2f323b] bg-[#111318] text-[#f4efe6] shadow-[0_40px_120px_rgba(9,12,18,0.38)]"
    >
      <!-- 背景光效 -->
      <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(74,222,128,0.08),transparent_28%),radial-gradient(circle_at_80%_20%,rgba(56,189,248,0.12),transparent_30%)]" />

      <!-- 头部 -->
      <div class="relative flex items-center justify-between border-b border-white/10 px-5 py-4 sm:px-7">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-3">
            <span class="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[9px] font-black uppercase tracking-[0.34em] text-[#c8c2b7]">
              StoryLite V2
            </span>
            <span v-if="currentScene?.chapter" class="inline-flex items-center rounded-full border border-[#3b6cf6]/30 bg-[#3b6cf6]/10 px-3 py-1 text-[9px] font-black uppercase tracking-[0.26em] text-[#8db1ff]">
              {{ currentScene.chapter }}
            </span>
          </div>
          <div class="mt-3 flex items-center gap-3">
            <div class="flex h-11 w-11 items-center justify-center rounded-full bg-[#4455ff] shadow-[0_0_40px_rgba(68,85,255,0.45)]">
              <Sparkles :size="16" :stroke-width="3.5" class="text-white" />
            </div>
            <div class="min-w-0">
              <div class="text-[10px] font-black uppercase tracking-[0.34em] text-[#888d9d]">多 AI 共演</div>
              <div class="truncate text-2xl font-[900] tracking-[-0.08em] text-white" style="font-family: 'Syne', sans-serif">
                {{ currentScene?.title || '假如模拟器' }}
              </div>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <div class="hidden rounded-full border border-white/10 bg-white/5 px-3 py-2 text-right sm:block">
            <div class="text-[9px] font-black uppercase tracking-[0.24em] text-[#888d9d]">Round</div>
            <div class="text-sm font-black tracking-[0.18em] text-white">{{ round }}/{{ STORY_LITE_V2_DEFAULT_MAX_ROUNDS }}</div>
          </div>
          <button
            v-if="gameStarted"
            class="flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/5 text-[#c8c2b7] transition-all hover:bg-white/10 hover:text-white active:scale-95"
            @click="restartGame"
          >
            <RotateCcw :size="16" :stroke-width="3.5" />
          </button>
        </div>
      </div>

      <!-- 主体内容 -->
      <div class="relative grid flex-1 gap-0 lg:grid-cols-[1fr_0.9fr]">
        <!-- 左侧：AI 回复区 -->
        <div class="flex flex-col border-b border-white/10 lg:border-b-0">
          <div class="flex-1 border-b border-white/10 px-5 py-5 sm:px-7 overflow-y-auto">
            <!-- 开始界面 -->
            <div v-if="!gameStarted" class="flex flex-col items-center justify-center h-full py-20">
              <div class="w-20 h-20 rounded-full bg-[#4455ff] shadow-[0_0_60px_rgba(68,85,255,0.5)] flex items-center justify-center mb-6">
                <Sparkles :size="32" :stroke-width="3" class="text-white" />
              </div>
              <h2 class="text-3xl font-black text-white mb-2" style="font-family: 'Syne', sans-serif">假如模拟器</h2>
              <p class="text-text-secondary mb-8 text-center max-w-md">
                输入一个"假如"场景，3 个 AI 将扮演不同角色与你共演剧情
              </p>

              <!-- 模型选择提示 -->
              <div class="w-full max-w-md mb-6">
                <div v-if="useMock" class="rounded-2xl border border-amber-400/20 bg-amber-500/[0.08] px-4 py-3 text-sm text-amber-300">
                  <p class="font-black uppercase tracking-[0.2em] text-[10px] mb-2">Demo 模式</p>
                  <p>当前使用演示模型，将显示预设剧情数据。</p>
                  <p class="mt-2 text-xs opacity-70">配置真实 API Key 后体验完整 AI 生成剧情。</p>
                </div>
                <div v-else-if="modelAssignment" class="rounded-2xl border border-emerald-400/20 bg-emerald-500/[0.08] px-4 py-3 text-sm text-emerald-300">
                  <p class="font-black uppercase tracking-[0.2em] text-[10px] mb-2">AI 已就绪</p>
                  <div class="flex gap-3 text-xs">
                    <span>引路人：{{ storyStore.getModelName(modelAssignment.guide) }}</span>
                    <span>·</span>
                    <span>伙伴：{{ storyStore.getModelName(modelAssignment.partner) }}</span>
                    <span>·</span>
                    <span>变量：{{ storyStore.getModelName(modelAssignment.variable) }}</span>
                  </div>
                </div>
              </div>

              <!-- 种子输入 -->
              <div class="w-full max-w-md space-y-3">
                <div class="flex items-center gap-2 px-4 py-3 rounded-xl bg-white/5 border border-white/10">
                  <input
                    v-model="seedInput"
                    type="text"
                    placeholder="例如：假如我是特工，拿到了一份机密文件..."
                    class="flex-1 bg-transparent text-sm text-white outline-none"
                    @keydown.enter.prevent="startGame"
                  />
                </div>
                <button
                  @click="startGame"
                  :disabled="processing"
                  class="w-full py-4 rounded-2xl bg-accent text-white font-black uppercase tracking-[0.2em] text-sm hover:opacity-90 transition-all active:scale-[0.98]"
                >
                  开始剧情
                </button>
              </div>

              <!-- 快速开始 -->
              <div class="mt-6 flex flex-wrap gap-2 justify-center">
                <button
                  v-for="suggestion in ['假如你是特工，拿到了一份机密文件', '假如你醒来发现在太空船里', '假如你发现了一个时间循环']"
                  :key="suggestion"
                  @click="seedInput = suggestion; startGame()"
                  :disabled="processing"
                  class="px-3 py-1.5 rounded-full bg-white/5 text-xs text-text-secondary hover:bg-white/10 hover:text-white transition-all"
                >
                  {{ suggestion }}
                </button>
              </div>
            </div>

            <!-- 游戏进行界面 -->
            <template v-else>
              <!-- 错误提示 -->
              <div v-if="error" class="mb-4 rounded-2xl border border-red-400/20 bg-red-500/[0.08] px-4 py-3 text-sm text-red-300">
                {{ error }}
              </div>

              <!-- Mock 模式提示 -->
              <div v-if="useMock && isStarted" class="mb-4 rounded-2xl border border-amber-400/20 bg-amber-500/[0.08] px-4 py-3 text-xs text-amber-300">
                <span class="font-black uppercase tracking-[0.2em]">Demo Mode</span> · 当前显示预设剧情数据
              </div>

              <!-- 情境描述 -->
              <div v-if="currentScene?.premise" class="mb-6 max-w-2xl">
                <div class="flex flex-wrap items-center gap-2 mb-3">
                  <span class="inline-flex items-center rounded-full bg-white/5 px-3 py-1 text-[9px] font-black uppercase tracking-[0.24em] text-[#d6d0c4]">
                    {{ currentScene.chapter }}
                  </span>
                  <span class="inline-flex items-center rounded-full border border-white/10 px-3 py-1 text-[9px] font-black uppercase tracking-[0.24em] text-[#888d9d]">
                    3 位 AI 共演
                  </span>
                </div>
                <p class="text-lg leading-8 text-[#c8c2b7]">
                  {{ currentScene.premise }}
                </p>
              </div>

              <!-- 加载中 -->
              <div v-if="processing && !currentScene?.responses?.length" class="flex flex-col items-center justify-center py-20">
                <Loader2 :size="32" class="text-accent animate-spin mb-4" />
                <p class="text-text-secondary text-sm">AI 正在构建剧情...</p>
              </div>

              <!-- 三个 AI 的回复 -->
              <div v-if="currentScene?.responses?.length" class="space-y-4">
                <div
                  v-for="res in currentScene.responses"
                  :key="res.role"
                  class="rounded-[24px] border px-4 py-4 transition-all"
                  :class="getRoleMeta(res.role).accent.includes('cyan') ? 'border-cyan-400/20 bg-cyan-500/[0.06]' : getRoleMeta(res.role).accent.includes('rose') ? 'border-rose-400/20 bg-rose-500/[0.06]' : 'border-amber-400/20 bg-amber-500/[0.06]'"
                >
                  <div class="flex items-center gap-2 mb-3">
                    <component
                      :is="getRoleMeta(res.role).icon === 'Target' ? Target : getRoleMeta(res.role).icon === 'Heart' ? Heart : Sparkles"
                      :size="14"
                      :stroke-width="3.5"
                      :class="getRoleMeta(res.role).accent"
                    />
                    <span class="text-[10px] font-black uppercase tracking-[0.26em]" :class="getRoleMeta(res.role).accent">
                      {{ getRoleMeta(res.role).label }}
                    </span>
                    <span class="text-[8px] font-black uppercase tracking-[0.2em] text-text-tertiary ml-auto">
                      {{ res.modelName }}
                    </span>
                  </div>
                  <p class="text-sm leading-7 text-[#dad4c8]">{{ res.text }}</p>
                  <p v-if="res.tone" class="mt-2 text-[10px] font-black uppercase tracking-[0.24em] text-text-tertiary">
                    语气：{{ res.tone }}
                  </p>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- 右侧：选择区 -->
        <div class="flex flex-col bg-[#0d0f14]">
          <div class="border-b border-white/10 px-5 py-5 sm:px-7">
            <div class="flex items-center justify-between gap-4">
              <div>
                <div class="text-[10px] font-black uppercase tracking-[0.32em] text-[#888d9d]">行动选项</div>
                <div class="mt-2 text-xl font-[900] tracking-[-0.06em] text-white" style="font-family: 'Syne', sans-serif">
                  {{ isCompleted ? '结局已锁定' : '你要回应谁？' }}
                </div>
              </div>
            </div>
          </div>

          <div class="flex flex-1 flex-col px-5 py-5 sm:px-7 overflow-y-auto">
            <!-- 结局展示 -->
            <div v-if="isCompleted && resultCard" class="flex flex-1 flex-col">
              <div class="rounded-[32px] border border-[#4f5eff]/25 bg-gradient-to-br from-[#1a2041] via-[#121624] to-[#0f1117] p-6 shadow-[0_24px_60px_rgba(0,0,0,0.28)]">
                <div class="text-[10px] font-black uppercase tracking-[0.32em] text-[#9dadff]">结局解锁</div>
                <div class="mt-3 text-2xl font-[900] leading-none tracking-[-0.08em] text-white" style="font-family: 'Syne', sans-serif">
                  {{ resultCard.title }}
                </div>
                <p class="mt-4 max-w-xl text-sm leading-7 text-[#d4d9ee]">{{ resultCard.summary }}</p>
                <p v-if="currentScene?.ending?.epilogue" class="mt-3 text-sm italic leading-7 text-[#9dacff]">
                  {{ currentScene.ending.epilogue }}
                </p>
              </div>
              <button
                class="mt-4 inline-flex items-center justify-center rounded-[24px] border border-white/10 bg-white px-5 py-4 text-[10px] font-black uppercase tracking-[0.34em] text-[#111318] transition-all hover:opacity-90 active:scale-[0.98]"
                @click="restartGame"
              >
                再跑一局
              </button>
            </div>

            <!-- 加载中 -->
            <div v-else-if="processing" class="flex flex-col items-center justify-center flex-1 py-20">
              <Loader2 :size="32" class="text-accent animate-spin mb-4" />
              <p class="text-text-secondary text-sm">AI 正在思考剧情走向...</p>
            </div>

            <!-- 选择按钮 -->
            <div v-else-if="currentScene?.choices?.length" class="grid flex-1 gap-4">
              <button
                v-for="choice in currentScene.choices"
                :key="choice.id"
                class="group flex flex-col justify-between rounded-[32px] border p-5 text-left transition-all duration-300 active:scale-[0.985]"
                :class="riskTheme(choice.risk).shell"
                @click="makeChoice(choice.id)"
              >
                <div>
                  <div class="flex items-center justify-between gap-3">
                    <span
                      class="inline-flex items-center rounded-full border px-3 py-1 text-[9px] font-black uppercase tracking-[0.24em]"
                      :class="riskTheme(choice.risk).badge"
                    >
                      {{ riskLabel(choice.risk) }}
                    </span>
                    <span v-if="choice.targetRole" class="text-[8px] font-black uppercase tracking-[0.22em] text-text-tertiary">
                      回应 {{ getRoleMeta(choice.targetRole).label }}
                    </span>
                  </div>

                  <div class="mt-4 flex items-start gap-4">
                    <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full" :class="riskTheme(choice.risk).icon">
                      <ArrowRight :size="18" :stroke-width="3.5" />
                    </div>
                    <div class="min-w-0">
                      <div class="text-xl font-[900] leading-none tracking-[-0.05em] text-white" style="font-family: 'Syne', sans-serif">
                        {{ choice.label }}
                      </div>
                      <p v-if="choice.hint" class="mt-2 text-sm leading-7 text-[#d6d0c4]">
                        {{ choice.hint }}
                      </p>
                    </div>
                  </div>
                </div>
              </button>
            </div>

            <!-- 玩法提示 -->
            <div v-if="!isCompleted && !processing && currentScene?.choices?.length" class="mt-4 rounded-[24px] border border-white/10 bg-white/[0.03] px-4 py-4">
              <div class="flex items-center gap-2">
                <ShieldCheck :size="15" :stroke-width="3.5" class="text-[#7de0a8]" />
                <span class="text-[10px] font-black uppercase tracking-[0.26em] text-[#7de0a8]">玩法说明</span>
              </div>
              <p class="mt-2 text-sm leading-7 text-[#c8c2b7]">
                3 个 AI 扮演不同角色同时输出。选择回应其中一个，你的选择会改变故事走向。
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
