import { ref } from 'vue'
import { useStoryLiveStore } from '@/stores/storyLive'
import { detectEndingIntent, shouldTriggerTwist, updateStoryState, type StoryLiveRole } from '@/features/play-modes/story-live'

/**
 * Extracted story flow logic from storyLive store.
 * Handles the continueStory two-phase generation (logic+emotion → twist eval)
 * and ending flow (detection → confirmation → grade).
 * Keeps the store under 800 lines.
 */
export function useStoryFlow() {
  const store = useStoryLiveStore()

  const pendingEndingText = ref<string | null>(null)

  async function continueStory(input: string): Promise<boolean> {
    const trimmed = input.trim()
    if (!trimmed || store.processing) return false

    // Check ending intent — expose to view for confirmation
    if (detectEndingIntent(trimmed)) {
      pendingEndingText.value = trimmed
      return true
    }

    // Delegate to store's raw generation
    return store._continueStoryRaw(trimmed)
  }

  function confirmEnding() {
    const text = pendingEndingText.value
    pendingEndingText.value = null
    if (text) store.endSession(text)
  }

  function dismissEnding() {
    pendingEndingText.value = null
  }

  return {
    pendingEndingText,
    continueStory,
    confirmEnding,
    dismissEnding,
  }
}
