<script setup lang="ts">
import { ref, provide, onMounted, onUnmounted, watch, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useSessionStore } from '@/stores/session'
import { useProviderStore } from '@/stores/provider'
import { useTheme } from '@/composables/useTheme'
import { FREE_PROVIDERS } from '@/data/freeProviders'
// NOTE: Root shell does not expose a drag-region header.
// Keep drag behavior scoped to page-level floating headers (Chat/Discuss/Advisors).
// import { startWindowDrag } from '@/utils/windowDrag'
import Sidebar from '@/components/layout/Sidebar.vue'
import IOSModelSheet from '@/components/shared/IOSModelSheet.vue'
import ToastContainer from '@/components/shared/ToastContainer.vue'
import CommandPalette from '@/components/shared/CommandPalette.vue'
import {
  Monitor, Smartphone, Sun, Moon, Layers, Plus, GitMerge,
  Menu, MessageSquare, Trash2, Package, Settings, Sparkles, Users, Home
} from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const sessionStore = useSessionStore()
const providerStore = useProviderStore()
const { theme, toggle: toggleTheme, v3Config } = useTheme()

const MOBILE_BREAKPOINT = 768
const platform = ref<'macos' | 'ios'>(window.innerWidth < MOBILE_BREAKPOINT ? 'ios' : 'macos')
const iosModelSheetOpen = ref(false)
const modelSheetRequest = ref<Record<string, unknown> | null>(null)
const sidebarCollapsed = ref(false)
const iosDrawerOpen = ref(false)

provide('platform', platform)

function onResize() {
  platform.value = window.innerWidth < MOBILE_BREAKPOINT ? 'ios' : 'macos'
}

const mouseX = ref(0)
const mouseY = ref(0)

function handleMouseMove(e: MouseEvent) {
  if (platform.value !== 'macos') return
  mouseX.value = (e.clientX / window.innerWidth - 0.5) * 40
  mouseY.value = (e.clientY / window.innerHeight - 0.5) * 40
}

function handleOpenModels() {
  modelSheetRequest.value = null
  iosModelSheetOpen.value = true
}

function handleOpenModelPicker(event: Event) {
  if (platform.value !== 'ios') return
  modelSheetRequest.value = ((event as CustomEvent<Record<string, unknown> | null>).detail) ?? null
  iosModelSheetOpen.value = true
}

function closeModelSheet() {
  iosModelSheetOpen.value = false
  modelSheetRequest.value = null
}

onMounted(() => {
  window.addEventListener('resize', onResize)
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('open-models', handleOpenModels)
  window.addEventListener('open-model-picker', handleOpenModelPicker)
  window.addEventListener('toggle-platform', togglePlatform)
  window.addEventListener('open-drawer', () => { iosDrawerOpen.value = true })
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('open-models', handleOpenModels)
  window.removeEventListener('open-model-picker', handleOpenModelPicker)
  window.removeEventListener('toggle-platform', togglePlatform)
  window.removeEventListener('open-drawer', () => { iosDrawerOpen.value = true })
})

appStore.initialize()
sessionStore.loadSessions()

const recommendedConfiguredCount = computed(() =>
  FREE_PROVIDERS.filter((provider) => providerStore.keyStatus[provider.id]).length,
)

const showQuickStartEntry = computed(() => recommendedConfiguredCount.value <= 2)

function togglePlatform() {
  platform.value = platform.value === 'macos' ? 'ios' : 'macos'
  iosDrawerOpen.value = false
}

watch(() => route.path, () => {
  iosDrawerOpen.value = false
})

// iOS drawer touch
const drawerTouchStartX = ref(0)
const drawerTouchCurrentX = ref(0)
const drawerDragging = ref(false)

