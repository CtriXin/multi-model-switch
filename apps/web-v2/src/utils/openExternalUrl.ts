import { invoke } from '@tauri-apps/api/core'

function isTauriRuntime() {
  return typeof window !== 'undefined' && ('__TAURI_INTERNALS__' in window || '__TAURI__' in window)
}

export async function openExternalUrl(url?: string | null) {
  if (!url || typeof window === 'undefined') return

  if (isTauriRuntime()) {
    try {
      await invoke('open_external_url', { url })
      return
    } catch {
      // Fall through to browser open as a soft fallback.
    }
  }

  window.open(url, '_blank', 'noopener,noreferrer')
}
