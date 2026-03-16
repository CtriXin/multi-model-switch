<script setup lang="ts">
import { ref, watch, nextTick, inject, computed } from 'vue'
import { Send, Square, ImagePlus, X } from 'lucide-vue-next'
import { useToastStore } from '@/stores/toast'
import type { ImageAttachment } from '@/stores/chat'

const MAX_IMAGES = 4
const MAX_SIZE_BYTES = 4 * 1024 * 1024 // 4MB after compression
const MAX_DIMENSION = 1024

const props = defineProps<{
  disabled?: boolean
  streaming?: boolean
  placeholder?: string
  restoreText?: string
}>()

const emit = defineEmits<{
  submit: [text: string, attachments: ImageAttachment[]]
  stop: []
  stopAndEdit: []
}>()

const platform = inject<import('vue').Ref<string>>('platform', ref('web'))
const isMobile = computed(() => platform.value === 'ios')
const text = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
const fileInputRef = ref<HTMLInputElement>()
const attachments = ref<ImageAttachment[]>([])
const dragOver = ref(false)

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}

function submit() {
  const val = text.value.trim()
  if (!val || props.disabled) return
  emit('submit', val, [...attachments.value])
  text.value = ''
  attachments.value = []
  nextTick(resize)
}

function resize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

// ── Image handling ──

function openFilePicker() {
  fileInputRef.value?.click()
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) processFiles(Array.from(input.files))
  input.value = '' // reset so same file can be re-selected
}

function onPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  const imageFiles: File[] = []
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) imageFiles.push(file)
    }
  }
  if (imageFiles.length) {
    e.preventDefault()
    processFiles(imageFiles)
  }
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  dragOver.value = true
}

function onDragLeave() {
  dragOver.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
  const files = e.dataTransfer?.files
  if (!files) return
  const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'))
  if (imageFiles.length) processFiles(imageFiles)
}

