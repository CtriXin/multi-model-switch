import { appendLocalDebugLog } from '@/utils/localDebugLog'

export type TimingPhase =
  | 'start'
  | 'mark'
  | 'success'
  | 'error'

export interface TimingLogEntry {
  ts: string
  monoMs: number
  elapsedMs: number
  label: string
  phase: TimingPhase
  meta?: Record<string, unknown>
}

const GLOBAL_KEY = '__MMS_TIMING_LOGS__'
const STORAGE_KEY = 'mms-timing-logs'

function nowMono() {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now()
  }
  return Date.now()
}

function isEnabled() {
  try {
    return globalThis.localStorage?.getItem('mms-timing-log') !== 'false'
  } catch {
    return true
  }
}

function normalizeError(error: unknown) {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
    }
  }
  return {
    message: String(error),
  }
}

export function pushTimingLog(
  label: string,
  phase: TimingPhase,
  elapsedMs: number,
  meta?: Record<string, unknown>,
) {
  const entry: TimingLogEntry = {
    ts: new Date().toISOString(),
    monoMs: nowMono(),
    elapsedMs: Math.round(elapsedMs),
    label,
    phase,
    meta,
  }

  appendLocalDebugLog<TimingLogEntry>(GLOBAL_KEY, STORAGE_KEY, entry)

  if (isEnabled()) {
    console.info('[mms-timing]', entry)
  }
}

export function createTimingSpan(label: string, meta?: Record<string, unknown>) {
  const startedAt = nowMono()
  pushTimingLog(label, 'start', 0, meta)

  return {
    mark(markLabel: string, extra?: Record<string, unknown>) {
      pushTimingLog(label, 'mark', nowMono() - startedAt, {
        ...meta,
        mark: markLabel,
        ...extra,
      })
    },
    success(extra?: Record<string, unknown>) {
      pushTimingLog(label, 'success', nowMono() - startedAt, {
        ...meta,
        ...extra,
      })
    },
    error(error: unknown, extra?: Record<string, unknown>) {
      pushTimingLog(label, 'error', nowMono() - startedAt, {
        ...meta,
        ...extra,
        error: normalizeError(error),
      })
    },
  }
}
