/**
 * End-to-end speed test composable.
 *
 * Two-phase approach:
 *   Phase 1 — Server-side speed API (existing, via ensureSparkringSpeedTestForToday)
 *   Phase 2 — Parallel mini-ping from phone to measure real e2e latency
 *
 * Results merge into sparkringSpeedMap so all downstream consumers
 * (compareBySpeed, getLabAutoPool, pickLabModelIds, etc.) automatically benefit.
 */

import { ref } from 'vue'
import { useAppStore } from '@/stores/app'
import { pingModelLatency, ApiError } from '@/services/api'
import { getFetchRuntime } from '@/services/runtime'

const E2E_STATE_KEY = 'mms-e2e-speed-state'
const E2E_JAIL_KEY = 'mms-e2e-jail'
const MIN_INTERVAL_MS = 5 * 60 * 1000       // 5 minutes between tests
const HOUR_MAX_TESTS = 6                      // max 6 tests per hour
const NETWORK_DEBOUNCE_MS = 3_000             // 3s debounce on network change
const VISIBILITY_STALE_MS = 10 * 60 * 1000   // re-test after 10min away
const PING_TIMEOUT_MS = 10_000                // 10s per model ping
const TOP_N_MODELS = 7                        // ping top 7 from server-side ranking
const PING_FAIL_THRESHOLD = 3                 // degrade after 3 consecutive failures
const PENALTY_LATENCY_MS = 99_999             // penalty value: sorts failed models to bottom

// 429 jail: escalating cooldown — 5h → 24h → 7d
const JAIL_COOLDOWNS_MS = [
  5 * 60 * 60 * 1000,      // 5 hours
  24 * 60 * 60 * 1000,     // 24 hours
  7 * 24 * 60 * 60 * 1000, // 7 days
]

interface JailEntry {
  /** Timestamp when the model is released */
  releaseAt: number
  /** How many times this model has been jailed (for escalation) */
  strikes: number
}

interface E2eState {
  lastTestAt: number
  hourResetAt: number
  hourCount: number
  networkFingerprint: string
  overrides: Record<string, number>
  failCounts: Record<string, number>
}

function loadJail(): Record<string, JailEntry> {
  try {
    const raw = localStorage.getItem(E2E_JAIL_KEY)
    if (!raw) return {}
    const jail = JSON.parse(raw) as Record<string, JailEntry>
    // Purge expired entries
    const now = Date.now()
    const active: Record<string, JailEntry> = {}
    for (const [id, entry] of Object.entries(jail)) {
      if (entry.releaseAt > now) active[id] = entry
    }
    if (Object.keys(active).length !== Object.keys(jail).length) {
      localStorage.setItem(E2E_JAIL_KEY, JSON.stringify(active))
    }
    return active
  } catch { return {} }
}

function saveJail(jail: Record<string, JailEntry>) {
  localStorage.setItem(E2E_JAIL_KEY, JSON.stringify(jail))
}

function jailModel(jail: Record<string, JailEntry>, modelId: string): JailEntry {
  const prev = jail[modelId]
  const strikes = Math.min((prev?.strikes ?? 0) + 1, JAIL_COOLDOWNS_MS.length)
  const cooldown = JAIL_COOLDOWNS_MS[strikes - 1]
  const entry: JailEntry = { releaseAt: Date.now() + cooldown, strikes }
  jail[modelId] = entry
  saveJail(jail)
  const hours = Math.round(cooldown / 3600000)
  console.warn(`[e2e-speed] ${modelId} jailed (strike ${strikes}/${JAIL_COOLDOWNS_MS.length}, cooldown ${hours}h)`)
  return entry
}

function isJailed(jail: Record<string, JailEntry>, modelId: string): boolean {
  const entry = jail[modelId]
  if (!entry) return false
  if (entry.releaseAt <= Date.now()) {
    delete jail[modelId]
    saveJail(jail)
    return false
  }
  return true
}

