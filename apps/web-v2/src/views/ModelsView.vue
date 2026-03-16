<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore, getModelColor, type ModelMeta } from '@/stores/app'
import { useProviderStore } from '@/stores/provider'
import { Cpu, Zap, Brain, Eye, Code, Loader2, AlertCircle, EyeOff, DollarSign, Image, RotateCcw } from 'lucide-vue-next'

const appStore = useAppStore()
const providerStore = useProviderStore()
const router = useRouter()

// Filter state
const filterFree = ref(true)
const filterVision = ref(false)

const suppressedCount = computed(() => appStore.getSuppressedModelIds().length)

const filteredModels = computed(() => {
  let models = appStore.models
  if (filterFree.value) models = models.filter(m => m.free)
  if (filterVision.value) models = models.filter(m => m.supportsVision)
  return models
})

const modelsByProvider = computed(() => {
  const map: Record<string, ModelMeta[]> = {}
  for (const m of filteredModels.value) {
    ;(map[m.provider] ??= []).push(m)
  }
  return map
})

const providerLabels: Record<string, string> = {
  anthropic: 'CLAUDE',
  openai: 'OPENAI',
  google: 'GOOGLE',
  deepseek: 'DEEPSEEK',
  moonshot: 'MOONSHOT',
  meta: 'META',
  mistral: 'MISTRAL',
  qwen: 'QWEN',
  cerebras: 'CEREBRAS',
}

function tierLabel(tier: number): string {
  return tier === 2 ? 'Premium' : tier === 1 ? 'Standard' : 'Free'
}

function tierClass(tier: number): string {
  return tier === 2
    ? 'bg-amber-500/15 text-amber-400 border-amber-500/20'
    : tier === 1
      ? 'bg-blue-500/15 text-blue-400 border-blue-500/20'
      : 'bg-green-500/15 text-green-400 border-green-500/20'
}

function formatContext(n: number): string {
  return n >= 1_000_000 ? `${n / 1_000_000}M` : `${n / 1000}K`
}

function formatPrice(n: number): string {
  return `$${n}`
}

const tagIcons: Record<string, typeof Cpu> = {
  reasoning: Brain,
  coding: Code,
  vision: Eye,
  fast: Zap,
}

function goToSettings() {
  router.push('/settings')
}
</script>

