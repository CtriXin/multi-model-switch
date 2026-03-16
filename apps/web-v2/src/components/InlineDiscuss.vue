<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useAppStore, getModelColor } from '@/stores/app'
import { useDiscussSession, type DiscussDepth } from '@/composables/useDiscussSession'
import { X, Zap, Flame, Rocket, Gavel, Loader2 } from 'lucide-vue-next'
import MarkdownIt from 'markdown-it'
import { sanitizeModelOutput } from '@/utils/modelOutput'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const props = defineProps<{
  prompt: string
  responses: Map<string, { content: string; model?: string }>
  selectedModel: string | null
  modelIds: string[]
}>()

const emit = defineEmits<{
  close: []
}>()

const appStore = useAppStore()
const session = useDiscussSession()

const depthOptions: { value: DiscussDepth; label: string; desc: string; hint?: string; icon: typeof Zap }[] = [
  { value: 'quick', label: '快速审查', desc: '指定 1-2 个模型审查，最快', icon: Rocket },
  { value: 'panel', label: '全局审查', desc: '每个模型综合评审全场（推荐）', icon: Zap },
  { value: 'full', label: '深度交叉', desc: '每对模型逐一审查，适用于高风险或复杂决策', hint: '输出为结构化观点，非最终方案。可配合 Rollup 生成行动计划。', icon: Flame },
]

const selectedDepth = ref<DiscussDepth>('panel')

function getModelName(id: string): string {
  if (id === '*') return '全体'
  return appStore.models.find(m => m.id === id)?.name ?? id
}

function getProvider(id: string): string {
  return appStore.models.find(m => m.id === id)?.provider ?? 'unknown'
}

function startDiscuss() {
  session.start({
    prompt: props.prompt,
    modelIds: props.modelIds,
    depth: selectedDepth.value,
  })
}

function handleRollup() {
  session.startRollup(props.prompt, props.modelIds)
}

const sanitizedSynthesis = computed(() => sanitizeModelOutput(session.phase3Text.value || ''))
const sanitizedRollup = computed(() => sanitizeModelOutput(session.rollupText.value || ''))
const synthesisHtml = computed(() => md.render(sanitizedSynthesis.value.content || ''))
const rollupHtml = computed(() => md.render(sanitizedRollup.value.content || ''))

// Auto-cleanup on unmount
watch(() => session.isActive.value, (active) => {
  if (!active && session.phase.value === 0) return
})
</script>

