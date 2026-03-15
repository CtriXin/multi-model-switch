<template>
  <div class="h-full flex flex-col pt-20 px-4 pb-4 overflow-hidden">
    <!-- Empty State -->
    <div
      v-if="!chatStore.isStreaming && chatStore.allStreams.length === 0"
      class="flex-1 flex flex-col items-center justify-center"
    >
      <div class="w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-100 to-purple-100 dark:from-indigo-500/20 dark:to-purple-500/20 flex items-center justify-center mb-6">
        <MessageSquare class="w-10 h-10 text-indigo-500" />
      </div>
      <h3 class="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-2">
        选择模型开始对话
      </h3>
      <p class="text-sm text-gray-500 text-center max-w-xs">
        至少选择 2 个模型，它们将同时回答你的问题
      </p>
    </div>

    <!-- Streaming View -->
    <div
      v-else
      class="flex-1 overflow-y-auto hide-scrollbar overscroll-none"
    >
      <!-- Prompt Bubble -->
      <div class="flex justify-center mb-6">
        <div class="px-5 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-2xl shadow-lg shadow-indigo-500/20 max-w-lg">
          <p class="text-sm">{{ currentPrompt }}</p>
        </div>
      </div>

      <!-- Response Cards -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <TransitionGroup name="fade-up">
          <div
            v-for="stream in chatStore.allStreams"
            :key="stream.modelId"
            class="glass rounded-2xl border border-white/30 overflow-hidden"
          >
            <!-- Card Header -->
            <div class="flex items-center gap-3 px-4 py-3 border-b border-white/10">
              <span class="text-xl">{{ getModelAvatar(stream.modelId) }}</span>
              <div class="flex-1">
                <p class="font-medium text-gray-800 dark:text-gray-100 text-sm">
                  {{ getModelName(stream.modelId) }}
                </p>
                <p class="text-xs text-gray-500">{{ getModelRole(stream.modelId) }}</p>
              </div>
              <div v-if="!stream.isComplete" class="flex gap-1">
                <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 typing-dot"></span>
                <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 typing-dot"></span>
                <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 typing-dot"></span>
              </div>
              <CheckCircle2 v-else class="w-4 h-4 text-green-500" />
            </div>

            <!-- Content -->
            <div class="p-4 prose prose-sm dark:prose-invert max-w-none">
              <p class="text-sm text-gray-700 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
                {{ stream.content }}
                <span v-if="!stream.isComplete" class="inline-block w-2 h-4 bg-indigo-500 animate-pulse ml-0.5 rounded-sm"></span>
              </p>
            </div>

            <!-- Actions -->
            <div v-if="stream.isComplete" class="flex items-center gap-2 px-4 py-3 border-t border-white/10">
              <button class="native-btn flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-indigo-50 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-300 text-sm font-medium">
                <ArrowRight class="w-4 h-4" />
                继续
              </button>
              <button class="native-btn p-2 rounded-lg bg-gray-100 dark:bg-white/10 text-gray-500">
                <Copy class="w-4 h-4" />
              </button>
            </div>
          </div>
        </TransitionGroup>
      </div>

      <!-- History -->
      <div v-if="chatStore.history.length > 0" class="mt-8">
        <h4 class="text-sm font-medium text-gray-500 mb-4">历史记录</h4>
        <div class="space-y-4">
          <div
            v-for="(item, idx) in chatStore.history"
            :key="idx"
            class="glass rounded-xl p-4 border border-white/20"
          >
            <p class="text-sm text-gray-600 dark:text-gray-300 mb-2">{{ item.prompt }}</p>
            <div class="flex items-center gap-2">
              <span
                v-for="resp in item.responses"
                :key="resp.modelId"
                class="text-xs px-2 py-1 rounded-full bg-gray-100 dark:bg-white/10 text-gray-600 dark:text-gray-300"
              >
                {{ getModelName(resp.modelId) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { useChatStore } from '@/stores/chat'
import { MessageSquare, CheckCircle2, ArrowRight, Copy } from 'lucide-vue-next'

const appStore = useAppStore()
const chatStore = useChatStore()

const currentPrompt = computed(() => chatStore.prompt)

function getModelName(id: string) {
  return appStore.models.find(m => m.id === id)?.name || id
}

function getModelAvatar(id: string) {
  return appStore.models.find(m => m.id === id)?.avatar || '🤖'
}

function getModelRole(id: string) {
  return appStore.models.find(m => m.id === id)?.role || ''
}
</script>
