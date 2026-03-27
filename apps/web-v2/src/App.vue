<script setup lang="ts">
import { ref, provide, onMounted, onUnmounted, computed, reactive } from 'vue'
import { Capacitor } from '@capacitor/core'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useSessionStore } from '@/stores/session'
import { useTheme } from '@/composables/useTheme'
import { useE2eSpeedTest } from '@/composables/useE2eSpeedTest'
import Sidebar from '@/components/layout/Sidebar.vue'
import IOSModelSheet from '@/components/shared/IOSModelSheet.vue'
import ToastContainer from '@/components/shared/ToastContainer.vue'
import CommandPalette from '@/components/shared/CommandPalette.vue'
import { MessageSquare, GitMerge, Users, Home, Package, Settings, FlaskConical, X, Compass } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const sessionStore = useSessionStore()
const { theme } = useTheme() // 必须在 App.vue 调用，保证 watchEffect 全生命周期持久，不随子页面卸载而销毁
const { setupListeners: setupE2eSpeed, teardownListeners: teardownE2eSpeed } = useE2eSpeedTest()

const isDarkMode = computed(() => theme.value === 'dark')
const logoSrc = computed(() => isDarkMode.value ? '/logos/logo-v5-light.png' : '/logos/logo-v5-dark.png')
const logoBg = computed(() => isDarkMode.value ? 'bg-white/90 shadow-lg' : 'bg-black shadow-lg')

// --- Robust Dual-End Logic ---
const detectedPlatform = ref(Capacitor.getPlatform())
const platform = computed(() => {
  const override = typeof route.query.platform === 'string' ? route.query.platform : ''
  if (override === 'ios' || override === 'web' || override === 'macos') return override
  return detectedPlatform.value
})
const windowWidth = ref(window.innerWidth)
// Threshold 1024px for Sidebar vs Drawer
const isMobileLayout = computed(() => windowWidth.value < 1024 || platform.value === 'ios')
const EDGE_SWIPE_WIDTH = 24
const SWIPE_TRIGGER_DISTANCE = 72

provide('platform', platform)
provide('isSmallScreen', isMobileLayout)

function handleResize() { windowWidth.value = window.innerWidth }

const iosDrawerOpen = ref(false)
function handleOpenDrawer() { iosDrawerOpen.value = true }
function handleOpenModels() {
  router.push('/models')
  iosDrawerOpen.value = false
}

const rootSwipe = reactive({
  active: false,
  startX: 0,
  startY: 0,
  triggered: false,
})

const drawerSwipe = reactive({
  active: false,
  startX: 0,
  startY: 0,
  triggered: false,
})

function resetRootSwipe() {
  rootSwipe.active = false
  rootSwipe.startX = 0
  rootSwipe.startY = 0
  rootSwipe.triggered = false
}

function resetDrawerSwipe() {
  drawerSwipe.active = false
  drawerSwipe.startX = 0
  drawerSwipe.startY = 0
  drawerSwipe.triggered = false
}

function onRootTouchStart(e: TouchEvent) {
  if (platform.value !== 'ios' || iosDrawerOpen.value) return
  const touch = e.touches[0]
  if (!touch || touch.clientX > EDGE_SWIPE_WIDTH) {
    resetRootSwipe()
    return
  }

  rootSwipe.active = true
  rootSwipe.startX = touch.clientX
  rootSwipe.startY = touch.clientY
  rootSwipe.triggered = false
}

function onRootTouchMove(e: TouchEvent) {
  if (!rootSwipe.active || rootSwipe.triggered) return
  const touch = e.touches[0]
  if (!touch) return

  const dx = touch.clientX - rootSwipe.startX
  const dy = touch.clientY - rootSwipe.startY

  if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 12) {
    resetRootSwipe()
    return
  }

  if (dx > SWIPE_TRIGGER_DISTANCE && Math.abs(dx) > Math.abs(dy)) {
    iosDrawerOpen.value = true
    rootSwipe.triggered = true
  }
}

function onRootTouchEnd() {
  resetRootSwipe()
}

