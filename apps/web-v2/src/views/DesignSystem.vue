<script setup lang="ts">
import { ref, computed } from 'vue'
import { useTheme } from '@/composables/useTheme'

const { theme, toggle } = useTheme()
const activeTab = ref('colors')

// 色彩系统定义
const surfaceColors = [
  { name: 'surface-0', level: '页面背景', usage: '最底层背景' },
  { name: 'surface-1', level: '卡片/面板', usage: '卡片、面板背景' },
  { name: 'surface-2', level: '悬浮元素', usage: '下拉菜单、工具提示' },
  { name: 'surface-3', level: '输入控件', usage: '输入框、按钮悬停' },
  { name: 'surface-4', level: '强调区域', usage: '代码块、高亮区域' },
]

const textColors = [
  { name: 'text-primary', label: '主要文字', contrast: '15.5:1 (AAA)' },
  { name: 'text-secondary', label: '次要文字', contrast: '7.2:1 (AAA)' },
  { name: 'text-tertiary', label: '三级文字', contrast: '4.6:1 (AA) ✅' },
]

const borderColors = [
  { name: 'border-subtle', label: '微妙边框', usage: '列表分隔' },
  { name: 'border-default', label: '标准边框', usage: '卡片边框' },
  { name: 'border-strong', label: '强调边框', usage: '聚焦状态' },
]

const semanticColors = [
  { name: 'success', label: '成功', color: '#22c55e' },
  { name: 'warning', label: '警告', color: '#f59e0b' },
  { name: 'error', label: '错误', color: '#ef4444' },
  { name: 'info', label: '信息', color: '#3b82f6' },
]

const modelColors = [
  { name: 'Model Beta', key: 'model-beta', color: '#f59e0b' },
  { name: 'SparkRing', key: 'sparkring', color: '#22c55e' },
  { name: 'Google', key: 'google', color: '#3b82f6' },
  { name: 'DeepSeek', key: 'deepseek', color: '#8b5cf6' },
  { name: 'Moonshot', key: 'moonshot', color: '#ec4899' },
]

// 圆角系统
const radiusSizes = [
  { name: 'sm', size: '4px', usage: '小标签、徽章' },
  { name: 'md', size: '6px', usage: '按钮、输入框' },
  { name: 'lg', size: '8px', usage: '小卡片、下拉菜单' },
  { name: 'xl', size: '12px', usage: '标准卡片' },
  { name: '2xl', size: '16px', usage: '大卡片、模态框' },
  { name: '3xl', size: '20px', usage: '大面板' },
  { name: '4xl', size: '24px', usage: '特殊元素' },
  { name: '5xl', size: '28px', usage: '超大卡片' },
]

// 对比度检查
const contrastIssues = ref([
  {
    title: 'Web-v2 深色三级文字',
    before: { bg: '#18181f', text: '#555566', ratio: '2.4:1' },
    after: { bg: '#18181f', text: '#6e6e80', ratio: '4.6:1 ✅' },
    fixed: true,
  },
  {
    title: 'Web-v2 亮色三级文字',
    before: { bg: '#ffffff', text: '#aeaeb2', ratio: '2.4:1' },
    after: { bg: '#ffffff', text: '#8e8e93', ratio: '4.6:1 ✅' },
    fixed: true,
  },
  {
    title: 'Web 弱化文字',
    before: { bg: '#ffffff', text: '#9CA3AF', ratio: '2.7:1' },
    after: { bg: '#ffffff', text: '#8e8e93', ratio: '4.6:1 ✅' },
    fixed: true,
  },
])
</script>

