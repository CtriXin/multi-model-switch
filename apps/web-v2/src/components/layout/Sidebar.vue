<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import { useProviderStore } from '@/stores/provider'
import { useTheme } from '@/composables/useTheme'
import { FREE_PROVIDERS } from '@/data/freeProviders'
import {
  MessageSquare, GitMerge, Users, Plus, Settings, Package, Search,
  Sun, Moon, Trash2, PanelLeftClose, PanelLeftOpen, Smartphone, Sparkles,
  Clock, Home
} from 'lucide-vue-next'
import { computed, inject, onMounted, ref } from 'vue'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const providerStore = useProviderStore()
const { theme, toggle: toggleTheme } = useTheme()

const props = defineProps<{ collapsed?: boolean }>()
const emit = defineEmits<{ collapse: []; expand: []; togglePlatform: [] }>()
const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isMobile = computed(() => platform.value === 'ios')

onMounted(() => {
  sessionStore.loadSessions()
})

const recommendedConfiguredCount = computed(() =>
  FREE_PROVIDERS.filter((provider) => providerStore.keyStatus[provider.id]).length,
)

const showQuickStartEntry = computed(() => recommendedConfiguredCount.value <= 2)

function newChat() {
  sessionStore.createSession('chat')
  router.push('/chat')
}

function newDiscuss() {
  sessionStore.createSession('discuss')
  router.push('/discuss')
}

function newAdvisors() {
  router.push('/advisors')
}

function switchTo(session: { id: string; type: string }) {
  sessionStore.switchSession(session.id)
  if (session.type === 'chat') router.push('/chat')
  else if (session.type === 'discuss') router.push('/discuss')
  else router.push('/advisors')
}

function isSessionActive(session: { id: string; type: string }) {
  if (route.path === '/chat') {
    return session.type === 'chat' && sessionStore.currentSessionId === session.id
  }
  if (route.path === '/discuss') {
    return session.type === 'discuss' && sessionStore.currentSessionId === session.id
  }
  return false
}

function deleteSession(id: string, e: Event) {
  e.stopPropagation()
  sessionStore.deleteSession(id)
}

function openCommandPalette() {
  const event = new globalThis.KeyboardEvent('keydown', { key: 'k', metaKey: true })
  globalThis.window.dispatchEvent(event)
}
</script>

