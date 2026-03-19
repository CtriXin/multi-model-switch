/**
 * SparkRing 体验通道 provisioning.
 *
 * Flow:
 *   - First launch: no key in Keychain → POST /api/provision (no tier)
 *     → server creates 50 RMB quota key → app stores in Keychain
 *   - Max mode (easter egg): POST /api/provision { tier: "max" }
 *     → server creates 500 RMB quota key → app overwrites in Keychain
 *
 * Idempotent: same install_id + tier always returns the same key.
 */

import { Capacitor } from '@capacitor/core'

const PROVISION_BASE = 'http://82.156.121.141:4001'
const LEGACY_PROVISION_BASE = 'http://82.156.121.141:4000'
const PROVISION_URL = `${PROVISION_BASE}/api/provision`
const API_BASE_URL = `${PROVISION_BASE}/v1`
const LEGACY_API_BASE_URL = `${LEGACY_PROVISION_BASE}/v1`

const INSTALL_ID_KEY = 'mms-install-id'
const PROVISION_STATE_KEY = 'mms-provision-state'
const APP_VERSION = '0.3.5'
const BUNDLE_ID = 'com.xin.lab'

export type ProvisionTier = 'default' | 'max'

export interface ProvisionResult {
  apiKey: string
  baseUrl: string
  tier: ProvisionTier
}

interface ProvisionState {
  tier: ProvisionTier
  installId: string
  provisionedAt: number
}

function getOrCreateInstallId(): string {
  let id = localStorage.getItem(INSTALL_ID_KEY)
  if (id) return id
  id = crypto.randomUUID()
  localStorage.setItem(INSTALL_ID_KEY, id)
  return id
}

function getProvisionState(): ProvisionState | null {
  try {
    const raw = localStorage.getItem(PROVISION_STATE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveProvisionState(state: ProvisionState) {
  localStorage.setItem(PROVISION_STATE_KEY, JSON.stringify(state))
}

export function getCurrentTier(): ProvisionTier | null {
  return getProvisionState()?.tier ?? null
}

export function isProvisioned(): boolean {
  return !!getProvisionState()
}

export function getInstallId(): string {
  return getOrCreateInstallId()
}

export function normalizeSparkringBaseUrl(baseUrl: string): string {
  const normalized = baseUrl.trim().replace(/\/$/, '')
  if (!normalized) return API_BASE_URL
  if (normalized === LEGACY_PROVISION_BASE || normalized === LEGACY_API_BASE_URL) {
    return API_BASE_URL
  }
  return normalized
}

function detectPlatform(): string {
  if (Capacitor.isNativePlatform()) {
    return Capacitor.getPlatform() === 'ios' ? 'ios' : 'macos'
  }
  return window.innerWidth < 768 ? 'ios' : 'macos'
}

/**
 * Call the provision endpoint.
 * - tier omitted or 'default': standard 50 RMB key
 * - tier 'max': high-quota 500 RMB key
 */
export async function provision(tier?: ProvisionTier): Promise<ProvisionResult | null> {
  const installId = getOrCreateInstallId()

  const body: Record<string, string> = {
    install_id: installId,
    platform: detectPlatform(),
    app_version: APP_VERSION,
    bundle_id: BUNDLE_ID,
  }
  if (tier === 'max') {
    body.tier = 'max'
  }

  try {
    const res = await fetch(PROVISION_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    // 429 with api_key means already_provisioned (idempotent), still usable
    if (!res.ok && res.status !== 429) return null

    const data = await res.json()
    const apiKey: string | undefined = data.api_key
    if (!apiKey) return null

    const baseUrl = normalizeSparkringBaseUrl(data.base_url || API_BASE_URL)
    const resolvedTier: ProvisionTier = tier === 'max' ? 'max' : 'default'

    saveProvisionState({
      tier: resolvedTier,
      installId,
      provisionedAt: Date.now(),
    })

    return { apiKey, baseUrl, tier: resolvedTier }
  } catch {
    // Network error — provision server unreachable
    return null
  }
}