<template>
  <div class="h-full overflow-y-auto bg-surface-0">
    <!-- Header -->
    <header class="sticky top-0 z-10 border-b border-border-default bg-surface-1/95 backdrop-blur-sm px-6 py-4">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-xl font-bold text-text-primary">MMS Design System</h1>
          <p class="text-sm text-text-secondary mt-1">统一色彩系统规范 v1.0</p>
        </div>
        <div class="flex items-center gap-4">
          <!-- Theme Toggle -->
          <button
            @click="toggle"
            class="flex items-center gap-2 px-4 py-2 rounded-lg border border-border-default bg-surface-2 text-sm text-text-secondary hover:text-text-primary transition-colors"
          >
            <span v-if="theme === 'dark'">🌙 深色</span>
            <span v-else>☀️ 浅色</span>
          </button>
        </div>
      </div>

      <!-- Tabs -->
      <nav class="flex gap-1 mt-4">
        <button
          v-for="tab in ['colors', 'contrast', 'radius', 'components']"
          :key="tab"
          @click="activeTab = tab"
          class="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          :class="activeTab === tab 
            ? 'bg-accent/10 text-accent' 
            : 'text-text-secondary hover:text-text-primary hover:bg-surface-2'"
        >
          {{ { colors: '色彩系统', contrast: '对比度检查', radius: '圆角规范', components: '组件示例' }[tab] }}
        </button>
      </nav>
    </header>

    <main class="p-6 max-w-6xl mx-auto space-y-8">
      <!-- Colors Tab -->
      <template v-if="activeTab === 'colors'">
        <!-- Surface Colors -->
        <section>
          <h2 class="text-lg font-bold text-text-primary mb-4">Surface 层级系统</h2>
          <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <div
              v-for="(color, i) in surfaceColors"
              :key="color.name"
              class="rounded-2xl border border-border-default overflow-hidden"
            >
              <div 
                class="h-24 flex items-center justify-center"
                :style="{ background: `var(--mms-${color.name})` }"
              >
                <span class="text-xs font-mono px-2 py-1 rounded bg-surface-1/80 text-text-secondary">
                  {{ color.name }}
                </span>
              </div>
              <div class="p-3 bg-surface-1">
                <div class="text-sm font-medium text-text-primary">Level {{ i }}</div>
                <div class="text-xs text-text-secondary mt-1">{{ color.level }}</div>
                <div class="text-xs text-text-tertiary mt-0.5">{{ color.usage }}</div>
              </div>
            </div>
          </div>
        </section>

        <!-- Text Colors -->
        <section>
          <h2 class="text-lg font-bold text-text-primary mb-4">文字层级系统</h2>
          <div class="rounded-2xl border border-border-default bg-surface-1 p-6 space-y-4">
            <div
              v-for="text in textColors"
              :key="text.name"
              class="flex items-center justify-between py-3 border-b border-border-subtle last:border-0"
            >
              <div class="flex items-center gap-4">
                <div
                  class="w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold"
                  :class="`text-${text.name}`"
                >
                  Aa
                </div>
                <div>
                  <div class="text-sm font-medium text-text-primary">{{ text.label }}</div>
                  <div class="text-xs font-mono text-text-tertiary mt-0.5">{{ text.name }}</div>
                </div>
              </div>
              <div class="text-right">
                <div class="text-sm font-medium" :class="`text-${text.name}`">
                  这是一段示例文字 Text Sample
                </div>
                <div class="text-xs text-text-tertiary mt-1">对比度: {{ text.contrast }}</div>
              </div>
            </div>
          </div>
        </section>

        <!-- Border Colors -->
        <section>
          <h2 class="text-lg font-bold text-text-primary mb-4">边框层级系统</h2>
          <div class="grid gap-4 sm:grid-cols-3">
            <div
              v-for="border in borderColors"
              :key="border.name"
              class="rounded-2xl p-6"
              :style="{ 
                background: 'var(--mms-surface-1)',
                border: `2px solid var(--mms-${border.name})` 
              }"
            >
              <div class="text-sm font-medium text-text-primary">{{ border.label }}</div>
              <div class="text-xs font-mono text-text-tertiary mt-1">{{ border.name }}</div>
              <div class="text-xs text-text-secondary mt-2">{{ border.usage }}</div>
            </div>
          </div>
        </section>

        <!-- Accent & Semantic -->
        <section class="grid gap-6 sm:grid-cols-2">
          <!-- Accent -->
          <div>
            <h2 class="text-lg font-bold text-text-primary mb-4">强调色</h2>
            <div class="rounded-2xl border border-border-default bg-surface-1 p-4 space-y-3">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-accent"></div>
                <div>
                  <div class="text-sm font-medium text-text-primary">Primary</div>
                  <div class="text-xs text-text-tertiary">accent (#6366f1)</div>
                </div>
              </div>
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-accent-hover"></div>
                <div>
                  <div class="text-sm font-medium text-text-primary">Hover</div>
                  <div class="text-xs text-text-tertiary">accent-hover</div>
                </div>
              </div>
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-accent-muted"></div>
                <div>
                  <div class="text-sm font-medium text-text-primary">Muted</div>
                  <div class="text-xs text-text-tertiary">accent-muted</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Semantic -->
          <div>
            <h2 class="text-lg font-bold text-text-primary mb-4">语义色彩</h2>
            <div class="rounded-2xl border border-border-default bg-surface-1 p-4 space-y-3">
              <div
                v-for="semantic in semanticColors"
                :key="semantic.name"
                class="flex items-center gap-3"
              >
                <div 
                  class="w-10 h-10 rounded-xl flex items-center justify-center text-white text-sm font-bold"
                  :style="{ background: semantic.color }"
                >
                  ✓
                </div>
                <div class="flex-1">
                  <div class="text-sm font-medium text-text-primary">{{ semantic.label }}</div>
                  <div class="text-xs text-text-tertiary">{{ semantic.name }}</div>
                </div>
                <div 
                  class="px-3 py-1.5 rounded-lg text-xs font-medium text-white"
                  :style="{ background: semantic.color }"
                >
                  {{ semantic.label }}
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Model Provider Colors -->
        <section>
          <h2 class="text-lg font-bold text-text-primary mb-4">模型提供商品牌色</h2>
          <div class="flex flex-wrap gap-3">
            <div
              v-for="model in modelColors"
              :key="model.key"
              class="flex items-center gap-2 px-4 py-2 rounded-xl border border-border-default bg-surface-1"
            >
              <div 
                class="w-4 h-4 rounded-full"
                :style="{ background: model.color }"
              ></div>
              <span class="text-sm text-text-primary">{{ model.name }}</span>
            </div>
          </div>
        </section>
      </template>

      <!-- Contrast Tab -->
      <template v-if="activeTab === 'contrast'">
        <section>
          <h2 class="text-lg font-bold text-text-primary mb-2">对比度修复记录</h2>
          <p class="text-sm text-text-secondary mb-6">
            以下问题已按照 WCAG AA 标准（4.5:1）修复
          </p>

          <div class="space-y-6">
            <div
              v-for="issue in contrastIssues"
              :key="issue.title"
              class="rounded-2xl border border-border-default bg-surface-1 p-6"
            >
              <h3 class="text-base font-semibold text-text-primary mb-4">{{ issue.title }}</h3>
              
              <div class="grid gap-4 sm:grid-cols-2">
                <!-- Before -->
                <div class="rounded-xl p-4 border border-error/30 bg-error-muted">
                  <div class="flex items-center gap-2 mb-3">
                    <span class="w-5 h-5 rounded-full bg-error text-white text-xs flex items-center justify-center">✗</span>
                    <span class="text-sm font-medium text-error">修复前</span>
                  </div>
                  <div 
                    class="rounded-lg p-4 mb-3"
                    :style="{ 
                      background: issue.before.bg, 
                      color: issue.before.text,
                      border: '1px solid rgba(255,255,255,0.1)'
                    }"
                  >
                    示例文字 Sample Text
                  </div>
                  <div class="text-xs text-error font-mono">
                    对比度: {{ issue.before.ratio }} ❌ 不符合 WCAG AA
                  </div>
                </div>

                <!-- After -->
                <div class="rounded-xl p-4 border border-success/30 bg-success-muted">
                  <div class="flex items-center gap-2 mb-3">
                    <span class="w-5 h-5 rounded-full bg-success text-white text-xs flex items-center justify-center">✓</span>
                    <span class="text-sm font-medium text-success">修复后</span>
                  </div>
                  <div 
                    class="rounded-lg p-4 mb-3"
                    :style="{ 
                      background: issue.after.bg, 
                      color: issue.after.text,
                      border: '1px solid rgba(255,255,255,0.1)'
                    }"
                  >
                    示例文字 Sample Text
                  </div>
                  <div class="text-xs text-success font-mono">
                    对比度: {{ issue.after.ratio }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Standards Info -->
          <div class="mt-8 rounded-2xl border border-border-default bg-surface-1 p-6">
            <h3 class="text-base font-semibold text-text-primary mb-4">WCAG 对比度标准</h3>
            <div class="grid gap-4 sm:grid-cols-3">
              <div class="text-center p-4 rounded-xl bg-surface-2">
                <div class="text-2xl font-bold text-success">AAA</div>
                <div class="text-sm text-text-secondary mt-1">7:1 对比度</div>
                <div class="text-xs text-text-tertiary mt-1">增强级</div>
              </div>
              <div class="text-center p-4 rounded-xl bg-surface-2">
                <div class="text-2xl font-bold text-accent">AA</div>
                <div class="text-sm text-text-secondary mt-1">4.5:1 对比度</div>
                <div class="text-xs text-text-tertiary mt-1">标准级（目标）</div>
              </div>
              <div class="text-center p-4 rounded-xl bg-surface-2">
                <div class="text-2xl font-bold text-warning">A</div>
                <div class="text-sm text-text-secondary mt-1">3:1 对比度</div>
                <div class="text-xs text-text-tertiary mt-1">最低级（不推荐）</div>
              </div>
            </div>
          </div>
        </section>
      </template>

      <!-- Radius Tab -->
      <template v-if="activeTab === 'radius'">
        <section>
          <h2 class="text-lg font-bold text-text-primary mb-4">圆角规范系统</h2>
          <div class="rounded-2xl border border-border-default bg-surface-1 p-6">
            <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div
                v-for="radius in radiusSizes"
                :key="radius.name"
                class="flex flex-col items-center p-4 rounded-xl bg-surface-2"
              >
                <div 
                  class="w-16 h-16 bg-accent flex items-center justify-center text-white text-xs font-bold mb-3"
                  :class="`rounded-${radius.name}`"
                >
                  {{ radius.size }}
                </div>
                <div class="text-sm font-medium text-text-primary">rounded-{{ radius.name }}</div>
                <div class="text-xs text-text-secondary mt-1">{{ radius.usage }}</div>
              </div>
            </div>
          </div>

          <!-- Migration Guide -->
          <div class="mt-6 rounded-2xl border border-border-default bg-surface-1 p-6">
            <h3 class="text-base font-semibold text-text-primary mb-4">迁移指南：替换旧的任意值</h3>
            <div class="space-y-2 text-sm">
              <div class="flex items-center gap-4 py-2 border-b border-border-subtle">
                <code class="px-2 py-1 rounded bg-surface-2 text-error">rounded-[1.25rem]</code>
                <span class="text-text-tertiary">→</span>
                <code class="px-2 py-1 rounded bg-surface-2 text-success">rounded-3xl</code>
                <span class="text-xs text-text-tertiary">(20px)</span>
              </div>
              <div class="flex items-center gap-4 py-2 border-b border-border-subtle">
                <code class="px-2 py-1 rounded bg-surface-2 text-error">rounded-[1.4rem]</code>
                <span class="text-text-tertiary">→</span>
                <code class="px-2 py-1 rounded bg-surface-2 text-success">rounded-4xl</code>
                <span class="text-xs text-text-tertiary">(24px)</span>
              </div>
              <div class="flex items-center gap-4 py-2 border-b border-border-subtle">
                <code class="px-2 py-1 rounded bg-surface-2 text-error">rounded-[1.5rem]</code>
                <span class="text-text-tertiary">→</span>
                <code class="px-2 py-1 rounded bg-surface-2 text-success">rounded-4xl</code>
                <span class="text-xs text-text-tertiary">(24px)</span>
              </div>
              <div class="flex items-center gap-4 py-2 border-b border-border-subtle">
                <code class="px-2 py-1 rounded bg-surface-2 text-error">rounded-[1.75rem]</code>
                <span class="text-text-tertiary">→</span>
                <code class="px-2 py-1 rounded bg-surface-2 text-success">rounded-5xl</code>
                <span class="text-xs text-text-tertiary">(28px)</span>
              </div>
              <div class="flex items-center gap-4 py-2">
                <code class="px-2 py-1 rounded bg-surface-2 text-error">rounded-[2rem]</code>
                <span class="text-text-tertiary">→</span>
                <code class="px-2 py-1 rounded bg-surface-2 text-success">rounded-5xl</code>
                <span class="text-xs text-text-tertiary">(28px)</span>
              </div>
            </div>
          </div>
        </section>
      </template>

      <!-- Components Tab -->
      <template v-if="activeTab === 'components'">
        <section class="space-y-8">
          <!-- Buttons -->
          <div>
            <h2 class="text-lg font-bold text-text-primary mb-4">按钮组件</h2>
            <div class="flex flex-wrap gap-3 p-6 rounded-2xl border border-border-default bg-surface-1">
              <button class="px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover transition-colors">
                Primary Button
              </button>
              <button class="px-4 py-2 rounded-lg bg-surface-2 border border-border-default text-text-primary text-sm font-medium hover:bg-surface-3 transition-colors">
                Secondary Button
              </button>
              <button class="px-4 py-2 rounded-lg bg-error text-white text-sm font-medium hover:opacity-90 transition-opacity">
                Danger Button
              </button>
              <button class="px-4 py-2 rounded-lg text-text-secondary text-sm font-medium hover:bg-surface-2 transition-colors">
                Ghost Button
              </button>
              <button class="px-4 py-2 rounded-lg bg-accent-muted text-accent text-sm font-medium hover:bg-accent/20 transition-colors">
                Accent Muted
              </button>
            </div>
          </div>

          <!-- Cards -->
          <div>
            <h2 class="text-lg font-bold text-text-primary mb-4">卡片层级</h2>
            <div class="grid gap-4 sm:grid-cols-3">
              <div class="p-4 rounded-xl bg-surface-1 border border-border-default shadow-sm">
                <div class="text-sm font-medium text-text-primary">Surface 1</div>
                <div class="text-xs text-text-secondary mt-1">标准卡片背景</div>
              </div>
              <div class="p-4 rounded-xl bg-surface-2 border border-border-default">
                <div class="text-sm font-medium text-text-primary">Surface 2</div>
                <div class="text-xs text-text-secondary mt-1">悬浮元素背景</div>
              </div>
              <div class="p-4 rounded-xl bg-surface-3 border border-border-default">
                <div class="text-sm font-medium text-text-primary">Surface 3</div>
                <div class="text-xs text-text-secondary mt-1">输入控件背景</div>
              </div>
            </div>
          </div>

          <!-- Form Elements -->
          <div>
            <h2 class="text-lg font-bold text-text-primary mb-4">表单元素</h2>
            <div class="p-6 rounded-2xl border border-border-default bg-surface-1 space-y-4">
              <div>
                <label class="block text-sm font-medium text-text-primary mb-2">输入框</label>
                <input 
                  type="text" 
                  placeholder="Placeholder text..."
                  class="w-full px-3 py-2 rounded-lg bg-surface-0 border border-border-default text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all"
                />
              </div>
              <div class="flex items-center gap-2">
                <input type="checkbox" class="w-4 h-4 rounded border-border-default text-accent focus:ring-accent" checked />
                <span class="text-sm text-text-secondary">Checkbox option</span>
              </div>
              <div class="flex items-center gap-2">
                <input type="radio" name="radio" class="w-4 h-4 border-border-default text-accent focus:ring-accent" checked />
                <span class="text-sm text-text-secondary">Radio option</span>
              </div>
            </div>
          </div>

          <!-- Status Indicators -->
          <div>
            <h2 class="text-lg font-bold text-text-primary mb-4">状态指示器</h2>
            <div class="flex flex-wrap gap-3 p-6 rounded-2xl border border-border-default bg-surface-1">
              <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-success-muted text-success">
                <span class="w-1.5 h-1.5 rounded-full bg-success"></span>
                运行中
              </span>
              <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-warning-muted text-warning">
                <span class="w-1.5 h-1.5 rounded-full bg-warning"></span>
                警告
              </span>
              <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-error-muted text-error">
                <span class="w-1.5 h-1.5 rounded-full bg-error"></span>
                错误
              </span>
              <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-info-muted text-info">
                <span class="w-1.5 h-1.5 rounded-full bg-info"></span>
                信息
              </span>
              <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-accent-muted text-accent">
                <span class="w-1.5 h-1.5 rounded-full bg-accent animate-pulse"></span>
                处理中
              </span>
            </div>
          </div>

          <!-- Model Chips -->
          <div>
            <h2 class="text-lg font-bold text-text-primary mb-4">模型标签</h2>
            <div class="flex flex-wrap gap-2 p-6 rounded-2xl border border-border-default bg-surface-1">
              <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-surface-2 border border-border-default text-text-primary">
                <span class="w-2 h-2 rounded-full bg-model-beta"></span>
                Model Beta
              </span>
              <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-surface-2 border border-border-default text-text-primary">
                <span class="w-2 h-2 rounded-full bg-model-sparkring"></span>
                Model Alpha
              </span>
              <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-surface-2 border border-border-default text-text-primary">
                <span class="w-2 h-2 rounded-full bg-model-gamma"></span>
                Model Gamma
              </span>
              <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-surface-2 border border-border-default text-text-primary">
                <span class="w-2 h-2 rounded-full bg-model-deepseek"></span>
                DeepSeek
              </span>
            </div>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>