function onDrawerTouchStart(e: TouchEvent) {
  if (platform.value !== 'ios' || !iosDrawerOpen.value) return
  const touch = e.touches[0]
  if (!touch) return

  drawerSwipe.active = true
  drawerSwipe.startX = touch.clientX
  drawerSwipe.startY = touch.clientY
  drawerSwipe.triggered = false
}

function onDrawerTouchMove(e: TouchEvent) {
  if (!drawerSwipe.active || drawerSwipe.triggered) return
  const touch = e.touches[0]
  if (!touch) return

  const dx = touch.clientX - drawerSwipe.startX
  const dy = touch.clientY - drawerSwipe.startY

  if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 12) {
    resetDrawerSwipe()
    return
  }

  if (dx < -SWIPE_TRIGGER_DISTANCE && Math.abs(dx) > Math.abs(dy)) {
    iosDrawerOpen.value = false
    drawerSwipe.triggered = true
  }
}

function onDrawerTouchEnd() {
  resetDrawerSwipe()
}

function iosNewChat() {
  sessionStore.createSession('chat')
  router.push('/chat')
  iosDrawerOpen.value = false
}

function iosSwitchSession(session: { id: string; type: string }) {
  sessionStore.switchSession(session.id)
  if (session.type === 'chat') router.push('/chat')
  else router.push('/discuss')
  iosDrawerOpen.value = false
}

function isDrawerSessionActive(session: { id: string; type: string }) {
  if (route.path === '/chat') {
    return session.type === 'chat' && sessionStore.currentSessionId === session.id
  }
  if (route.path === '/discuss') {
    return session.type === 'discuss' && sessionStore.currentSessionId === session.id
  }
  return false
}

onMounted(async () => {
  await appStore.initialize()
  sessionStore.loadSessions()
  setupE2eSpeed()

  window.addEventListener('resize', handleResize)
  window.addEventListener('open-drawer', handleOpenDrawer)
  window.addEventListener('open-models', handleOpenModels)
})

onUnmounted(() => {
  teardownE2eSpeed()
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('open-drawer', handleOpenDrawer)
  window.removeEventListener('open-models', handleOpenModels)
})

const isLabActive = computed(() => {
  return route.path.startsWith('/lab') || ['/challenge', '/turtle-soup', '/story-lite', '/story-live', '/multi-life'].includes(route.path)
})
</script>

