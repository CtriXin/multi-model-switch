<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]" @click.self="$emit('close')">
      <div class="absolute inset-0 bg-black/20 backdrop-blur-sm" @click="$emit('close')" />
      <div class="relative w-full max-w-lg bg-white rounded-2xl shadow-float overflow-hidden animate-slide-up">
        <!-- Search Input -->
        <div class="flex items-center gap-3 px-4 py-3 border-b border-gray-100">
          <Search class="w-4 h-4 text-gray-400 flex-shrink-0" />
          <input
            ref="inputRef"
            v-model="query"
            type="text"
            placeholder="搜索命令..."
            class="flex-1 text-sm bg-transparent focus:outline-none placeholder-gray-400"
            @keydown.escape="$emit('close')"
            @keydown.down.prevent="moveDown"
            @keydown.up.prevent="moveUp"
            @keydown.enter.prevent="execute"
          />
          <kbd class="text-[10px] px-1 py-0.5 bg-gray-100 rounded border border-gray-200 text-gray-400">ESC</kbd>
        </div>

        <!-- Commands List -->
        <div class="max-h-[300px] overflow-y-auto py-1">
          <button
            v-for="(cmd, i) in filteredCommands"
            :key="cmd.id"
            @click="executeCmd(cmd)"
            class="w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors"
            :class="i === activeIndex ? 'bg-accent-50 text-accent-700' : 'text-gray-700 hover:bg-gray-50'"
          >
            <component :is="cmd.icon" class="w-4 h-4 flex-shrink-0 opacity-60" />
            <span class="flex-1">{{ cmd.label }}</span>
            <span v-if="cmd.shortcut" class="text-[10px] text-gray-400">{{ cmd.shortcut }}</span>
          </button>
          <div v-if="filteredCommands.length === 0" class="px-4 py-6 text-center text-sm text-gray-400">
            没有匹配的命令
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, markRaw, type Component } from 'vue'
import { useRouter } from 'vue-router'
import {
  Search, MessageSquare, Users, Bot, Settings,
  Home, Plus, Trash2,
} from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'
import { useChatStore } from '@/stores/chat'
import { useDiscussStore } from '@/stores/discuss'

const emit = defineEmits<{ close: [] }>()

const router = useRouter()
const appStore = useAppStore()
const chatStore = useChatStore()
const discussStore = useDiscussStore()

const query = ref('')
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement>()

interface Cmd {
  id: string
  label: string
  icon: Component
  action: () => void
  shortcut?: string
}

const commands: Cmd[] = [
  { id: 'home', label: '返回首页', icon: markRaw(Home), action: () => router.push('/') },
  { id: 'new-chat', label: '新建对话', icon: markRaw(MessageSquare), action: () => router.push('/chat') },
  { id: 'new-discuss', label: '新建讨论', icon: markRaw(Users), action: () => router.push('/discuss') },
  { id: 'models', label: '模型管理', icon: markRaw(Bot), action: () => router.push('/models') },
  { id: 'settings', label: '设置', icon: markRaw(Settings), action: () => router.push('/settings') },
  { id: 'preset-flagship', label: '预设: 旗舰对决', icon: markRaw(Plus), action: () => appStore.applyPreset('chat', 'flagship'), shortcut: '🏆' },
  { id: 'preset-fast', label: '预设: 快速三巨头', icon: markRaw(Plus), action: () => appStore.applyPreset('chat', 'fast'), shortcut: '⚡' },
  { id: 'clear-chat', label: '清空当前对话', icon: markRaw(Trash2), action: () => chatStore.clearSession() },
  { id: 'clear-discuss', label: '清空当前讨论', icon: markRaw(Trash2), action: () => discussStore.clearSession() },
]

const filteredCommands = computed(() => {
  if (!query.value) return commands
  const q = query.value.toLowerCase()
  return commands.filter(c => c.label.toLowerCase().includes(q) || c.id.includes(q))
})

function moveDown() {
  if (activeIndex.value < filteredCommands.value.length - 1) activeIndex.value++
}

function moveUp() {
  if (activeIndex.value > 0) activeIndex.value--
}

function execute() {
  const cmd = filteredCommands.value[activeIndex.value]
  if (cmd) executeCmd(cmd)
}

function executeCmd(cmd: Cmd) {
  cmd.action()
  emit('close')
}

onMounted(() => inputRef.value?.focus())
</script>
