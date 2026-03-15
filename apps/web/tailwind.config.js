/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 白色工作台主色调
        workbench: {
          bg: '#FFFFFF',
          surface: '#FAFAFA',
          elevated: '#FFFFFF',
        },
        // 边框系统
        border: {
          DEFAULT: '#E5E7EB',
          light: '#F3F4F6',
          strong: '#D1D5DB',
        },
        // 文字系统 - 高对比度
        text: {
          primary: '#111827',
          secondary: '#374151',
          tertiary: '#6B7280',
          muted: '#9CA3AF',
        },
        // 模型等级颜色
        tier: {
          economy: '#10B981',   // 绿色 - 经济
          standard: '#3B82F6',  // 蓝色 - 主力
          premium: '#F59E0B',   // 橙色 - 旗舰
        },
        // 状态颜色
        status: {
          loading: '#6B7280',
          streaming: '#3B82F6',
          done: '#10B981',
          error: '#EF4444',
        },
        // 强调色
        accent: {
          primary: '#4F46E5',
          hover: '#4338CA',
          light: '#EEF2FF',
        },
        // Discuss 阶段颜色
        phase: {
          1: '#8B5CF6',  // 紫色 - Phase 1
          2: '#EC4899',  // 粉色 - Phase 2
          3: '#F59E0B',  // 橙色 - Phase 3
        }
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)',
        'card-hover': '0 4px 6px rgba(0, 0, 0, 0.1), 0 2px 4px rgba(0, 0, 0, 0.06)',
        'elevated': '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
        'floating': '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
      },
      borderRadius: {
        'card': '12px',
        'card-lg': '16px',
        'pill': '9999px',
      },
      fontFamily: {
        sans: [
          'Inter',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono',
          'Fira Code',
          'Consolas',
          'Monaco',
          'monospace',
        ],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'shimmer': 'shimmer 2s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-1000px 0' },
          '100%': { backgroundPosition: '1000px 0' },
        },
      },
    },
  },
  plugins: [],
}
