<template>
  <div class="relative flex items-start gap-4 mb-8 animate-slide-up">
    <!-- Timeline Node -->
    <div
      class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 z-10 shadow-sm text-white text-sm font-semibold"
      :class="colorClass"
    >
      {{ phase }}
    </div>

    <!-- Content -->
    <div class="flex-1 mt-1">
      <div class="flex items-center gap-2 mb-3">
        <h3 class="text-sm font-semibold text-gray-900">{{ title }}</h3>
        <span v-if="subtitle" class="text-xs text-gray-400">{{ subtitle }}</span>
        <!-- Status Pill -->
        <span
          v-if="status === 'running'"
          class="text-[10px] px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full font-medium flex items-center gap-1"
        >
          <span class="w-1 h-1 rounded-full bg-blue-500 animate-pulse-dot" />
          进行中
        </span>
        <span
          v-else-if="status === 'done'"
          class="text-[10px] px-2 py-0.5 bg-green-50 text-green-600 rounded-full font-medium"
        >完成</span>
      </div>
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DiscussPhase } from '@mms/contracts'

defineProps<{
  phase: DiscussPhase
  title: string
  subtitle?: string
  current: DiscussPhase
  status: 'waiting' | 'running' | 'done'
  colorClass: string
}>()
</script>
