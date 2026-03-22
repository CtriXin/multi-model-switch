<script setup lang="ts">
import { computed, ref } from 'vue'
import { getModelColor } from '@/stores/app'
import { Copy, Check, MessageSquare, RefreshCw, RefreshCcw, Sparkles, Share2 } from 'lucide-vue-next'
import MarkdownIt from 'markdown-it'
import { sanitizeModelOutput } from '@/utils/modelOutput'
import { shareText } from '@/composables/useShare'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const props = defineProps<{
  modelId: string
  modelName: string
  provider: string
  content: string
  elapsed?: number
  tier?: number
  error?: string
  errorCode?: string
  brief?: Record<string, string>
  streaming?: boolean
  active?: boolean   // visual focus (carousel current, highlighted)
  selected?: boolean // user explicitly chose this answer
  carousel?: boolean
}>()

const emit = defineEmits<{ select: []; discuss: []; retry: []; replace: []; randomReplace: [] }>()

const copied = ref(false)
const sanitized = computed(() => sanitizeModelOutput(props.content || ''))
const html = computed(() => md.render(sanitized.value.content || ''))
const color = computed(() => getModelColor(props.provider))
const initial = computed(() => (props.modelName || props.modelId || '?').charAt(0).toUpperCase())
const isDone = computed(() => !!props.elapsed && !props.streaming)
const derivedErrorCode = computed(() => {
  if (props.errorCode) return props.errorCode
  const lower = (props.error || '').toLowerCase()
  if (!lower) return ''
  if (/does not support chat completions|unsupported.*chat|not support.*chat/.test(lower)) return 'chat_unsupported'
  if (/does not support image|image.*not.*support/.test(lower)) return 'image_unsupported'
  if (/context length|too many tokens|prompt is too long/.test(lower)) return 'context_too_long'
  if (/rate limit|额度限制|频率/.test(lower)) return 'rate_limited'
  if (/not found|not available|不可用/.test(lower)) return 'model_unavailable'
  if (/api key|invalid key|无效/.test(lower)) return 'invalid_key'
  return ''
})
const errorTag = computed(() => {
  const map: Record<string, string> = {
    chat_unsupported: '不支持聊天',
    image_unsupported: '不支持图片',
    context_too_long: '上下文过长',
    rate_limited: '频率受限',
    model_unavailable: '暂不可用',
    invalid_key: 'Key 失效',
  }
  return derivedErrorCode.value ? map[derivedErrorCode.value] : ''
})
const canReplaceModel = computed(() =>
  !!props.error && !props.streaming,
)

