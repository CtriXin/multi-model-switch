<script setup lang="ts">
import type { CommitteePhase } from '@/features/committee'

defineProps<{
  phase: CommitteePhase
  title: string
  subtitle?: string
  status: 'waiting' | 'running' | 'done'
  colorClass: string
}>()
</script>

<template>
  <div class="relative flex items-start gap-4 mb-8 animate-slide-up">
    <div
      class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 z-10 shadow-sm text-white text-sm font-semibold"
      :class="colorClass"
    >
      {{ phase }}
    </div>

    <div class="flex-1 mt-1">
      <div class="flex items-center gap-2 mb-3 flex-wrap">
        <h3 class="text-sm font-semibold text-text-primary">{{ title }}</h3>
        <span v-if="subtitle" class="text-xs text-text-tertiary">{{ subtitle }}</span>
        <span
          v-if="status === 'running'"
          class="text-[10px] px-2 py-0.5 rounded-full font-medium flex items-center gap-1 bg-accent/10 text-accent"
        >
          <span class="w-1 h-1 rounded-full bg-accent animate-pulse_dot" />
          进行中
        </span>
        <span
          v-else-if="status === 'done'"
          class="text-[10px] px-2 py-0.5 rounded-full font-medium bg-green-500/10 text-green-500"
        >
          完成
        </span>
      </div>
      <slot />
    </div>
  </div>
</template>