function loadState(): E2eState {
  try {
    const raw = localStorage.getItem(E2E_STATE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return {
    lastTestAt: 0,
    hourResetAt: 0,
    hourCount: 0,
    networkFingerprint: '',
    overrides: {},
    failCounts: {},
  }
}

function saveState(state: E2eState) {
  localStorage.setItem(E2E_STATE_KEY, JSON.stringify(state))
}

function getNetworkFingerprint(): string {
  const conn = (navigator as any).connection
  if (conn) {
    return `${conn.type ?? 'unknown'}-${conn.effectiveType ?? 'unknown'}`
  }
  return navigator.onLine ? 'online' : 'offline'
}

export function useE2eSpeedTest() {
  const running = ref(false)
  const state = ref(loadState())
  const jail = loadJail()
  let networkChangeTimer: ReturnType<typeof setTimeout> | null = null

  function canRunE2eTest(): boolean {
    if (running.value) return false
    if (!navigator.onLine) return false

    const now = Date.now()

    // Minimum interval
    if (now - state.value.lastTestAt < MIN_INTERVAL_MS) return false

    // Hourly cap: reset if more than 1 hour since last reset
    if (now - state.value.hourResetAt > 60 * 60 * 1000) {
      state.value.hourResetAt = now
      state.value.hourCount = 0
    }
    if (state.value.hourCount >= HOUR_MAX_TESTS) return false

    return true
  }

  async function runE2ePing() {
    const appStore = useAppStore()
    if (!appStore.hasVisibleSparkringProvider()) {
      console.info('[e2e-speed] skipped: no visible sparkring provider')
      return
    }
    if (!canRunE2eTest()) {
      console.info('[e2e-speed] skipped: throttled')
      return
    }

    running.value = true
    console.info('[e2e-speed] starting e2e ping test...')
    try {
      // Phase 1: ensure server-side speed data is fresh
      await appStore.ensureSparkringSpeedTestForToday()

      const speedMap = appStore.sparkringSpeedMap
      if (!Object.keys(speedMap).length) {
        console.info('[e2e-speed] skipped: no server-side speed data')
        return
      }

      // Pick top N models by server-side latency, excluding jailed models
      const allOk = Object.values(speedMap)
        .filter((m) => m.status === 'ok' && m.latencyMs != null)
        .sort((a, b) => (a.latencyMs ?? Infinity) - (b.latencyMs ?? Infinity))

      // Apply penalty to jailed models so they sort to bottom
      const jailedIds: string[] = []
      const candidates = allOk
        .filter((m) => {
          if (isJailed(jail, m.modelId)) {
            jailedIds.push(m.modelId)
            return false
          }
          return true
        })
        .slice(0, TOP_N_MODELS)

      // Penalize jailed models in speed map (they stay hidden from ping but sort last)
      if (jailedIds.length) {
        const jailOverrides: Record<string, number> = {}
        for (const id of jailedIds) jailOverrides[id] = PENALTY_LATENCY_MS
        appStore.applyE2eSpeedOverrides(jailOverrides)
      }

      if (!candidates.length) return

      // Resolve runtime (provider + apiKey)
      const runtime = await getFetchRuntime('sparkring')
      if (!runtime) return

      console.info('[e2e-speed] pinging', candidates.map((c) => c.modelId.replace('sparkring/', '')))

      // Phase 2: parallel e2e ping
      const results = await Promise.allSettled(
        candidates.map(async (m) => {
          const controller = new AbortController()
          const timer = setTimeout(() => controller.abort(), PING_TIMEOUT_MS)
          try {
            const rawModelId = m.modelId.replace(/^sparkring\//, '')
            const latency = await pingModelLatency({
              provider: runtime.provider,
              apiKey: runtime.apiKey,
              model: rawModelId,
              signal: controller.signal,
            })
            return { modelId: m.modelId, latency, rateLimited: false }
          } catch (e) {
            // 429 = rate limited, model temporarily unusable for chat too
            if (e instanceof ApiError && e.status === 429) {
              return { modelId: m.modelId, latency: PENALTY_LATENCY_MS, rateLimited: true }
            }
            throw e
          } finally {
            clearTimeout(timer)
          }
        }),
      )

      // Build overrides from successful pings
      const overrides: Record<string, number> = {}
      const failCounts = { ...state.value.failCounts }

      for (let i = 0; i < results.length; i++) {
        const modelId = candidates[i].modelId
        const result = results[i]
        if (result.status === 'fulfilled') {
          if (result.value.rateLimited) {
            // 429: jail with escalating cooldown (5h → 24h → 7d) + hide from UI
            const entry = jailModel(jail, modelId)
            appStore.suppressModelUntil(modelId, entry.releaseAt)
            overrides[modelId] = PENALTY_LATENCY_MS
            continue
          }
          overrides[modelId] = result.value.latency
          failCounts[modelId] = 0
          console.info(`[e2e-speed] ${modelId} → ${Math.round(result.value.latency)}ms`)
        } else {
          const reason = result.reason
          const errMsg = reason instanceof Error ? reason.message : String(reason)
          failCounts[modelId] = (failCounts[modelId] ?? 0) + 1
          console.warn(`[e2e-speed] ${modelId} ping failed (${failCounts[modelId]}/${PING_FAIL_THRESHOLD}): ${errMsg}`)
          if (failCounts[modelId] >= PING_FAIL_THRESHOLD) {
            overrides[modelId] = PENALTY_LATENCY_MS
            console.warn(`[e2e-speed] ${modelId} → degraded (${PENALTY_LATENCY_MS}ms penalty)`)
          }
        }
      }

      if (Object.keys(overrides).length) {
        appStore.applyE2eSpeedOverrides(overrides)
      }

      // Update throttle state
      const now = Date.now()
      state.value = {
        ...state.value,
        lastTestAt: now,
        hourCount: state.value.hourCount + 1,
        networkFingerprint: getNetworkFingerprint(),
        overrides,
        failCounts,
      }
      saveState(state.value)
      console.info('[e2e-speed] test complete', {
        tested: candidates.length,
        succeeded: Object.keys(overrides).length,
      })
    } catch (e) {
      console.warn('[e2e-speed] test failed', e)
    } finally {
      running.value = false
    }
  }

  function onNetworkChange() {
    const newFingerprint = getNetworkFingerprint()
    if (newFingerprint === state.value.networkFingerprint) return

    console.info('[e2e-speed] network change detected', {
      from: state.value.networkFingerprint,
      to: newFingerprint,
    })

    state.value.networkFingerprint = newFingerprint

    // Clear stale e2e data (server-side stays valid)
    const appStore = useAppStore()
    appStore.clearE2eSpeedOverrides()
    state.value.overrides = {}
    saveState(state.value)

    // Debounced re-test
    if (networkChangeTimer) clearTimeout(networkChangeTimer)
    networkChangeTimer = setTimeout(() => void runE2ePing(), NETWORK_DEBOUNCE_MS)
  }

  function onVisibilityChange() {
    if (document.visibilityState !== 'visible') return
    if (Date.now() - state.value.lastTestAt > VISIBILITY_STALE_MS) {
      void runE2ePing()
    }
  }

  function setupListeners() {
    // Restore cached e2e overrides if network fingerprint matches
    const currentFingerprint = getNetworkFingerprint()
    if (
      state.value.networkFingerprint === currentFingerprint
      && Object.keys(state.value.overrides).length
    ) {
      const appStore = useAppStore()
      appStore.applyE2eSpeedOverrides(state.value.overrides)
    } else {
      state.value.networkFingerprint = currentFingerprint
    }

    // Web listeners
    window.addEventListener('online', onNetworkChange)
    window.addEventListener('offline', onNetworkChange)
    const conn = (navigator as any).connection
    conn?.addEventListener?.('change', onNetworkChange)
    document.addEventListener('visibilitychange', onVisibilityChange)

    // Run initial e2e test
    void runE2ePing()
  }

  function teardownListeners() {
    window.removeEventListener('online', onNetworkChange)
    window.removeEventListener('offline', onNetworkChange)
    const conn = (navigator as any).connection
    conn?.removeEventListener?.('change', onNetworkChange)
    document.removeEventListener('visibilitychange', onVisibilityChange)
    if (networkChangeTimer) clearTimeout(networkChangeTimer)
  }

  return {
    running,
    setupListeners,
    teardownListeners,
    runE2ePing,
  }
}