async function processFiles(files: File[]) {
  const toast = useToastStore()
  const remaining = MAX_IMAGES - attachments.value.length
  if (remaining <= 0) {
    toast.info(`最多附加 ${MAX_IMAGES} 张图片`)
    return
  }
  const toProcess = files.slice(0, remaining)
  if (files.length > remaining) {
    toast.info(`最多附加 ${MAX_IMAGES} 张图片，已忽略多余的`)
  }

  for (const file of toProcess) {
    try {
      const dataUrl = await compressImage(file)
      if (dataUrl.length > MAX_SIZE_BYTES * 1.37) { // base64 overhead ~37%
        toast.error(`${file.name} 压缩后仍超过 4MB，请使用更小的图片`)
        continue
      }
      attachments.value.push({
        id: `img-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        dataUrl,
        name: file.name,
        size: file.size,
      })
    } catch {
      toast.error(`${file.name} 处理失败`)
    }
  }
}

function compressImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      let { width, height } = img
      // Scale down to max dimension
      if (width > MAX_DIMENSION || height > MAX_DIMENSION) {
        const ratio = Math.min(MAX_DIMENSION / width, MAX_DIMENSION / height)
        width = Math.round(width * ratio)
        height = Math.round(height * ratio)
      }
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, 0, 0, width, height)
      resolve(canvas.toDataURL('image/jpeg', 0.85))
    }
    img.onerror = reject
    img.src = URL.createObjectURL(file)
  })
}

function removeAttachment(id: string) {
  attachments.value = attachments.value.filter(a => a.id !== id)
}

watch(text, () => nextTick(resize))
watch(() => props.restoreText, (value) => {
  if (!value) return
  text.value = value
  nextTick(resize)
})
</script>

<template>
  <div class="border-t border-border-subtle bg-surface-1">
    <div class="max-w-5xl mx-auto px-4 py-3">
      <!-- Image preview row -->
      <div v-if="attachments.length" class="flex gap-2 mb-2 overflow-x-auto pb-1">
        <div
          v-for="img in attachments"
          :key="img.id"
          class="relative shrink-0 group"
        >
          <img
            :src="img.dataUrl"
            :alt="img.name"
            class="h-16 w-16 object-cover rounded-lg border border-border-subtle"
          />
          <button
            @click="removeAttachment(img.id)"
            class="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-red-500 text-white
                   flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <X :size="10" />
          </button>
        </div>
      </div>

      <div
        class="flex min-h-[52px] items-end gap-2 rounded-xl border px-2.5 py-2 transition-colors duration-150 relative overflow-hidden"
        :class="[
          streaming
            ? 'border-accent/50 bg-accent/5'
            : dragOver
              ? 'border-accent bg-accent/10'
              : 'border-border-default bg-surface-2 focus-within:border-accent/40',
        ]"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        @drop="onDrop"
      >
        <!-- Streaming aurora border effect -->
        <div
          v-if="streaming"
          class="absolute inset-0 rounded-xl pointer-events-none"
          style="background: linear-gradient(90deg, #6366f1, #818cf8, #a78bfa, #6366f1); background-size: 300% 100%; animation: aurora-flow 2s linear infinite; opacity: 0.15;"
        />
        <div
          v-if="streaming"
          class="absolute inset-0 rounded-xl pointer-events-none border-2 border-accent/30"
          style="animation: pulse-border 1.5s ease-in-out infinite;"
        />
        <!-- Image button -->
        <button
          v-if="!streaming"
          @click="openFilePicker"
          type="button"
          :disabled="disabled"
          class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg
                 text-text-tertiary hover:text-text-secondary hover:bg-surface-3
                 transition-colors self-end disabled:opacity-40"
          title="插入图片"
        >
          <ImagePlus :size="16" />
        </button>

        <input
          ref="fileInputRef"
          type="file"
          accept="image/*"
          multiple
          class="hidden"
          @change="onFileSelect"
        />

        <textarea
          ref="textareaRef"
          v-model="text"
          @keydown="handleKeydown"
          @paste="onPaste"
          :placeholder="streaming ? '生成中...' : (placeholder ?? '输入消息... (Shift+Enter 换行)')"
          :disabled="disabled || streaming"
          rows="1"
          class="flex-1 bg-transparent text-base text-text-primary placeholder-text-tertiary
                 resize-none py-2 pl-1.5 pr-1 outline-none max-h-40 min-h-[36px]
                 disabled:opacity-40 disabled:cursor-not-allowed relative z-10"
        />
        <div class="flex shrink-0 items-center gap-1.5 self-end">
          <button
            v-if="streaming"
            @click="emit('stop')"
            type="button"
            class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30
                   active:scale-95 transition-all"
            title="停止生成"
          >
            <Square :size="16" fill="currentColor" />
          </button>
          <button
            v-if="streaming"
            @click="emit('stopAndEdit')"
            type="button"
            class="inline-flex h-9 items-center rounded-lg border border-border-subtle px-3 text-[11px] font-medium text-text-secondary transition-colors hover:bg-surface-3"
            title="终止当前回答并把原问题放回输入框"
          >
            终止并编辑
          </button>
          <button
            v-else
            @click="submit"
            type="button"
            :disabled="!text.trim() || disabled"
            class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-all active:scale-95"
            :class="text.trim() && !disabled
              ? 'bg-accent text-white hover:bg-accent-hover'
              : 'text-text-tertiary'"
          >
            <Send :size="16" />
          </button>
        </div>
      </div>
      <div class="flex items-center justify-between mt-1.5 px-1">
        <span v-if="!isMobile" class="text-[10px] text-text-tertiary">
          <kbd class="px-1 py-0.5 rounded bg-surface-3 text-[9px]">⌘K</kbd> 命令面板
        </span>
        <span v-else />
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes aurora-flow {
  0% { background-position: 0% 50%; }
  100% { background-position: 300% 50%; }
}

@keyframes pulse-border {
  0%, 100% { border-color: rgba(99, 102, 241, 0.3); }
  50% { border-color: rgba(99, 102, 241, 0.6); }
}
</style>
