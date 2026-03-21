import { ref, watchEffect, reactive, watch, computed } from 'vue'

export type ThemeMode = 'dark' | 'light' | 'auto'

function detectSystemTheme(): 'dark' | 'light' {
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: light)').matches) {
    return 'light'
  }
  return 'dark'
}

function getInitialMode(): ThemeMode {
  if (typeof localStorage !== 'undefined') {
    const saved = localStorage.getItem('mms-theme')
    if (saved === 'dark' || saved === 'light' || saved === 'auto') return saved as ThemeMode
  }
  return 'light'
}

const themeMode = ref<ThemeMode>(getInitialMode())
const systemTheme = ref<'dark' | 'light'>(detectSystemTheme())

// Track system theme changes for auto mode
if (typeof window !== 'undefined') {
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
    systemTheme.value = e.matches ? 'light' : 'dark'
  })
}

// Resolved theme: what's actually applied to the DOM
const theme = computed<'dark' | 'light'>(() =>
  themeMode.value === 'auto' ? systemTheme.value : themeMode.value
)

// V3 Cinematic Parameters State
const defaultV3Config = {
  blurAmount: 25,
  saturation: 130,
  borderOpacity: 12,
  noiseOpacity: 6,
  showAurora: true
}

function getInitialV3Config() {
  if (typeof localStorage !== 'undefined') {
    const saved = localStorage.getItem('mms-v3-config')
    if (saved) {
      try {
        return { ...defaultV3Config, ...JSON.parse(saved) }
      } catch (e) {
        return defaultV3Config
      }
    }
  }
  return defaultV3Config
}

const v3Config = reactive(getInitialV3Config())

watch(v3Config, (newVal) => {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('mms-v3-config', JSON.stringify(newVal))
  }
}, { deep: true })

export function useTheme() {
  watchEffect(() => {
    const resolved = theme.value
    const el = document.documentElement
    if (resolved === 'light') {
      el.classList.add('light')
      el.classList.remove('dark')
    } else {
      el.classList.add('dark')
      el.classList.remove('light')
    }

    el.style.setProperty('--v3-blur', `${v3Config.blurAmount}px`)
    el.style.setProperty('--v3-saturate', `${v3Config.saturation}%`)
    el.style.setProperty('--v3-border-opacity', `${v3Config.borderOpacity / 100}`)
    el.style.setProperty('--v3-noise', `${v3Config.noiseOpacity / 100}`)
  })

  function setThemeMode(mode: ThemeMode) {
    themeMode.value = mode
    localStorage.setItem('mms-theme', mode)
  }

  // Cycles light → auto → dark → light (for mobile button)
  function toggle() {
    const cycle: ThemeMode[] = ['light', 'auto', 'dark']
    const idx = cycle.indexOf(themeMode.value)
    setThemeMode(cycle[(idx + 1) % 3])
  }

  return { theme, themeMode, toggle, setThemeMode, v3Config }
}
