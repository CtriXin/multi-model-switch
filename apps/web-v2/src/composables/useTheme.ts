import { ref, watchEffect } from 'vue'

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
    } else {
      el.classList.remove('light')
    }
  })

  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    localStorage.setItem('mms-theme', theme.value)
  }

  return { theme, toggle }
}
