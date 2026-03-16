<template>
  <div class="overflow-hidden rounded-[1.25rem] border border-rose-100 bg-white shadow-card">
    <div class="bg-gradient-to-r from-rose-50 to-amber-50 px-4 py-3">
      <div class="flex items-center gap-2 text-xs">
        <span class="font-semibold text-rose-700">{{ roleName }}</span>
        <span class="text-slate-300">vs</span>
        <span class="text-slate-500">{{ targetName }}</span>
        <span
          v-if="review.ok"
          class="ml-auto rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-medium text-slate-500"
        >
          {{ review.elapsed.toFixed(1) }}s
        </span>
      </div>
    </div>

    <div class="space-y-3 px-4 py-4 text-xs leading-6 text-slate-600">
      <template v-if="review.ok">
        <div>
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Rebuttal</div>
          <p>{{ review.rebuttal }}</p>
        </div>
        <div>
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Belief Lock</div>
          <p>{{ review.keepBelief }}</p>
        </div>
        <div class="rounded-2xl bg-slate-950 px-3 py-3 text-slate-100">
          {{ review.integration }}
        </div>
      </template>

      <template v-else>
        <div class="space-y-2">
          <div class="h-3 rounded-full bg-slate-100 animate-pulse" />
          <div class="h-3 w-11/12 rounded-full bg-slate-100 animate-pulse" />
          <div class="h-3 w-8/12 rounded-full bg-slate-100 animate-pulse" />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DebateExchange } from '@/features/committee'

defineProps<{
  review: DebateExchange
  roleName: string
  targetName: string
}>()
</script>
