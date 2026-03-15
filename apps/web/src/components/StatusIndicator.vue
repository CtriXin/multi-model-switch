<template>
  <div class="flex items-center gap-1.5">
    <span
      :class="[
        'w-2 h-2 rounded-full',
        statusClasses[status]
      ]"
    />
    <span class="text-xs text-gray-500">{{ statusText[status] }}</span>
  </div>
</template>

<script setup lang="ts">
import type { ResponseStatus } from '@mms/contracts'

const props = defineProps<{
  status: ResponseStatus
}>()

const statusClasses: Record<ResponseStatus, string> = {
  idle: 'bg-gray-300',
  loading: 'bg-gray-400 animate-pulse',
  streaming: 'bg-blue-500 animate-pulse',
  done: 'bg-emerald-500',
  error: 'bg-red-500',
  cancelled: 'bg-gray-300',
}

const statusText: Record<ResponseStatus, string> = {
  idle: '等待中',
  loading: '加载中',
  streaming: '输出中',
  done: '完成',
  error: '错误',
  cancelled: '取消',
}
</script>
