<template>
  <div class="h-[calc(100vh-4rem)] flex flex-col">
    <!-- Main Content Area -->
    <div ref="scrollContainer" class="flex-1 overflow-y-auto">
      <div v-if="!hasRounds && !isStreaming" class="h-full flex flex-col items-center justify-center px-4">
        <!-- Empty State -->
        <div class="text-center max-w-lg">
          <div class="w-16 h-16 bg-indigo-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
            <MessageSquare class="w-8 h-8 text-indigo-600" />
          </div>
          <h2 class="text-2xl font-semibold text-gray-900 mb-2">开始多模型对话</h2>
          <p class="text-gray-600 mb-6">
            {{ selectedModels.length > 0
              ? `已选择 ${selectedModels.length} 个模型，输入问题开始对话`
              : '请先选择模型，然后输入你的问题' }}
          </p>
          <button
            v-if="selectedModels.length === 0"
            @click="showPicker = true"
            class="px-6 py-3 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 transition-colors"
          >
            选择模型
          </button>
        </div>
      </div>

      <!-- Chat Rounds -->
      <div v-else class="p-4 space-y-8">
        <div
          v-for="round in rounds"
          :key="round.id"
          :ref="(el) => { if (el) roundRefs[round.id] = el as HTMLElement }"
          class="space-y-4"
        >
          <!-- User Prompt -->
          <div class="flex justify-end">
            <div class="max-w-2xl bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-5 py-3">
              <p class="text-sm">{{ round.prompt }}</p>
              <span class="text-xs text-indigo-200 mt-1 block">
                {{ formatTime(round.timestamp) }}
              </span>
            </div>
          </div>

          <!-- Split View (Left Main + Right Thumbnails) -->
          <SplitView
            :round="getRoundWithCurrentResponses(round)"
            :models="models"
            :viewed-responses="chatStore.viewedResponses[round.id]"
            @select="(modelId) => selectResponse(round.id, modelId)"
          />
        </div>

        <!-- Streaming Responses -->
        <div v-if="isStreaming" class="space-y-4">
          <div class="flex justify-end">
            <div class="max-w-2xl bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-5 py-3">
              <p class="text-sm">{{ currentPrompt }}</p>
            </div>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            <ChatResponseCard
              v-for="response in allResponses"
              :key="response.model"
              :response="response"
              @select="null"
            />
          </div>
        </div>

        <div class="h-4"></div>
      </div>
    </div>

    <!-- Input Area -->
    <div class="border-t border-gray-200 bg-white p-4">
      <div class="max-w-4xl mx-auto">
        <div class="flex items-end gap-3">
          <div class="flex-1 relative">
            <textarea
              v-model="inputText"
              :placeholder="inputPlaceholder"
              :disabled="isStreaming"
              rows="1"
              class="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
              @keydown.enter.prevent="handleSubmit"
              @input="autoResize"
              ref="textareaRef"
            ></textarea>
          </div>
          <button
            @click="handleSubmit"
            :disabled="!canSubmit"
            class="px-6 py-3 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <Send class="w-4 h-4" />
            发送
          </button>
        </div>

        <!-- Selected Models Bar -->
        <div class="flex items-center gap-2 mt-3 flex-wrap">
          <span class="text-xs text-gray-500">当前模型:</span>
          <span
            v-for="model in selectedModelObjects"
            :key="model.id"
            class="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded-lg"
          >
            {{ model.name }}
            <button
              @click="removeModel(model.id)"
              class="text-gray-400 hover:text-red-500"
            >
              <X class="w-3 h-3" />
            </button>
          </span>
          <button
            @click="showPicker = true"
            class="text-xs text-indigo-600 hover:text-indigo-700 font-medium"
          >
            + 添加
          </button>
          <div class="flex-1"></div>
          <button
            v-if="selectedModels.length >= 2"
            @click="jumpToDiscuss"
            class="flex items-center gap-1.5 px-3 py-1.5 text-xs text-purple-600 hover:text-purple-700 hover:bg-purple-50 rounded-lg transition-colors"
          >
            <Users class="w-3.5 h-3.5" />
            进入讨论
          </button>
          <button
            @click="showPicker = true"
            class="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
          >
            <RefreshCw class="w-3.5 h-3.5" />
            更换模型
          </button>
        </div>
      </div>
    </div>

    <!-- Model Picker Modal -->
    <ModelPicker
      v-model:show="showPicker"
      :models="appStore.models"
      :selected="selectedModels"
      :presets="appStore.presets"
      @toggle="toggleModel"
      @apply-preset="applyPreset"
      @clear="clearSelection"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { MessageSquare, Send, X, RefreshCw, Users } from 'lucide-vue-next'
import { useAppStore, useChatStore } from '@/stores'
import type { ChatRound, ChatResponse } from '@mms/contracts'
import { nextTick } from 'vue'
import ModelPicker from '@/components/ModelPicker.vue'
import ChatResponseCard from '@/components/ChatResponseCard.vue'
import SplitView from '@/components/SplitView.vue'

const appStore = useAppStore()
const chatStore = useChatStore()
const router = useRouter()
const route = useRoute()

const showPicker = ref(false)
const inputText = ref('')
const currentPrompt = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
const scrollContainer = ref<HTMLElement>()

