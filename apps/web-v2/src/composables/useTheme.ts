import { ref, watchEffect, reactive, watch } from 'vue'

type Theme = 'dark' | 'light'

function detectSystemTheme(): Theme {
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: light)').matches) {
    return 'light'
  }
  return 'dark'
}

function getInitialTheme(): Theme {
  if (typeof localStorage !== 'undefined') {
    const saved = localStorage.getItem('mms-theme') as Theme | null
    if (saved === 'dark' || saved === 'light') return saved
  }
  return detectSystemTheme()
}

const theme = ref<Theme>(getInitialTheme())

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

// Sync V3 config to localStorage
watch(v3Config, (newVal) => {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('mms-v3-config', JSON.stringify(newVal))
  }
}, { deep: true })

export function useTheme() {
  // Listen for system theme changes (only applies if user hasn't manually set)
  if (typeof window !== 'undefined') {
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    mq.addEventListener('change', (e) => {
      // Only auto-follow if no manual override stored
      if (!localStorage.getItem('mms-theme')) {
        theme.value = e.matches ? 'light' : 'dark'
      }
    })
  }

  watchEffect(() => {
    const el = document.documentElement
    if (theme.value === 'light') {
      el.classList.add('light')
      el.classList.remove('dark')
    } else {
      el.classList.add('dark')
      el.classList.remove('light')
    }

    // Sync V3 parameters to CSS variables
    el.style.setProperty('--v3-blur', `${v3Config.blurAmount}px`)
    el.style.setProperty('--v3-saturate', `${v3Config.saturation}%`)
    el.style.setProperty('--v3-border-opacity', `${v3Config.borderOpacity / 100}`)
    el.style.setProperty('--v3-noise', `${v3Config.noiseOpacity / 100}`)
  })

  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    localStorage.setItem('mms-theme', theme.value)
  }

  return { theme, toggle, v3Config }
}

