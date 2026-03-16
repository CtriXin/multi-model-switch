<script setup lang="ts">
import { ref, computed, onMounted, inject, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore, getModelColor } from '@/stores/app'
import { useDiscussStore, type DiscussDepth } from '@/stores/discuss'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toast'
import InputBar from '@/components/chat/InputBar.vue'
import ModelChipBar from '@/components/chat/ModelChipBar.vue'
import MarkdownIt from 'markdown-it'
import { sanitizeModelOutput } from '@/utils/modelOutput'
import {
  MessageSquare, CheckCircle, AlertTriangle, Lightbulb,
  ArrowRight, RotateCcw, GitMerge, Zap, Flame, Rocket,
  Gavel, Loader2,
} from 'lucide-vue-next'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const discussStore = useDiscussStore()
const sessionStore = useSessionStore()
const toast = useToastStore()
const platform = inject<import('vue').Ref<string>>('platform')
const restoredDraft = ref('')

const hasModels = computed(() => appStore.selectedModels.length >= 2)

// Depth selector
const selectedDepth = ref<DiscussDepth>('panel')
const depthOptions: { value: DiscussDepth; label: string; desc: string; hint?: string; icon: typeof Zap }[] = [
  { value: 'quick', label: '快速审查', desc: '指定 1-2 个模型审查，最快', icon: Rocket },
  { value: 'panel', label: '全局审查', desc: '每个模型综合评审全场（推荐）', icon: Zap },
  { value: 'full', label: '深度交叉', desc: '每对模型逐一审查，适用于高风险或复杂决策', hint: '输出为结构化观点，非最终方案。可配合 Rollup 生成行动计划。', icon: Flame },
]

// Pending topic — submitted but depth not chosen yet
const pendingTopic = ref<string | null>(null)

onMounted(() => {
  const ctx = route.query.context as string
  if (ctx && hasModels.value && !discussStore.hasResults) {
    pendingTopic.value = ctx
  }
})

function handleSubmit(text: string) {
  restoredDraft.value = ''
  if (!hasModels.value) {
    toast.info('请至少选择 2 个模型')
    return
  }
  // Don't allow new submit while streaming or results exist
  if (discussStore.streaming) return
  if (discussStore.hasResults) {
    toast.info('请先点击「新讨论」重置当前讨论')
    return
  }

  // Show depth selector
  pendingTopic.value = text
}

function startWithDepth() {
  if (!pendingTopic.value) return

  if (!sessionStore.currentSessionId) {
    sessionStore.createSession('discuss')
  }

  discussStore.startDiscussion(pendingTopic.value, appStore.selectedModelIds, selectedDepth.value).then(() => {
    sessionStore.saveCurrentSession()
  })
  pendingTopic.value = null
}

function handleReset() {
  if (discussStore.streaming) return
  discussStore.reset()
  pendingTopic.value = null
  restoredDraft.value = ''
}

async function handleStopAndEdit() {
  const draft = discussStore.stopAndRestoreDraft()
  pendingTopic.value = null
  restoredDraft.value = ''
  await nextTick()
  restoredDraft.value = draft
}

function continueToChat() {
  const sanitizedRollup = sanitizeModelOutput(discussStore.rollupText || '')
  const sanitizedSynthesis = sanitizeModelOutput(discussStore.phase3Text || '')
  // Carry discuss context to chat — prefer rollup if available, fallback to synthesis
  const context = discussStore.rollupText
    ? `[行动计划] ${discussStore.topic}\n\n${sanitizedRollup.content}`
    : discussStore.phase3Text
      ? `[讨论结论] ${discussStore.topic}\n\n${sanitizedSynthesis.content}`
      : discussStore.topic
  router.push({ path: '/chat', query: { context } })
}

function getModelName(id: string): string {
  if (id === '*') return '全体'
  return appStore.models.find(m => m.id === id)?.name ?? id
}

function getProvider(id: string): string {
  return appStore.models.find(m => m.id === id)?.provider ?? 'unknown'
}

const phaseLabels = ['', '独立分析', '交叉审查', '综合结论']
const depthLabel = computed(() => {
  if (discussStore.depth === 'full') return '深度交叉'
  if (discussStore.depth === 'panel') return '全局审查'
  return '快速审查'
})

const sanitizedSynthesis = computed(() => sanitizeModelOutput(discussStore.phase3Text || ''))
const sanitizedRollup = computed(() => sanitizeModelOutput(discussStore.rollupText || ''))
const synthesis = computed(() => md.render(sanitizedSynthesis.value.content || ''))
const rollupHtml = computed(() => md.render(sanitizedRollup.value.content || ''))

