import plugin from 'tailwindcss/plugin'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          0: 'var(--c-surface-0)',
          1: 'var(--c-surface-1)',
          2: 'var(--c-surface-2)',
          3: 'var(--c-surface-3)',
          4: 'var(--c-surface-4)',
        },
        border: {
          subtle: 'var(--c-border-subtle)',
          default: 'var(--c-border-default)',
          strong: 'var(--c-border-strong)',
        },
        text: {
          primary: 'var(--c-text-primary)',
          secondary: 'var(--c-text-secondary)',
          tertiary: 'var(--c-text-tertiary)',
        },
        accent: {
          DEFAULT: '#6366f1',
          hover: '#818cf8',
          muted: '#6366f126',
        },
        model: {
          claude: '#f59e0b',
          openai: '#10b981',
          google: '#3b82f6',
          deepseek: '#8b5cf6',
          moonshot: '#ec4899',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'SF Pro Text', 'Helvetica Neue', 'sans-serif'],
        mono: ['SF Mono', 'Menlo', 'Monaco', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        'slide-right': 'slideRight 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        'scale-in': 'scaleIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
        pulse_dot: 'pulseDot 1.4s ease-in-out infinite',
        cursor_blink: 'cursorBlink 1s step-end infinite',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } },
        slideUp: { from: { opacity: '0', transform: 'translateY(8px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        slideRight: { from: { opacity: '0', transform: 'translateX(-8px)' }, to: { opacity: '1', transform: 'translateX(0)' } },
        scaleIn: { from: { opacity: '0', transform: 'scale(0.95)' }, to: { opacity: '1', transform: 'scale(1)' } },
        pulseDot: { '0%, 100%': { opacity: '0.4' }, '50%': { opacity: '1' } },
        cursorBlink: { '0%, 100%': { opacity: '1' }, '50%': { opacity: '0' } },
      },
    },
  },
  plugins: [
    plugin(function ({ addBase }) {
      addBase({
        /* Dark theme (default) */
        ':root': {
          '--c-surface-0': '#0a0a0f',
          '--c-surface-1': '#111118',
          '--c-surface-2': '#18181f',
          '--c-surface-3': '#1f1f28',
          '--c-surface-4': '#282833',
          '--c-border-subtle': 'rgba(255,255,255,0.04)',
          '--c-border-default': 'rgba(255,255,255,0.08)',
          '--c-border-strong': 'rgba(255,255,255,0.13)',
          '--c-text-primary': '#e8e8f0',
          '--c-text-secondary': '#8888a0',
          '--c-text-tertiary': '#555566',
        },
        /* Light theme */
        'html.light': {
          '--c-surface-0': '#f5f5f7',
          '--c-surface-1': '#ffffff',
          '--c-surface-2': '#f0f0f2',
          '--c-surface-3': '#e5e5ea',
          '--c-surface-4': '#d1d1d6',
          '--c-border-subtle': 'rgba(0,0,0,0.04)',
          '--c-border-default': 'rgba(0,0,0,0.08)',
          '--c-border-strong': 'rgba(0,0,0,0.15)',
          '--c-text-primary': '#1d1d1f',
          '--c-text-secondary': '#636366',
          '--c-text-tertiary': '#aeaeb2',
        },
      })
    }),
  ],
}