<template>
  <!-- Base: Force bg-surface-0 to prevent black flickering -->
  <div
    class="flex h-screen w-screen overflow-hidden bg-surface-0 font-sans text-text-primary selection:bg-accent/30 transition-colors duration-300"
    @touchstart.passive="onRootTouchStart"
    @touchmove.passive="onRootTouchMove"
    @touchend.passive="onRootTouchEnd"
    @touchcancel.passive="onRootTouchEnd">
    
    <!-- Sidebar: Only on wide screens -->
    <Sidebar v-if="!isMobileLayout" :collapsed="appStore.sidebarCollapsed" @collapse="appStore.toggleSidebar" @expand="appStore.toggleSidebar" />

    <!-- Main Content: Always flexible and clear -->
    <main :class="['flex-1 flex flex-col min-w-0 relative z-10 overflow-x-hidden bg-surface-0', platform === 'ios' ? 'safe-top safe-bottom' : '']">
      <router-view v-slot="{ Component }">
        <component :is="Component" :key="route.fullPath" />
      </router-view>
    </main>

    <!-- UNIFIED MOBILE DRAWER -->
    <Transition name="drawer">
      <div
        v-if="iosDrawerOpen"
        :class="['fixed inset-0 z-[100] flex flex-col bg-surface-0', platform === 'ios' ? 'safe-top' : '']"
        @touchstart.passive="onDrawerTouchStart"
        @touchmove.passive="onDrawerTouchMove"
        @touchend.passive="onDrawerTouchEnd"
        @touchcancel.passive="onDrawerTouchEnd">
        <div class="flex items-center justify-between px-6 py-4 border-b border-black/5 dark:border-white/5">
          <div class="flex items-center gap-2.5">
            <div :class="[logoBg, 'w-10 h-10 rounded-[10px] flex items-center justify-center border border-white/10 shrink-0 overflow-hidden shadow-lg']">
              <img
                :src="logoSrc"
                alt="SparkRing"
                class="w-10 h-10 object-contain"
              />
            </div>
            <div class="flex flex-col">
              <div class="flex items-center text-[13px] font-black uppercase leading-tight tracking-[0.15em] select-none">
                <span :class="[isDarkMode ? 'from-indigo-300 via-blue-400 to-purple-400' : 'from-indigo-950 via-indigo-800 to-purple-700', 'bg-gradient-to-r bg-clip-text text-transparent']">Spark</span>
                <span class="bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">Ring</span>
              </div>
              <div class="flex w-full justify-between pr-1 -mt-0.5 text-[9px] font-bold uppercase text-text-tertiary opacity-60">
                <span>思</span><span>路</span><span>集</span>
              </div>
            </div>
          </div>
          <button @click="iosDrawerOpen = false" class="p-2 rounded-full hover:bg-black/5 transition-all">
            <X :size="20" stroke-width="3.5" />
          </button>
        </div>
        <div class="flex-1 overflow-y-auto px-4 py-6 space-y-2">
          <template v-for="link in [
            { path: '/', icon: Home, label: '首页' }, 
            { path: '/chat', icon: MessageSquare, label: '多问几家' }, 
            { path: '/discuss', icon: GitMerge, label: '深度对质' }, 
            { path: '/advisors-v2', icon: Compass, label: '锦囊参谋' },
            { path: '/lab', icon: FlaskConical, label: '创意实验室' }
          ]" :key="link.path">
            <button @click="router.push(link.path); iosDrawerOpen = false" class="w-full flex items-center gap-4 px-5 py-4 rounded-3xl transition-all active:scale-95" :class="(link.path === '/lab' ? isLabActive : route.path === link.path) ? 'bg-text-primary text-surface-1 shadow-xl' : 'bg-transparent text-text-primary hover:bg-black/5'">
              <component :is="link.icon" :size="20" stroke-width="3.5" />
              <span class="font-black text-sm uppercase tracking-widest">{{ link.label }}</span>
            </button>
          </template>

          <div v-if="sessionStore.sortedSessions.length" class="mt-6 border-t border-black/5 dark:border-white/5 pt-5 space-y-2">
            <p class="px-2 text-[10px] font-black uppercase tracking-[0.28em] text-text-tertiary opacity-50">最近的</p>
            <button
              v-for="session in sessionStore.sortedSessions"
              :key="session.id"
              @click="iosSwitchSession(session)"
              class="w-full flex items-start gap-3 px-4 py-3.5 rounded-2xl text-left transition-all active:scale-[0.98]"
              :class="isDrawerSessionActive(session)
                ? 'bg-text-primary text-surface-1 shadow-lg'
                : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'">
              <div class="flex-1 min-w-0">
                <div class="text-xs font-bold truncate">{{ session.title }}</div>
                <div class="text-[9px] mt-1 uppercase font-black tracking-widest opacity-45">
                  {{ sessionStore.formatTime(session.updatedAt) }} · {{ session.messageCount }} 轮
                </div>
              </div>
            </button>
          </div>
        </div>
        <div class="p-6 border-t border-black/5 grid grid-cols-2 gap-3">
          <button @click="router.push('/models'); iosDrawerOpen = false" class="flex flex-col items-center gap-2 p-4 rounded-3xl bg-white/5 border border-white/5 active:scale-95 transition-all">
            <Package :size="20" stroke-width="3" /><span class="text-[10px] font-black uppercase tracking-widest">模型库</span>
          </button>
          <button @click="router.push('/settings'); iosDrawerOpen = false" class="flex flex-col items-center gap-2 p-4 rounded-3xl bg-white/5 border border-white/5 active:scale-95 transition-all">
            <Settings :size="20" stroke-width="3" /><span class="text-[10px] font-black uppercase tracking-widest">设置</span>
          </button>
        </div>
      </div>
    </Transition>

    <IOSModelSheet />
    <ToastContainer />
    <CommandPalette />
  </div>
</template>

<style>
.drawer-enter-active, .drawer-leave-active { transition: transform 0.4s cubic-bezier(0.32, 0.72, 0, 1); }
.drawer-enter-from, .drawer-leave-to { transform: translateX(-100%); }
</style>
