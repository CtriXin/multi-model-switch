<template>
  <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">历史会话</h1>
        <p class="text-gray-600 mt-1">查看和管理你的对话记录</p>
      </div>
      <div class="flex gap-3">
        <router-link
          to="/chat"
          class="px-4 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition-colors"
        >
          新建对话
        </router-link>
      </div>
    </div>

    <div class="grid gap-4">
      <div
        v-for="session in sessions"
        :key="session.id"
        class="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-md transition-shadow"
      >
        <div class="flex items-start justify-between">
          <div>
            <div class="flex items-center gap-2 mb-2">
              <span
                :class="[
                  'px-2 py-0.5 text-xs font-medium rounded-full',
                  session.mode === 'chat'
                    ? 'bg-indigo-100 text-indigo-700'
                    : 'bg-purple-100 text-purple-700'
                ]"
              >
                {{ session.mode === 'chat' ? '对话' : '讨论' }}
              </span>
              <span class="text-sm text-gray-500">
                {{ formatDate(session.createdAt) }}
              </span>
            </div>
            <h3 class="font-semibold text-gray-900 mb-1">{{ session.title }}</h3>
            <div class="flex items-center gap-2 text-sm text-gray-500">
              <span>{{ session.models.length }} 个模型</span>
              <span>·</span>
              <span>{{ session.messageCount }} 条消息</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              title="导出"
            >
              <Download class="w-5 h-5" />
            </button>
            <button
              class="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
              title="删除"
            >
              <Trash2 class="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="sessions.length === 0" class="text-center py-16">
      <History class="w-12 h-12 text-gray-300 mx-auto mb-4" />
      <h3 class="text-lg font-medium text-gray-900 mb-1">暂无会话</h3>
      <p class="text-gray-500">开始你的第一次对话吧</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Download, Trash2, History } from 'lucide-vue-next'
import { useAppStore } from '@/stores'

const appStore = useAppStore()

const sessions = computed(() => [
  {
    id: '1',
    mode: 'chat' as const,
    title: '前端框架选择讨论',
    models: ['claude-sonnet-4-6', 'gpt-4.1-mini', 'gemini-2.5-pro'],
    createdAt: new Date(Date.now() - 86400000).toISOString(),
    messageCount: 12,
  },
  {
    id: '2',
    mode: 'discuss' as const,
    title: 'API 设计方案评审',
    models: ['claude-opus-4-6', 'deepseek-r1'],
    createdAt: new Date(Date.now() - 172800000).toISOString(),
    messageCount: 1,
  },
])

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>
