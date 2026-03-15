<template>
  <div
    :class="[
      'rounded-xl border overflow-hidden transition-all duration-300',
      selected
        ? 'bg-white border-indigo-500 shadow-lg ring-2 ring-indigo-100'
        : archived
          ? 'bg-gray-50/80 border-gray-200'
          : 'bg-white border-gray-200 hover:border-gray-300 hover:shadow-md'
    ]"
  >
    <!-- Header - Always visible -->
    <div
      class="flex items-center justify-between px-3 py-2.5 cursor-pointer"
      @click="archived && $emit('toggle-expand')"
    >
      <div class="flex items-center gap-2 min-w-0">
        <!-- Expand icon for archived -->
        <ChevronDown
          v-if="archived"
          :class="[
            'w-3.5 h-3.5 text-gray-400 flex-shrink-0 transition-transform duration-200',
            expanded ? 'rotate-180' : ''
          ]"
        />
        <span :class="['text-sm font-medium truncate', selected ? 'text-indigo-900' : 'text-gray-700']">
          {{ modelName }}
        </span>
        <TierBadge v-if="modelMeta && !archived" :tier="modelMeta.tier" />
      </div>
      <div class="flex items-center gap-1.5 flex-shrink-0 ml-2">
        <span v-if="archived" class="text-xs text-gray-400">归档</span>
        <StatusIndicator :status="response.status" />
      </div>
    </div>

    <!-- Content - Hidden when archived and collapsed -->
    <div v-if="!archived || expanded" class="border-t border-gray-100">
      <!-- Content -->
      <div :class="['px-3', archived ? 'py-2' : 'py-3']">
        <!-- Loading -->
        <div v-if="response.status === 'loading'" class="space-y-1.5">
          <div class="h-3 bg-gray-100 rounded animate-pulse"></div>
          <div class="h-3 bg-gray-100 rounded animate-pulse w-3/4"></div>
          <div class="h-3 bg-gray-100 rounded animate-pulse w-1/2"></div>
        </div>

        <!-- Error -->
        <div v-else-if="response.status === 'error'" class="text-red-600 text-xs">
          {{ response.error || '请求失败' }}
        </div>

        <!-- Content -->
        <div v-else class="prose prose-sm max-w-none">
          <div class="markdown-body text-sm" v-html="renderedContent"></div>
        </div>
      </div>

      <!-- Brief Footer -->
      <div v-if="response.status === 'done' && response.brief" class="px-3 py-2 bg-gray-50/50 border-t border-gray-100">
        <div class="text-xs text-gray-500 space-y-0.5">
          <p v-if="response.brief.approach" class="truncate">
            <span class="text-gray-400">方案:</span> {{ response.brief.approach }}
          </p>
        </div>
      </div>

      <!-- Actions -->
      <div v-if="response.status === 'done'" class="flex items-center gap-1.5 px-3 py-2 border-t border-gray-100">
        <button
          v-if="!selected && !archived"
          @click="$emit('select')"
          class="flex-1 px-2.5 py-1 text-xs font-medium rounded-md transition-colors bg-gray-100 text-gray-600 hover:bg-gray-200"
        >
          选择
        </button>
        <button
          v-if="archived"
          @click="$emit('select')"
          class="flex-1 px-2.5 py-1 text-xs font-medium rounded-md transition-colors bg-indigo-50 text-indigo-600 hover:bg-indigo-100"
        >
          设为选中
        </button>
        <button
          @click="copyContent"
          class="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-md transition-colors"
          title="复制"
        >
          <Copy class="w-3.5 h-3.5" />
        </button>
      </div>

      <!-- Elapsed Time Footer -->
      <div class="px-3 py-1.5 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
        <span class="text-[10px] text-gray-400 flex items-center gap-1">
          <Clock class="w-3 h-3" />
          耗时 {{ formatElapsed(response.elapsed) }}
        </span>
        <span v-if="response.timestamp" class="text-[10px] text-gray-300">
          {{ formatTime(response.timestamp) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Copy, ChevronDown, Clock } from 'lucide-vue-next'
import MarkdownIt from 'markdown-it'
import type { ChatResponse, ModelMeta } from '@mms/contracts'
import { useAppStore } from '@/stores'
import TierBadge from './TierBadge.vue'
import StatusIndicator from './StatusIndicator.vue'

const props = defineProps<{
  response: ChatResponse
  selected?: boolean
  archived?: boolean
  expanded?: boolean
}>()

defineEmits<{
  select: []
  'toggle-expand': []
}>()

const appStore = useAppStore()

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
})

const modelMeta = computed((): ModelMeta | undefined => {
  return appStore.models.find(m => m.id === props.response.model)
})

const modelName = computed(() => {
  return modelMeta.value?.name || props.response.model
})

const renderedContent = computed(() => {
  const content = props.response.displayText || props.response.content
  const cleanContent = content.replace(/<BRIEF>[\s\S]*?<\/BRIEF>/gi, '').trim()
  return md.render(cleanContent)
})

function copyContent() {
  navigator.clipboard.writeText(props.response.content)
}

function formatElapsed(seconds: number): string {
  if (!seconds || seconds <= 0) return '0s'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}m ${secs}s`
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>
