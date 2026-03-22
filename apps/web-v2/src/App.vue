<script setup lang="ts">
import { ref, provide, onMounted, onUnmounted, watch, computed, reactive, inject } from 'vue'
import { Capacitor } from '@capacitor/core'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useProviderStore } from '@/stores/provider'
import { useTheme } from '@/composables/useTheme'
import Sidebar from '@/components/layout/Sidebar.vue'
import IOSModelSheet from '@/components/shared/IOSModelSheet.vue'
import ToastContainer from '@/components/shared/ToastContainer.vue'
import CommandPalette from '@/components/shared/CommandPalette.vue'
import { Sparkles, MessageSquare, GitMerge, Users, Home, Package, Settings, FlaskConical, X } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const providerStore = useProviderStore()
useTheme() // 必须在 App.vue 调用，保证 watchEffect 全生命周期持久，不随子页面卸载而销毁

// --- Robust Dual-End Logic ---
const platform = ref(Capacitor.getPlatform())
const windowWidth = ref(window.innerWidth)
// Threshold 1024px for Sidebar vs Drawer
const isMobileLayout = computed(() => windowWidth.value < 1024 || platform.value === 'ios')

provide('platform', platform)
provide('isSmallScreen', isMobileLayout)

function handleResize() { windowWidth.value = window.innerWidth }

const iosDrawerOpen = ref(false)
function handleOpenDrawer() { iosDrawerOpen.value = true }

onMounted(async () => {
  await appStore.initialize()
  window.addEventListener('resize', handleResize)
  window.addEventListener('open-drawer', () => { iosDrawerOpen.value = true })
  window.addEventListener('open-models', () => { 
    router.push('/models')
    iosDrawerOpen.value = false
  })
})

onUnmounted(() => { window.removeEventListener('resize', handleResize) })

const isLabActive = computed(() => {
  return route.path.startsWith('/lab') || ['/challenge', '/turtle-soup', '/story-lite', '/story-live', '/multi-life'].includes(route.path)
})
</script>

<template>
  <!-- Base: Force bg-surface-0 to prevent black flickering -->
  <div class="flex h-screen w-screen overflow-hidden bg-surface-0 font-sans text-text-primary selection:bg-accent/30 transition-colors duration-300">
    
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
      <div v-if="iosDrawerOpen" :class="['fixed inset-0 z-[100] flex flex-col bg-surface-0', platform === 'ios' ? 'safe-top' : '']">
        <div class="flex items-center justify-between px-6 py-4 border-b border-black/5 dark:border-white/5">
          <div class="flex items-center gap-2">
            <Sparkles :size="20" stroke-width="3.5" class="text-accent" />
            <span class="font-black tracking-tight uppercase">SparkRing</span>
          </div>
          <button @click="iosDrawerOpen = false" class="p-2 rounded-full hover:bg-black/5 transition-all">
            <X :size="20" stroke-width="3.5" />
          </button>
        </div>
        <div class="flex-1 overflow-y-auto px-4 py-6 space-y-2">
          <template v-for="link in [
            { path: '/', icon: Home, label: '首页体验' }, 
            { path: '/chat', icon: MessageSquare, label: '多问几家' }, 
            { path: '/discuss', icon: GitMerge, label: '深度对质' }, 
            { path: '/advisors', icon: Users, label: '锦囊参谋' },
            { path: '/lab', icon: FlaskConical, label: '互动实验室' }
          ]" :key="link.path">
            <button @click="router.push(link.path); iosDrawerOpen = false" class="w-full flex items-center gap-4 px-5 py-4 rounded-3xl transition-all active:scale-95" :class="(link.path === '/lab' ? isLabActive : route.path === link.path) ? 'bg-text-primary text-surface-1 shadow-xl' : 'bg-transparent text-text-primary hover:bg-black/5'">
              <component :is="link.icon" :size="20" stroke-width="3.5" />
              <span class="font-black text-sm uppercase tracking-widest">{{ link.label }}</span>
            </button>
          </template>
        </div>
        <div class="p-6 border-t border-black/5 grid grid-cols-2 gap-3">
          <button @click="router.push('/models'); iosDrawerOpen = false" class="flex flex-col items-center gap-2 p-4 rounded-3xl bg-white/5 border border-white/5 active:scale-95 transition-all">
            <Package :size="20" stroke-width="3" /><span class="text-[10px] font-black uppercase tracking-widest">模型管理</span>
          </button>
          <button @click="router.push('/settings'); iosDrawerOpen = false" class="flex flex-col items-center gap-2 p-4 rounded-3xl bg-white/5 border border-white/5 active:scale-95 transition-all">
            <Settings :size="20" stroke-width="3" /><span class="text-[10px] font-black uppercase tracking-widest">偏好设置</span>
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