const roundRefs = ref<Record<string, HTMLElement>>({})

const models = computed(() => appStore.models)
// Use chat-specific selection
const selectedModels = computed(() => appStore.chatSelectedModels)
const selectedModelObjects = computed(() => appStore.chatSelectedModelObjects)
const rounds = computed(() => chatStore.rounds)
const isStreaming = computed(() => chatStore.isStreaming)
const allResponses = computed(() => chatStore.allResponses)
const hasRounds = computed(() => chatStore.hasRounds)

const inputPlaceholder = computed(() => {
  if (selectedModels.value.length === 0) return '请先选择模型...'
  return '输入问题，按 Enter 发送...'
})

const canSubmit = computed(() => {
  return inputText.value.trim() && selectedModels.value.length >= 2 && !isStreaming.value
})

function autoResize() {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 200) + 'px'
  }
}

async function handleSubmit() {
  if (!canSubmit.value) return

  const prompt = inputText.value.trim()
  currentPrompt.value = prompt
  inputText.value = ''

  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }

  const roundId = await chatStore.startChat(selectedModels.value, prompt)

  // Scroll to make the new round visible with user's message at top
  nextTick(() => {
    const roundEl = roundId ? roundRefs.value[roundId] : null
    if (roundEl && scrollContainer.value) {
      const containerRect = scrollContainer.value.getBoundingClientRect()
      const roundRect = roundEl.getBoundingClientRect()
      const relativeTop = roundRect.top - containerRect.top + scrollContainer.value.scrollTop
      scrollContainer.value.scrollTo({
        top: Math.max(0, relativeTop - 16), // 16px padding
        behavior: 'smooth'
      })
    }
  })
}

function getModelName(modelId: string): string {
  const model = models.value.find(m => m.id === modelId)
  return model?.name || modelId
}

function getResponse(round: ChatRound, modelId: string): ChatResponse | undefined {
  return round.responses.find(r => r.model === modelId)
}

function getOtherResponses(round: ChatRound): ChatResponse[] {
  return round.responses.filter(r => r.model !== round.selectedModel)
}

function selectResponse(roundId: string, modelId: string) {
  chatStore.selectResponse(roundId, modelId)
  // Keep the round in view after selection
  nextTick(() => {
    const roundEl = roundRefs.value[roundId]
    if (roundEl && scrollContainer.value) {
      const containerRect = scrollContainer.value.getBoundingClientRect()
      const roundRect = roundEl.getBoundingClientRect()
      // If round is above visible area, scroll to it
      if (roundRect.top < containerRect.top) {
        const relativeTop = roundRect.top - containerRect.top + scrollContainer.value.scrollTop
        scrollContainer.value.scrollTo({
          top: Math.max(0, relativeTop - 16),
          behavior: 'smooth'
        })
      }
    }
  })
}

function removeModel(modelId: string) {
  appStore.toggleModel('chat', modelId)
}

function toggleModel(modelId: string) {
  appStore.toggleModel('chat', modelId)
}

function applyPreset(presetId: string) {
  appStore.applyPreset('chat', presetId)
}

function clearSelection() {
  appStore.clearSelection('chat')
}

function jumpToDiscuss() {
  // Copy current chat selection to discuss
  appStore.copySelection('chat', 'discuss')

  // Build context from chat rounds
  const context = buildChatContext()

  // Navigate to discuss with context in query params
  router.push({
    path: '/discuss',
    query: { context: encodeURIComponent(context) }
  })
}

function buildChatContext(): string {
  if (rounds.value.length === 0) return ''

  const parts: string[] = ['以下是对话历史：\n']

  for (const round of rounds.value) {
    parts.push(`用户：${round.prompt}`)

    if (round.selectedModel) {
      const selected = getResponse(round, round.selectedModel)
      if (selected) {
        parts.push(`${getModelName(round.selectedModel)}：${selected.content.slice(0, 500)}`)
      }
    }

    // Add other models' responses as context
    const others = getOtherResponses(round)
    if (others.length > 0) {
      parts.push('\n其他模型的观点：')
      for (const resp of others) {
        parts.push(`${getModelName(resp.model)}：${resp.content.slice(0, 200)}...`)
      }
    }

    parts.push('---')
  }

  return parts.join('\n\n')
}

function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

// Merge current streaming responses into round for display
function getRoundWithCurrentResponses(round: ChatRound): ChatRound {
  const current = chatStore.currentResponses
  const hasCurrentData = Object.keys(current).length > 0

  if (!hasCurrentData) return round

  // Create merged responses from current streaming data
  const mergedResponses = Object.values(current).map(r => ({ ...r }))

  return {
    ...round,
    responses: mergedResponses.length > 0 ? mergedResponses : round.responses,
  }
}

// Handle context from Discuss
onMounted(async () => {
  const contextFromDiscuss = route.query.context as string | undefined
  if (contextFromDiscuss) {
    const decodedContext = decodeURIComponent(contextFromDiscuss)
    // Auto-send the discuss conclusion as first message
    if (selectedModels.value.length >= 2) {
      await chatStore.startChat(selectedModels.value, decodedContext)
      // Clear query params
      router.replace({ path: '/chat' })
    } else {
      // Store in input if no models selected
      inputText.value = decodedContext
    }
  }
})
</script>
