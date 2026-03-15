<template>
  <div class="h-full flex flex-col">
    <!-- Chat Content -->
    <div ref="scrollArea" class="flex-1 overflow-y-auto">
      <!-- Empty State -->
      <div v-if="!chatStore.hasRounds && !chatStore.isStreaming" class="h-full flex flex-col items-center justify-center px-6">
        <div class="text-center max-w-md animate-fade-in">
          <div class="w-12 h-12 rounded-2xl bg-accent-50 flex items-center justify-center mx-auto mb-4">
            <MessageSquare class="w-6 h-6 text-accent-600" />
          </div>
          <h2 class="text-lg font-semibold text-gray-900 mb-1.5">开始多模型对话</h2>
          <p class="text-sm text-gray-500 mb-5">
            选择模型后输入你的问题，多个模型将同时回答
          </p>
        </div>
      </div>

      <!-- Rounds -->
      <div v-else class="max-w-5xl mx-auto px-4 py-6 space-y-8">
        <div v-for="round in chatStore.rounds" :key="round.id" class="space-y-4 animate-slide-up">
          <!-- User Message -->
          <div class="flex justify-end">
            <div class="max-w-xl bg-accent-600 text-white rounded-2xl rounded-tr-md px-4 py-3 shadow-sm">
              <p class="text-sm leading-relaxed whitespace-pre-wrap">{{ round.prompt }}</p>
              <span class="text-[11px] text-accent-200 mt-1 block">{{ formatTime(round.timestamp) }}</span>
            </div>
          </div>

          <!-- Responses Grid -->
          <div class="grid gap-3" :class="gridClass">
            <ResponseCard
              v-for="resp in getResponses(round)"
              :key="resp.model"
              :response="resp"
              :model-name="appStore.getModelName(resp.model)"
              :model-meta="appStore.getModel(resp.model)"
              :selected="round.selectedModel === resp.model"
              @select="chatStore.selectResponse(round.id, resp.model)"
            />
          </div>
        </div>

        <!-- No separate streaming block — getResponses merges live data into the last round -->
      </div>
    </div>

    <!-- Input Area -->
    <div class="border-t border-gray-200/60 bg-white safe-bottom">
      <!-- Model Chips -->
      <div class="px-4 pt-3 pb-1">
        <div class="flex items-center gap-1.5 flex-wrap max-w-5xl mx-auto">
          <ModelChip
            v-for="model in appStore.chatSelectedModelObjects"
            :key="model.id"
            :model="model"
            removable
            @remove="appStore.toggleModel('chat', model.id)"
          />
          <button
            @click="showModelSheet = true"
            class="inline-flex items-center gap-1 px-2 py-1 text-[11px] text-accent-600 hover:bg-accent-50 rounded-md transition-colors"
          >
            <Plus class="w-3 h-3" />
            模型
          </button>
          <div class="flex-1" />
          <button
            v-if="appStore.chatSelectedModels.length >= 2"
            @click="jumpToDiscuss"
            class="inline-flex items-center gap-1 px-2 py-1 text-[11px] text-purple-600 hover:bg-purple-50 rounded-md transition-colors"
          >
            <Users class="w-3 h-3" />
            深度讨论
          </button>
        </div>
      </div>

      <!-- Input -->
      <div class="px-4 pb-3">
        <div class="max-w-5xl mx-auto flex items-end gap-2">
          <div class="flex-1 relative bg-gray-50 rounded-xl border border-gray-200 focus-within:border-accent-400 focus-within:ring-2 focus-within:ring-accent-100 transition-all">
            <textarea
              ref="inputRef"
              v-model="inputText"
              :placeholder="inputPlaceholder"
              :disabled="chatStore.isStreaming"
              rows="1"
              class="w-full px-4 py-2.5 bg-transparent text-sm resize-none focus:outline-none disabled:opacity-50 max-h-[120px]"
              @keydown="handleKeydown"
              @input="autoResize"
            />
          </div>
          <button
            @click="handleSubmit"
            :disabled="!canSubmit"
            class="p-2.5 bg-accent-600 text-white rounded-xl hover:bg-accent-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
          >
            <ArrowUp class="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>

    <!-- Model Sheet -->
    <ModelSheet
      v-model:open="showModelSheet"
      mode="chat"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { MessageSquare, Plus, Users, ArrowUp } from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'
import { useChatStore } from '@/stores/chat'
import type { ChatRound } from '@mms/contracts'
import ResponseCard from '@/components/ResponseCard.vue'
import ModelChip from '@/components/ModelChip.vue'
import ModelSheet from '@/components/ModelSheet.vue'

const appStore = useAppStore()
const chatStore = useChatStore()
const router = useRouter()

const inputText = ref('')
const inputRef = ref<HTMLTextAreaElement>()
const scrollArea = ref<HTMLElement>()
const showModelSheet = ref(false)

const modelCount = computed(() => appStore.chatSelectedModels.length)

const gridClass = computed(() => {
  if (modelCount.value <= 2) return 'grid-cols-1 lg:grid-cols-2'
  return 'grid-cols-1 lg:grid-cols-2 xl:grid-cols-3'
})

const inputPlaceholder = computed(() => {
  if (modelCount.value === 0) return '请先选择模型...'
  if (modelCount.value < 2) return '至少选择 2 个模型...'
  return '输入你的问题... (Enter 发送，Shift+Enter 换行)'
})

const canSubmit = computed(() =>
  inputText.value.trim() && modelCount.value >= 2 && !chatStore.isStreaming
)

function getResponses(round: ChatRound) {
  if (round.responses.length > 0) return round.responses
  return Object.values(chatStore.currentResponses)
}

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSubmit()
  }
}

async function handleSubmit() {
  if (!canSubmit.value) return
  const prompt = inputText.value.trim()
  inputText.value = ''
  if (inputRef.value) inputRef.value.style.height = 'auto'

  chatStore.startChat(appStore.chatSelectedModels, prompt)

  await nextTick()
  if (scrollArea.value) {
    scrollArea.value.scrollTop = scrollArea.value.scrollHeight
  }
}

function jumpToDiscuss() {
  appStore.copySelection('chat', 'discuss')
  router.push('/discuss')
}

function formatTime(ts: string): string {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>
