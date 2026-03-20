<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ArrowRight, Heart, Loader2, RotateCcw, ShieldCheck, Sparkles, Target, ArrowLeft } from 'lucide-vue-next'
import { useStoryLiteV2Store } from '@/stores/storyLiteV2'
import { STORY_LITE_V2_DEFAULT_MAX_ROUNDS, STORY_LITE_V2_ROLES } from '@/features/play-modes/story-lite-v2'
import type { StoryLiteV2RiskLevel, StoryLiteV2Role } from '@/features/play-modes/story-lite-v2/types'
import type { EndingGrade } from '@/features/play-modes/shared'

const router = useRouter()
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
  <div class="h-full flex flex-col items-center p-3 sm:p-4 lg:p-6 overflow-hidden relative">
    <section
      class="w-full max-w-6xl flex-1 flex flex-col glass-v3 rounded-[32px] lg:rounded-[40px] shadow-2xl border border-white/10 overflow-hidden relative z-10 transition-all duration-700"
    >
      <!-- 背景光效 -->
      <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(74,222,128,0.05),transparent_28%),radial-gradient(circle_at_80%_20%,rgba(56,189,248,0.08),transparent_30%)]" />

      <!-- 主体内容 -->
      <div class="relative grid flex-1 gap-0 lg:grid-cols-[1fr_0.9fr] overflow-hidden">
        <!-- 左侧：AI 回复区 -->
        <div class="flex flex-col border-b border-white/5 lg:border-b-0 lg:border-r overflow-hidden">
          <div class="flex-1 px-6 py-8 overflow-y-auto custom-scrollbar">
            <!-- 开始界面 -->
            <div v-if="!gameStarted" class="flex flex-col items-center justify-center h-full max-w-lg mx-auto py-10">
              <div class="w-20 h-20 rounded-[32px] bg-accent/10 shadow-xl flex items-center justify-center mb-8 rotate-3">
                <Sparkles :size="32" :stroke-width="3.5" class="text-accent" />
              </div>
              <h2 class="text-3xl font-black text-text-primary mb-4 tracking-tight uppercase text-center">假如模拟器</h2>
              <p class="text-sm text-text-tertiary mb-10 text-center leading-relaxed opacity-80">
                输入一个“假如”场景，3 位 AI 将扮演不同角色与你共演一段不可思议的剧情走向。
              </p>

              <!-- 种子输入 -->
              <div class="w-full space-y-4">
                <div class="flex items-center gap-3 px-5 py-4 rounded-2xl bg-white/5 border border-white/10 focus-within:border-accent/40 focus-within:ring-4 focus-within:ring-accent/5 transition-all">
                  <input
                    v-model="seedInput"
                    type="text"
                    placeholder="例如：假如我醒来发现在太空船里..."
                    class="flex-1 bg-transparent text-sm text-text-primary outline-none placeholder:text-text-quaternary"
                    @keydown.enter.prevent="startGame"
                  />
                </div>
                <button
                  @click="startGame"
                  :disabled="processing"
                  class="w-full py-4 rounded-2xl bg-accent text-white font-black uppercase tracking-[0.2em] text-xs hover:opacity-90 transition-all active:scale-[0.98] lab-breathing-btn shadow-lg shadow-accent/20"
                >
                  开启时空裂痕
                </button>
              </div>

              <!-- 快速开始 -->
              <div class="mt-8 flex flex-wrap gap-2 justify-center">
                <button
                  v-for="suggestion in ['假如你是特工，拿到了一份机密文件', '假如你醒来发现在太空船里', '假如你发现了一个时间循环']"
                  :key="suggestion"
                  @click="seedInput = suggestion; startGame()"
                  :disabled="processing"
                  class="px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-[10px] font-black uppercase tracking-widest text-text-tertiary hover:bg-white/10 hover:text-text-primary transition-all"
                >
                  {{ suggestion }}
                </button>
              </div>
            </div>

            <!-- 游戏进行界面 -->
            <template v-else>
              <!-- 情境描述 -->
              <div v-if="currentScene?.premise" class="mb-10 animate-fade-in">
                <div class="flex items-center gap-2 mb-4">
                  <div class="w-1 h-4 bg-accent rounded-full"></div>
                  <span class="text-[10px] font-black uppercase tracking-[0.24em] text-text-tertiary">
                    场景描述 · SCENE
                  </span>
                </div>
                <p class="text-base leading-relaxed text-text-primary lab-flowing-text italic opacity-90">
                  {{ currentScene.premise }}
                </p>
              </div>

              <!-- 三个 AI 的回复 -->
              <div v-if="currentScene?.responses?.length" class="space-y-6">
                <div
                  v-for="res in currentScene.responses"
                  :key="res.role"
                  class="rounded-[28px] border p-6 transition-all animate-fade-in"
                  :class="getRoleMeta(res.role).accent.includes('cyan') ? 'border-cyan-400/20 bg-cyan-500/[0.04]' : getRoleMeta(res.role).accent.includes('rose') ? 'border-rose-400/20 bg-rose-500/[0.06]' : 'border-amber-400/20 bg-amber-500/[0.04]'"
                >
                  <div class="flex items-center gap-3 mb-4">
                    <div class="w-8 h-8 rounded-xl flex items-center justify-center bg-white/5 border border-white/10">
                      <component
                        :is="getRoleMeta(res.role).icon === 'Target' ? Target : getRoleMeta(res.role).icon === 'Heart' ? Heart : Sparkles"
                        :size="14"
                        :stroke-width="4"
                        :class="getRoleMeta(res.role).accent"
                      />
                    </div>
                    <span class="text-[10px] font-black uppercase tracking-[0.26em]" :class="getRoleMeta(res.role).accent">
                      {{ getRoleMeta(res.role).label }}
                    </span>
                    <span class="text-[8px] font-black uppercase tracking-[0.2em] text-text-quaternary ml-auto opacity-40">
                      {{ res.modelName }}
                    </span>
                  </div>
                  <p class="text-sm leading-relaxed text-text-secondary lab-flowing-text">{{ res.text }}</p>
                </div>
              </div>

              <!-- 加载中 -->
              <div v-if="processing" class="flex flex-col items-center justify-center py-10">
                <Loader2 :size="24" class="text-accent animate-spin mb-3 opacity-40" />
                <p class="text-[10px] font-black uppercase tracking-widest text-text-tertiary opacity-40">AI 正在构思下一幕...</p>
              </div>
            </template>
          </div>
        </div>

        <!-- 右侧：选择区 -->
        <div class="flex flex-col bg-white/5 backdrop-blur-sm">
          <div class="border-b border-white/5 px-6 py-6">
            <div class="text-[10px] font-black uppercase tracking-[0.32em] text-text-tertiary">行动中枢 · ACTION</div>
            <div class="mt-2 text-xl font-black tracking-tight text-text-primary uppercase">
              {{ isCompleted ? '命定的结局' : '你将回应谁？' }}
            </div>
          </div>

          <div class="flex-1 flex flex-col px-6 py-6 overflow-y-auto custom-scrollbar">
            <!-- 结局展示 -->
            <div v-if="isCompleted && resultCard" class="flex-1 flex flex-col animate-fade-in">
              <div class="rounded-[36px] border border-accent/20 bg-accent/5 p-8 shadow-inner relative overflow-hidden group">
                <div class="absolute -right-8 -top-8 w-32 h-32 bg-accent/10 blur-3xl group-hover:scale-150 transition-transform duration-1000"></div>
                <div class="text-[10px] font-black uppercase tracking-[0.32em] text-accent mb-4">结局已解锁</div>
                <div class="text-2xl font-black leading-tight tracking-tight text-text-primary uppercase">
                  {{ resultCard.title }}
                </div>
                <p class="mt-6 text-sm leading-relaxed text-text-secondary opacity-90">{{ resultCard.summary }}</p>
                <p v-if="currentScene?.ending?.epilogue" class="mt-4 text-xs italic leading-relaxed text-accent/80 font-medium">
                  {{ currentScene.ending.epilogue }}
                </p>
              </div>
              <button
                class="mt-6 w-full py-4 rounded-2xl bg-text-primary text-surface-1 text-[10px] font-black uppercase tracking-[0.34em] transition-all hover:opacity-90 active:scale-[0.98] shadow-xl"
                @click="restartGame"
              >
                重返假如
              </button>
            </div>

            <!-- 选择按钮 -->
            <div v-else-if="currentScene?.choices?.length" class="grid gap-4">
              <button
                v-for="choice in currentScene.choices"
                :key="choice.id"
                class="group flex flex-col justify-between rounded-[28px] border p-6 text-left transition-all duration-300 active:scale-[0.98] relative overflow-hidden"
                :class="riskTheme(choice.risk).shell"
                @click="makeChoice(choice.id)"
              >
                <div class="relative z-10">
                  <div class="flex items-center justify-between gap-3 mb-4">
                    <span
                      class="inline-flex items-center rounded-lg border px-2 py-1 text-[8px] font-black uppercase tracking-[0.24em]"
                      :class="riskTheme(choice.risk).badge"
                    >
                      {{ riskLabel(choice.risk) }}
                    </span>
                    <span v-if="choice.targetRole" class="text-[8px] font-black uppercase tracking-[0.22em] text-text-tertiary opacity-40">
                      TARGET: {{ getRoleMeta(choice.targetRole).label }}
                    </span>
                  </div>

                  <div class="flex items-start gap-4">
                    <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/5 border border-white/10 group-hover:bg-accent group-hover:text-white transition-all">
                      <ArrowRight :size="18" :stroke-width="3.5" />
                    </div>
                    <div class="min-w-0">
                      <div class="text-lg font-black leading-tight tracking-tight text-text-primary uppercase">
                        {{ choice.label }}
                      </div>
                      <p v-if="choice.hint" class="mt-2 text-xs leading-relaxed text-text-tertiary opacity-60 line-clamp-2">
                        {{ choice.hint }}
                      </p>
                    </div>
                  </div>
                </div>
              </button>
            </div>

            <!-- 玩法提示 -->
            <div v-if="!isCompleted && !processing && currentScene?.choices?.length" class="mt-6 p-5 rounded-2xl border border-white/5 bg-white/5">
              <div class="flex items-center gap-2 mb-2">
                <ShieldCheck :size="14" :stroke-width="4" class="text-emerald-400" />
                <span class="text-[9px] font-black uppercase tracking-[0.26em] text-emerald-400">实验协议</span>
              </div>
              <p class="text-[11px] leading-relaxed text-text-tertiary opacity-60">
                该实验采用 3 位 AI 同时输出模式。你的每一次抉择都将定向反馈给其中一位扮演者，并以此重塑时空走向。
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
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

.animate-fade-in {
  animation: fadeIn 0.6s cubic-bezier(0.32, 0.72, 0, 1) forwards;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 10px;
}
</style>