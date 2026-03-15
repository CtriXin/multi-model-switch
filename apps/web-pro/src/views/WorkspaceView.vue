<template>
  <div class="h-full flex overflow-hidden bg-surface-1">
    <!-- Mobile Overlay -->
    <div
      v-if="appStore.sidebarOpen && isMobile"
      class="fixed inset-0 z-40 bg-black/30 md:hidden"
      @click="appStore.toggleSidebar()"
    />

    <!-- Sidebar -->
    <Transition name="sidebar">
      <aside
        v-if="appStore.sidebarOpen"
        class="w-[var(--sidebar-width)] flex-shrink-0 bg-white border-r border-gray-200/80 flex flex-col h-full md:relative fixed z-50 md:z-auto"
      >
        <!-- Sidebar Header -->
        <div class="h-[var(--header-height)] flex items-center justify-between px-4 border-b border-gray-100">
          <div class="flex items-center gap-2">
            <div class="w-7 h-7 rounded-lg bg-accent-600 flex items-center justify-center">
              <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 12h4l2-6 3 12 2-6h5"/>
              </svg>
            </div>
            <span class="font-semibold text-sm text-gray-900">MMS</span>
          </div>
          <button
            @click="appStore.toggleSidebar()"
            class="p-1 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100 transition-colors"
          >
            <PanelLeftClose class="w-4 h-4" />
          </button>
        </div>

        <!-- New Session Buttons -->
        <div class="p-3 space-y-1.5">
          <button
            @click="startNewChat"
            class="w-full flex items-center gap-2.5 px-3 py-2 text-sm font-medium text-gray-700 rounded-lg hover:bg-accent-50 hover:text-accent-700 transition-colors"
          >
            <MessageSquare class="w-4 h-4" />
            新对话
          </button>
          <button
            @click="startNewDiscuss"
            class="w-full flex items-center gap-2.5 px-3 py-2 text-sm font-medium text-gray-700 rounded-lg hover:bg-purple-50 hover:text-purple-700 transition-colors"
          >
            <Users class="w-4 h-4" />
            新讨论
          </button>
        </div>

        <div class="h-px bg-gray-100 mx-3" />

        <!-- Session List -->
        <div class="flex-1 overflow-y-auto px-3 py-2">
          <div class="text-[11px] font-medium text-gray-400 uppercase tracking-wider px-2 mb-2">
            最近会话
          </div>
          <div class="space-y-0.5">
            <button
              v-for="session in appStore.sessions"
              :key="session.id"
              @click="openSession(session)"
              class="w-full text-left px-2.5 py-2 rounded-lg text-sm hover:bg-gray-50 transition-colors group"
              :class="activeSessionId === session.id ? 'bg-accent-50 text-accent-700' : 'text-gray-700'"
            >
              <div class="flex items-center gap-2">
                <component
                  :is="session.mode === 'chat' ? MessageSquare : Users"
                  class="w-3.5 h-3.5 flex-shrink-0"
                  :class="session.mode === 'chat' ? 'text-accent-500' : 'text-purple-500'"
                />
                <span class="truncate flex-1 font-medium">{{ session.title }}</span>
              </div>
              <div class="flex items-center gap-2 mt-1 pl-5.5">
                <span class="text-[11px] text-gray-400">{{ formatDate(session.updatedAt) }}</span>
                <span class="text-[11px] text-gray-400">{{ session.messageCount }} 条</span>
              </div>
            </button>
          </div>
        </div>

        <!-- Sidebar Footer -->
        <div class="p-3 border-t border-gray-100 space-y-0.5">
          <router-link
            to="/models"
            class="flex items-center gap-2.5 px-3 py-2 text-sm text-gray-600 rounded-lg hover:bg-gray-50 transition-colors"
            :class="$route.name === 'models' ? 'bg-gray-50 text-gray-900' : ''"
          >
            <Bot class="w-4 h-4" />
            模型管理
          </router-link>
          <router-link
            to="/settings"
            class="flex items-center gap-2.5 px-3 py-2 text-sm text-gray-600 rounded-lg hover:bg-gray-50 transition-colors"
            :class="$route.name === 'settings' ? 'bg-gray-50 text-gray-900' : ''"
          >
            <Settings class="w-4 h-4" />
            设置
          </router-link>
        </div>
      </aside>
    </Transition>

    <!-- Main Area -->
    <div class="flex-1 flex flex-col min-w-0 h-full">
      <!-- Top Bar (compact) -->
      <header class="h-[var(--header-height)] flex items-center justify-between px-4 border-b border-gray-200/60 bg-white/80 backdrop-blur-glass flex-shrink-0">
        <div class="flex items-center gap-2">
          <button
            v-if="!appStore.sidebarOpen"
            @click="appStore.toggleSidebar()"
            class="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100 transition-colors"
          >
            <PanelLeft class="w-4 h-4" />
          </button>
          <!-- Breadcrumb -->
          <nav class="flex items-center gap-1 text-sm">
            <router-link to="/" class="text-gray-400 hover:text-gray-600 transition-colors">
              <Home class="w-4 h-4" />
            </router-link>
            <ChevronRight v-if="currentPageName" class="w-3 h-3 text-gray-300" />
            <span v-if="currentPageName" class="font-medium text-gray-700">{{ currentPageName }}</span>
          </nav>
        </div>

        <div class="flex items-center gap-2">
          <!-- Quick Command -->
          <button
            @click="appStore.toggleCommandPalette()"
            class="hidden md:flex items-center gap-2 px-3 py-1.5 text-xs text-gray-400 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors border border-gray-200/60"
          >
            <Search class="w-3.5 h-3.5" />
            <span>搜索</span>
            <kbd class="text-[10px] bg-white px-1 py-0.5 rounded border border-gray-200">⌘K</kbd>
          </button>
        </div>
      </header>

      <!-- Content -->
      <main class="flex-1 overflow-hidden">
        <router-view v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" />
          </Transition>
        </router-view>
      </main>
    </div>

    <!-- Command Palette -->
    <CommandPalette v-if="appStore.commandPaletteOpen" @close="appStore.commandPaletteOpen = false" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  PanelLeftClose, PanelLeft, MessageSquare, Users,
  Bot, Settings, Home, ChevronRight, Search,
} from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'
import type { Session } from '@mms/contracts'
import CommandPalette from '@/components/CommandPalette.vue'