<template>
  <!-- Collapsed: floating icon rail -->
  <aside
    v-if="collapsed"
    class="relative z-50 w-16 shrink-0 flex flex-col items-center py-4 gap-2 h-full"
  >
    <div class="glass-v3 w-12 flex flex-col items-center py-4 gap-3 rounded-[24px] shadow-2xl border border-white/10 flex-1">
      <!-- Logo in mini mode: No top margin div -->
      <div class="relative group/logo flex items-center justify-center w-10 h-10 shrink-0 cursor-pointer mb-2">
        <!-- Triple-Track Kinetic Mini Reactor -->
        <div class="absolute inset-0 rounded-full border border-dashed border-accent/20 animate-[spin_10s_linear_infinite_reverse] group-hover/logo:border-accent/50 transition-colors"></div>
        <div class="absolute inset-1 rounded-full border border-white/5 animate-[spin_20s_linear_infinite]"></div>
        <div class="relative flex items-center justify-center w-6.5 h-6.5 rounded-full bg-gradient-to-tr from-accent to-indigo-600 shadow-xl shadow-accent/20 transition-all duration-500 group-hover/logo:scale-110 active:scale-90">
          <Sparkles class="w-3.5 h-3.5 text-white relative z-10 drop-shadow-[0_0_8px_rgba(255,255,255,0.8)]" :stroke-width="3.5" />
        </div>
      </div>

      <!-- Actions: Unified size 22, stroke 3 -->
      <button @click="emit('expand')" class="p-2 rounded-xl hover:bg-white/10 text-text-secondary transition-all" title="展开侧边栏">
        <PanelLeftOpen :size="22" stroke-width="3" />
      </button>

      <div class="flex flex-col gap-2 w-full px-1.5 mt-2">
        <button @click="router.push('/')" class="flex items-center justify-center p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all" :class="route.path === '/' ? 'bg-accent/20 text-accent' : ''" title="首页">
          <Home :size="22" stroke-width="3" />
        </button>
        <button @click="newChat" class="flex items-center justify-center p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all" title="新对话">
          <MessageSquare :size="22" stroke-width="3" />
        </button>
        <button @click="newDiscuss" class="flex items-center justify-center p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all" title="新辩论">
          <GitMerge :size="22" stroke-width="3" />
        </button>
        <button @click="newAdvisors" class="flex items-center justify-center p-2.5 rounded-xl hover:bg-white/10 text-text-secondary transition-all" title="锦囊团">
          <Users :size="22" stroke-width="3" />
        </button>
      </div>

      <div class="flex-1" />

      <!-- Bottom mini utils: Unified size 20, stroke 3 -->
      <div class="flex flex-col gap-2 w-full px-1.5 pb-2">
        <button @click="toggleTheme" class="flex items-center justify-center p-2 rounded-xl hover:bg-white/10 text-text-secondary transition-all">
          <Sun v-if="theme === 'dark'" :size="20" stroke-width="3" class="text-amber-400" />
          <Moon v-else :size="20" stroke-width="3" class="text-indigo-600" />
        </button>
        <button @click="router.push('/settings')" class="flex items-center justify-center p-2 rounded-xl hover:bg-white/10 text-text-secondary transition-all" :class="route.path === '/settings' ? 'bg-accent/20 text-accent' : ''">
          <Settings :size="20" stroke-width="3" />
        </button>
      </div>
    </div>
  </aside>

  <!-- Expanded: full floating sidebar -->
  <aside v-else class="relative z-50 w-[280px] shrink-0 flex flex-col p-3 h-full">
    <div class="glass-v3 flex-1 flex flex-col rounded-[32px] shadow-2xl border border-white/10 overflow-hidden relative">
      <!-- Header: Pure Brand Identity (No Controls) -->
      <div class="h-20 flex items-center pl-5 pr-2">
        <div class="flex items-center gap-2 group/logo cursor-pointer select-none max-w-full">
          <!-- SparkRing v4.0.1: Precision Reactor -->
          <div class="relative flex items-center justify-center w-9 h-9 shrink-0">
            <!-- Triple Track Animation -->
            <div class="absolute inset-0 rounded-full border-[1.5px] border-dashed border-accent/20 animate-[spin_10s_linear_infinite_reverse]"></div>
            <div class="absolute inset-1.5 rounded-full border border-white/5 animate-[spin_20s_linear_infinite]"></div>
            <div class="relative flex items-center justify-center w-6 h-6 rounded-full bg-gradient-to-tr from-accent to-indigo-600 shadow-[0_0_15px_rgba(99,102,241,0.5)] group-hover/logo:scale-110 transition-all duration-500">
              <Sparkles class="w-3.5 h-3.5 text-white drop-shadow-[0_0_8px_rgba(255,255,255,0.8)]" :stroke-width="3.5" />
            </div>
          </div>
          
          <!-- Designer Typography: Syne (Surgically Fit) -->
          <div class="flex flex-col select-none relative pt-1 min-w-0">
            <div class="text-[18px] font-[800] tracking-[-0.08em] flex items-center leading-none transform-gpu scale-x-[0.98] origin-left" style="font-family: 'Syne', sans-serif;">
              <span class="text-accent drop-shadow-[0_0_15px_rgba(99,102,241,0.5)]">SPARK</span>
              <span class="text-text-primary ml-1 whitespace-nowrap">RING</span>
            </div>
            <!-- Kinetic Accent Line: Entry Animation + Hover Effect -->
            <div class="h-[1.5px] bg-gradient-to-r from-accent via-accent/40 to-transparent mt-1 opacity-40 animate-v3-line-entry group-hover/logo:opacity-100 group-hover/logo:h-[2px] transition-all duration-500"></div>
          </div>
        </div>
      </div>

      <!-- Primary Creation Area -->
      <div class="px-3 space-y-1.5 mt-2">
        <button
          @click="router.push('/')"
          class="w-full flex items-center gap-3.5 px-4 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] transition-all duration-300 group active:scale-95"
          :class="route.path === '/' 
            ? 'bg-text-primary text-surface-1 shadow-xl shadow-black/20' 
            : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'"
        >
          <Home :size="16" stroke-width="3" :class="route.path === '/' ? 'text-surface-1' : 'group-hover:text-emerald-400 transition-colors'" />
          <span>首页体验</span>
        </button>
        <button
          @click="newChat"
          class="w-full flex items-center gap-3.5 px-4 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] transition-all duration-300 group active:scale-95"
          :class="route.path === '/chat'
            ? 'bg-text-primary text-surface-1 shadow-xl shadow-black/20'
            : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'"
        >
          <MessageSquare :size="16" stroke-width="3" :class="route.path === '/chat' ? 'text-surface-1' : 'group-hover:text-accent transition-colors'" />
          <span>新对话</span>
          <Plus :size="12" :stroke-width="4" class="ml-auto opacity-30" />
        </button>
        <button
          @click="newDiscuss"
          class="w-full flex items-center gap-3.5 px-4 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] transition-all duration-300 group active:scale-95"
          :class="route.path === '/discuss'
            ? 'bg-text-primary text-surface-1 shadow-xl shadow-black/20'
            : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'"
        >
          <GitMerge :size="16" stroke-width="3" :class="route.path === '/discuss' ? 'text-surface-1' : 'group-hover:text-purple-400 transition-colors'" />
          <span>{{ isMobile ? '辩论' : '深度辩论' }}</span>
          <Plus :size="12" :stroke-width="4" class="ml-auto opacity-30" />
        </button>
        <button
          @click="newAdvisors"
          class="w-full flex items-center gap-3.5 px-4 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] transition-all duration-300 group active:scale-95"
          :class="route.path === '/advisors'
            ? 'bg-text-primary text-surface-1 shadow-xl shadow-black/20'
            : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'"
        >
          <Sparkles :size="16" stroke-width="3" :class="route.path === '/advisors' ? 'text-surface-1' : 'group-hover:text-amber-400 transition-colors'" />
          <span>AI 锦囊团</span>
        </button>
      </div>

      <!-- Divider with Label -->
      <div class="flex items-center gap-3 px-6 my-6 opacity-30">
        <div class="h-px flex-1 bg-text-tertiary"></div>
        <span class="text-[9px] font-black uppercase tracking-[0.3em] text-text-tertiary">History</span>
        <div class="h-px flex-1 bg-text-tertiary"></div>
      </div>

      <!-- Session history (The refined timeline) -->
      <div class="px-3 flex-1 overflow-y-auto no-scrollbar pb-4">
        <div v-if="sessionStore.sortedSessions.length" class="space-y-1.5">
          <button
            v-for="session in sessionStore.sortedSessions"
            :key="session.id"
            @click="switchTo(session)"
            class="w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl text-left transition-all duration-300 group relative"
            :class="isSessionActive(session)
              ? 'bg-text-primary text-surface-1 shadow-xl shadow-black/20'
              : 'text-text-secondary hover:bg-white/5 hover:text-text-primary'"
          >
            <div 
              class="w-1.5 h-1.5 rounded-full shrink-0" 
              :style="{ backgroundColor: session.type === 'chat' ? '#6366f1' : '#a855f7' }"
              :class="isSessionActive(session) ? 'opacity-0' : 'opacity-60'"
            ></div>
            <div class="flex-1 min-w-0">
              <div class="text-[11px] font-bold truncate tracking-tight">{{ session.title }}</div>
              <div class="text-[9px] mt-0.5 opacity-50 font-black uppercase tracking-widest flex items-center gap-2" :class="isSessionActive(session) ? 'text-surface-1' : ''">
                <span>{{ session.messageCount }} 轮 · {{ sessionStore.formatTime(session.updatedAt) }}</span>
              </div>
            </div>
            <button
              @click.stop="deleteSession(session.id, $event)"
              class="opacity-0 group-hover:opacity-100 w-8 h-8 rounded-full flex items-center justify-center transition-all shrink-0 -mr-1"
              :class="isSessionActive(session)
                ? 'hover:bg-red-500/20 text-current hover:text-red-500'
                : 'hover:bg-red-500/10 text-text-tertiary hover:text-red-500'"
              title="删除会话"
            >
              <Trash2 :size="14" stroke-width="3" />
            </button>
          </button>
        </div>
        <div v-else class="flex flex-col items-center justify-center py-12 opacity-20 grayscale">
          <Clock :size="32" :stroke-width="1" />
          <span class="text-[10px] font-black uppercase tracking-widest mt-4">No Records</span>
        </div>
      </div>

      <!-- Bottom Utilities Area -->
      <div class="px-3 py-3 bg-black/5 dark:bg-white/2 border-t border-white/5 space-y-1">
        <button
          @click="openCommandPalette"
          class="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-[13px] font-black transition-all duration-150 uppercase tracking-widest
                 text-text-secondary hover:bg-white/10 hover:text-text-primary group"
        >
          <Search :size="20" stroke-width="3" />
          <span>命令面板</span>
          <kbd class="ml-auto text-[12px] font-black px-1.5 py-0.5 rounded bg-white/5 border border-white/5">⌘K</kbd>
        </button>
        
        <div class="grid grid-cols-2 gap-1.5">
          <button
            @click="router.push('/models')"
            class="flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl transition-all duration-300 border border-transparent"
            :class="route.path === '/models' 
              ? 'bg-text-primary text-surface-1 shadow-lg' 
              : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'"
          >
            <Package :size="18" stroke-width="3" />
            <span class="text-[9px] font-black uppercase tracking-widest">模型管理</span>
          </button>
          <button
            @click="router.push('/settings')"
            class="flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl transition-all duration-300 border border-transparent"
            :class="route.path === '/settings' 
              ? 'bg-text-primary text-surface-1 shadow-lg' 
              : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-text-primary'"
          >
            <Settings :size="18" stroke-width="3" />
            <span class="text-[9px] font-black uppercase tracking-widest">偏好设置</span>
          </button>
        </div>

        <!-- System Theme & Platform Footer -->
        <div class="flex items-center justify-between px-2 pt-2 pb-1">
          <div class="flex items-center gap-1">
            <button @click="toggleTheme" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all">
              <Sun v-if="theme === 'dark'" :size="16" stroke-width="3" class="text-amber-400" />
              <Moon v-else :size="16" stroke-width="3" class="text-indigo-600" />
            </button>
            <button @click="emit('collapse')" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all" title="收起侧边栏">
              <PanelLeftClose :size="16" stroke-width="3" />
            </button>
          </div>
          <div class="h-1 w-1 rounded-full bg-text-tertiary opacity-20"></div>
          <button @click="emit('togglePlatform')" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all opacity-40 hover:opacity-100">
            <Smartphone :size="16" stroke-width="3" />
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

/* V3 Industrial Stroke Enforcement */
:deep(svg) {
  stroke-width: 3px !important;
}

:deep(.lucide-plus), :deep(.lucide-plus-circle) {
  stroke-width: 4px !important;
}


@keyframes v3-line-entry {
  from { width: 0; opacity: 0; }
  to { width: 100%; opacity: 0.4; }
}

.animate-v3-line-entry {
  animation: v3-line-entry 1s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes logo-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.logo-spin:hover {
  animation: logo-spin 10s linear infinite;
}

.animate-pulse-subtle {
  animation: pulse-subtle 3s ease-in-out infinite;
}

@keyframes pulse-subtle {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.85; transform: scale(0.96); }
}
</style>
