<script setup lang="ts">
import { ref, provide, onMounted, onUnmounted, watch, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useSessionStore } from '@/stores/session'
import { useProviderStore } from '@/stores/provider'
import { useTheme } from '@/composables/useTheme'
import { FREE_PROVIDERS } from '@/data/freeProviders'
import Sidebar from '@/components/layout/Sidebar.vue'
import IOSTabBar from '@/components/layout/IOSTabBar.vue'
import IOSModelSheet from '@/components/shared/IOSModelSheet.vue'
import ToastContainer from '@/components/shared/ToastContainer.vue'
import CommandPalette from '@/components/shared/CommandPalette.vue'
import {
  Monitor, Smartphone, Sun, Moon, Layers, Plus, GitMerge,
  Menu, MessageSquare, Trash2, Package, Settings,
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const sessionStore = useSessionStore()
const providerStore = useProviderStore()
const { theme, toggle: toggleTheme } = useTheme()

// Auto-detect mobile: < 768px → mobile layout
const MOBILE_BREAKPOINT = 768
const platform = ref<'macos' | 'ios'>(window.innerWidth < MOBILE_BREAKPOINT ? 'ios' : 'macos')
const iosModelSheetOpen = ref(false)
const sidebarCollapsed = ref(false)
const iosDrawerOpen = ref(false)

provide('platform', platform)

function onResize() {
  platform.value = window.innerWidth < MOBILE_BREAKPOINT ? 'ios' : 'macos'
}
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))

appStore.initialize()
sessionStore.loadSessions()

const recommendedConfiguredCount = computed(() =>
  FREE_PROVIDERS.filter((provider) => providerStore.keyStatus[provider.id]).length,
)

const showQuickStartEntry = computed(() => recommendedConfiguredCount.value <= 2)
const showDesktopToolbar = computed(() => true)

function togglePlatform() {
  platform.value = platform.value === 'macos' ? 'ios' : 'macos'
  iosDrawerOpen.value = false
}

// Auto-close drawer on route change
watch(() => route.path, () => {
  iosDrawerOpen.value = false
})

// iOS drawer touch handling
const drawerTouchStartX = ref(0)
const drawerTouchCurrentX = ref(0)
const drawerDragging = ref(false)

function onDrawerTouchStart(e: TouchEvent) {
  const x = e.touches[0].clientX
  if (!iosDrawerOpen.value && x < 24) {
    drawerDragging.value = true
    drawerTouchStartX.value = x
    drawerTouchCurrentX.value = x
  }
  if (iosDrawerOpen.value) {
    drawerDragging.value = true
    drawerTouchStartX.value = x
    drawerTouchCurrentX.value = x
  }
}

function onDrawerTouchMove(e: TouchEvent) {
  if (!drawerDragging.value) return
  drawerTouchCurrentX.value = e.touches[0].clientX
}

function onDrawerTouchEnd() {
  if (!drawerDragging.value) return
  const delta = drawerTouchCurrentX.value - drawerTouchStartX.value
  if (!iosDrawerOpen.value && delta > 80) {
    iosDrawerOpen.value = true
  } else if (iosDrawerOpen.value && delta < -60) {
    iosDrawerOpen.value = false
  }
  drawerDragging.value = false
}

function iosNewChat() {
  sessionStore.createSession('chat')
  router.push('/chat')
  iosDrawerOpen.value = false
}

function iosNewDiscuss() {
  sessionStore.createSession('discuss')
  router.push('/discuss')
  iosDrawerOpen.value = false
}

function iosSwitchSession(session: { id: string; type: string }) {
  sessionStore.switchSession(session.id)
  router.push(session.type === 'chat' ? '/chat' : '/discuss')
  iosDrawerOpen.value = false
}

function iosDeleteSession(id: string, e: Event) {
  e.stopPropagation()
  sessionStore.deleteSession(id)
}
</script>