const tierLabel = computed(() => {
  if (props.tier === 2) return '旗舰'
  if (props.tier === 1) return '主力'
  return '基础'
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

async function handleShare() {
  await shareText(props.modelName, props.content)
}
</script>

<template>
  <div
    class="glass-v3 rounded-[24px] overflow-hidden transition-all duration-300 group flex flex-col cursor-pointer"
    :class="[
      carousel ? 'h-auto' : 'h-full min-h-0',
      selected
        ? 'ring-2 shadow-2xl scale-[1.01] z-10'
        : active
          ? 'ring-1 shadow-lg'
          : 'hover:shadow-xl hover:-translate-y-1',
    ]"
    :style="selected
      ? { borderColor: color, boxShadow: `0 8px 32px ${color}30`, '--tw-ring-color': color + '50' }
      : active
        ? { borderColor: color + '80', boxShadow: `0 4px 12px ${color}10`, '--tw-ring-color': color + '25' }
        : { borderColor: color + '40' }"
  >

    <!-- Header -->
    <div class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 border-b border-border-subtle/50">
      <div class="flex min-w-0 items-center gap-2.5">
        <!-- Avatar with initial -->
        <div
          class="w-6 h-6 rounded-lg flex items-center justify-center text-[10px] font-bold text-white shrink-0"
          :style="{ backgroundColor: color }"
        >
          {{ initial }}
        </div>
        <span class="text-sm font-medium text-text-primary truncate">{{ modelName }}</span>
      </div>
      <div class="flex min-w-[104px] shrink-0 items-center justify-end gap-2">
        <span
          v-if="errorTag"
          class="inline-flex h-5 items-center rounded px-1.5 text-[9px] font-medium shrink-0 bg-orange-500/15 text-orange-400"
        >{{ errorTag }}</span>
        <span
          v-if="tier !== undefined"
          class="inline-flex h-5 items-center rounded px-1.5 text-[9px] font-medium shrink-0"
          :class="tierClass"
        >{{ tierLabel }}</span>
        <!-- Elapsed time -->
        <span v-if="elapsed" class="w-8 shrink-0 text-right text-[10px] text-text-tertiary">
          {{ elapsed.toFixed(1) }}s
        </span>
        <span v-else class="w-8 shrink-0" />
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

    <!-- Content area (scrollable) -->
    <div class="px-4 py-3" :class="carousel ? 'overflow-visible' : 'flex-1 min-h-0 overflow-y-auto'">
      <!-- Error state -->
      <div v-if="error" class="relative py-4">
        <div class="rounded-2xl border border-red-500/20 bg-surface-2/60 px-4 py-3 pr-5">
          <p class="text-xs leading-7 text-text-secondary">{{ error }}</p>
        </div>
        <!-- Replace + Random buttons as floating capsules -->
        <div v-if="canReplaceModel" class="flex items-center gap-2 mt-3">
          <button
            @click.stop="emit('replace')"
            class="inline-flex items-center gap-1.5 rounded-full border border-orange-400/30 bg-surface-1/90 px-4 py-2 text-xs font-medium text-orange-400 shadow-lg transition-colors hover:bg-orange-500/10"
          >
            <RefreshCcw :size="14" />
            更换模型
          </button>
          <button
            @click.stop="emit('randomReplace')"
            class="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-surface-1/90 px-4 py-2 text-xs font-medium text-accent shadow-lg transition-colors hover:bg-accent/10"
          >
            <Sparkles :size="14" />
            随机替换
          </button>
        </div>
      </div>

      <!-- Loading skeleton -->
      <div v-else-if="!content && streaming" class="space-y-2.5">
        <div class="h-3 bg-surface-3 rounded-full animate-pulse w-full" />
        <div class="h-3 bg-surface-3 rounded-full animate-pulse w-4/5" style="animation-delay: 0.1s" />
        <div class="h-3 bg-surface-3 rounded-full animate-pulse w-3/5" style="animation-delay: 0.2s" />
      </div>

      <!-- Rendered markdown content -->
      <div v-else-if="sanitized.content" class="md-body max-w-none" v-html="html" />

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

      <div
        v-if="sanitized.hiddenThink"
        class="mt-3 text-[10px] italic text-text-tertiary"
      >
        已隐藏模型思考过程，只展示最终内容
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

    <!-- Footer (when done) — sticky at bottom -->
    <div v-if="isDone && !error" class="flex items-center gap-1 px-4 py-2 border-t border-white/5 shrink-0 bg-black/5 dark:bg-white/5 backdrop-blur-md">
      <!-- Select / Selected -->
      <button
        v-if="!selected"
        @click.stop="emit('select')"
        class="rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors hover:bg-surface-3"
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
        辩论
      </button>

      <!-- Copy button -->
      <button
        @click.stop="emit('retry')"
        class="p-1.5 rounded-md text-text-tertiary transition-colors opacity-60 group-hover:opacity-100 hover:bg-surface-3 hover:text-text-secondary"
        title="重试该模型"
      >
        <RefreshCw :size="13" />
      </button>

      <button
        @click.stop="copyContent"
        class="p-1.5 rounded-md transition-colors opacity-60 group-hover:opacity-100"
        :class="copied ? 'text-green-400' : 'text-text-tertiary hover:text-text-secondary hover:bg-surface-3'"
        :title="copied ? '已复制' : '复制'"
      >
        <component :is="copied ? Check : Copy" :size="13" />
      </button>

      <button
        @click.stop="handleShare"
        class="p-1.5 rounded-md text-text-tertiary transition-colors opacity-60 group-hover:opacity-100 hover:bg-surface-3 hover:text-text-secondary"
        title="分享"
      >
        <Share2 :size="13" />
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
