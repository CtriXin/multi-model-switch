<template>
  <div
    :class="[
      'group relative p-4 rounded-xl border-2 cursor-pointer transition-all duration-200',
      selected
        ? 'border-indigo-500 bg-indigo-50'
        : disabled
          ? 'border-gray-100 bg-gray-50 opacity-50 cursor-not-allowed'
          : 'border-gray-200 bg-white hover:border-indigo-300 hover:shadow-md'
    ]"
    @click="!disabled && $emit('toggle')"
  >
    <!-- Selection Indicator -->
    <div
      :class="[
        'absolute top-3 right-3 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors',
        selected
          ? 'border-indigo-500 bg-indigo-500'
          : 'border-gray-300 bg-white group-hover:border-indigo-400'
      ]"
    >
      <Check v-if="selected" class="w-3 h-3 text-white" />
    </div>

    <!-- Model Info -->
    <div class="pr-8">
      <!-- Name & Provider -->
      <div class="flex items-center gap-2 mb-2">
        <h4 class="font-medium text-gray-900">{{ model.name }}</h4>
        <TierBadge :tier="model.tier" />
      </div>

      <!-- Tags -->
      <div class="flex flex-wrap gap-1.5 mb-3">
        <span
          v-for="tag in model.tags"
          :key="tag"
          class="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full"
        >
          {{ tagLabels[tag] || tag }}
        </span>
      </div>

      <!-- Specs -->
      <div class="flex items-center gap-4 text-xs text-gray-500">
        <span class="flex items-center gap-1">
          <DollarSign class="w-3.5 h-3.5" />
          {{ formatPrice(model.priceInput) }} / {{ formatPrice(model.priceOutput) }}
        </span>
        <span class="flex items-center gap-1">
          <Maximize class="w-3.5 h-3.5" />
          {{ formatContext(model.contextWindow) }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Check, DollarSign, Maximize } from 'lucide-vue-next'
import type { ModelMeta, ModelTag } from '@mms/contracts'
import TierBadge from './TierBadge.vue'

const props = defineProps<{
  model: ModelMeta
  selected: boolean
  disabled?: boolean
}>()

defineEmits<{
  toggle: []
}>()

const tagLabels: Record<ModelTag, string> = {
  fast: '快速',
  reasoning: '推理',
  recommended: '推荐',
  vision: '视觉',
  coding: '编程',
}

function formatPrice(price: number): string {
  if (price < 1) return `${(price * 100).toFixed(1)}¢`
  return `$${price.toFixed(1)}`
}

function formatContext(window: number): string {
  if (window >= 1000000) return `${(window / 1000000).toFixed(1)}M`
  if (window >= 1000) return `${(window / 1000).toFixed(0)}K`
  return `${window}`
}
</script>
