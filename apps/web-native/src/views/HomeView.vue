<template>
  <div class="min-h-screen flex flex-col">
    <!-- Hero -->
    <div class="flex-1 flex flex-col items-center justify-center px-6 pt-12 pb-8">
      <!-- Logo & Title -->
      <div class="relative mb-8">
        <div class="w-24 h-24 rounded-3xl bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center shadow-2xl shadow-indigo-500/30 bubble-float">
          <span class="text-4xl">🔀</span>
        </div>
        <div class="absolute -bottom-1 -right-1 w-8 h-8 bg-green-500 rounded-full flex items-center justify-center shadow-lg">
          <Zap class="w-4 h-4 text-white" />
        </div>
      </div>

      <h1 class="text-4xl font-bold gradient-text mb-3 text-center">
        Multi-Model Studio
      </h1>
      <p class="text-gray-500 dark:text-gray-400 text-center max-w-md mb-10">
        同时让多个 AI 思考，比较不同视角，做出更好的决策
      </p>

      <!-- Mode Selection -->
      <div class="w-full max-w-sm space-y-4">
        <button
          @click="enterWorkspace('chat')"
          class="native-btn w-full p-5 rounded-2xl glass border border-white/20 dark:border-white/10 flex items-center gap-4 group"
        >
          <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center group-hover:scale-110 transition-transform">
            <MessageSquare class="w-7 h-7 text-white" />
          </div>
          <div class="flex-1 text-left">
            <h3 class="font-semibold text-gray-900 dark:text-white">Chat 对话</h3>
            <p class="text-sm text-gray-500 dark:text-gray-400">多模型并行，快速对比答案</p>
          </div>
          <ChevronRight class="w-5 h-5 text-gray-400 group-hover:text-indigo-500 group-hover:translate-x-1 transition-all" />
        </button>

        <button
          @click="enterWorkspace('discuss')"
          class="native-btn w-full p-5 rounded-2xl glass border border-white/20 dark:border-white/10 flex items-center gap-4 group"
        >
          <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-pink-500 to-rose-600 flex items-center justify-center group-hover:scale-110 transition-transform">
            <Users class="w-7 h-7 text-white" />
          </div>
          <div class="flex-1 text-left">
            <h3 class="font-semibold text-gray-900 dark:text-white">Discuss 讨论</h3>
            <p class="text-sm text-gray-500 dark:text-gray-400">三阶段收敛，深度决策</p>
          </div>
          <ChevronRight class="w-5 h-5 text-gray-400 group-hover:text-pink-500 group-hover:translate-x-1 transition-all" />
        </button>
      </div>

      <!-- Quick presets -->
      <div class="mt-8 flex flex-wrap justify-center gap-2">
        <button
          v-for="preset in presets"
          :key="preset.id"
          @click="applyPreset(preset)"
          class="native-btn px-4 py-2 rounded-full text-sm bg-gray-100 dark:bg-white/10 text-gray-600 dark:text-gray-300 hover:bg-indigo-100 dark:hover:bg-indigo-500/20 transition-colors"
        >
          {{ preset.name }}
        </button>
      </div>
    </div>

    <!-- Bottom bar -->
    <div class="px-6 pb-8 flex justify-center gap-4">
      <button
        @click="appStore.toggleDark()"
        class="native-btn p-3 rounded-full glass border border-white/20"
      >
        <Sun v-if="appStore.isDark" class="w-5 h-5 text-amber-500" />
        <Moon v-else class="w-5 h-5 text-indigo-500" />
      </button>
      <button class="native-btn p-3 rounded-full glass border border-white/20">
        <Settings class="w-5 h-5 text-gray-500" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { MessageSquare, Users, ChevronRight, Zap, Sun, Moon, Settings } from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const appStore = useAppStore()

const presets = ref([
  { id: 'fast', name: '🚀 快速对比', models: ['claude-haiku', 'gpt-4o-mini'] },
  { id: 'quality', name: '💎 高质量', models: ['claude-4', 'gpt-5'] },
  { id: 'balanced', name: '⚖️ 均衡', models: ['claude-4', 'gemini-3', 'codex-2'] },
  { id: 'code', name: '💻 代码', models: ['codex-2', 'gemini-3'] }
])

function enterWorkspace(mode: 'chat' | 'discuss') {
  appStore.setMode(mode)
  router.push({ path: '/workspace', query: { mode } })
}

function applyPreset(preset: { id: string; models: string[] }) {
  preset.models.forEach(id => appStore.toggleModel(id))
  router.push('/workspace')
}
</script>