<template>
  <div class="flex-1 overflow-y-auto">
    <div class="max-w-4xl mx-auto px-6 py-8 space-y-8">
      <div class="flex items-end justify-between">
        <div>
          <h1 class="text-lg font-semibold text-text-primary">模型管理</h1>
          <p class="text-xs text-text-tertiary mt-1">
            <template v-if="appStore.loading">加载中...</template>
            <template v-else-if="appStore.models.length">
              {{ filteredModels.length }} / {{ appStore.models.length }} 个模型
            </template>
            <template v-else>未加载模型</template>
          </p>
        </div>

        <!-- Filter chips -->
        <div v-if="appStore.models.length" class="flex items-center gap-2">
          <button
            v-if="suppressedCount"
            @click="appStore.restoreSuppressedModels()"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border
                   bg-amber-500/10 text-amber-400 border-amber-500/25 hover:bg-amber-500/20"
          >
            <RotateCcw :size="12" />
            恢复隐藏 ({{ suppressedCount }})
          </button>
          <button
            @click="filterFree = !filterFree"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border"
            :class="filterFree
              ? 'bg-green-500/15 text-green-400 border-green-500/30'
              : 'bg-surface-2 text-text-tertiary border-border-subtle hover:bg-surface-3'"
          >
            <DollarSign :size="12" />
            仅免费
          </button>
          <button
            @click="filterVision = !filterVision"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border"
            :class="filterVision
              ? 'bg-purple-500/15 text-purple-400 border-purple-500/30'
              : 'bg-surface-2 text-text-tertiary border-border-subtle hover:bg-surface-3'"
          >
            <Image :size="12" />
            支持图片
          </button>
        </div>
      </div>

      <!-- Loading state -->
      <div v-if="appStore.loading" class="flex items-center justify-center py-16">
        <Loader2 :size="24" class="text-accent animate-spin" />
        <span class="ml-2 text-sm text-text-tertiary">正在加载模型列表...</span>
      </div>

      <!-- Empty state: no configured providers -->
      <div
        v-else-if="!appStore.models.length"
        class="card p-8 text-center space-y-3"
      >
        <AlertCircle :size="32" class="text-text-tertiary mx-auto" />
        <p class="text-sm text-text-secondary">{{ appStore.error || '未配置 API 通道' }}</p>
        <p class="text-xs text-text-tertiary">请先在设置中配置 Provider 和 API Key</p>
        <button
          @click="goToSettings"
          class="text-xs text-accent hover:text-accent/80 px-4 py-2 rounded-lg border border-accent/30
                 hover:bg-accent/10 transition-colors mt-2"
        >
          前往设置
        </button>
      </div>

      <!-- Filter result empty -->
      <div
        v-else-if="!filteredModels.length && (filterFree || filterVision)"
        class="card p-8 text-center space-y-2"
      >
        <EyeOff :size="24" class="text-text-tertiary mx-auto" />
        <p class="text-sm text-text-secondary">
          没有符合过滤条件的模型
        </p>
        <button
          @click="filterFree = false; filterVision = false"
          class="text-xs text-accent hover:text-accent/80"
        >
          清除过滤
        </button>
      </div>

      <!-- Provider groups -->
      <template v-else>
        <div
          v-for="(models, provider) in modelsByProvider"
          :key="provider"
          class="space-y-3"
        >
          <div class="flex items-center gap-2">
            <span
              class="w-3 h-3 rounded-full"
              :style="{ backgroundColor: getModelColor(provider) }"
            />
            <h2 class="text-xs font-bold uppercase tracking-wider text-text-tertiary">
              {{ providerLabels[provider] ?? provider.toUpperCase() }}
            </h2>
            <span class="text-[10px] text-text-tertiary">({{ models.length }})</span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <div
              v-for="model in models"
              :key="model.id"
              class="card p-4 space-y-3 hover:border-border-hover transition-colors"
            >
              <!-- Header -->
              <div class="flex items-start justify-between">
                <div class="min-w-0">
                  <div class="flex items-center gap-1.5 flex-wrap">
                    <h3 class="text-sm font-semibold text-text-primary">{{ model.name }}</h3>
                    <span
                      v-if="model.free"
                      class="text-[9px] px-1.5 py-0.5 bg-green-500/15 text-green-400 rounded-full font-medium"
                    >FREE</span>
                    <span
                      v-if="model.supportsVision"
                      class="text-[9px] px-1.5 py-0.5 bg-purple-500/15 text-purple-400 rounded-full font-medium"
                    >VISION</span>
                  </div>
                  <p class="text-[10px] text-text-tertiary font-mono mt-0.5">{{ model.id }}</p>
                </div>
                <span
                  class="text-[10px] font-medium px-2 py-0.5 rounded-full border shrink-0 ml-2"
                  :class="tierClass(model.tier)"
                >{{ tierLabel(model.tier) }}</span>
              </div>

              <!-- Stats -->
              <div class="grid grid-cols-3 gap-2 text-center">
                <div>
                  <p class="text-[10px] text-text-tertiary">Context</p>
                  <p class="text-xs font-medium text-text-primary">{{ formatContext(model.contextWindow) }}</p>
                </div>
                <div>
                  <p class="text-[10px] text-text-tertiary">Input</p>
                  <p class="text-xs font-medium text-text-primary">{{ formatPrice(model.priceInput) }}/M</p>
                </div>
                <div>
                  <p class="text-[10px] text-text-tertiary">Output</p>
                  <p class="text-xs font-medium text-text-primary">{{ formatPrice(model.priceOutput) }}/M</p>
                </div>
              </div>

              <!-- Tags -->
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="tag in model.tags"
                  :key="tag"
                  class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]
                         bg-surface-3 text-text-tertiary"
                >
                  <component :is="tagIcons[tag] ?? Cpu" :size="10" />
                  {{ tag }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Error -->
      <div v-if="appStore.error && appStore.models.length" class="card p-3 border-amber-500/30">
        <p class="text-xs text-amber-400">{{ appStore.error }}</p>
      </div>
    </div>
  </div>
</template>
