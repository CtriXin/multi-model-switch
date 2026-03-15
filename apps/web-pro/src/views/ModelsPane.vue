<template>
  <div class="h-full overflow-y-auto px-6 py-8">
    <div class="max-w-4xl mx-auto">
      <h2 class="text-lg font-semibold text-gray-900 mb-6">模型管理</h2>

      <!-- Categories -->
      <div v-for="(models, category) in categorized" :key="category" class="mb-8">
        <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">{{ category }}</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <div
            v-for="model in models"
            :key="model.id"
            class="p-4 bg-white rounded-xl border border-gray-200 hover:shadow-card transition-all"
          >
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium text-gray-900">{{ model.name }}</span>
              <span
                class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                :class="tierClass(model.tier)"
              >{{ tierName(model.tier) }}</span>
            </div>
            <div class="text-[11px] text-gray-400 space-y-0.5">
              <div>Provider: {{ model.provider }}</div>
              <div>Context: {{ (model.contextWindow / 1000).toFixed(0) }}K</div>
              <div>价格: ${{ model.priceInput }}/M → ${{ model.priceOutput }}/M</div>
            </div>
            <div class="flex items-center gap-1 mt-2">
              <span
                v-for="tag in model.tags"
                :key="tag"
                class="text-[10px] px-1.5 py-0.5 bg-gray-50 text-gray-500 rounded"
              >{{ tag }}</span>
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
import type { ModelMeta, ModelTier } from '@mms/contracts'

const appStore = useAppStore()

const categorized = computed(() => {
  const result: Record<string, ModelMeta[]> = {}
  for (const m of appStore.models) {
    if (!result[m.category]) result[m.category] = []
    result[m.category].push(m)
  }
  return result
})

function tierClass(tier: ModelTier): string {
  return tier === 2 ? 'bg-amber-50 text-amber-600'
    : tier === 1 ? 'bg-blue-50 text-blue-600'
    : 'bg-emerald-50 text-emerald-600'
}

function tierName(tier: ModelTier): string {
  return tier === 2 ? '旗舰' : tier === 1 ? '主力' : '经济'
}
</script>
