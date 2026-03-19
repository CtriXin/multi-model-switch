<script setup lang="ts">
import { ref, watch, nextTick, inject, computed } from 'vue'
import { Send, Square, ImagePlus, X } from 'lucide-vue-next'
import { useToastStore } from '@/stores/toast'
import { useAppStore } from '@/stores/app'
import type { ImageAttachment } from '@/stores/chat'

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

const appStore = useAppStore()
const platform = inject<import('vue').Ref<string>>('platform', ref('web'))
const isMobile = computed(() => platform.value === 'ios')
const text = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
const fileInputRef = ref<HTMLInputElement>()
const attachments = ref<ImageAttachment[]>([])
const dragOver = ref(false)

const hasModels = computed(() => appStore.selectedModels.length > 0)

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

function openFilePicker() {
  fileInputRef.value?.click()
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) processFiles(Array.from(input.files))
  input.value = '' 
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

async function processFiles(files: File[]) {
  const toast = useToastStore()
  const remaining = 4 - attachments.value.length
  if (remaining <= 0) return
  const toProcess = files.slice(0, remaining)
  for (const file of toProcess) {
    try {
      const dataUrl = await compressImage(file)
      attachments.value.push({
        id: `img-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        dataUrl,
        name: file.name,
        size: file.size,
      })
    } catch {
      toast.error(`${file.name} 上传失败`)
    }
  }
}

function compressImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      let { width, height } = img
      if (width > 1024 || height > 1024) {
        const ratio = Math.min(1024 / width, 1024 / height)
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
  <div class="relative w-full px-1.5">
    <div v-if="attachments.length" class="flex gap-2 mb-3 overflow-x-auto pb-1 px-4">
      <div v-for="img in attachments" :key="img.id" class="relative shrink-0 group/img">
        <img :src="img.dataUrl" class="h-14 w-14 object-cover rounded-xl border border-white/10 shadow-lg transition-transform group-hover/img:scale-[0.98]" />
        <button
          @click="removeAttachment(img.id)"
          class="absolute top-0 right-0 -translate-y-1/3 translate-x-1/3 w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center opacity-0 group-hover/img:opacity-100 transition-all hover:scale-110 active:scale-90 z-10 shadow-md"
        >
          <X :size="10" :stroke-width="3" />
        </button>
      </div>
    </div>

    <div
      class="relative flex min-h-[44px] items-end gap-1.5 transition-all duration-300 group"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="dragOver = false"
    >
      <!-- Colorful Icon when models are selected -->
      <button v-if="!streaming" @click="openFilePicker" type="button" :disabled="disabled" 
              class="h-10 w-10 shrink-0 flex items-center justify-center rounded-full transition-all self-end mb-0.5 ml-1"
              :class="hasModels 
                ? 'bg-gradient-to-br from-indigo-500 via-purple-500 to-fuchsia-500 text-white shadow-lg scale-105' 
                : 'text-text-tertiary hover:bg-black/5 dark:hover:bg-white/5'">
        <ImagePlus :size="20" />
      </button>

      <input ref="fileInputRef" type="file" accept="image/*" multiple class="hidden" @change="onFileSelect" />

      <textarea
        ref="textareaRef"
        v-model="text"
        @keydown="handleKeydown"
        @paste="onPaste"
        :placeholder="streaming ? '正在生成...' : (placeholder ?? '问点什么...')"
        :disabled="disabled || streaming"
        rows="1"
        class="flex-1 bg-transparent text-base text-text-primary placeholder:text-text-tertiary/40 resize-none py-2 px-1 outline-none max-h-40 min-h-[40px] disabled:opacity-40 font-medium leading-6"
      />
      
      <div class="flex shrink-0 items-center gap-1.5 self-end mb-0.5 mr-1">
        <button v-if="streaming" @click="emit('stop')" class="h-10 w-10 flex items-center justify-center rounded-full bg-red-500/20 text-red-400"><Square :size="16" fill="currentColor" /></button>
        <button v-if="streaming" @click="emit('stopAndEdit')" class="h-10 px-4 rounded-xl bg-white/5 border border-white/5 text-[10px] font-black uppercase text-text-secondary">停下修改</button>
        <button v-else @click="submit" :disabled="!text.trim() || disabled" 
                class="h-10 w-10 flex items-center justify-center rounded-full transition-all duration-500" 
                :class="text.trim() && !disabled ? 'bg-accent text-white shadow-xl scale-105' : 'bg-white/5 text-text-tertiary'">
          <Send :size="18" />
        </button>
      </div>
    </div>
  </div>
</template>
