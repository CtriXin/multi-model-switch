<template>
  <div class="bg-white rounded-xl border border-gray-200 shadow-card overflow-hidden">
    <div class="px-4 py-3 border-b border-gray-100">
      <div class="flex items-center justify-between">
        <span class="text-sm font-medium text-gray-800">{{ modelName }}</span>
        <span
          v-if="summary.ok"
          class="text-[10px] text-green-600 bg-green-50 px-1.5 py-0.5 rounded"
        >{{ summary.elapsed.toFixed(1) }}s</span>
        <span v-else class="text-[10px] text-gray-400 animate-pulse">生成中...</span>
      </div>
    </div>

    <div class="px-4 py-3">
      <div v-if="!summary.ok && !summary.error" class="space-y-2">
        <div class="h-2.5 bg-gray-100 rounded animate-pulse w-full" />
        <div class="h-2.5 bg-gray-100 rounded animate-pulse w-2/3" />
      </div>
      <div v-else-if="summary.error" class="text-xs text-red-500">{{ summary.error }}</div>
      <div v-else-if="summary.brief" class="space-y-2 text-xs">
        <div>
          <span class="text-gray-400 font-medium">方案：</span>
          <span class="text-gray-700">{{ summary.brief.approach }}</span>
        </div>
        <div>
          <span class="text-gray-400 font-medium">理由：</span>
          <span class="text-gray-700">{{ summary.brief.reasoning }}</span>
        </div>
        <div v-if="summary.brief.risks.length">
          <span class="text-gray-400 font-medium">风险：</span>
          <span class="text-gray-700">{{ summary.brief.risks.join('、') }}</span>
        </div>
        <div>
          <span class="text-gray-400 font-medium">下一步：</span>
          <span class="text-gray-700">{{ summary.brief.nextStep }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Phase1Summary } from '@mms/contracts'

defineProps<{
  summary: Phase1Summary
  modelName: string
}>()
</script>
