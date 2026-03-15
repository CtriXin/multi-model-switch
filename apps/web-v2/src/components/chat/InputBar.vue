<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { Send, Square, GitMerge } from 'lucide-vue-next'

const props = defineProps<{
  disabled?: boolean
  streaming?: boolean
  placeholder?: string
  showDiscuss?: boolean
}>()

const emit = defineEmits<{
  submit: [text: string]
  stop: []
  discuss: []
}>()

const text = ref('')
const textareaRef = ref<HTMLTextAreaElement>()

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}

function submit() {
  const val = text.value.trim()
  if (!val || props.disabled) return
  emit('submit', val)
  text.value = ''
  nextTick(resize)
}

function resize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

watch(text, () => nextTick(resize))
</script>

<template>
  <div class="border-t border-border-subtle bg-surface-1">
    <div class="max-w-3xl mx-auto px-4 py-3">
      <div
        class="flex items-end gap-1.5 rounded-xl border transition-colors duration-150"
        :class="streaming
          ? 'border-accent/30 bg-accent/5'
          : 'border-border-default bg-surface-2 focus-within:border-accent/40'"
      >
        <textarea
          ref="textareaRef"
          v-model="text"
          @keydown="handleKeydown"
          :placeholder="placeholder ?? '输入消息... (Shift+Enter 换行)'"
          :disabled="disabled || streaming"
          rows="1"
          class="flex-1 bg-transparent text-base text-text-primary placeholder-text-tertiary
                 resize-none py-3 pl-4 pr-1 outline-none max-h-40
                 disabled:opacity-40 disabled:cursor-not-allowed"
        />
        <div class="flex items-center gap-1 pr-2 pb-2">
          <!-- Discuss button -->
          <button
            v-if="showDiscuss && !streaming"
            @click="emit('discuss')"
            class="p-2 rounded-lg text-purple-400 hover:bg-purple-500/10
                   active:scale-95 transition-all"
            title="进入讨论模式"
          >
            <GitMerge :size="16" />
          </button>

          <!-- Stop / Send -->
          <button
            v-if="streaming"
            @click="emit('stop')"
            class="p-2.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30
                   active:scale-95 transition-all"
            title="停止生成"
          >
            <Square :size="18" fill="currentColor" />
          </button>
          <button
            v-else
            @click="submit"
            :disabled="!text.trim() || disabled"
            class="p-2.5 rounded-lg transition-all active:scale-95"
            :class="text.trim() && !disabled
              ? 'bg-accent text-white hover:bg-accent-hover'
              : 'text-text-tertiary'"
          >
            <Send :size="18" />
          </button>
        </div>
      </div>
      <div class="flex items-center justify-between mt-1.5 px-1">
        <span class="text-[10px] text-text-tertiary">
          <kbd class="px-1 py-0.5 rounded bg-surface-3 text-[9px]">⌘K</kbd> 命令面板
        </span>
        <span v-if="streaming" class="text-[10px] text-accent flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-accent animate-pulse_dot" />
          生成中...
        </span>
      </div>
    </div>
  </div>
</template>
