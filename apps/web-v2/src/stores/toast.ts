import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface Toast {
  id: string
  type: 'info' | 'success' | 'error'
  message: string
  duration: number
}

export const useToastStore = defineStore('toast', () => {
  const toasts = ref<Toast[]>([])

  function add(type: Toast['type'], message: string, duration = 3000) {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    toasts.value.push({ id, type, message, duration })
    if (duration > 0) {
      setTimeout(() => remove(id), duration)
    }
  }

  function remove(id: string) {
    const idx = toasts.value.findIndex(t => t.id === id)
    if (idx >= 0) toasts.value.splice(idx, 1)
  }

  const info = (msg: string) => add('info', msg)
  const success = (msg: string) => add('success', msg)
  const error = (msg: string) => add('error', msg, 5000)

  return { toasts, add, remove, info, success, error }
})
