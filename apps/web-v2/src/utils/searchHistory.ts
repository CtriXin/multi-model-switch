/**
 * Shared model search history — persisted in localStorage.
 * Used by ModelChipBar, IOSModelSheet, CommitteeModelPoolPicker.
 */

const STORAGE_KEY = 'mms-model-search-history'
const MAX_ITEMS = 6

export function getSearchHistory(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function addSearchHistory(keyword: string) {
  const trimmed = keyword.trim()
  if (!trimmed || trimmed.length < 2) return
  const list = getSearchHistory().filter(k => k !== trimmed)
  list.unshift(trimmed)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_ITEMS)))
}

export function clearSearchHistory() {
  localStorage.removeItem(STORAGE_KEY)
}
