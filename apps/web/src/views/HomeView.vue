<template>
  <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
    <!-- Hero Section -->
    <div class="text-center mb-16">
      <h1 class="text-4xl font-bold text-gray-900 mb-4">
        多模型协作工作台
      </h1>
      <p class="text-lg text-gray-600 max-w-2xl mx-auto">
        同时与多个 AI 模型对话，比较不同观点，获得更全面的答案。
        支持 Chat 对比模式和 Discuss 深度讨论模式。
      </p>
    </div>

    <!-- Mode Selection Cards -->
    <div class="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
      <!-- Chat Mode -->
      <router-link
        to="/chat"
        class="group relative bg-white rounded-2xl border border-gray-200 p-8 hover:border-indigo-500 hover:shadow-lg transition-all duration-300"
      >
        <div class="absolute top-6 right-6 w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center group-hover:bg-indigo-600 transition-colors">
          <MessageSquare class="w-6 h-6 text-indigo-600 group-hover:text-white transition-colors" />
        </div>
        <h2 class="text-2xl font-semibold text-gray-900 mb-3">Chat 对话</h2>
        <p class="text-gray-600 mb-6">
          同时向多个模型提问，并行获取回答。适合快速比较不同模型的观点和风格。
        </p>
        <ul class="space-y-2 text-sm text-gray-500">
          <li class="flex items-center gap-2">
            <CheckCircle class="w-4 h-4 text-indigo-500" />
            多模型并行响应
          </li>
          <li class="flex items-center gap-2">
            <CheckCircle class="w-4 h-4 text-indigo-500" />
            卡片式对比展示
          </li>
          <li class="flex items-center gap-2">
            <CheckCircle class="w-4 h-4 text-indigo-500" />
            支持多轮对话
          </li>
        </ul>
      </router-link>

      <!-- Discuss Mode -->
      <router-link
        to="/discuss"
        class="group relative bg-white rounded-2xl border border-gray-200 p-8 hover:border-purple-500 hover:shadow-lg transition-all duration-300"
      >
        <div class="absolute top-6 right-6 w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center group-hover:bg-purple-600 transition-colors">
          <Users class="w-6 h-6 text-purple-600 group-hover:text-white transition-colors" />
        </div>
        <h2 class="text-2xl font-semibold text-gray-900 mb-3">Discuss 讨论</h2>
        <p class="text-gray-600 mb-6">
          三阶段深度讨论：独立方案 → 交叉审查 → 综合结论。适合复杂问题的多角度分析。
        </p>
        <ul class="space-y-2 text-sm text-gray-500">
          <li class="flex items-center gap-2">
            <CheckCircle class="w-4 h-4 text-purple-500" />
            三阶段结构化讨论
          </li>
          <li class="flex items-center gap-2">
            <CheckCircle class="w-4 h-4 text-purple-500" />
            模型间交叉审查
          </li>
          <li class="flex items-center gap-2">
            <CheckCircle class="w-4 h-4 text-purple-500" />
            第三方中立综合
          </li>
        </ul>
      </router-link>
    </div>

    <!-- Quick Start -->
    <div class="mt-16 text-center">
      <p class="text-gray-500 mb-4">快速开始</p>
      <div class="flex flex-wrap justify-center gap-3">
        <button
          v-for="preset in quickPresets"
          :key="preset.id"
          @click="quickStart(preset)"
          class="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium transition-colors"
        >
          {{ preset.name }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { MessageSquare, Users, CheckCircle } from 'lucide-vue-next'
import { useAppStore } from '@/stores'
import type { Preset } from '@mms/contracts'

const router = useRouter()
const appStore = useAppStore()

const quickPresets = computed(() => appStore.presets.slice(0, 4))

function quickStart(preset: Preset) {
  appStore.applyPreset(preset.id)
  router.push('/chat')
}
</script>