<template>
  <!-- macOS / Desktop Layout -->
  <div v-if="platform === 'macos'" class="flex h-screen overflow-hidden">
    <!-- Sidebar: always visible, either collapsed (icon rail) or expanded -->
    <Sidebar
      :collapsed="sidebarCollapsed"
      @collapse="sidebarCollapsed = true"
      @expand="sidebarCollapsed = false"
      @toggle-platform="togglePlatform"
    />

    <!-- Main content -->
    <main class="flex-1 flex flex-col min-w-0 bg-surface-0">
      <header
        v-if="showDesktopToolbar"
        class="h-12 flex items-center justify-between px-4 border-b border-border-subtle shrink-0"
        style="-webkit-app-region: drag"
      >
        <div class="flex items-center gap-2 text-sm text-text-secondary" style="-webkit-app-region: no-drag">
          <span class="font-medium text-text-primary">{{ route.meta.title }}</span>
          <span v-if="appStore.selectedModels.length" class="text-text-tertiary">
            · {{ appStore.selectedModels.length }} 个模型
          </span>
        </div>
        <div class="flex items-center gap-1" style="-webkit-app-region: no-drag">
          <button @click="iosModelSheetOpen = true" class="btn-ghost flex items-center gap-1.5 relative">
            <Layers :size="14" />
            <span class="text-xs">模型</span>
            <span
              v-if="appStore.selectedModels.length"
              class="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold text-white"
            >
              {{ appStore.selectedModels.length }}
            </span>
          </button>
          <button @click="togglePlatform" class="btn-ghost flex items-center gap-1.5">
            <Smartphone :size="14" />
            <span class="text-xs">移动端</span>
          </button>
        </div>
      </header>

      <!-- Page content -->
      <div class="flex-1 flex flex-col overflow-hidden">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>

  <!-- iOS / Mobile Layout -->
  <div
    v-else
    class="flex flex-col h-screen overflow-hidden bg-surface-0"
    @touchstart.passive="onDrawerTouchStart"
    @touchmove.passive="onDrawerTouchMove"
    @touchend.passive="onDrawerTouchEnd"
  >
    <!-- Mobile Nav Bar -->
    <header class="h-12 flex items-center justify-between px-4 border-b border-border-subtle shrink-0 safe-top">
      <div class="flex items-center gap-2">
        <button @click="iosDrawerOpen = true" class="btn-icon">
          <Menu :size="20" />
        </button>
      </div>
      <span class="font-semibold text-base">{{ route.meta.title }}</span>
      <div class="flex items-center gap-1">
        <button @click="toggleTheme" class="btn-icon" :title="theme === 'dark' ? '浅色' : '深色'">
          <Sun v-if="theme === 'dark'" :size="18" />
          <Moon v-else :size="18" />
        </button>
        <button @click="iosModelSheetOpen = true" class="btn-icon relative">
          <Layers :size="18" />
          <span
            v-if="appStore.selectedModels.length"
            class="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-accent text-white
                   text-[10px] font-bold flex items-center justify-center"
          >{{ appStore.selectedModels.length }}</span>
        </button>
      </div>
    </header>

    <!-- Mobile Content -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" :key="route.path" />
        </transition>
      </router-view>
    </div>

    <!-- Mobile Tab Bar -->
    <IOSTabBar />

    <!-- Mobile Model Sheet -->
    <IOSModelSheet :open="iosModelSheetOpen" @close="iosModelSheetOpen = false" />

    <!-- Mobile Side Drawer -->
    <Teleport to="body">
      <transition name="drawer-overlay">
        <div
          v-if="iosDrawerOpen"
          class="fixed inset-0 bg-black/50 z-40"
          @click="iosDrawerOpen = false"
        />
      </transition>
      <transition name="drawer-panel">
        <div
          v-if="iosDrawerOpen"
          class="fixed inset-y-0 left-0 w-[280px] max-w-[85vw] z-50 flex flex-col glass-strong border-r border-border-subtle safe-top"
        >
          <!-- Drawer header -->
          <div class="h-14 flex items-center px-5 border-b border-border-subtle">
            <span class="text-base font-bold text-text-primary">MMS</span>
          </div>

          <!-- New session buttons -->
          <div class="px-3 py-3 space-y-1">
            <button
              @click="iosNewChat"
              class="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-base
                     text-text-primary active:bg-white/8 transition-colors"
            >
              <MessageSquare :size="20" />
              <span class="font-medium">新对话</span>
              <Plus :size="14" class="ml-auto text-text-tertiary" />
            </button>
            <button
              @click="iosNewDiscuss"
              class="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-base
                     text-text-primary active:bg-white/8 transition-colors"
            >
              <GitMerge :size="20" />
              <span class="font-medium">新讨论</span>
              <Plus :size="14" class="ml-auto text-text-tertiary" />
            </button>
          </div>

          <div class="mx-5 h-px bg-border-subtle" />

          <!-- Session history -->
          <div class="flex-1 overflow-y-auto px-3 py-3">
            <p class="text-xs font-medium text-text-tertiary uppercase tracking-wider px-3 mb-2">最近会话</p>
            <div v-if="sessionStore.sortedSessions.length" class="space-y-0.5">
              <button
                v-for="session in sessionStore.sortedSessions"
                :key="session.id"
                @click="iosSwitchSession(session)"
                class="w-full flex items-start gap-3 px-3 py-3 rounded-xl text-left transition-colors"
                :class="sessionStore.currentSessionId === session.id
                  ? 'bg-white/8 text-text-primary'
                  : 'text-text-secondary active:bg-white/5'"
              >
                <MessageSquare v-if="session.type === 'chat'" :size="18" class="mt-0.5 shrink-0" :stroke-width="1.5" />
                <GitMerge v-else :size="18" class="mt-0.5 shrink-0" :stroke-width="1.5" />
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium truncate">{{ session.title }}</div>
                  <div class="text-xs text-text-tertiary flex items-center gap-2 mt-1">
                    <span>{{ sessionStore.formatTime(session.updatedAt) }}</span>
                    <span>{{ session.messageCount }} 条</span>
                  </div>
                </div>
                <button
                  @click="iosDeleteSession(session.id, $event)"
                  class="p-1 rounded-lg active:bg-red-500/10 transition-all shrink-0 mt-0.5"
                >
                  <Trash2 :size="14" class="text-text-tertiary" />
                </button>
              </button>
            </div>
            <p v-else class="text-sm text-text-tertiary text-center py-6">暂无历史会话</p>
          </div>

          <!-- Drawer bottom nav -->
          <div class="px-3 py-3 border-t border-border-subtle space-y-1">
            <button
              v-if="showQuickStartEntry"
              @click="router.push('/setup'); iosDrawerOpen = false"
              class="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm text-text-secondary active:bg-white/8"
            >
              <span class="text-base leading-none">🚀</span>
              快速开始
            </button>
            <button
              @click="router.push('/models'); iosDrawerOpen = false"
              class="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm text-text-secondary active:bg-white/8"
            >
              <Package :size="16" />
              模型管理
            </button>
            <button
              @click="togglePlatform"
              class="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm text-text-secondary active:bg-white/8"
            >
              <Monitor :size="16" />
              桌面端
            </button>
            <button
              @click="router.push('/settings'); iosDrawerOpen = false"
              class="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm text-text-secondary active:bg-white/8"
            >
              <Settings :size="16" />
              设置
            </button>
          </div>
        </div>
      </transition>
    </Teleport>
  </div>

  <IOSModelSheet
    v-if="platform === 'macos'"
    :open="iosModelSheetOpen"
    @close="iosModelSheetOpen = false"
  />

  <!-- Global overlays -->
  <ToastContainer />
  <CommandPalette />
</template>

<style scoped>
/* iOS drawer */
.drawer-overlay-enter-active,
.drawer-overlay-leave-active { transition: opacity 0.3s ease; }
.drawer-overlay-enter-from,
.drawer-overlay-leave-to { opacity: 0; }

.drawer-panel-enter-active { animation: drawerIn 0.3s cubic-bezier(0.32, 0.72, 0, 1); }
.drawer-panel-leave-active { animation: drawerOut 0.2s ease-in; }
@keyframes drawerIn {
  from { transform: translateX(-100%); }
  to { transform: translateX(0); }
}
@keyframes drawerOut {
  from { transform: translateX(0); }
  to { transform: translateX(-100%); }
}

/* Safe area padding */
.safe-top { padding-top: env(safe-area-inset-top); }
</style>