const appStore = useAppStore()
const router = useRouter()
const route = useRoute()

const isMobile = ref(typeof window !== 'undefined' ? window.innerWidth < 768 : false)

function handleResize() {
  isMobile.value = window.innerWidth < 768
}

// Auto-close sidebar on mobile after navigation
watch(() => route.path, () => {
  if (isMobile.value && appStore.sidebarOpen) {
    appStore.sidebarOpen = false
  }
})

const activeSessionId = computed(() => {
  return route.params.id as string || null
})

const currentPageName = computed(() => {
  const names: Record<string, string> = {
    home: '',
    chat: '对话',
    discuss: '讨论',
    models: '模型管理',
    settings: '设置',
    setup: 'API 配置',
  }
  return names[route.name as string] || ''
})

function startNewChat() {
  router.push('/chat')
}

function startNewDiscuss() {
  router.push('/discuss')
}

function openSession(session: Session) {
  router.push(`/${session.mode}/${session.id}`)
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffDays === 0) return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (diffDays === 1) return '昨天'
  if (diffDays < 7) return `${diffDays} 天前`
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// Global keyboard shortcut
function handleKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    appStore.toggleCommandPalette()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  window.addEventListener('resize', handleResize)
})
onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.sidebar-enter-active { transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.sidebar-leave-active { transition: all 0.2s ease-in; }
.sidebar-enter-from { opacity: 0; transform: translateX(-20px); }
.sidebar-leave-to { opacity: 0; transform: translateX(-20px); }

.page-enter-active { transition: all 0.2s ease-out; }
.page-leave-active { transition: all 0.15s ease-in; }
.page-enter-from { opacity: 0; }
.page-leave-to { opacity: 0; }
</style>
