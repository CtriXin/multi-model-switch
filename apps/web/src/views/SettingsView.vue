<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
    <h1 class="text-2xl font-bold text-gray-900 mb-8">设置</h1>

    <div class="space-y-6">
      <!-- Providers Section -->
      <div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-200">
          <h2 class="text-lg font-semibold text-gray-900">模型提供商</h2>
          <p class="text-sm text-gray-500 mt-1">管理你的 API 密钥和账户</p>
        </div>
        <div class="divide-y divide-gray-200">
          <div
            v-for="provider in providers"
            :key="provider.id"
            class="px-6 py-4 flex items-center justify-between"
          >
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center">
                <Key class="w-5 h-5 text-gray-600" />
              </div>
              <div>
                <h3 class="font-medium text-gray-900">{{ provider.name }}</h3>
                <p class="text-sm text-gray-500">
                  {{ provider.hasOAuth ? '支持 OAuth' : 'API Key 认证' }}
                </p>
              </div>
            </div>
            <div class="flex items-center gap-3">
              <span
                :class="[
                  'px-2 py-1 text-xs font-medium rounded-full',
                  provider.enabled
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-gray-100 text-gray-600'
                ]"
              >
                {{ provider.enabled ? '已启用' : '未启用' }}
              </span>
              <button class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                <ChevronRight class="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Accounts Section -->
      <div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-200">
          <h2 class="text-lg font-semibold text-gray-900">账户</h2>
          <p class="text-sm text-gray-500 mt-1">已连接的账户</p>
        </div>
        <div class="divide-y divide-gray-200">
          <div
            v-for="account in accounts"
            :key="account.id"
            class="px-6 py-4 flex items-center justify-between"
          >
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center">
                <User class="w-5 h-5 text-indigo-600" />
              </div>
              <div>
                <h3 class="font-medium text-gray-900">{{ account.name }}</h3>
                <p class="text-sm text-gray-500">{{ account.email }}</p>
              </div>
            </div>
            <span class="px-2 py-1 text-xs font-medium bg-emerald-100 text-emerald-700 rounded-full">
              已连接
            </span>
          </div>
        </div>
      </div>

      <!-- About Section -->
      <div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-200">
          <h2 class="text-lg font-semibold text-gray-900">关于</h2>
        </div>
        <div class="px-6 py-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-gray-600">版本</span>
            <span class="text-gray-900 font-medium">{{ version }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-gray-600">功能</span>
            <div class="flex gap-2">
              <span
                v-for="feature in features"
                :key="feature"
                class="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full"
              >
                {{ feature }}
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
import { Key, ChevronRight, User } from 'lucide-vue-next'
import { useAppStore } from '@/stores'

const appStore = useAppStore()

const providers = computed(() => appStore.providers)
const accounts = computed(() => appStore.accounts)
const version = computed(() => appStore.config?.version || '0.1.0')
const features = computed(() => appStore.config?.features || [])
</script>
