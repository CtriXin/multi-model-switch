import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface Toast {
  id: string
  type: 'info' | 'success' | 'error' | 'warning'
  message: string
  duration: number
  /** Optional action button */
  action?: {
    label: string
    onClick: () => void
  }
  /** Countdown seconds remaining (for UI progress) */
  countdown?: number
}

export const useToastStore = defineStore('toast', () => {
  const toasts = ref<Toast[]>([])

  function add(type: Toast['type'], message: string, duration = 3000) {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    toasts.value.push({ id, type, message, duration })
    if (duration > 0) {
      setTimeout(() => remove(id), duration)
    }
    return id
  }

  function remove(id: string) {
    const idx = toasts.value.findIndex(t => t.id === id)
    if (idx >= 0) toasts.value.splice(idx, 1)
  }

  /**
   * Show a warning toast with countdown + cancel action.
   * Returns a promise: resolves true if countdown finishes, false if cancelled.
   */
  function countdown(
    message: string,
    seconds = 5,
    actionLabel = '取消',
  ): Promise<boolean> {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    let cancelled = false
    let intervalId: ReturnType<typeof setInterval>

    return new Promise((resolve) => {
      const toast: Toast = {
        id,
        type: 'warning',
        message: `${message} (${seconds}s)`,
        duration: 0, // manual control
        countdown: seconds,
        action: {
          label: actionLabel,
          onClick: () => {
            cancelled = true
            clearInterval(intervalId)
            remove(id)
            resolve(false)
          },
        },
      }
      toasts.value.push(toast)

      let remaining = seconds
      intervalId = setInterval(() => {
        remaining--
        const t = toasts.value.find(t => t.id === id)
        if (t) {
          t.countdown = remaining
          t.message = `${message} (${remaining}s)`
        }
        if (remaining <= 0) {
          clearInterval(intervalId)
          remove(id)
          if (!cancelled) resolve(true)
        }
      }, 1000)
    })
  }

  const info = (msg: string) => add('info', msg)
  const success = (msg: string) => add('success', msg)
  const error = (msg: string) => add('error', msg, 5000)

  return { toasts, add, remove, countdown, info, success, error }
})
