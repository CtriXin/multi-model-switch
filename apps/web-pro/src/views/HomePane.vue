<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-3xl mx-auto px-6 py-16">
      <!-- Welcome -->
      <div class="text-center mb-12 animate-fade-in">
        <div class="w-14 h-14 rounded-2xl bg-gradient-to-br from-accent-500 to-purple-600 flex items-center justify-center mx-auto mb-5 shadow-lg">
          <svg class="w-7 h-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 12h4l2-6 3 12 2-6h5"/>
          </svg>
        </div>
        <h1 class="text-2xl font-bold text-gray-900 mb-2">多模型协作工作台</h1>
        <p class="text-gray-500 text-sm max-w-md mx-auto">
          同时与多个 AI 模型对话、比较、讨论，获得更全面的决策支持。
        </p>
      </div>

      <!-- Setup Guide Banner -->
      <button
        @click="$router.push('/setup')"
        class="w-full mb-8 p-4 bg-gradient-to-r from-emerald-50 to-cyan-50 border border-emerald-200/60 rounded-2xl text-left hover:shadow-card transition-all group animate-fade-in"
      >
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-cyan-500 flex items-center justify-center flex-shrink-0 shadow-sm">
            <KeyRound class="w-5 h-5 text-white" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="text-sm font-semibold text-gray-900">{{ keyStore.isFirstTime ? '快速配置免费 API' : 'API 配置' }}</span>
              <span
                v-if="keyStore.isFirstTime"
                class="text-[10px] px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded-full font-medium animate-pulse"
              >3 分钟上手</span>
              <span v-else class="text-[10px] px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded-full font-medium">
                {{ keyStore.configuredCount }} 个已配置
              </span>
            </div>
            <p class="text-xs text-gray-400 mt-0.5">
              {{ keyStore.isFirstTime ? '注册即送免费额度，支持 DeepSeek、智谱、Google Gemini 等' : '管理你的 API 密钥和服务商配置' }}
            </p>
          </div>
          <ArrowUpRight class="w-4 h-4 text-gray-300 group-hover:text-emerald-500 transition-colors flex-shrink-0" />
        </div>
      </button>

      <!-- Mode Cards -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-12">
        <button
          @click="$router.push('/chat')"
          class="group text-left p-5 bg-white rounded-2xl border border-gray-200 hover:border-accent-300 hover:shadow-elevated transition-all duration-200"
        >
          <div class="flex items-start justify-between mb-3">
            <div class="w-10 h-10 rounded-xl bg-accent-50 flex items-center justify-center group-hover:bg-accent-100 transition-colors">
              <MessageSquare class="w-5 h-5 text-accent-600" />
            </div>
            <ArrowUpRight class="w-4 h-4 text-gray-300 group-hover:text-accent-500 transition-colors" />
          </div>
          <h3 class="font-semibold text-gray-900 mb-1">Chat 对话</h3>
          <p class="text-sm text-gray-500 leading-relaxed">
            多模型并行响应，实时对比不同观点
          </p>
          <div class="flex items-center gap-2 mt-3">
            <span class="text-[11px] px-2 py-0.5 bg-accent-50 text-accent-600 rounded-full">多轮对话</span>
            <span class="text-[11px] px-2 py-0.5 bg-gray-50 text-gray-500 rounded-full">并行对比</span>
          </div>
        </button>

        <button
          @click="$router.push('/discuss')"
          class="group text-left p-5 bg-white rounded-2xl border border-gray-200 hover:border-purple-300 hover:shadow-elevated transition-all duration-200"
        >
          <div class="flex items-start justify-between mb-3">
            <div class="w-10 h-10 rounded-xl bg-purple-50 flex items-center justify-center group-hover:bg-purple-100 transition-colors">
              <Users class="w-5 h-5 text-purple-600" />
            </div>
            <ArrowUpRight class="w-4 h-4 text-gray-300 group-hover:text-purple-500 transition-colors" />
          </div>
          <h3 class="font-semibold text-gray-900 mb-1">Discuss 讨论</h3>
          <p class="text-sm text-gray-500 leading-relaxed">
            三阶段深度讨论，交叉审查得出综合结论
          </p>
          <div class="flex items-center gap-2 mt-3">
            <span class="text-[11px] px-2 py-0.5 bg-purple-50 text-purple-600 rounded-full">结构化讨论</span>
            <span class="text-[11px] px-2 py-0.5 bg-gray-50 text-gray-500 rounded-full">交叉审查</span>
          </div>
        </button>
      </div>

      <!-- Presets -->
      <div class="mb-12">
        <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">快速预设</h3>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
          <button
            v-for="preset in appStore.presets"
            :key="preset.id"
            @click="quickStart(preset.id)"
            class="px-3 py-2.5 bg-white rounded-xl border border-gray-200 hover:border-gray-300 hover:shadow-card text-left transition-all"
          >
            <span class="text-base mb-1 block">{{ preset.icon }}</span>
            <span class="text-sm font-medium text-gray-800 block">{{ preset.name }}</span>
            <span class="text-[11px] text-gray-400">{{ getPresetModelCount(preset.id) }} 个模型</span>
          </button>
        </div>
      </div>

      <!-- Keyboard hint -->
      <div class="text-center text-sm text-gray-400">
        <kbd class="px-1.5 py-0.5 bg-gray-100 rounded text-xs border border-gray-200">⌘K</kbd>
        <span class="ml-1.5">打开命令面板</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { MessageSquare, Users, ArrowUpRight, KeyRound } from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'
import { useKeyStore } from '@/stores/keys'

const appStore = useAppStore()
const keyStore = useKeyStore()
const router = useRouter()

function quickStart(presetId: string) {
  appStore.applyPreset('chat', presetId)
  router.push('/chat')
}

function getPresetModelCount(presetId: string): number {
  return appStore.presets.find(p => p.id === presetId)?.models.length || 0
}
</script>
