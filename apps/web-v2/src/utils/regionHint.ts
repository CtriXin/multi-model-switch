export type RegionHint = 'cn' | 'intl' | 'unknown'

const REGION_HINT_KEY = 'mms-region-hint'
const REGION_HINT_LAST_DAY_KEY = 'mms-region-hint-last-day'
const CN_TIMEZONES = new Set([
  'Asia/Shanghai',
  'Asia/Chongqing',
  'Asia/Harbin',
  'Asia/Urumqi',
  'Asia/Hong_Kong',
  'Asia/Macau',
])

function getLocalDayStamp(value = new Date()) {
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

function readCachedRegionHint(): RegionHint {
  try {
    const raw = localStorage.getItem(REGION_HINT_KEY)
    if (raw === 'cn' || raw === 'intl' || raw === 'unknown') return raw
  } catch {
    // ignore cache read errors
  }
  return 'unknown'
}

function persistRegionHint(hint: RegionHint) {
  try {
    localStorage.setItem(REGION_HINT_KEY, hint)
    localStorage.setItem(REGION_HINT_LAST_DAY_KEY, getLocalDayStamp())
  } catch {
    // ignore cache write errors
  }
}

function shouldReuseCachedHint() {
  try {
    return localStorage.getItem(REGION_HINT_LAST_DAY_KEY) === getLocalDayStamp()
  } catch {
    return false
  }
}

export function getImmediateRegionHint(): RegionHint {
  const cached = readCachedRegionHint()
  if (cached !== 'unknown') return cached

  const language = (navigator.language || '').toLowerCase()
  const languages = (navigator.languages || []).join(',').toLowerCase()
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone

  if (language.includes('zh-cn') || languages.includes('zh-cn')) return 'cn'
  if (timeZone && CN_TIMEZONES.has(timeZone)) return 'cn'
  return 'unknown'
}

function probeImage(url: string, timeoutMs = 1800): Promise<number | null> {
  return new Promise((resolve) => {
    if (typeof Image === 'undefined') {
      resolve(null)
      return
    }

    const startedAt = performance.now()
    const image = new Image()
    let settled = false
    const finalize = (value: number | null) => {
      if (settled) return
      settled = true
      window.clearTimeout(timeoutId)
      resolve(value)
    }

    const timeoutId = window.setTimeout(() => finalize(null), timeoutMs)
    image.onload = () => finalize(performance.now() - startedAt)
    image.onerror = () => finalize(null)
    image.src = `${url}${url.includes('?') ? '&' : '?'}mms_probe=${Date.now()}`
  })
}

function inferFromProbe(baiduMs: number | null, googleMs: number | null, fallback: RegionHint): RegionHint {
  if (baiduMs != null && googleMs == null) return 'cn'
  if (googleMs != null && baiduMs == null) return 'intl'

  if (baiduMs != null && googleMs != null) {
    if (baiduMs + 250 < googleMs) return 'cn'
    if (googleMs + 250 < baiduMs) return 'intl'
  }

  return fallback
}

export async function resolveRegionHintForToday(seedHint: RegionHint = 'unknown'): Promise<RegionHint> {
  const cached = readCachedRegionHint()
  if (shouldReuseCachedHint() && cached !== 'unknown') return cached

  const fallback = seedHint === 'unknown' ? getImmediateRegionHint() : seedHint
  const [baiduMs, googleMs] = await Promise.all([
    probeImage('https://www.baidu.com/favicon.ico'),
    probeImage('https://www.google.com/favicon.ico'),
  ])

  const hint = inferFromProbe(baiduMs, googleMs, fallback)
  persistRegionHint(hint)
  return hint
}