function onDrawerTouchStart(e: TouchEvent) {
  const x = e.touches[0].clientX
  if ((!iosDrawerOpen.value && x < 24) || iosDrawerOpen.value) {
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
  if (!iosDrawerOpen.value && delta > 80) iosDrawerOpen.value = true
  else if (iosDrawerOpen.value && delta < -60) iosDrawerOpen.value = false
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
</script>

<template>
  <!-- V3 GLOBAL CINEMATIC LAYER -->
  <div class="fixed inset-0 pointer-events-none z-[9999] opacity-[var(--v3-noise,0.06)] mix-blend-overlay"
       style="background-image: url('https://grainy-gradients.vercel.app/noise.svg');"></div>

  <div v-if="v3Config.showAurora" 
       class="fixed -inset-[100px] pointer-events-none overflow-hidden z-0 opacity-40 dark:opacity-20 transition-all duration-1000"
       :style="{ transform: `translate3d(${mouseX}px, ${mouseY}px, 0)` }">
    <div class="absolute top-[10%] left-[10%] w-[60%] h-[60%] bg-indigo-500/30 blur-[150px] animate-v3-blob rounded-full" />
    <div class="absolute top-[20%] right-[10%] w-[50%] h-[50%] bg-purple-500/20 blur-[120px] animate-v3-blob animation-delay-2000 rounded-full" />
    <div class="absolute bottom-[10%] left-[20%] w-[70%] h-[50%] bg-blue-500/10 blur-[180px] animate-v3-blob animation-delay-4000 rounded-full" />
  </div>

  <div class="flex h-screen overflow-hidden relative z-10"
       @touchstart.passive="onDrawerTouchStart"
       @touchmove.passive="onDrawerTouchMove"
       @touchend.passive="onDrawerTouchEnd">

    <!-- Sidebar: macOS (Left rail) or iOS (Hidden, triggered by event) -->
    <Sidebar
      v-if="platform === 'macos'"
      :collapsed="sidebarCollapsed"
      @collapse="sidebarCollapsed = true"
      @expand="sidebarCollapsed = false"
      @toggle-platform="togglePlatform"
    />

    <!-- Main Content Area -->
    <main class="flex-1 flex flex-col min-w-0 bg-transparent relative">
      <div class="flex-1 flex flex-col overflow-hidden">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </transition>
        </router-view>
      </div>
    </main>

    <!-- Mobile Side Drawer -->
    <Teleport to="body">
      <transition name="drawer-overlay">
        <div v-if="iosDrawerOpen" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-[10000]" @click="iosDrawerOpen = false" />
      </transition>
      <transition name="drawer-panel">
        <div v-if="iosDrawerOpen" class="fixed inset-y-0 left-0 w-[300px] max-w-[85vw] z-[10001] flex flex-col p-3 safe-top">
          <div class="glass-v3 flex-1 flex flex-col rounded-[32px] shadow-2xl border border-white/10 overflow-hidden bg-white dark:bg-[#0b0b18]">
            <!-- Header: Logo & Theme -->
            <div class="h-16 flex items-center justify-between px-6 border-b border-white/5">
              <div class="flex items-center gap-2.5">
                <div class="relative flex items-center justify-center w-7 h-7 rounded-full bg-gradient-to-tr from-accent to-purple-500 shadow-lg">
                  <div class="absolute inset-0.5 rounded-full border-2 border-white/20"></div>
                  <Sparkles class="w-4 h-4 text-white" />
                </div>
                <span class="text-xl font-black tracking-tighter flex items-baseline">
                  <span class="text-accent italic">Spark</span>
                  <span class="text-text-primary">Ring</span>
                </span>
              </div>
              <button
                @click="toggleTheme"
                class="p-2 rounded-full hover:bg-white/5 text-text-secondary transition-all active:scale-90"
              >
                <Sun v-if="theme === 'dark'" :size="20" :stroke-width="3" class="text-amber-400" />
                <Moon v-else :size="20" :stroke-width="3" class="text-indigo-600" />
              </button>
            </div>

            <!-- Feature Navigation -->
            <div class="px-3 py-6 space-y-2 overflow-y-auto no-scrollbar">
              <div class="px-4 mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary opacity-40">Quick Action</div>
              <button @click="iosNewChat" class="w-full flex items-center gap-4 px-5 py-4 rounded-2xl bg-accent text-white shadow-xl shadow-accent/20 active:scale-95 transition-all">
                <Plus :size="20" :stroke-width="4" /> <span class="font-black uppercase tracking-widest text-[11px]">开启新对话</span>
              </button>

              <div class="h-px bg-white/5 my-4 mx-4" />

              <div class="px-4 mb-2 text-[10px] font-black uppercase tracking-[0.3em] text-text-tertiary opacity-40">Main Menu</div>
              <button @click="router.push('/'); iosDrawerOpen = false" class="w-full flex items-center gap-4 px-5 py-4 rounded-2xl transition-all duration-300 active:scale-95" 
                :class="route.path === '/' ? 'bg-text-primary text-surface-1 shadow-xl' : 'text-text-secondary hover:bg-white/5'">
                <Home :size="20" :stroke-width="3" /> <span class="font-black uppercase tracking-widest text-[11px]">首页体验</span>
              </button>
              <button @click="router.push('/chat'); iosDrawerOpen = false" class="w-full flex items-center gap-4 px-5 py-4 rounded-2xl transition-all duration-300 active:scale-95" 
                :class="route.path === '/chat' ? 'bg-text-primary text-surface-1 shadow-xl' : 'text-text-secondary hover:bg-white/5'">
                <MessageSquare :size="20" :stroke-width="3" /> <span class="font-black uppercase tracking-widest text-[11px]">对话模式</span>
              </button>
              <button @click="router.push('/discuss'); iosDrawerOpen = false" class="w-full flex items-center gap-4 px-5 py-4 rounded-2xl transition-all duration-300 active:scale-95" 
                :class="route.path === '/discuss' ? 'bg-text-primary text-surface-1 shadow-xl' : 'text-text-secondary hover:bg-white/5'">
                <GitMerge :size="20" :stroke-width="3" /> <span class="font-black uppercase tracking-widest text-[11px]">深度辩论</span>
              </button>
              <button @click="router.push('/advisors'); iosDrawerOpen = false" class="w-full flex items-center gap-4 px-5 py-4 rounded-2xl transition-all duration-300 active:scale-95" 
                :class="route.path === '/advisors' ? 'bg-text-primary text-surface-1 shadow-xl' : 'text-text-secondary hover:bg-white/5'">
                <Users :size="20" :stroke-width="3" /> <span class="font-black uppercase tracking-widest text-[11px]">AI 锦囊团</span>
              </button>
            </div>

            <!-- Session History -->
            <div class="flex-1 overflow-y-auto px-3 py-2 border-t border-white/5 mt-2">
              <p class="text-[10px] font-black text-text-tertiary uppercase tracking-widest px-4 mb-2 mt-4 opacity-40">Recent History</p>
              <div v-if="sessionStore.sortedSessions.length" class="space-y-1">
                <button v-for="session in sessionStore.sortedSessions" :key="session.id" @click="iosSwitchSession(session)" class="w-full flex items-start gap-3 px-4 py-3.5 rounded-2xl text-left transition-all active:scale-[0.98]" :class="sessionStore.currentSessionId === session.id ? 'bg-text-primary text-surface-1 shadow-lg' : 'text-text-secondary active:bg-white/5'">
                  <div class="flex-1 min-w-0">
                    <div class="text-xs font-bold truncate">{{ session.title }}</div>
                    <div class="text-[9px] mt-1 uppercase font-black tracking-widest opacity-50" :class="sessionStore.currentSessionId === session.id ? 'text-surface-1' : ''">
                      {{ sessionStore.formatTime(session.updatedAt) }} · {{ session.messageCount }} 轮
                    </div>
                  </div>
                </button>
              </div>
            </div>

            <!-- Footer Utilities -->
            <div class="px-3 py-4 bg-black/5 dark:bg-white/2 border-t border-white/5 flex gap-2">
              <button @click="router.push('/models'); iosDrawerOpen = false" class="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-white/5 text-text-secondary text-[10px] font-black uppercase tracking-widest">
                <Package :size="16" :stroke-width="3" />
                模型
              </button>
              <button @click="router.push('/settings'); iosDrawerOpen = false" class="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-white/5 text-text-secondary text-[10px] font-black uppercase tracking-widest">
                <Settings :size="16" :stroke-width="3" />
                设置
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
.drawer-overlay-enter-active, .drawer-overlay-leave-active { transition: opacity 0.4s ease; }
.drawer-overlay-enter-from, .drawer-overlay-leave-to { opacity: 0; }
.drawer-panel-enter-active { animation: drawerIn 0.4s cubic-bezier(0.32, 0.72, 0, 1); }
.drawer-panel-leave-active { animation: drawerOut 0.3s ease-in; }
@keyframes drawerIn { from { transform: translateX(-100%); } to { transform: translateX(0); } }
@keyframes drawerOut { from { transform: translateX(0); } to { transform: translateX(-100%); } }
.safe-top { padding-top: env(safe-area-inset-top); }
.page-enter-active { animation: pageIn 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.page-leave-active { animation: pageOut 0.2s ease-in; }
@keyframes pageIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes pageOut { from { opacity: 1; } to { opacity: 0; } }
</style>
