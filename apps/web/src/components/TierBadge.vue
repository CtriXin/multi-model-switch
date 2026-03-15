<template>
  <span
    :class="[
      'inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full',
      tierClasses[tier]
    ]"
  >
    {{ tierNames[tier] }}
  </span>
</template>

<script setup lang="ts">
import type { ModelTier } from '@mms/contracts'

const props = defineProps<{
  tier: ModelTier
}>()

const tierClasses: Record<ModelTier, string> = {
  0: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
  1: 'bg-blue-50 text-blue-700 border border-blue-200',
  2: 'bg-amber-50 text-amber-700 border border-amber-200',
}

const tierNames: Record<ModelTier, string> = {
  0: '经济',
  1: '主力',
  2: '旗舰',
}
</script>