<template>
  <div class="mt-4 rounded-xl border border-purple-500/20 bg-surface-1 overflow-hidden animate-slide-up">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
      <div class="flex items-center gap-2">
        <div class="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
        <span class="text-sm font-medium text-text-primary">深入讨论</span>
        <span v-if="session.phase.value > 0" class="text-xs text-text-tertiary">
          Phase {{ session.phase.value }}/3
        </span>
      </div>
      <button
        @click="session.reset(); emit('close')"
        class="p-1 rounded-lg hover:bg-surface-3 transition-colors"
      >
        <X :size="14" class="text-text-tertiary" />
      </button>
    </div>

    <!-- Depth selector (before starting) -->
    <div v-if="session.phase.value === 0" class="p-4">
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
      <p
        v-if="depthOptions.find(o => o.value === selectedDepth)?.hint"
        class="text-[10px] text-text-tertiary mb-3 px-1 leading-relaxed"
      >
        {{ depthOptions.find(o => o.value === selectedDepth)?.hint }}
      </p>
      <button
        @click="startDiscuss"
        class="w-full py-2 rounded-lg bg-purple-500 hover:bg-purple-600
               text-white text-sm font-medium transition-colors active:scale-[0.98]"
      >
        开始讨论
      </button>
    </div>

    <!-- Phase 1: Independent Analysis -->
    <div v-if="session.phase.value >= 1" class="p-4 border-b border-border-subtle">
      <h4 class="text-xs font-medium text-text-tertiary uppercase tracking-wide mb-3">
        Phase 1 · 独立方案
        <span v-if="session.phase.value === 1 && session.streaming.value" class="inline-flex gap-1 ml-2">
          <span class="w-1 h-1 rounded-full bg-purple-400 animate-pulse_dot" />
          <span class="w-1 h-1 rounded-full bg-purple-400 animate-pulse_dot" style="animation-delay:.2s" />
          <span class="w-1 h-1 rounded-full bg-purple-400 animate-pulse_dot" style="animation-delay:.4s" />
        </span>
      </h4>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        <div
          v-for="result in session.phase1Results.value"
          :key="result.model"
          class="rounded-lg bg-surface-2 p-3"
        >
          <div class="flex items-center gap-2 mb-2">
            <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: getModelColor(getProvider(result.model)) }" />
            <span class="text-xs font-medium text-text-primary">{{ getModelName(result.model) }}</span>
          </div>
          <p class="text-xs text-text-secondary mb-1"><strong>方案：</strong>{{ result.data.approach }}</p>
          <p class="text-xs text-text-tertiary">{{ result.data.reasoning }}</p>
        </div>
      </div>
    </div>

    <!-- Phase 2: Cross Review -->
    <div v-if="session.phase.value >= 2" class="p-4 border-b border-border-subtle">
      <h4 class="text-xs font-medium text-text-tertiary uppercase tracking-wide mb-3">
        Phase 2 · {{ selectedDepth === 'full' ? '交叉审查' : selectedDepth === 'panel' ? '全局审查' : '快速审查' }}
        <span v-if="session.phase.value === 2 && session.streaming.value" class="inline-flex gap-1 ml-2">
          <span class="w-1 h-1 rounded-full bg-purple-400 animate-pulse_dot" />
          <span class="w-1 h-1 rounded-full bg-purple-400 animate-pulse_dot" style="animation-delay:.2s" />
          <span class="w-1 h-1 rounded-full bg-purple-400 animate-pulse_dot" style="animation-delay:.4s" />
        </span>
      </h4>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div
          v-for="(review, idx) in session.phase2Results.value"
          :key="idx"
          class="rounded-lg bg-surface-2 p-3"
        >
          <div class="flex items-center gap-1 mb-2 text-[10px] text-text-tertiary">
            <span class="font-medium text-text-secondary">{{ getModelName(review.reviewer) }}</span>
            <span>→</span>
            <span class="font-medium text-text-secondary">{{ getModelName(review.target) }}</span>
          </div>
          <p class="text-xs text-green-400/80 mb-1">✓ {{ review.data.agreement }}</p>
          <p class="text-xs text-amber-400/80 mb-1">⚡ {{ review.data.challenge }}</p>
          <p class="text-xs text-blue-400/80">💡 {{ review.data.betterOption }}</p>
        </div>
      </div>
    </div>

    <!-- Phase 3: Synthesis -->
    <div v-if="session.phase.value >= 3" class="p-4 border-b border-border-subtle">
      <h4 class="text-xs font-medium text-text-tertiary uppercase tracking-wide mb-3">
        Phase 3 · 综合结论
      </h4>
      <div class="md-body text-sm" v-html="synthesisHtml" />
      <div v-if="sanitizedSynthesis.hiddenThink" class="mt-3 text-[10px] italic text-text-tertiary">
        已隐藏模型思考过程，只展示最终结论
      </div>
      <span
        v-if="session.streaming.value && session.phase.value === 3"
        class="inline-block w-1.5 h-4 bg-purple-400 ml-0.5 animate-cursor_blink align-text-bottom"
      />
    </div>

    <!-- Rollup: Action Plan -->
    <div v-if="session.phase.value >= 3 && !session.streaming.value" class="p-4">
      <!-- Rollup trigger -->
      <div v-if="session.rollupPhase.value === 'idle'">
        <button
          @click="handleRollup"
          class="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg
                 border border-amber-500/20 hover:bg-amber-500/5 transition-colors group"
        >
          <Gavel :size="13" class="text-amber-400 group-hover:scale-110 transition-transform" />
          <span class="text-xs text-text-secondary group-hover:text-text-primary transition-colors">
            制定行动计划
          </span>
        </button>
        <p class="text-[10px] text-text-tertiary text-center mt-1">
          综合观点为唯一可落地方案
        </p>
      </div>

      <!-- Rollup result -->
      <div v-else>
        <div class="flex items-center gap-2 mb-3">
          <Gavel :size="13" class="text-amber-400" />
          <span class="text-xs font-medium text-text-primary">行动计划</span>
          <span v-if="session.rollupModel.value" class="text-[10px] text-text-tertiary bg-surface-3 px-1.5 py-0.5 rounded">
            由 {{ session.rollupModel.value }} 制定
          </span>
          <Loader2
            v-if="session.rollupPhase.value === 'streaming'"
            :size="12"
            class="text-amber-400 animate-spin ml-auto"
          />
        </div>
        <template v-if="session.rollupText.value">
          <div class="md-body text-sm" v-html="rollupHtml" />
          <div v-if="sanitizedRollup.hiddenThink" class="mt-3 text-[10px] italic text-text-tertiary">
            已隐藏模型思考过程，只展示行动计划
          </div>
        </template>
        <div v-else class="space-y-2">
          <div class="h-3 bg-surface-3 rounded animate-pulse w-full" />
          <div class="h-3 bg-surface-3 rounded animate-pulse w-4/5" />
        </div>
        <span
          v-if="session.rollupPhase.value === 'streaming' && session.rollupText.value"
          class="inline-block w-1.5 h-4 bg-amber-400 ml-0.5 animate-cursor_blink align-text-bottom"
        />
      </div>
    </div>
  </div>
</template>
