<template>
  <div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-purple-50/50">
      <div class="flex items-center gap-2">
        <span class="font-medium text-gray-900">{{ modelName }}</span>
        <TierBadge v-if="modelMeta" :tier="modelMeta.tier" />
      </div>
      <StatusIndicator :status="status" />
    </div>

    <!-- Content -->
    <div class="p-4">
      <!-- Loading -->
      <div v-if="summary.ok === false && !summary.error" class="space-y-2">
        <div class="h-4 bg-gray-100 rounded animate-pulse"></div>
        <div class="h-4 bg-gray-100 rounded animate-pulse w-3/4"></div>
        <div class="h-4 bg-gray-100 rounded animate-pulse w-1/2"></div>
      </div>

      <!-- Error -->
      <div v-else-if="summary.error" class="text-red-600 text-sm">
        {{ summary.error }}
      </div>

      <!-- Brief Content -->
      <div v-else-if="summary.brief" class="space-y-3 text-sm">
        <div v-if="summary.brief.approach" class="flex gap-2">
          <span class="text-purple-600 font-medium whitespace-nowrap">方案:</span>
          <span class="text-gray-700">{{ summary.brief.approach }}</span>
        </div>
        <div v-if="summary.brief.reasoning" class="flex gap-2">
          <span class="text-purple-600 font-medium whitespace-nowrap">推理:</span>
          <span class="text-gray-700">{{ summary.brief.reasoning }}</span>
        </div>
        <div v-if="summary.brief.risks?.length" class="flex gap-2">
          <span class="text-purple-600 font-medium whitespace-nowrap">风险:</span>
          <ul class="text-gray-700 space-y-0.5">
            <li v-for="risk in summary.brief.risks" :key="risk" class="text-gray-600">• {{ risk }}</li>
          </ul>
        </div>
        <div v-if="summary.brief.keyDecisions?.length" class="flex gap-2">
          <span class="text-purple-600 font-medium whitespace-nowrap">决策:</span>
          <ul class="text-gray-700 space-y-0.5">
            <li v-for="decision in summary.brief.keyDecisions" :key="decision" class="text-gray-600">• {{ decision }}</li>
          </ul>
        </div>
        <div v-if="summary.brief.nextStep" class="flex gap-2">
          <span class="text-purple-600 font-medium whitespace-nowrap">下一步:</span>
          <span class="text-gray-700">{{ summary.brief.nextStep }}</span>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div v-if="summary.elapsed > 0" class="px-4 py-2 bg-gray-50 text-xs text-gray-500 text-right">
      耗时 {{ formatElapsed(summary.elapsed) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Phase1Summary, ModelMeta, ResponseStatus } from '@mms/contracts'
import { useAppStore } from '@/stores'
import TierBadge from './TierBadge.vue'
import StatusIndicator from './StatusIndicator.vue'

const props = defineProps<{
  summary: Phase1Summary
}>()

const appStore = useAppStore()

const modelMeta = computed((): ModelMeta | undefined => {
  return appStore.models.find(m => m.id === props.summary.model)
})

const modelName = computed(() => {
  return modelMeta.value?.name || props.summary.model
})

const status = computed((): ResponseStatus => {
  if (props.summary.error) return 'error'
  if (props.summary.ok) return 'done'
  return 'loading'
})

function formatElapsed(seconds: number): string {
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`
  return `${seconds.toFixed(1)}s`
}
</script>
