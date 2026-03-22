export function appendLocalDebugLog<T>(
  globalKey: string,
  storageKey: string,
  entry: T,
  limit = 120,
) {
  const root = globalThis as typeof globalThis & Record<string, unknown>
  const current = Array.isArray(root[globalKey]) ? [...(root[globalKey] as T[])] : loadStoredDebugLog<T>(storageKey)
  current.push(entry)
  const next = current.slice(-limit)
  root[globalKey] = next

  try {
    globalThis.localStorage?.setItem(storageKey, JSON.stringify(next))
  } catch {
    // Ignore quota / availability failures and keep the in-memory copy.
  }

  return next
}

function loadStoredDebugLog<T>(storageKey: string) {
  try {
    const raw = globalThis.localStorage?.getItem(storageKey)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed as T[] : []
  } catch {
    return []
  }
}
