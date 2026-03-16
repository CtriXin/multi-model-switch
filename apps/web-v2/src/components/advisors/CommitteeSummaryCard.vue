<script setup lang="ts">
import { computed } from 'vue'
import { getModelColor, useAppStore } from '@/stores/app'
import { CATEGORY_META, getStanceLabels, type PersonaDefinition } from '@/stores/persona'
import type { RoleSummary } from '@/features/committee'

const props = defineProps<{
  summary: RoleSummary
  role: PersonaDefinition
  modelName: string
}>()

const appStore = useAppStore()
const stance = computed(() => getStanceLabels(props.role.stance))
const providerColor = computed(() => {
  const provider = appStore.models.find((model) => model.id === props.summary.modelId)?.provider || ''
  return getModelColor(provider)
})
</script>

<template>
  <div class="rounded-[1.25rem] border border-border-default bg-surface-1 overflow-hidden shadow-sm">
    <div class="border-b border-border-subtle bg-surface-2/70 px-4 py-3">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-sm font-semibold text-text-primary">{{ role.name }}</span>
            <span class="text-[10px] font-medium text-text-tertiary">{{ role.title }}</span>
          </div>
          <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[10px]">
            <span class="rounded-full bg-surface-3 px-2 py-0.5 text-text-secondary">{{ CATEGORY_META[role.category].label }}</span>
            <span class="rounded-full bg-sky-500/10 px-2 py-0.5 text-sky-400">{{ stance.cognition }}</span>
            <span class="rounded-full bg-amber-500/10 px-2 py-0.5 text-amber-400">{{ stance.horizon }}</span>
            <span class="rounded-full bg-emerald-500/10 px-2 py-0.5 text-emerald-400">{{ stance.interest }}</span>
          </div>
        </div>
        <div class="flex flex-col items-end gap-1 text-right">
          <div
            v-if="summary.ok"
            class="inline-flex w-fit rounded-full bg-green-500/10 px-2 py-1 text-[10px] font-medium text-green-500"
          >
            {{ summary.elapsed.toFixed(1) }}s
          </div>
          <div
            v-else-if="summary.error"
            class="inline-flex w-fit rounded-full bg-red-500/10 px-2 py-1 text-[10px] text-red-400"
          >
            失败
          </div>
          <div v-else class="inline-flex w-fit rounded-full bg-surface-3 px-2 py-1 text-[10px] text-text-tertiary animate-pulse">
            思考中
          </div>
          <div
            class="inline-flex w-fit items-center gap-1 rounded-full border px-2 py-0.5 text-[10px]"
            :style="{ borderColor: `${providerColor}30`, backgroundColor: `${providerColor}12` }"
          >
            <span class="h-1.5 w-1.5 rounded-full" :style="{ backgroundColor: providerColor }" />
            <span class="text-text-secondary">{{ modelName }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="space-y-3 px-4 py-4">
      <template v-if="summary.ok">
        <div>
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-tertiary">一句判断</div>
          <p class="text-sm font-medium leading-6 text-text-primary">{{ summary.headline }}</p>
        </div>
        <div>
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-tertiary">他是怎么想的</div>
          <p class="text-xs leading-6 text-text-secondary">{{ summary.viewpoint }}</p>
        </div>
        <div>
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-tertiary">他最不放心什么</div>
          <p class="text-xs leading-6 text-text-secondary">{{ summary.tension }}</p>
        </div>
        <div class="rounded-2xl bg-surface-0 px-3 py-3 text-xs leading-6 text-text-primary border border-border-subtle">
          {{ summary.recommendation }}
        </div>
      </template>

      <template v-else-if="summary.error">
        <div class="rounded-2xl bg-red-500/5 border border-red-500/15 px-3 py-3 text-xs leading-6 text-red-300">
          {{ summary.error }}
        </div>
      </template>

      <template v-else>
        <div class="space-y-2">
          <div class="h-3 rounded-full bg-surface-3 animate-pulse" />
          <div class="h-3 w-10/12 rounded-full bg-surface-3 animate-pulse" />
          <div class="h-3 w-8/12 rounded-full bg-surface-3 animate-pulse" />
        </div>
      </template>
    </div>
  </div>
</template>
