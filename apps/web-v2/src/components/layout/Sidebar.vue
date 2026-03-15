<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import { useTheme } from '@/composables/useTheme'
import {
  MessageSquare, GitMerge, Plus, Settings, Package,
  Sun, Moon, Trash2, PanelLeftClose, PanelLeftOpen,
} from 'lucide-vue-next'
import { onMounted } from 'vue'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const { theme, toggle: toggleTheme } = useTheme()

const props = defineProps<{ collapsed?: boolean }>()
const emit = defineEmits<{ collapse: []; expand: [] }>()

onMounted(() => {
  sessionStore.loadSessions()
})

function newChat() {
  sessionStore.createSession('chat')
  router.push('/chat')
}

function newDiscuss() {
  sessionStore.createSession('discuss')
  router.push('/discuss')
}

function switchTo(session: { id: string; type: string }) {
  sessionStore.switchSession(session.id)
  router.push(session.type === 'chat' ? '/chat' : '/discuss')
}

function deleteSession(id: string, e: Event) {
  e.stopPropagation()
  sessionStore.deleteSession(id)
}
</script>

<template>
  <!-- Collapsed: icon rail -->
  <aside
    v-if="collapsed"
    class="w-12 shrink-0 flex flex-col items-center border-r border-border-subtle glass py-2 gap-1"
  >
    <!-- Expand -->
    <button @click="emit('expand')" class="btn-icon mb-2" title="展开侧边栏">
      <PanelLeftOpen :size="16" />
    </button>

    <!-- New chat -->
    <button @click="newChat" class="btn-icon" title="新对话">
      <MessageSquare :size="16" />
    </button>

    <!-- New discuss -->
    <button @click="newDiscuss" class="btn-icon" title="新讨论">
      <GitMerge :size="16" />
    </button>

    <div class="flex-1" />

    <!-- Theme -->
    <button @click="toggleTheme" class="btn-icon" :title="theme === 'dark' ? '浅色模式' : '深色模式'">
      <Sun v-if="theme === 'dark'" :size="14" />
      <Moon v-else :size="14" />
    </button>

    <!-- Models -->
    <button
      @click="router.push('/models')"
      class="btn-icon"
      :class="route.path === '/models' ? 'text-text-primary' : ''"
      title="模型管理"
    >
      <Package :size="16" />
    </button>

    <!-- Settings -->
    <button
      @click="router.push('/settings')"
      class="btn-icon"
      :class="route.path === '/settings' ? 'text-text-primary' : ''"
      title="设置"
    >
      <Settings :size="16" />
    </button>
  </aside>

  <!-- Expanded: full sidebar -->
  <aside v-else class="w-60 shrink-0 flex flex-col border-r border-border-subtle glass">
    <!-- Header: drag area + logo + collapse -->
    <div class="h-12 flex items-center justify-between px-4" style="-webkit-app-region: drag">
      <span class="text-sm font-bold text-text-primary" style="-webkit-app-region: no-drag">MMS</span>
      <div class="flex items-center gap-1" style="-webkit-app-region: no-drag">
        <button @click="toggleTheme" class="btn-icon" :title="theme === 'dark' ? '浅色模式' : '深色模式'">
          <Sun v-if="theme === 'dark'" :size="14" />
          <Moon v-else :size="14" />
        </button>
        <button @click="emit('collapse')" class="btn-icon" title="收起侧边栏">
          <PanelLeftClose :size="14" />
        </button>
      </div>
    </div>

    <!-- New session buttons -->
    <div class="px-2 space-y-0.5">
      <button
        @click="newChat"
        class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all duration-150
               text-text-secondary hover:bg-white/4 hover:text-text-primary"
      >
        <MessageSquare :size="16" :stroke-width="1.8" />
        <span class="font-medium">新对话</span>
        <Plus :size="12" class="ml-auto text-text-tertiary" />
      </button>
      <button
        @click="newDiscuss"
        class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all duration-150
               text-text-secondary hover:bg-white/4 hover:text-text-primary"
      >
        <GitMerge :size="16" :stroke-width="1.8" />
        <span class="font-medium">新讨论</span>
        <Plus :size="12" class="ml-auto text-text-tertiary" />
      </button>
    </div>

    <!-- Divider -->
    <div class="mx-4 my-3 h-px bg-border-subtle" />

    <!-- Session history -->
    <div class="px-2 flex-1 overflow-y-auto">
      <div class="flex items-center justify-between mb-2 px-2">
        <span class="text-[10px] font-medium text-text-tertiary uppercase tracking-wider">最近会话</span>
      </div>

      <div v-if="sessionStore.sortedSessions.length" class="space-y-0.5">
        <button
          v-for="session in sessionStore.sortedSessions"
          :key="session.id"
          @click="switchTo(session)"
          class="w-full flex items-start gap-2 px-2 py-2 rounded-lg text-left transition-all duration-150 group"
          :class="sessionStore.currentSessionId === session.id
            ? 'bg-white/8 text-text-primary'
            : 'text-text-secondary hover:bg-white/4 hover:text-text-primary'"
        >
          <MessageSquare v-if="session.type === 'chat'" :size="14" class="mt-0.5 shrink-0" :stroke-width="1.5" />
          <GitMerge v-else :size="14" class="mt-0.5 shrink-0" :stroke-width="1.5" />
          <div class="flex-1 min-w-0">
            <div class="text-xs font-medium truncate">{{ session.title }}</div>
            <div class="text-[10px] text-text-tertiary flex items-center gap-2 mt-0.5">
              <span>{{ sessionStore.formatTime(session.updatedAt) }}</span>
              <span>{{ session.messageCount }} 条</span>
            </div>
          </div>
          <button
            @click="deleteSession(session.id, $event)"
            class="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/10 transition-all shrink-0 mt-0.5"
          >
            <Trash2 :size="12" class="text-text-tertiary hover:text-red-400" />
          </button>
        </button>
      </div>
      <p v-else class="text-xs text-text-tertiary py-4 text-center">
        暂无历史会话
      </p>
    </div>

    <!-- Bottom nav -->
    <div class="p-2 border-t border-border-subtle space-y-0.5">
      <button
        @click="router.push('/models')"
        class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all duration-150"
        :class="route.path === '/models'
          ? 'bg-white/8 text-text-primary'
          : 'text-text-secondary hover:bg-white/4 hover:text-text-primary'"
      >
        <Package :size="16" :stroke-width="1.8" />
        <span>模型管理</span>
      </button>
      <button
        @click="router.push('/settings')"
        class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all duration-150"
        :class="route.path === '/settings'
          ? 'bg-white/8 text-text-primary'
          : 'text-text-secondary hover:bg-white/4 hover:text-text-primary'"
      >
        <Settings :size="16" :stroke-width="1.8" />
        <span>设置</span>
      </button>
    </div>
  </aside>
</template>
