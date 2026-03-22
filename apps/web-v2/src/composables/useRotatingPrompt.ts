import { onUnmounted, ref, unref, watch, type Ref } from 'vue'

type MaybeRef<T> = T | Ref<T>

export function useRotatingPrompt(
  promptsSource: MaybeRef<string[]>,
  enabledSource: MaybeRef<boolean>,
  intervalMs = 2800,
) {
  const currentPrompt = ref('')
  let promptIndex = 0
  let timer: ReturnType<typeof setInterval> | null = null

  function stopTimer() {
    if (!timer) return
    clearInterval(timer)
    timer = null
  }

  function restartTimer() {
    stopTimer()
    const prompts = unref(promptsSource)
    const enabled = unref(enabledSource)

    currentPrompt.value = prompts[0] ?? ''
    promptIndex = 0

    if (!enabled || prompts.length <= 1) return

    timer = setInterval(() => {
      promptIndex = (promptIndex + 1) % prompts.length
      currentPrompt.value = prompts[promptIndex] ?? ''
    }, intervalMs)
  }

  watch(
    [() => unref(promptsSource), () => unref(enabledSource)],
    restartTimer,
    { immediate: true, deep: true },
  )

  onUnmounted(stopTimer)

  return currentPrompt
}
