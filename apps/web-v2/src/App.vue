<script setup lang="ts">
import { ref, provide, onMounted, onUnmounted, watch, computed, reactive } from 'vue'
import { Capacitor } from '@capacitor/core'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useSessionStore } from '@/stores/session'
import { useProviderStore } from '@/stores/provider'
import { useTheme } from '@/composables/useTheme'
import Sidebar from '@/components/layout/Sidebar.vue'
import IOSModelSheet from '@/components/shared/IOSModelSheet.vue'
import ToastContainer from '@/components/shared/ToastContainer.vue'
import CommandPalette from '@/components/shared/CommandPalette.vue'
import {
  Sparkles, MessageSquare, GitMerge, Users, Plus, Home, Package, Settings, Sun, Moon,
  ChevronLeft, Menu, Laptop, Smartphone, Flame, Target, Soup, Clapperboard
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const sessionStore = useSessionStore()
const providerStore = useProviderStore()
const { theme, toggle: toggleTheme, v3Config } = useTheme()

const MOBILE_BREAKPOINT = 768
const isNative = Capacitor.isNativePlatform()
const platform = ref<'macos' | 'ios'>(isNative || window.innerWidth < MOBILE_BREAKPOINT ? 'ios' : 'macos')
const iosDrawerOpen = ref(false)
const iosModelSheetOpen = ref(false)
const modelSheetRequest = ref<any>(null)
const EDGE_SWIPE_WIDTH = 24
const SWIPE_TRIGGER_DISTANCE = 72

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

provide('platform', platform)

function onResize() {
  platform.value = isNative || window.innerWidth < MOBILE_BREAKPOINT ? 'ios' : 'macos'
}

function handleOpenModels() {
  modelSheetRequest.value = null
  iosModelSheetOpen.value = true
}

function handleOpenModelPicker(e: any) {
  if (platform.value === 'ios') {
    iosModelSheetOpen.value = true
    modelSheetRequest.value = e.detail
  }
}

function closeModelSheet() {
  iosModelSheetOpen.value = false
}

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
  if (platform.value !== 'ios' || iosDrawerOpen.value || iosModelSheetOpen.value) return
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

function iosSwitchSession(session: any) {
  sessionStore.switchSession(session.id)
  if (session.type === 'chat') router.push('/chat')
  else router.push('/discuss')
  iosDrawerOpen.value = false
}

function isDrawerSessionActive(session: any) {
  return sessionStore.currentSessionId === session.id && (route.path === '/chat' || route.path === '/discuss')
}

function handleOpenDrawer() {
  iosDrawerOpen.value = true
}

onMounted(() => {
  window.addEventListener('resize', onResize)
  window.addEventListener('open-models', handleOpenModels)
  window.addEventListener('open-model-picker', handleOpenModelPicker)
  window.addEventListener('open-drawer', handleOpenDrawer)

  appStore.initialize()
  sessionStore.loadSessions()
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('open-models', handleOpenModels)
  window.removeEventListener('open-model-picker', handleOpenModelPicker)
  window.removeEventListener('open-drawer', handleOpenDrawer)
})

watch(() => route.path, () => {
  iosDrawerOpen.value = false
})
</script>

<template>
  <div
    :class="['h-full w-full overflow-hidden flex transition-colors duration-500', theme === 'dark' ? 'dark bg-[#0b0b18]' : 'bg-[#f5f5f7]']"
    @touchstart.passive="onRootTouchStart"
    @touchmove.passive="onRootTouchMove"
    @touchend.passive="onRootTouchEnd"
    @touchcancel.passive="onRootTouchEnd">
    <!-- V3 AURORA ENGINE -->
    <div v-if="v3Config.showAurora"
      class="fixed -inset-[100px] pointer-events-none z-0 overflow-hidden opacity-50 dark:opacity-100">
      <div
        class="absolute top-[10%] left-[10%] w-[60%] h-[60%] bg-accent/20 blur-[120px] animate-v3-blob rounded-full">
      </div>
      <div
        class="absolute bottom-[10%] right-[10%] w-[50%] h-[50%] bg-purple-500/10 blur-[100px] animate-v3-blob-delayed rounded-full">
      </div>
    </div>

    <!-- V3 FILM GRAIN OVERLAY -->
    <div
      class="fixed inset-0 pointer-events-none z-[9999] opacity-[0.03] dark:opacity-[0.05] mix-blend-overlay"
      style="background-image: url('https://grainy-gradients.vercel.app/noise.svg');"></div>

    <!-- Desktop Sidebar (Only for macOS platform) -->
    <Sidebar v-if="platform === 'macos'" />

    <main
      :class="['flex-1 flex flex-col min-w-0 relative z-10 overflow-x-hidden', platform === 'ios' ? 'safe-top safe-bottom' : '']">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- MOBILE DRAWER (Improved V3 Light Mode) -->
    <Teleport to="body">
      <transition name="drawer-overlay">
        <div v-if="iosDrawerOpen" class="fixed inset-0 bg-black/40 backdrop-blur-sm z-[10000]"
          @click="iosDrawerOpen = false" />
      </transition>
      <transition name="drawer-panel">
        <div v-if="iosDrawerOpen"
          class="mobile-drawer-shell fixed inset-y-0 left-0 w-[300px] max-w-[85vw] z-[10001] flex flex-col px-3"
          @touchstart.passive="onDrawerTouchStart"
          @touchmove.passive="onDrawerTouchMove"
          @touchend.passive="onDrawerTouchEnd"
          @touchcancel.passive="onDrawerTouchEnd">

          <!-- The Bleached Container -->
          <div
            class="mobile-drawer-container flex-1 flex flex-col rounded-[32px] shadow-[0_30px_80px_rgba(0,0,0,0.3)] border border-white/10 overflow-hidden"
            :class="theme === 'dark' ? 'glass-v3 bg-[#0b0b18]' : 'bg-white'">

            <!-- Header (PERFECT SYMMETRY FIX - py-8) -->
            <div
              class="flex items-center justify-center border-b border-black/[0.03] dark:border-white/5 relative shrink-0 py-8">
              <div class="flex items-center gap-3">
                <div class="relative flex items-center justify-center w-10 h-10 shrink-0">
                  <div
                    class="absolute inset-0 rounded-full border border-dashed border-accent/30 animate-[spin_10s_linear_infinite_reverse]">
                  </div>
                  <div
                    class="relative flex items-center justify-center w-7 h-7 rounded-full bg-gradient-to-tr from-accent to-indigo-600 shadow-lg">
                    <Sparkles class="w-4 h-4 text-white" :stroke-width="3.5" />
                  </div>
                </div>
                <div class="flex flex-col select-none">
                  <div
                    class="flex items-center text-[20px] font-black tracking-tighter uppercase italic leading-none">
                    <span class="text-accent">SPARK</span>
                    <span class="text-text-primary ml-1.5">RING</span>
                  </div>
                  <div
                    class="h-[1.5px] bg-gradient-to-r from-accent via-accent/30 to-transparent mt-1.5 opacity-40">
                  </div>
                </div>
              </div>
            </div>

            <!-- Navigation Area -->
            <div class="px-3 py-6 space-y-2 overflow-y-auto no-scrollbar flex-1">
              <div
                class="px-4 mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary opacity-40">
                新建</div>
              <button @click="iosNewChat"
                class="w-full flex items-center gap-4 px-5 py-4 rounded-2xl bg-accent text-white shadow-xl shadow-accent/20 active:scale-95 transition-all">
                <Plus :size="20" stroke-width="4" /> <span
                  class="font-black uppercase tracking-widest text-[11px]">新聊天</span>
              </button>

              <div class="h-px bg-black/[0.03] dark:bg-white/5 my-4 mx-4" />

              <div class="px-4 mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary opacity-40">导航</div>
              <template v-for="link in [
                { path: '/', icon: Home, label: '首页' },
                { path: '/chat', icon: MessageSquare, label: '聊天' },
                { path: '/discuss', icon: GitMerge, label: '辩论' },
                { path: '/advisors', icon: Users, label: '参谋团' },
                { path: '/challenge', icon: Flame, label: '每日一辩' },
                { path: '/story-lite', icon: Target, label: '剧情冒险' },
                { path: '/turtle-soup', icon: Soup, label: '海龟汤' },
                { path: '/story-live', icon: Clapperboard, label: '剧情共演' }
              ]" :key="link.path">
                <button v-if="link.path !== '/' || appStore.showHomeEntry" @click="router.push(link.path); iosDrawerOpen = false" 
                  class="w-full flex items-center gap-4 px-5 py-4 rounded-2xl transition-all duration-300 active:scale-95" 
                  :class="route.path === link.path 
                    ? 'bg-text-primary text-surface-1 shadow-xl' 
                    : 'bg-transparent text-text-primary hover:bg-black/[0.03] dark:hover:bg-white/5'"
                >
                  <component :is="link.icon" :size="20" stroke-width="3" /> <span class="font-black uppercase tracking-widest text-[11px]">{{ link.label }}</span>
                </button>
              </template>

              <!-- Session History Section -->
              <div class="mt-8 border-t border-black/[0.03] dark:border-white/5 pt-6">
                <p
                  class="text-[10px] font-black text-text-tertiary uppercase tracking-widest px-4 mb-2 opacity-40">
                  最近的</p>
                <div v-if="sessionStore.sortedSessions.length" class="space-y-1 px-1 pb-4">
                  <button v-for="session in sessionStore.sortedSessions" :key="session.id"
                    @click="iosSwitchSession(session)"
                    class="w-full flex items-start gap-3 px-4 py-3.5 rounded-2xl text-left transition-all active:scale-[0.98]"
                    :class="isDrawerSessionActive(session) 
                      ? 'bg-text-primary text-surface-1 shadow-lg' 
                      : 'text-text-primary hover:bg-black/[0.03] dark:hover:bg-white/5'">
                    <div class="flex-1 min-w-0">
                      <div class="text-xs font-bold truncate">{{ session.title }}</div>
                      <div class="text-[9px] mt-1 uppercase font-black tracking-widest opacity-40"
                        :class="isDrawerSessionActive(session) ? 'text-surface-1' : ''">
                        {{ sessionStore.formatTime(session.updatedAt) }} ·
                        聊了 {{ session.messageCount }} 轮
                      </div>
                    </div>
                  </button>
                </div>
              </div>
            </div>

            <!-- Footer (PERFECT SYMMETRY FIX - py-8) -->
            <div
              class="px-3 border-t border-black/[0.03] dark:border-white/5 flex gap-2 shrink-0 py-8">
              <button v-for="util in [
                { path: '/models', icon: Package, label: '模型库' },
                { path: '/settings', icon: Settings, label: '设置' }
              ]" :key="util.path" @click="router.push(util.path); iosDrawerOpen = false"
                class="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl transition-all border border-transparent font-black uppercase tracking-widest text-[10px]"
                :class="route.path === util.path 
                  ? 'bg-text-primary text-surface-1 shadow-lg' 
                  : 'bg-black/[0.03] dark:bg-white/5 text-text-primary hover:bg-black/[0.06]'">
                <component :is="util.icon" :size="16" stroke-width="3" />
                <span>{{ util.label }}</span>
              </button>
              <button @click="toggleTheme"
                class="px-4 flex items-center justify-center rounded-xl bg-black/[0.03] dark:bg-white/5 text-text-secondary hover:text-text-primary active:scale-90 transition-all border border-transparent">
                <Sun v-if="theme === 'dark'" :size="18" stroke-width="3" class="text-amber-400" />
                <Moon v-else :size="18" stroke-width="3" class="text-indigo-600" />
              </button>
            </div>
          </div>
        </div>
      </transition>
    </Teleport>
  </div>

  <IOSModelSheet :open="iosModelSheetOpen" :request="modelSheetRequest" @close="closeModelSheet" />
  <ToastContainer />
  <CommandPalette />
