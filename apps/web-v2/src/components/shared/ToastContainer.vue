<script setup lang="ts">
import { useToastStore } from '@/stores/toast'
import { X, CheckCircle, AlertCircle, Info } from 'lucide-vue-next'
import { TransitionGroup } from 'vue'

const toast = useToastStore()

const iconMap = {
  info: Info,
  success: CheckCircle,
  error: AlertCircle,
}

const colorMap = {
  info: 'border-blue-500/30 bg-blue-500/10',
  success: 'border-green-500/30 bg-green-500/10',
  error: 'border-red-500/30 bg-red-500/10',
}

const iconColorMap = {
  info: 'text-blue-400',
  success: 'text-green-400',
  error: 'text-red-400',
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
      <TransitionGroup name="toast">
        <div
          v-for="t in toast.toasts"
          :key="t.id"
          class="pointer-events-auto flex items-center gap-2.5 px-4 py-2.5 rounded-xl border
                 glass-strong shadow-lg max-w-xs animate-slide-up"
          :class="colorMap[t.type]"
        >
          <component :is="iconMap[t.type]" :size="16" :class="iconColorMap[t.type]" />
          <span class="text-sm text-text-primary flex-1">{{ t.message }}</span>
          <button @click="toast.remove(t.id)" class="text-text-tertiary hover:text-text-primary">
            <X :size="14" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-active { animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.toast-leave-active { animation: fadeOut 0.2s ease-out forwards; }
.toast-move { transition: transform 0.3s ease; }
@keyframes fadeOut { to { opacity: 0; transform: translateX(20px); } }
@keyframes slideUp { from { opacity: 0; transform: translateY(-8px); } }
</style>
