<template>
  <div class="rounded-[1.25rem] border border-white/70 bg-white/90 shadow-card backdrop-blur-sm overflow-hidden">
    <div class="border-b border-slate-100 bg-slate-50/70 px-4 py-3">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="flex items-center gap-2">
            <span class="text-sm font-semibold text-slate-900">{{ role.name }}</span>
            <span class="text-[10px] font-medium text-slate-500">{{ role.title }}</span>
          </div>
          <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
            <span class="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">{{ role.categoryLabel }}</span>
            <span class="rounded-full bg-cyan-50 px-2 py-0.5 text-cyan-700">{{ role.axes.outlook }}</span>
            <span class="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700">{{ role.axes.horizon }}</span>
            <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700">{{ role.axes.interest }}</span>
          </div>
        </div>
        <div class="text-right">
          <div
            v-if="summary.ok"
            class="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-medium text-emerald-700"
          >
            {{ summary.elapsed.toFixed(1) }}s
          </div>
          <div v-else class="rounded-full bg-slate-100 px-2 py-1 text-[10px] text-slate-500 animate-pulse">
            思考中
          </div>
          <div class="mt-1 text-[10px] text-slate-400">{{ modelName }}</div>
        </div>
      </div>
    </div>

    <div class="space-y-3 px-4 py-4">
      <template v-if="summary.ok">
        <div>
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Headline</div>
          <p class="text-sm font-medium leading-6 text-slate-900">{{ summary.headline }}</p>
        </div>
        <div>
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Viewpoint</div>
          <p class="text-xs leading-6 text-slate-600">{{ summary.viewpoint }}</p>
        </div>
        <div>
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Tension</div>
          <p class="text-xs leading-6 text-slate-600">{{ summary.tension }}</p>
        </div>
        <div class="rounded-2xl bg-slate-950 px-3 py-3 text-xs leading-6 text-slate-100">
          {{ summary.recommendation }}
        </div>
      </template>

      <template v-else>
        <div class="space-y-2">
          <div class="h-3 rounded-full bg-slate-100 animate-pulse" />
          <div class="h-3 w-10/12 rounded-full bg-slate-100 animate-pulse" />
          <div class="h-3 w-8/12 rounded-full bg-slate-100 animate-pulse" />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CommitteeRole, RoleSummary } from '@/features/committee'

defineProps<{
  summary: RoleSummary
  role: CommitteeRole
  modelName: string
}>()
</script>
