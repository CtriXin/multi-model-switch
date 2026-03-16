<script setup lang="ts">
import { computed } from 'vue'
import { getModelColor, useAppStore } from '@/stores/app'
import type { DebateExchange } from '@/features/committee'

const props = defineProps<{
  review: DebateExchange
  roleName: string
  targetName: string
}>()

const appStore = useAppStore()
const modelName = computed(() =>
  appStore.models.find((model) => model.id === props.review.modelId)?.name || props.review.modelId
)
const providerColor = computed(() => {
  const provider = appStore.models.find((model) => model.id === props.review.modelId)?.provider || ''
  return getModelColor(provider)
})
</script>

<template>
  <div class="overflow-hidden rounded-[1.25rem] border border-amber-500/20 bg-surface-1 shadow-sm">
    <div class="bg-gradient-to-r from-rose-500/8 to-amber-500/8 px-4 py-3">
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <span class="font-semibold text-rose-300">{{ props.roleName }}</span>
        <span class="text-text-tertiary">vs</span>
        <span class="text-text-secondary">{{ props.targetName }}</span>
        <span
          class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px]"
          :style="{ borderColor: `${providerColor}30`, backgroundColor: `${providerColor}12` }"
        >
          <span class="h-1.5 w-1.5 rounded-full" :style="{ backgroundColor: providerColor }" />
          <span class="text-text-secondary">{{ modelName }}</span>
        </span>
        <span
          v-if="props.review.ok"
          class="ml-auto rounded-full bg-surface-1 px-2 py-0.5 text-[10px] font-medium text-text-tertiary"
        >
          {{ props.review.elapsed.toFixed(1) }}s
        </span>
      </div>
    </div>

    <div class="space-y-3 px-4 py-4 text-xs leading-6 text-text-secondary">
      <template v-if="props.review.ok">
        <div>
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-tertiary">他先反驳什么</div>
          <p>{{ props.review.rebuttal }}</p>
        </div>
        <div>
          <div class="mb-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-tertiary">哪条线不能退</div>
          <p>{{ props.review.keepBelief }}</p>
        </div>
        <div class="rounded-2xl bg-surface-0 px-3 py-3 text-text-primary border border-border-subtle">
          {{ props.review.integration }}
        </div>
      </template>

      <template v-else-if="props.review.error">
        <div class="rounded-2xl bg-red-500/5 border border-red-500/15 px-3 py-3 text-red-300">
          {{ props.review.error }}
        </div>
      </template>

      <template v-else>
        <div class="space-y-2">
          <div class="h-3 rounded-full bg-surface-3 animate-pulse" />
          <div class="h-3 w-11/12 rounded-full bg-surface-3 animate-pulse" />
          <div class="h-3 w-8/12 rounded-full bg-surface-3 animate-pulse" />
        </div>
      </template>
    </div>
  </div>
</template>