function handleRollup() {
  discussStore.startRollup(appStore.selectedModelIds)
}
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="flex-1 overflow-y-auto">
      <!-- Empty state -->
      <div
        v-if="!discussStore.hasResults && !discussStore.streaming && !pendingTopic"
        class="flex flex-col items-center justify-center h-full text-center px-6"
      >
        <div class="w-16 h-16 rounded-2xl bg-purple-500/10 flex items-center justify-center mb-4 animate-fade-in">
          <GitMerge :size="28" class="text-purple-400" />
        </div>
        <h2 class="text-lg font-semibold text-text-primary mb-2 animate-slide-up">
          多模型讨论
        </h2>
        <p class="text-sm text-text-secondary max-w-sm animate-slide-up" style="animation-delay: 50ms">
          各模型独立分析、交叉审查、最终综合出统一结论
        </p>
        <p v-if="!hasModels" class="text-xs text-text-tertiary mt-4 animate-slide-up" style="animation-delay: 100ms">
          {{ platform === 'ios' ? '点击右上角选择 2 个以上模型' : '从上方模型栏选择 2 个以上模型开始' }}
        </p>
      </div>

      <!-- Depth selector (after topic submitted, before starting) -->
      <div
        v-else-if="pendingTopic && !discussStore.hasResults && !discussStore.streaming"
        class="max-w-2xl mx-auto px-4 py-8"
      >
        <div class="rounded-xl border border-purple-500/20 bg-surface-1 overflow-hidden animate-slide-up">
          <!-- Topic preview -->
          <div class="px-4 py-3 border-b border-border-subtle">
            <span class="text-xs text-text-tertiary">讨论主题</span>
            <p class="text-sm text-text-primary mt-1">{{ pendingTopic }}</p>
          </div>

          <!-- Depth selector -->
          <div class="p-4">
            <p class="text-xs text-text-secondary mb-3">选择讨论深度：</p>
            <div class="grid grid-cols-3 gap-2 mb-4">
              <button
                v-for="opt in depthOptions"
                :key="opt.value"
                @click="selectedDepth = opt.value"
                class="flex flex-col items-center gap-1.5 p-3 rounded-lg border transition-all text-center"
                :class="selectedDepth === opt.value
                  ? 'border-purple-500/40 bg-purple-500/10'
                  : 'border-border-subtle hover:border-border-strong'"
              >
                <component :is="opt.icon" :size="16"
                  :class="selectedDepth === opt.value ? 'text-purple-400' : 'text-text-tertiary'" />
                <span class="text-xs font-medium"
                  :class="selectedDepth === opt.value ? 'text-purple-400' : 'text-text-primary'">
                  {{ opt.label }}
                </span>
                <span class="text-[10px] text-text-tertiary leading-tight">{{ opt.desc }}</span>
              </button>
            </div>

            <!-- Depth hint -->
            <p
              v-if="depthOptions.find(o => o.value === selectedDepth)?.hint"
              class="text-[10px] text-text-tertiary mb-4 px-1 leading-relaxed"
            >
              {{ depthOptions.find(o => o.value === selectedDepth)?.hint }}
            </p>

            <!-- Participating models -->
            <div class="flex items-center gap-2 mb-4">
              <span class="text-xs text-text-tertiary">参与模型：</span>
              <div class="flex items-center gap-1">
                <div
                  v-for="mid in appStore.selectedModelIds"
                  :key="mid"
                  class="w-5 h-5 rounded-md flex items-center justify-center text-[9px] font-bold text-white"
                  :style="{ backgroundColor: getModelColor(getProvider(mid)) }"
                  :title="getModelName(mid)"
                >
                  {{ getModelName(mid).charAt(0) }}
                </div>
              </div>
            </div>

            <button
              @click="startWithDepth"
              class="w-full py-2.5 rounded-lg bg-purple-500 hover:bg-purple-600
                     text-white text-sm font-medium transition-colors active:scale-[0.98]"
            >
              开始讨论
            </button>
          </div>
        </div>
      </div>

      <!-- Discussion content -->
      <div v-else class="max-w-5xl mx-auto px-4 py-4">
        <!-- Topic + depth badge -->
        <div class="mb-6 animate-slide-up">
          <div class="flex items-center gap-2">
            <span class="text-xs text-text-tertiary uppercase tracking-wider">讨论主题</span>
            <span class="text-[9px] px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-400 font-medium">
              {{ depthLabel }}
            </span>
          </div>
          <p class="text-sm text-text-primary mt-1">{{ discussStore.topic }}</p>
        </div>

        <!-- Phase timeline -->
        <div class="relative">
          <!-- Timeline line -->
          <div class="absolute left-[15px] top-0 bottom-0 w-px bg-border-subtle" />

          <!-- Phase 1 -->
          <div class="relative pl-10 pb-8 animate-slide-up" style="animation-delay: 50ms">
            <div class="absolute left-0 top-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
              :class="discussStore.phase >= 1 ? 'bg-violet-500/20 text-violet-400 ring-2 ring-violet-500/30' : 'bg-surface-3 text-text-tertiary'">
              1
            </div>
            <h3 class="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
              {{ phaseLabels[1] }}
              <span v-if="discussStore.phase === 1 && discussStore.streaming"
                class="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse_dot" />
              <CheckCircle v-else-if="discussStore.phase > 1" :size="14" class="text-green-400" />
            </h3>

            <div v-if="discussStore.phase1Results.length" class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div
                v-for="(r, i) in discussStore.phase1Results"
                :key="r.model"
                class="card p-3 animate-scale-in"
                :style="{ animationDelay: i * 80 + 'ms' }"
              >
                <div class="flex items-center gap-2 mb-2">
                  <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: getModelColor(getProvider(r.model)) }" />
                  <span class="text-xs font-medium text-text-primary">{{ getModelName(r.model) }}</span>
                </div>
                <div class="space-y-1.5 text-xs text-text-secondary">
                  <p><span class="text-text-tertiary">方案:</span> {{ r.data.approach }}</p>
                  <p><span class="text-text-tertiary">理由:</span> {{ r.data.reasoning }}</p>
                  <div class="flex flex-wrap gap-1 mt-1">
                    <span
                      v-for="risk in r.data.risks"
                      :key="risk"
                      class="px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 text-[10px]"
                    >{{ risk }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-else-if="discussStore.phase === 1" class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div v-for="i in appStore.selectedModels.length" :key="i" class="card p-3 space-y-2">
                <div class="h-3 bg-surface-3 rounded animate-pulse w-1/3" />
                <div class="h-3 bg-surface-3 rounded animate-pulse w-full" />
                <div class="h-3 bg-surface-3 rounded animate-pulse w-2/3" />
              </div>
            </div>
          </div>

          <!-- Phase 2 -->
          <div v-if="discussStore.phase >= 2" class="relative pl-10 pb-8 animate-slide-up">
            <div class="absolute left-0 top-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
              :class="discussStore.phase >= 2 ? 'bg-pink-500/20 text-pink-400 ring-2 ring-pink-500/30' : 'bg-surface-3 text-text-tertiary'">
              2
            </div>
            <h3 class="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
              {{ depthLabel }}
              <span v-if="discussStore.phase === 2 && discussStore.streaming"
                class="w-1.5 h-1.5 rounded-full bg-pink-400 animate-pulse_dot" />
              <CheckCircle v-else-if="discussStore.phase > 2" :size="14" class="text-green-400" />
            </h3>

            <div class="space-y-2">
              <div
                v-for="(r, i) in discussStore.phase2Results"
                :key="`${r.reviewer}-${r.target}`"
                class="card p-3 animate-slide-right"
                :style="{ animationDelay: i * 60 + 'ms' }"
              >
                <div class="flex items-center gap-2 mb-2 text-xs">
                  <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: getModelColor(getProvider(r.reviewer)) }" />
                  <span class="font-medium text-text-primary">{{ getModelName(r.reviewer) }}</span>
                  <ArrowRight :size="10" class="text-text-tertiary" />
                  <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: getModelColor(getProvider(r.target)) }" />
                  <span class="text-text-secondary">{{ getModelName(r.target) }}</span>
                </div>
                <div class="space-y-1 text-xs">
                  <p class="flex items-start gap-1.5">
                    <CheckCircle :size="12" class="text-green-400 shrink-0 mt-0.5" />
                    <span class="text-text-secondary">{{ r.data.agreement }}</span>
                  </p>
                  <p class="flex items-start gap-1.5">
                    <AlertTriangle :size="12" class="text-amber-400 shrink-0 mt-0.5" />
                    <span class="text-text-secondary">{{ r.data.challenge }}</span>
                  </p>
                  <p class="flex items-start gap-1.5">
                    <Lightbulb :size="12" class="text-blue-400 shrink-0 mt-0.5" />
                    <span class="text-text-secondary">{{ r.data.betterOption }}</span>
                  </p>
                </div>
              </div>
            </div>
          </div>

          <!-- Phase 3 -->
          <div v-if="discussStore.phase >= 3" class="relative pl-10 pb-4 animate-slide-up">
            <div class="absolute left-0 top-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold
              bg-amber-500/20 text-amber-400 ring-2 ring-amber-500/30">
              3
            </div>
            <h3 class="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
              {{ phaseLabels[3] }}
              <span v-if="discussStore.streaming"
                class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse_dot" />
            </h3>

            <div class="card p-4">
              <template v-if="discussStore.phase3Text">
                <div class="md-body" v-html="synthesis" />
                <div v-if="sanitizedSynthesis.hiddenThink" class="mt-3 text-[10px] italic text-text-tertiary">
                  已隐藏模型思考过程，只展示最终结论
                </div>
              </template>
              <div v-else class="space-y-2">
                <div class="h-3 bg-surface-3 rounded animate-pulse w-full" />
                <div class="h-3 bg-surface-3 rounded animate-pulse w-4/5" />
                <div class="h-3 bg-surface-3 rounded animate-pulse w-3/5" />
              </div>
              <span
                v-if="discussStore.streaming && discussStore.phase3Text"
                class="inline-block w-1.5 h-4 bg-amber-400 ml-0.5 animate-cursor_blink align-text-bottom"
              />
            </div>
          </div>
        </div>

        <!-- Rollup: Action Plan -->
        <div v-if="discussStore.hasResults && !discussStore.streaming" class="mt-6">
          <!-- Rollup trigger button -->
          <div
            v-if="discussStore.rollupPhase === 'idle'"
            class="rounded-xl border border-amber-500/20 bg-surface-1 overflow-hidden animate-slide-up"
          >
            <button
              @click="handleRollup"
              class="flex items-center justify-center gap-2 w-full px-4 py-3 cursor-pointer
                     hover:bg-surface-2 transition-colors group"
            >
              <Gavel :size="14" class="text-amber-400 group-hover:scale-110 transition-transform" />
              <span class="text-sm text-text-secondary group-hover:text-text-primary transition-colors">
                制定行动计划 — Rollup 综合出可落地方案
              </span>
            </button>
            <p class="text-[10px] text-text-tertiary text-center pb-2 px-4">
              将讨论观点综合为唯一方案，包含取舍、风险和下一步行动
            </p>
          </div>

          <!-- Rollup streaming/done -->
          <div
            v-else
            class="rounded-xl border border-amber-500/20 bg-surface-1 overflow-hidden animate-slide-up"
          >
            <div class="flex items-center gap-2 px-4 py-3 border-b border-border-subtle">
              <Gavel :size="14" class="text-amber-400" />
              <span class="text-sm font-medium text-text-primary">行动计划</span>
              <span v-if="discussStore.rollupModel" class="text-[10px] text-text-tertiary bg-surface-3 px-1.5 py-0.5 rounded">
                由 {{ discussStore.rollupModel }} 制定
              </span>
              <Loader2
                v-if="discussStore.rollupPhase === 'streaming'"
                :size="12"
                class="text-amber-400 animate-spin ml-auto"
              />
            </div>
            <div class="p-4">
              <template v-if="discussStore.rollupText">
                <div class="md-body text-sm" v-html="rollupHtml" />
                <div v-if="sanitizedRollup.hiddenThink" class="mt-3 text-[10px] italic text-text-tertiary">
                  已隐藏模型思考过程，只展示行动计划
                </div>
              </template>
              <div v-else class="space-y-2">
                <div class="h-3 bg-surface-3 rounded animate-pulse w-full" />
                <div class="h-3 bg-surface-3 rounded animate-pulse w-4/5" />
                <div class="h-3 bg-surface-3 rounded animate-pulse w-3/5" />
              </div>
              <span
                v-if="discussStore.rollupPhase === 'streaming' && discussStore.rollupText"
                class="inline-block w-1.5 h-4 bg-amber-400 ml-0.5 animate-cursor_blink align-text-bottom"
              />
            </div>
          </div>
        </div>

        <!-- Post-discussion actions -->
        <div
          v-if="discussStore.hasResults && !discussStore.streaming"
          class="flex items-center gap-2 mt-4 animate-fade-in"
        >
          <button @click="continueToChat" class="btn-primary flex items-center gap-1.5 text-xs">
            <MessageSquare :size="13" />
            继续对话
          </button>
          <button
            @click="handleReset"
            class="btn-ghost flex items-center gap-1.5 text-xs"
          >
            <RotateCcw :size="13" />
            新讨论
          </button>
        </div>
      </div>
    </div>

    <!-- Model chip bar -->
    <ModelChipBar />

    <!-- Input -->
    <InputBar
      :disabled="!hasModels || discussStore.hasResults"
      :streaming="discussStore.streaming"
      :placeholder="discussStore.hasResults ? '点击「新讨论」重置后可输入新主题...' : hasModels ? '输入讨论主题...' : '请先选择 2 个以上模型...'"
      :restore-text="restoredDraft"
      @submit="handleSubmit"
      @stop="discussStore.stopDiscussion"
      @stop-and-edit="handleStopAndEdit"
    />
  </div>
</template>
