<template>
  <div class="h-full overflow-y-auto px-6 py-8">
    <div class="max-w-2xl mx-auto">
      <h2 class="text-lg font-semibold text-gray-900 mb-6">设置</h2>

      <div class="space-y-6">
        <!-- API Keys -->
        <router-link
          to="/setup"
          class="block bg-white rounded-xl border border-gray-200 p-5 hover:border-emerald-300 hover:shadow-card transition-all group"
        >
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-sm font-medium text-gray-900 mb-1">API 密钥配置</h3>
              <p class="text-xs text-gray-400">
                {{ keyStore.configuredCount > 0
                  ? `已配置 ${keyStore.configuredCount} 个服务商`
                  : '尚未配置，点击获取免费 API Key' }}
              </p>
            </div>
            <div class="flex items-center gap-2">
              <div class="flex gap-1">
                <div
                  v-for="p in providers"
                  :key="p.id"
                  class="w-2 h-2 rounded-full"
                  :class="keyStore.hasKey(p.id) ? 'bg-emerald-500' : 'bg-gray-200'"
                />
              </div>
              <ChevronRight class="w-4 h-4 text-gray-300 group-hover:text-emerald-500 transition-colors" />
            </div>
          </div>
        </router-link>

        <div class="bg-white rounded-xl border border-gray-200 p-5">
          <h3 class="text-sm font-medium text-gray-900 mb-3">外观</h3>
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <span class="text-sm text-gray-600">侧边栏默认展开</span>
              <button class="w-10 h-6 bg-accent-600 rounded-full relative">
                <span class="absolute right-1 top-1 w-4 h-4 bg-white rounded-full shadow" />
              </button>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-sm text-gray-600">紧凑模式</span>
              <button class="w-10 h-6 bg-gray-200 rounded-full relative">
                <span class="absolute left-1 top-1 w-4 h-4 bg-white rounded-full shadow" />
              </button>
            </div>
          </div>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5">
          <h3 class="text-sm font-medium text-gray-900 mb-3">关于</h3>
          <div class="text-sm text-gray-500 space-y-1">
            <p>MMS Pro v0.3.0</p>
            <p>多模型协作工作台</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'
import { useKeyStore, PROVIDERS } from '@/stores/keys'

const keyStore = useKeyStore()
const providers = PROVIDERS
</script>
