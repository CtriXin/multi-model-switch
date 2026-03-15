<script setup lang="ts">
import { computed, ref } from 'vue'
import { getModelColor } from '@/stores/app'
import { Copy, Check, MessageSquare, RefreshCw } from 'lucide-vue-next'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const props = defineProps<{
  modelId: string
  modelName: string
  provider: string
  content: string
  elapsed?: number
  tier?: number
  error?: string
  brief?: Record<string, string>
  streaming?: boolean
  active?: boolean   // visual focus (carousel current, highlighted)
  selected?: boolean // user explicitly chose this answer
  carousel?: boolean
}>()

const emit = defineEmits<{ select: []; discuss: []; retry: [] }>()

const copied = ref(false)
const html = computed(() => md.render(props.content || ''))
const color = computed(() => getModelColor(props.provider))
const initial = computed(() => props.modelName.charAt(0).toUpperCase())
const isDone = computed(() => !!props.elapsed && !props.streaming)

const tierLabel = computed(() => {
  if (props.tier === 2) return '旗舰'
  if (props.tier === 1) return '主力'
  return '经济'
})

const tierClass = computed(() => {
  if (props.tier === 2) return 'bg-amber-500/15 text-amber-400'
  if (props.tier === 1) return 'bg-blue-500/15 text-blue-400'
  return 'bg-green-500/15 text-green-400'
})

async function copyContent() {
  await navigator.clipboard.writeText(props.content)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}
</script>

<template>
  <div
    class="rounded-xl border overflow-hidden transition-all duration-200 group"
    :class="[
      carousel ? 'bg-surface-2' : 'card',
      selected
        ? 'ring-1 shadow-lg'
        : active
          ? 'ring-1 shadow-lg'
          : 'hover:border-border-strong hover:shadow-md',
    ]"
    :style="selected
      ? { borderColor: color + '60', boxShadow: `0 4px 12px ${color}15`, '--tw-ring-color': color + '30' }
      : active
        ? { borderColor: color + '40', boxShadow: `0 4px 12px ${color}10`, '--tw-ring-color': color + '25' }
        : {}"
  >
    <!-- Provider color top bar (hidden when selected — border already shows color) -->
    <div v-if="!selected" class="h-[3px]" :style="{ backgroundColor: color }" />

    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-2.5 border-b border-border-subtle/50">
      <div class="flex items-center gap-2.5 min-w-0">
        <!-- Avatar with initial -->
        <div
          class="w-6 h-6 rounded-lg flex items-center justify-center text-[10px] font-bold text-white shrink-0"
          :style="{ backgroundColor: color }"
        >
          {{ initial }}
        </div>
        <span class="text-sm font-medium text-text-primary truncate">{{ modelName }}</span>
        <!-- Tier badge -->
        <span
          v-if="tier !== undefined"
          class="text-[9px] px-1.5 py-0.5 rounded font-medium shrink-0"
          :class="tierClass"
        >{{ tierLabel }}</span>
      </div>
      <div class="flex items-center gap-2">
        <!-- Elapsed time -->
        <span v-if="elapsed" class="text-[10px] text-text-tertiary">
          {{ elapsed.toFixed(1) }}s
        </span>
        <!-- Status dot -->
        <div
          class="w-1.5 h-1.5 rounded-full shrink-0"
          :class="error
            ? 'bg-red-500'
            : streaming
              ? 'bg-green-400 animate-pulse_dot'
              : isDone
                ? 'bg-green-500'
                : 'bg-text-tertiary animate-pulse_dot'"
        />
      </div>
    </div>

    <!-- Content area -->
    <div class="px-4 py-3">
      <!-- Error state -->
      <div v-if="error" class="text-center py-4">
        <p class="text-xs text-red-400 mb-3">{{ error }}</p>
        <button
          @click.stop="emit('retry')"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                 text-text-secondary bg-surface-3 hover:bg-surface-2 transition-colors"
        >
          <RefreshCw :size="12" />
          换一个模型
        </button>
      </div>

      <!-- Loading skeleton -->
      <div v-else-if="!content && streaming" class="space-y-2.5">
        <div class="h-3 bg-surface-3 rounded-full animate-pulse w-full" />
        <div class="h-3 bg-surface-3 rounded-full animate-pulse w-4/5" style="animation-delay: 0.1s" />
        <div class="h-3 bg-surface-3 rounded-full animate-pulse w-3/5" style="animation-delay: 0.2s" />
      </div>

      <!-- Rendered markdown content -->
      <div v-else-if="content" class="md-body" v-html="html" />

      <!-- Streaming typing indicator -->
      <div v-if="streaming && content" class="mt-3 flex items-center gap-1.5">
        <span
          class="w-1.5 h-1.5 rounded-full animate-typing"
          :style="{ backgroundColor: color, animationDelay: '0s' }"
        />
        <span
          class="w-1.5 h-1.5 rounded-full animate-typing"
          :style="{ backgroundColor: color, animationDelay: '0.15s' }"
        />
        <span
          class="w-1.5 h-1.5 rounded-full animate-typing"
          :style="{ backgroundColor: color, animationDelay: '0.3s' }"
        />
      </div>

      <!-- Brief -->
      <div v-if="brief && Object.keys(brief).length" class="mt-3 pt-3 border-t border-border-subtle">
        <div class="grid grid-cols-2 gap-x-4 gap-y-1.5">
          <div v-for="(val, key) in brief" :key="key">
            <span class="text-[10px] text-text-tertiary uppercase">{{ key }}</span>
            <p class="text-xs text-text-secondary">{{ val }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Footer (when done) -->
    <div v-if="isDone" class="flex items-center gap-1 px-4 py-2 border-t border-border-subtle/50">
      <!-- Select / Selected -->
      <button
        v-if="!selected"
        @click.stop="emit('select')"
        class="text-[11px] px-2.5 py-1 font-medium rounded-md transition-colors"
        :class="`hover:bg-[${color}15]`"
        :style="{ color }"
      >
        选择此回答
      </button>
      <div v-else class="text-[11px] font-medium flex items-center gap-1" :style="{ color }">
        <Check :size="12" /> 已选择
      </div>

      <div class="flex-1" />

      <!-- Discuss button -->
      <button
        v-if="selected"
        @click.stop="emit('discuss')"
        class="text-[11px] px-2 py-1 text-purple-400 hover:bg-purple-500/10 rounded-md transition-colors
               opacity-0 group-hover:opacity-100 flex items-center gap-1"
      >
        <MessageSquare :size="11" />
        讨论
      </button>

      <!-- Copy button -->
      <button
        @click.stop="copyContent"
        class="p-1.5 rounded-md transition-colors opacity-60 group-hover:opacity-100"
        :class="copied ? 'text-green-400' : 'text-text-tertiary hover:text-text-secondary hover:bg-surface-3'"
        :title="copied ? '已复制' : '复制'"
      >
        <component :is="copied ? Check : Copy" :size="13" />
      </button>
    </div>
  </div>
</template>

<style scoped>
@keyframes typing {
  0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); }
  30% { opacity: 1; transform: scale(1.2); }
}
.animate-typing {
  animation: typing 1.2s ease-in-out infinite;
}
</style>
