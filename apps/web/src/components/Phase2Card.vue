<template>
  <div class="bg-white rounded-xl border border-pink-200 overflow-hidden">
    <!-- Header -->
    <div class="flex items-center gap-3 px-4 py-3 border-b border-pink-100 bg-pink-50/30">
      <div class="flex items-center gap-2">
        <span class="font-medium text-gray-900">{{ reviewerName }}</span>
        <span class="text-gray-400">审查</span>
        <span class="font-medium text-gray-900">{{ targetName }}</span>
      </div>
      <div class="flex-1"></div>
      <StatusIndicator :status="status" />
    </div>

    <!-- Content -->
    <div class="p-4 space-y-3">
      <!-- Loading -->
      <div v-if="review.skipped" class="text-gray-500 text-sm italic">
        跳过审查
      </div>

      <div v-else-if="review.ok && review.data" class="space-y-3 text-sm">
        <div v-if="review.agreement" class="flex gap-2">
          <span class="text-pink-600 font-medium whitespace-nowrap">认同:</span>
          <span class="text-gray-700">{{ review.agreement }}</span>
        </div>
        <div v-if="review.challenge" class="flex gap-2">
          <span class="text-pink-600 font-medium whitespace-nowrap">质疑:</span>
          <span class="text-gray-700">{{ review.challenge }}</span>
        </div>
        <div v-if="review.betterOption" class="flex gap-2">
          <span class="text-pink-600 font-medium whitespace-nowrap">建议:</span>
          <span class="text-gray-700">{{ review.betterOption }}</span>
        </div>
      </div>

      <div v-else-if="review.error" class="text-red-600 text-sm">
        {{ review.error }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Phase2Review, ResponseStatus } from '@mms/contracts'
import { useAppStore } from '@/stores'
import StatusIndicator from './StatusIndicator.vue'

const props = defineProps<{
  review: Phase2Review
}>()

const appStore = useAppStore()

const reviewerName = computed(() => {
  const model = appStore.models.find(m => m.id === props.review.reviewer)
  return model?.name || props.review.reviewer
})

const targetName = computed(() => {
  const model = appStore.models.find(m => m.id === props.review.target)
  return model?.name || props.review.target
})

const status = computed((): ResponseStatus => {
  if (props.review.skipped) return 'cancelled'
  if (props.review.error) return 'error'
  if (props.review.ok) return 'done'
  return 'loading'
})
</script>
