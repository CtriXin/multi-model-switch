<template>
  <div class="bg-white rounded-xl border border-gray-200 shadow-card overflow-hidden">
    <div class="px-4 py-2.5 border-b border-gray-100 flex items-center gap-2">
      <span class="text-xs font-medium text-pink-600">{{ reviewerName }}</span>
      <span class="text-[10px] text-gray-300">→</span>
      <span class="text-xs text-gray-500">审查 {{ targetName }}</span>
    </div>
    <div class="px-4 py-3 space-y-2 text-xs">
      <div v-if="review.agreement">
        <span class="text-green-500 font-medium">认同：</span>
        <span class="text-gray-700">{{ review.agreement }}</span>
      </div>
      <div v-if="review.challenge">
        <span class="text-red-500 font-medium">质疑：</span>
        <span class="text-gray-700">{{ review.challenge }}</span>
      </div>
      <div v-if="review.betterOption">
        <span class="text-blue-500 font-medium">改进：</span>
        <span class="text-gray-700">{{ review.betterOption }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Phase2Review } from '@mms/contracts'

defineProps<{
  review: Phase2Review
  reviewerName: string
  targetName: string
}>()
</script>
