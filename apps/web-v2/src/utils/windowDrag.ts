import { getCurrentWindow } from '@tauri-apps/api/window'

const NO_DRAG_SELECTOR = [
  'button',
  'a',
  'input',
  'textarea',
  'select',
  'option',
  '[role="button"]',
  '[data-no-window-drag="true"]',
].join(', ')

function isTauriRuntime() {
  return typeof window !== 'undefined' && ('__TAURI_INTERNALS__' in window || '__TAURI__' in window)
}

export async function startWindowDrag(event: MouseEvent) {
  if (event.button !== 0) return

  const target = event.target as HTMLElement | null
  if (target?.closest(NO_DRAG_SELECTOR)) return

  if (!isTauriRuntime()) return

  try {
    await getCurrentWindow().startDragging()
  } catch {
    // Ignore drag failures in non-tauri or transient states.
  }
}
