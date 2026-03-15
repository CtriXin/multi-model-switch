<template>
  <div
    class="rounded-xl border overflow-hidden transition-all duration-200"
    :class="cardClass"
    @click="$emit('select')"
  >
    <!-- Header -->
    <div class="flex items-center justify-between px-3 py-2 border-b border-gray-100/80">
      <div class="flex items-center gap-2 min-w-0">
        <div
          class="w-5 h-5 rounded-md flex items-center justify-center text-[9px] font-bold text-white flex-shrink-0"
          :style="{ background: modelColor }"
        >
          {{ initial }}
        </div>
        <span class="text-xs font-medium text-gray-800 truncate">{{ modelName }}</span>
        <span
          v-if="modelMeta"
          class="text-[9px] px-1 py-0.5 rounded font-medium"
          :class="tierClass"
        >{{ tierLabel }}</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span v-if="response.status === 'done'" class="text-[10px] text-gray-400">
          {{ formatElapsed(response.elapsed) }}
        </span>
        <div
          class="w-1.5 h-1.5 rounded-full"
          :class="statusDotClass"
        />
      </div>
    </div>

    <!-- Content -->
    <div class="px-3 py-2.5">
      <!-- Loading -->
      <div v-if="response.status === 'loading'" class="space-y-2">
        <div class="h-2.5 bg-gray-100 rounded animate-pulse w-full" />
        <div class="h-2.5 bg-gray-100 rounded animate-pulse w-3/4" />
        <div class="h-2.5 bg-gray-100 rounded animate-pulse w-1/2" />
      </div>

      <!-- Error -->
      <div v-else-if="response.status === 'error'" class="text-xs text-red-500">
        {{ response.error || '请求失败' }}
      </div>

      <!-- Content -->
      <div v-else class="prose-chat text-[13px] leading-relaxed max-h-[400px] overflow-y-auto" v-html="rendered" />

      <!-- Streaming indicator -->
      <div v-if="response.status === 'streaming'" class="mt-2 flex gap-1">
        <span class="w-1 h-1 rounded-full bg-accent-400 animate-typing" style="animation-delay:0s" />
        <span class="w-1 h-1 rounded-full bg-accent-400 animate-typing" style="animation-delay:0.15s" />
        <span class="w-1 h-1 rounded-full bg-accent-400 animate-typing" style="animation-delay:0.3s" />
      </div>
    </div>

    <!-- Footer Actions -->
    <div v-if="response.status === 'done'" class="flex items-center gap-1 px-3 py-1.5 border-t border-gray-100/80">
      <button
        v-if="!selected"
        @click.stop="$emit('select')"
        class="text-[11px] px-2 py-1 font-medium text-accent-600 hover:bg-accent-50 rounded-md transition-colors"
      >
        选择此回答
      </button>
      <div v-else class="text-[11px] text-accent-600 font-medium flex items-center gap-1">
        <Check class="w-3 h-3" /> 已选择
      </div>
      <div class="flex-1" />
      <button
        @click.stop="copyContent"
        class="p-1 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-50 transition-colors"
        title="复制"
      >
        <Copy class="w-3 h-3" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import { Copy, Check } from 'lucide-vue-next'
import type { ChatResponse, ModelMeta, ModelTier } from '@mms/contracts'

const props = defineProps<{
  response: ChatResponse
  modelName: string
  modelMeta?: ModelMeta
  selected: boolean
}>()

defineEmits<{ select: [] }>()

const md = new MarkdownIt({ html: false, linkify: true })

const rendered = computed(() => {
  const content = props.response.content.replace(/<BRIEF>[\s\S]*?<\/BRIEF>/gi, '').trim()
  return md.render(content)
})

const initial = computed(() => props.modelName.charAt(0).toUpperCase())

const modelColor = computed(() => {
  const colors = ['#6366f1', '#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ec4899', '#06b6d4', '#f97316']
  const hash = props.response.model.split('').reduce((a, b) => a + b.charCodeAt(0), 0)
  return colors[hash % colors.length]
})

const cardClass = computed(() =>
  props.selected
    ? 'bg-white border-accent-400 shadow-md ring-1 ring-accent-100 cursor-default'
    : 'bg-white border-gray-200 hover:border-gray-300 hover:shadow-card cursor-pointer'
)

const tierClass = computed(() => {
  if (!props.modelMeta) return ''
  const t = props.modelMeta.tier
  return t === 2 ? 'bg-amber-50 text-amber-600' : t === 1 ? 'bg-blue-50 text-blue-600' : 'bg-emerald-50 text-emerald-600'
})

const tierLabel = computed(() => {
  if (!props.modelMeta) return ''
  const names: Record<ModelTier, string> = { 0: '经济', 1: '主力', 2: '旗舰' }
  return names[props.modelMeta.tier]
})

const statusDotClass = computed(() => {
  switch (props.response.status) {
    case 'loading': return 'bg-gray-300 animate-pulse-dot'
    case 'streaming': return 'bg-green-400 animate-pulse-dot'
    case 'done': return 'bg-green-500'
    case 'error': return 'bg-red-500'
    default: return 'bg-gray-300'
  }
})

function formatElapsed(s: number): string {
  if (!s || s <= 0) return ''
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m${Math.floor(s % 60)}s`
}

function copyContent() {
  navigator.clipboard.writeText(props.response.content)
}
</script>