</template>

<style scoped>
/* V3 Industrial Stroke Enforcement */
:deep(svg) {
  stroke-width: 3px !important;
}
:deep(.lucide-plus),
:deep(.lucide-plus-circle) {
  stroke-width: 4px !important;
}

.drawer-overlay-enter-active,
.drawer-overlay-leave-active {
  transition: opacity 0.4s ease;
}
.drawer-overlay-enter-from,
.drawer-overlay-leave-to {
  opacity: 0;
}

.drawer-panel-enter-active {
  animation: drawerIn 0.4s cubic-bezier(0.32, 0.72, 0, 1);
}
.drawer-panel-leave-active {
  animation: drawerOut 0.3s ease-in;
}
@keyframes drawerIn {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(0);
  }
}
@keyframes drawerOut {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(-100%);
  }
}

.safe-top {
  padding-top: max(10px, calc(env(safe-area-inset-top) - 12px));
}
.safe-bottom {
  padding-bottom: env(safe-area-inset-bottom);
}
.mobile-drawer-shell {
  padding-top: max(18px, calc(env(safe-area-inset-top) - 4px));
  padding-bottom: calc(env(safe-area-inset-bottom) + 12px);
}
.page-enter-active {
  animation: pageIn 0.2s ease-out;
}
.page-leave-active {
  animation: pageOut 0.15s ease-in;
}
@keyframes pageIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@keyframes pageOut {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
  }
}
</style>
