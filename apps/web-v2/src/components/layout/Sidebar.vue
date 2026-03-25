<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useSessionStore } from '@/stores/session'
import { useProviderStore } from '@/stores/provider'
import { useTheme } from '@/composables/useTheme'
import {
  MessageSquare, GitMerge, Users, Plus, Settings, Package, Search,
  Sun, Moon, Trash2, PanelLeftClose, PanelLeftOpen, Smartphone,
  Clock, Home, FlaskConical, Compass
} from 'lucide-vue-next'
import { computed, inject, onMounted, ref } from 'vue'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const sessionStore = useSessionStore()
const providerStore = useProviderStore()
const { theme, toggle: toggleTheme } = useTheme()

const isDarkMode = computed(() => theme.value === 'dark')
const logoSrc = computed(() => isDarkMode.value ? '/logos/logo-v5-light.png' : '/logos/logo-v5-dark.png')
const logoBg = computed(() => isDarkMode.value ? 'bg-white/90 shadow-[0_0_20px_rgba(255,255,255,0.15)]' : 'bg-black shadow-xl')

const props = defineProps<{ collapsed?: boolean }>()
const emit = defineEmits<{ collapse: []; expand: []; togglePlatform: [] }>()
const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isMobile = computed(() => platform.value === 'ios')

function isSessionActive(session: { id: string }) {
  return sessionStore.currentSessionId === session.id
}

function switchTo(session: { id: string; type: string }) {
  sessionStore.switchSession(session.id)
  router.push(session.type === 'discuss' ? '/discuss' : '/chat')
}

function deleteSession(id: string, e: Event) {
  e.stopPropagation()
  sessionStore.deleteSession(id)
}

onMounted(() => {
  sessionStore.loadSessions()
})
</script>

