<template>
  <span
    class="inline-flex items-center gap-1 pl-1.5 pr-1 py-0.5 rounded-md text-[11px] font-medium border transition-colors"
    :class="chipClass"
  >
    <span
      class="w-3.5 h-3.5 rounded flex items-center justify-center text-[8px] font-bold text-white flex-shrink-0"
      :style="{ background: color }"
    >{{ model.name.charAt(0) }}</span>
    <span class="truncate max-w-[100px]">{{ model.name }}</span>
    <span
      v-if="model.tier !== undefined"
      class="text-[9px] opacity-60"
    >{{ model.tier === 2 ? '★' : model.tier === 1 ? '●' : '○' }}</span>
    <button
      v-if="removable"
      @click.stop="$emit('remove')"
      class="ml-0.5 p-0.5 rounded hover:bg-black/5 transition-colors"
    >
      <X class="w-2.5 h-2.5" />
    </button>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { X } from 'lucide-vue-next'
import type { ModelMeta } from '@mms/contracts'

const props = defineProps<{
  model: ModelMeta
  removable?: boolean
}>()

defineEmits<{ remove: [] }>()

const color = computed(() => {
  const colors = ['#6366f1', '#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ec4899', '#06b6d4', '#f97316']
  const hash = props.model.id.split('').reduce((a, b) => a + b.charCodeAt(0), 0)
  return colors[hash % colors.length]
})

const chipClass = computed(() => {
  return 'bg-white border-gray-200 text-gray-700'
})
</script>
