<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { Search, MessageSquare, GitMerge, Zap, Palette, Sparkles } from 'lucide-vue-next'

const router = useRouter()
const appStore = useAppStore()
const open = ref(false)
const query = ref('')
const selectedIndex = ref(0)

interface Command {
  id: string
  label: string
  desc: string
  icon: any
  action: () => void
}

const commands: Command[] = [
  { id: 'chat', label: '前往对话', desc: '多模型并行对话', icon: MessageSquare, action: () => router.push('/chat') },
  { id: 'discuss', label: '前往讨论', desc: '三阶段深度讨论', icon: GitMerge, action: () => router.push('/discuss') },
  { id: 'design-v3', label: '设计系统 V3', desc: '电影级设计系统', icon: Sparkles, action: () => router.push('/v3/design') },
  { id: 'design', label: '设计系统', desc: '基础设计组件预览', icon: Palette, action: () => router.push('/design') },
  ...([
    { id: 'preset-coding', name: '编程对决' },
    { id: 'preset-reasoning', name: '深度推理' },
    { id: 'preset-fast', name: '快速响应' },
  ]).map(p => ({
    id: p.id,
    label: `应用预设: ${p.name}`,
    desc: '快捷模型组合',
    icon: Zap,
    action: () => {
      const preset = appStore.presets.find(pr => pr.id === p.id)
      if (preset) appStore.applyPreset(preset)
    },
  })),
]

const filteredCommands = ref(commands)

function updateFilter() {
  const q = query.value.toLowerCase()
  filteredCommands.value = q
    ? commands.filter(c => c.label.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q))
    : commands
  selectedIndex.value = 0
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectedIndex.value = Math.min(selectedIndex.value + 1, filteredCommands.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectedIndex.value = Math.max(selectedIndex.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const cmd = filteredCommands.value[selectedIndex.value]
    if (cmd) { cmd.action(); close() }
  } else if (e.key === 'Escape') {
    close()
  }
}

function close() {
  open.value = false
  query.value = ''
  selectedIndex.value = 0
}

function onGlobalKey(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    open.value = !open.value
    if (!open.value) close()
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKey))
onUnmounted(() => window.removeEventListener('keydown', onGlobalKey))
</script>

<template>
  <Teleport to="body">
    <Transition name="page">
      <div v-if="open" class="fixed inset-0 z-[9998] flex items-start justify-center pt-[15vh]" @click.self="close">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/50" @click="close" />

        <!-- Panel -->
        <div class="relative w-full max-w-md glass-strong rounded-2xl border border-border-default shadow-2xl overflow-hidden animate-scale-in">
          <!-- Search input -->
          <div class="flex items-center gap-3 px-4 py-3 border-b border-border-subtle">
            <Search :size="16" class="text-text-tertiary shrink-0" />
            <input
              v-model="query"
              @input="updateFilter"
              @keydown="handleKeydown"
              placeholder="输入命令..."
              class="flex-1 bg-transparent text-sm text-text-primary placeholder-text-tertiary outline-none"
              autofocus
            />
            <kbd class="px-1.5 py-0.5 rounded bg-surface-3 text-[10px] text-text-tertiary">esc</kbd>
          </div>

          <!-- Results -->
          <div class="max-h-64 overflow-y-auto py-1">
            <button
              v-for="(cmd, i) in filteredCommands"
              :key="cmd.id"
              @click="cmd.action(); close()"
              @mouseenter="selectedIndex = i"
              class="w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors"
              :class="i === selectedIndex ? 'bg-white/5 text-text-primary' : 'text-text-secondary'"
            >
              <component :is="cmd.icon" :size="16" :class="i === selectedIndex ? 'text-accent' : ''" />
              <div class="text-left">
                <div>{{ cmd.label }}</div>
                <div class="text-[10px] text-text-tertiary">{{ cmd.desc }}</div>
              </div>
            </button>
            <div v-if="!filteredCommands.length" class="px-4 py-6 text-center text-sm text-text-tertiary">
              没有匹配的命令
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