<template>
  <!-- Collapsed icons rail -->
  <aside v-if="collapsed"
    class="relative z-50 w-16 shrink-0 flex flex-col items-center py-4 gap-2 h-full">
    <div
      class="glass-v3 w-12 flex flex-col items-center py-4 gap-3 rounded-[24px] shadow-2xl border border-white/10 flex-1">
      <div
        class="relative group/logo flex items-center justify-center w-10 h-10 shrink-0 cursor-pointer mb-2"
        @click="router.push('/')">
        <div :class="[logoBg, 'w-10 h-10 rounded-[10px] flex items-center justify-center transition-all duration-300 group-hover/logo:scale-110 overflow-hidden border border-white/5']">
          <img
            :src="logoSrc"
            alt="SparkRing"
            class="w-10 h-10 object-contain"
          />
        </div>
      </div>

      <button @click="emit('expand')"
        class="p-2 rounded-xl hover:bg-white/10 text-text-secondary transition-all">
        <PanelLeftOpen :size="22" stroke-width="3" />
      </button>

      <div class="flex flex-col gap-2 w-full px-1.5 mt-2">
        <button @click="router.push('/')"
          class="flex items-center justify-center p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all"
          :class="route.path === '/' ? 'bg-accent/20 text-accent' : ''">
          <Home :size="22" stroke-width="3" />
        </button>
        <button @click="newChat"
          class="flex items-center justify-center p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all"
          :class="route.path === '/chat' ? 'bg-accent/20 text-accent' : ''">
          <MessageSquare :size="22" stroke-width="3" />
        </button>
        <button @click="newDiscuss"
          class="flex items-center justify-center p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all"
          :class="route.path === '/discuss' ? 'bg-accent/20 text-accent' : ''">
          <GitMerge :size="22" stroke-width="3" />
        </button>
        <button @click="newAdvisors"
          class="flex items-center justify-center p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all"
          :class="route.path === '/advisors' ? 'bg-accent/20 text-accent' : ''">
          <Users :size="22" stroke-width="3" />
        </button>
        <button @click="router.push('/advisors-v2')"
          class="flex items-center justify-center p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all"
          :class="route.path === '/advisors-v2' ? 'bg-accent/20 text-accent' : ''">
          <Compass :size="20" stroke-width="3" />
        </button>
        <button @click="goLab"
          class="flex items-center justify-center p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all"
          :class="route.path.startsWith('/lab') || ['/challenge', '/turtle-soup', '/story-lite', '/story-live', '/multi-life'].includes(route.path) ? 'bg-accent/20 text-accent' : ''">
          <FlaskConical :size="22" stroke-width="3" />
        </button>
      </div>

      <div class="flex-1" />
      <button @click="router.push('/settings')"
        class="p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all mb-2">
        <Settings :size="20" stroke-width="3" />
      </button>
    </div>
  </aside>

  <!-- Expanded sidebar -->
  <aside v-else class="relative z-50 w-[280px] shrink-0 flex flex-col p-3 h-full">
    <div
      class="glass-v3 flex-1 flex flex-col rounded-[32px] shadow-2xl border border-white/10 overflow-hidden relative">
      <div class="h-20 flex items-center pl-5 pr-2">
        <div class="flex items-center gap-2 group/logo cursor-pointer select-none"
          @click="router.push('/')">
          <div :class="[logoBg, 'w-12 h-12 rounded-[12px] flex items-center justify-center transition-all duration-300 group-hover/logo:scale-105 shrink-0 overflow-hidden border border-white/10']">
            <img
              :src="logoSrc"
              alt="SparkRing"
              class="w-12 h-12 object-contain"
            />
          </div>
          <div class="flex flex-col ml-1">
            <div class="flex items-center text-[14px] font-black uppercase leading-tight tracking-[0.15em] select-none">
              <span :class="[isDarkMode ? 'from-indigo-300 via-blue-400 to-purple-400' : 'from-indigo-950 via-indigo-800 to-purple-700', 'bg-gradient-to-r bg-clip-text text-transparent']">Spark</span>
              <span class="bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">Ring</span>
            </div>
            <div class="flex w-full justify-between pr-1.5 -mt-0.5 text-[10px] font-bold uppercase text-text-tertiary opacity-70">
              <span>思</span><span>路</span><span>集</span>
            </div>
          </div>
        </div>
      </div>

      <div class="px-3 space-y-1.5 mt-2">
        <button @click="router.push('/')"
          class="w-full flex items-center gap-3.5 px-4 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] transition-all group active:scale-95"
          :class="route.path === '/' ? 'bg-text-primary text-surface-1 shadow-xl' : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'">
          <Home :size="16" stroke-width="3"
            :class="route.path === '/' ? 'text-surface-1' : 'group-hover:text-emerald-400'" />
          <span>首页</span>
        </button>
        <button @click="newChat"
          class="w-full flex items-center gap-3.5 px-4 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] transition-all group active:scale-95"
          :class="route.path === '/chat' ? 'bg-text-primary text-surface-1 shadow-xl' : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'">
          <MessageSquare :size="16" stroke-width="3"
            :class="route.path === '/chat' ? 'text-surface-1' : 'group-hover:text-blue-400'" />
          <span>多问几家</span>
        </button>
        <button @click="newDiscuss"
          class="w-full flex items-center gap-3.5 px-4 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] transition-all group active:scale-95"
          :class="route.path === '/discuss' ? 'bg-text-primary text-surface-1 shadow-xl' : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'">
          <GitMerge :size="16" stroke-width="3"
            :class="route.path === '/discuss' ? 'text-surface-1' : 'group-hover:text-purple-400'" />
          <span>深度对质</span>
        </button>
        <button @click="router.push('/advisors-v2')"
          class="w-full flex items-center gap-3.5 px-4 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] transition-all group active:scale-95"
          :class="route.path === '/advisors-v2' ? 'bg-text-primary text-surface-1 shadow-xl' : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'">
          <Compass :size="16" stroke-width="3" :class="route.path === '/advisors-v2' ? 'text-surface-1' : 'group-hover:text-emerald-400'" />
          <span>锦囊参谋</span>
        </button>
        <button @click="goLab"
          class="w-full flex items-center gap-3.5 px-4 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] transition-all group active:scale-95"
          :class="route.path.startsWith('/lab') || ['/challenge', '/turtle-soup', '/story-lite', '/story-live', '/multi-life'].includes(route.path) ? 'bg-text-primary text-surface-1 shadow-xl' : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'">
          <FlaskConical :size="16" stroke-width="3"
            :class="route.path.startsWith('/lab') ? 'text-surface-1' : 'group-hover:text-orange-400'" />
          <span>创意实验室</span>
          <span
            class="ml-auto text-[8px] font-black bg-accent/20 text-accent px-1.5 py-0.5 rounded-full">New</span>
        </button>
      </div>

      <div class="flex items-center gap-3 px-6 my-6 opacity-30 shrink-0">
        <div class="h-px flex-1 bg-text-tertiary"></div>
        <span
          class="text-[9px] font-black uppercase tracking-[0.3em] text-text-tertiary">历史</span>
        <div class="h-px flex-1 bg-text-tertiary"></div>
      </div>

      <div class="px-3 flex-1 overflow-y-auto no-scrollbar pb-4 min-h-0">
        <div v-if="sessionStore.sortedSessions.length" class="space-y-1.5">
          <button v-for="session in sessionStore.sortedSessions" :key="session.id"
            @click="switchTo(session)"
            class="w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl text-left transition-all group relative"
            :class="isSessionActive(session) ? 'bg-text-primary text-surface-1 shadow-xl' : 'text-text-secondary hover:bg-white/5'">
            <div class="w-1.5 h-1.5 rounded-full shrink-0"
              :style="{ backgroundColor: session.type === 'chat' ? '#6366f1' : '#a855f7' }"
              :class="isSessionActive(session) ? 'opacity-0' : 'opacity-60'"></div>
            <div class="flex-1 min-w-0">
              <div class="text-[11px] font-bold truncate tracking-tight">{{ session.title }}</div>
              <div class="text-[9px] mt-0.5 opacity-50 font-black uppercase tracking-widest">
                {{ sessionStore.formatTime(session.updatedAt) }}</div>
            </div>
            <button @click.stop="deleteSession(session.id, $event)"
              class="opacity-0 group-hover:opacity-100 w-8 h-8 rounded-full flex items-center justify-center hover:bg-red-500/10 hover:text-red-500 transition-all shrink-0">
              <Trash2 :size="14" stroke-width="3" />
            </button>
          </button>
        </div>
      </div>

      <div class="px-3 py-3 bg-black/5 border-t border-white/5 shrink-0">
        <div class="grid grid-cols-2 gap-1.5">
          <button @click="router.push('/models')"
            class="flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl transition-all border border-transparent bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary">
            <Package :size="18" stroke-width="3" /><span
              class="text-[9px] font-black uppercase tracking-widest">模型库</span>
          </button>
          <button @click="router.push('/settings')"
            class="flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl transition-all border border-transparent bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary">
            <Settings :size="18" stroke-width="3" /><span
              class="text-[9px] font-black uppercase tracking-widest">设置</span>
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
:deep(svg) {
  stroke-width: 3px !important;
}
</style>
