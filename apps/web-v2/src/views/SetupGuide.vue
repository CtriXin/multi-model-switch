<script setup lang="ts">
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useProviderStore } from '@/stores/provider'
import { useTheme } from '@/composables/useTheme'
import {
  Sparkles, MessageSquare, GitMerge, Users, Zap, Check, ChevronRight,
  Settings, Package, Shield, ExternalLink, Key, Menu, ArrowRight,
  ChevronLeft, Globe, Compass, Rocket, Info, ArrowLeft, Heart, Gift
} from 'lucide-vue-next'
import SetupProviderCard from '@/components/SetupProviderCard.vue'
import { CN_PROVIDERS, INTL_PROVIDERS } from '@/data/freeProviders'
import { getExperienceMode, setExperienceMode, type ExperienceMode } from '@/utils/experienceMode'

const appStore = useAppStore()
const providerStore = useProviderStore()
const router = useRouter()
const { theme } = useTheme()

const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isMobile = computed(() => platform.value === 'ios')

// Entry State Logic: 'none' | 'demo' | 'full'
const currentMode = ref<'none' | 'demo' | 'full'>('none')

const configuredCount = computed(() => 
  providerStore.providers.filter(p => providerStore.keyStatus[p.id]).length
)

// Friends Mode Guidance Logic
const usageCount = ref(Number(localStorage.getItem('mms-demo-usage-count') || 0))
const showFriendsNudge = computed(() => 
  currentMode.value === 'demo' && usageCount.value >= 3 && !appStore.showFriendsMode
)

function handleTileClick(path: string) {
  if (currentMode.value === 'demo') {
    usageCount.value += 1
    localStorage.setItem('mms-demo-usage-count', String(usageCount.value))
  }
  router.push(path)
}

function selectMode(mode: 'demo' | 'full') {
  currentMode.value = mode
  setExperienceMode(mode === 'demo' ? 'demo' : 'byok')
}

function resetMode() {
  currentMode.value = 'none'
}

// Provider Expansion State
const expandedProviderId = ref<string | null>(null)
function toggleProvider(id: string) {
  expandedProviderId.value = expandedProviderId.value === id ? null : id
}

const sortedCNProviders = computed(() => {
  const list = [...CN_PROVIDERS]
  const id = expandedProviderId.value
  if (!id || !CN_PROVIDERS.some(p => p.id === id)) return list
  const idx = list.findIndex(p => p.id === id)
  const [item] = list.splice(idx, 1)
  return [item, ...list]
})

const sortedIntlProviders = computed(() => {
  const list = [...INTL_PROVIDERS]
  const id = expandedProviderId.value
  if (!id || !INTL_PROVIDERS.some(p => p.id === id)) return list
  const idx = list.findIndex(p => p.id === id)
  const [item] = list.splice(idx, 1)
  return [item, ...list]
})

function openDrawer() {
  window.dispatchEvent(new CustomEvent('open-drawer'))
}

const coreTiles = [
  {
    id: 'chat',
    name: '多问几家',
    desc: '一个问题，多方对证',
    icon: MessageSquare,
    path: '/chat',
    color: 'from-blue-500 to-indigo-600',
    stats: () => `${appStore.selectedModelIds.length} 个已选`
  },
  {
    id: 'discuss',
    name: '对质一下',
    desc: '让它们互相挑刺',
    icon: GitMerge,
    path: '/discuss',
    color: 'from-purple-500 to-fuchsia-600',
    stats: () => '3 步流程'
  },
  {
    id: 'advisors',
    name: '找人商量',
    desc: '12个不同立场角色',
    icon: Users,
    path: '/advisors',
    color: 'from-emerald-500 to-teal-600',
    stats: () => '12 个角色'
  },
  {
    id: 'models',
    name: '接你自己的',
    desc: '连上你的 API Key',
    icon: Package,
    path: '/models',
    color: 'from-orange-400 to-rose-500',
    stats: () => `${appStore.models.length} 个可用`
  }
]

onMounted(() => {
  providerStore.refreshKeyStatus()
  const saved = getExperienceMode()
  if (saved) {
    currentMode.value = saved === 'demo' ? 'demo' : 'full'
  }
})
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">
    <!-- Group 1: Floating Capsule Header -->
    <div class="z-40 px-4 pt-2 sm:pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <!-- Left: Navigation -->
        <div class="flex items-center gap-2">
          <button v-if="currentMode !== 'none'" @click="resetMode" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors" title="返回模式选择">
            <ArrowLeft :size="18" stroke-width="3" />
          </button>
          <button v-else @click="openDrawer" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors sm:hidden">
            <Menu :size="18" stroke-width="3" />
          </button>
          <div class="hidden sm:flex items-center justify-center w-8 h-8 rounded-full bg-accent text-white shadow-lg shrink-0">
            <Sparkles :size="16" stroke-width="3" />
          </div>
        </div>

        <!-- Center: Branding -->
        <div class="flex items-center gap-2.5 min-w-0">
          <div class="sm:hidden flex items-center justify-center w-7 h-7 rounded-full bg-accent text-white shadow-lg shrink-0">
            <Sparkles :size="14" stroke-width="3" />
          </div>
          <div class="min-w-0 text-center sm:text-left">
            <h1 class="text-sm font-black text-text-primary truncate tracking-tight uppercase">SparkRing Hub</h1>
            <p class="text-[9px] text-text-tertiary font-black uppercase tracking-widest opacity-50 hidden sm:block">Cinematic Model Workbench</p>
          </div>
        </div>

        <!-- Right: Global Actions -->
        <div class="flex items-center gap-2">
          <button @click="router.push('/settings')" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all" title="系统设置">
            <Settings :size="18" stroke-width="3" />
          </button>
        </div>
      </header>
    </div>

    <div class="flex-1 overflow-y-auto custom-scrollbar">
      <div class="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-12">
        <!-- Hero Section -->
        <section class="text-center py-6 sm:py-10 space-y-6">
          <div class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-accent/10 border border-accent/20 text-accent text-[10px] font-black uppercase tracking-[0.2em] animate-fade-in">
            <Zap :size="12" fill="currentColor" /> SparkRing v0.3.5
          </div>
          <div class="space-y-3">
            <h2 class="text-4xl sm:text-6xl font-black text-text-primary tracking-tighter leading-tight">
              问一个AI心里没底？
            </h2>
            <p class="text-sm sm:text-base text-text-tertiary font-medium max-w-xl mx-auto opacity-70">
              同时问几个，答案放一起比。谁靠谱，一眼就知道。
            </p>
          </div>
        </section>

        <!-- Main Hub Content with Out-In Transition -->
        <Transition name="hub-phase" mode="out-in">
          <!-- Phase 1: Mode Selection -->
          <section v-if="currentMode === 'none'" key="selection" class="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
            <!-- Demo Mode Card -->
            <button @click="selectMode('demo')" 
              class="group relative flex flex-col p-8 rounded-[40px] glass-v3 border border-white/10 shadow-2xl transition-all duration-500 hover:-translate-y-2 hover:border-emerald-500/30 text-left overflow-hidden active:scale-95">
              <div class="absolute -right-4 -top-4 w-32 h-32 blur-[60px] bg-emerald-500/20 opacity-0 group-hover:opacity-100 transition-opacity"></div>
              <div class="flex items-start gap-6 mb-8">
                <div class="w-16 h-16 rounded-3xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 text-emerald-500 shadow-lg group-hover:scale-110 transition-transform duration-500">
                  <Sparkles :size="32" stroke-width="3" />
                </div>
                <div class="space-y-1">
                  <h3 class="text-2xl font-black text-text-primary uppercase tracking-tight">先试试</h3>
                  <p class="text-[10px] font-black text-emerald-500 uppercase tracking-widest opacity-60">体验模式 · Demo Mode</p>
                </div>
              </div>
              <p class="text-sm text-text-tertiary font-medium leading-relaxed mb-10 opacity-70">
                免登录、免配置，直接体验 Demo 模型模拟真实的对话和辩论流程。
              </p>
              <div class="mt-auto flex items-center justify-between">
                <span class="text-[11px] font-black text-emerald-500 uppercase tracking-widest border-b-2 border-emerald-500/20 pb-1">开始体验</span>
                <ChevronRight :size="20" class="text-emerald-500" stroke-width="3" />
              </div>
            </button>

            <!-- Full Mode Card -->
            <button @click="selectMode('full')" 
              class="group relative flex flex-col p-8 rounded-[40px] glass-v3 border border-white/10 shadow-2xl transition-all duration-500 hover:-translate-y-2 hover:border-accent/30 text-left overflow-hidden active:scale-95">
              <div class="absolute -right-4 -top-4 w-32 h-32 blur-[60px] bg-accent/20 opacity-0 group-hover:opacity-100 transition-opacity"></div>
              <div class="flex items-start gap-6 mb-8">
                <div class="w-16 h-16 rounded-3xl bg-accent/10 flex items-center justify-center border border-accent/20 text-accent shadow-lg group-hover:scale-110 transition-transform duration-500">
                  <Zap :size="32" stroke-width="3" />
                </div>
                <div class="space-y-1">
                  <h3 class="text-2xl font-black text-text-primary uppercase tracking-tight">完整功能</h3>
                  <p class="text-[10px] font-black text-accent uppercase tracking-widest opacity-60">生产力模式 · Pro Mode</p>
                </div>
              </div>
              <p class="text-sm text-text-tertiary font-medium leading-relaxed mb-10 opacity-70">
                使用真实 AI 模型（SparkRing 自动通道 + 您已配置的 API Key）。
              </p>
              <div class="mt-auto flex items-center justify-between">
                <span class="text-[11px] font-black text-accent uppercase tracking-widest border-b-2 border-accent/20 pb-1">立即进入</span>
                <ChevronRight :size="20" class="text-accent" stroke-width="3" />
              </div>
            </button>
          </section>

          <!-- Phase 2: Functional Tiles -->
          <div v-else key="hub" class="space-y-12">
            <!-- Hub Tiles (Launchpad) -->
            <section class="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
              <button v-for="tile in coreTiles" :key="tile.id" @click="handleTileClick(tile.path)"
                class="group relative flex flex-col p-5 sm:p-6 lg:p-8 rounded-[32px] lg:rounded-[40px] glass-v3 border border-white/10 shadow-2xl transition-all duration-500 lg:hover:-translate-y-2 lg:hover:border-white/20 active:scale-95 text-left overflow-hidden">
                <div class="hidden lg:block absolute -right-4 -top-4 w-32 h-32 blur-[60px] opacity-0 group-hover:opacity-20 transition-opacity" :class="`bg-gradient-to-br ${tile.color}`"></div>
                
                <div class="flex items-center justify-between mb-8">
                  <div class="w-12 h-12 rounded-2xl flex items-center justify-center text-white shadow-xl transition-transform duration-500 group-hover:scale-110" :class="`bg-gradient-to-br ${tile.color}`">
                    <component :is="tile.icon" :size="24" stroke-width="3" />
                  </div>
                  <ArrowRight :size="20" class="text-text-tertiary opacity-0 -translate-x-4 group-hover:opacity-100 group-hover:translate-x-0 transition-all" stroke-width="3" />
                </div>

                <div class="space-y-1.5 mb-auto">
                  <h3 class="text-lg sm:text-xl font-black text-text-primary uppercase tracking-tight">{{ tile.name }}</h3>
                  <p class="text-[11px] sm:text-xs text-text-tertiary font-medium leading-relaxed opacity-60">{{ tile.desc }}</p>
                </div>

                <div class="mt-6 pt-4 border-t border-white/5 flex items-center gap-2">
                  <div class="w-1.5 h-1.5 rounded-full bg-accent shadow-[0_0_8px_rgba(var(--color-accent),0.6)] animate-pulse"></div>
                  <span class="text-[9px] font-black uppercase tracking-widest text-text-tertiary opacity-40">{{ tile.stats() }}</span>
                </div>
              </button>
            </section>

            <!-- Mode Switcher (Compact) -->
            <div class="flex justify-center">
              <div class="inline-flex p-1 bg-black/20 dark:bg-white/5 rounded-full border border-white/5 shadow-inner">
                <button @click="currentMode = 'demo'" 
                  class="px-4 py-1.5 text-[9px] font-black uppercase tracking-widest rounded-full transition-all"
                  :class="currentMode === 'demo' ? 'bg-emerald-500 text-white shadow-lg' : 'text-text-tertiary hover:text-text-secondary'">
                  体验模式
                </button>
                <button @click="currentMode = 'full'" 
                  class="px-4 py-1.5 text-[9px] font-black uppercase tracking-widest rounded-full transition-all"
                  :class="currentMode === 'full' ? 'bg-accent text-white shadow-lg' : 'text-text-tertiary hover:text-text-secondary'">
                  全功能
                </button>
              </div>
            </div>

            <!-- Provider Lists (Only in Full Mode) -->
            <div v-if="currentMode === 'full'" class="space-y-16 pt-8 border-t border-white/5">
              <!-- CN Providers -->
              <section class="space-y-6">
                <div class="flex items-center gap-4 px-2">
                  <div class="w-10 h-10 rounded-2xl bg-red-500/10 flex items-center justify-center border border-red-500/20 text-red-500">
                    <Rocket :size="20" stroke-width="3" />
                  </div>
                  <div>
                    <h3 class="text-xl font-black text-text-primary uppercase tracking-tight">国产精选</h3>
                    <p class="text-[10px] text-text-tertiary font-black uppercase tracking-widest opacity-50">国内直连 · 响应极速 · 中文特化</p>
                  </div>
                </div>
                
                <TransitionGroup name="provider-list" tag="div" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  <SetupProviderCard 
                    v-for="p in sortedCNProviders" 
                    :key="p.id" 
                    :provider="p" 
                    :expanded="expandedProviderId === p.id"
                    :class="[
                      'transition-all duration-500',
                      expandedProviderId === p.id ? 'md:col-span-2 lg:col-span-3' : ''
                    ]"
                    @toggleExpand="toggleProvider(p.id)"
                  />
                </TransitionGroup>
              </section>

              <!-- INTL Providers -->
              <section class="space-y-6">
                <div class="flex items-center gap-4 px-2">
                  <div class="w-10 h-10 rounded-2xl bg-blue-500/10 flex items-center justify-center border border-blue-500/20 text-blue-500">
                    <Globe :size="20" stroke-width="3" />
                  </div>
                  <div>
                    <h3 class="text-xl font-black text-text-primary uppercase tracking-tight">全球大模型</h3>
                    <p class="text-[10px] text-text-tertiary font-black uppercase tracking-widest opacity-50">最强智力 · 极速推理 · 免费额度</p>
                  </div>
                </div>
                
                <TransitionGroup name="provider-list" tag="div" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  <SetupProviderCard 
                    v-for="p in sortedIntlProviders" 
                    :key="p.id" 
                    :provider="p" 
                    :expanded="expandedProviderId === p.id"
                    :class="[
                      'transition-all duration-500',
                      expandedProviderId === p.id ? 'md:col-span-2 lg:col-span-3' : ''
                    ]"
                    @toggleExpand="toggleProvider(p.id)"
                  />
                </TransitionGroup>
              </section>
            </div>
          </div>
        </Transition>

        <!-- Friends Mode Guidance Nudge -->
        <Transition name="fade-slide">
          <div v-if="showFriendsNudge" 
            class="max-w-4xl mx-auto p-8 rounded-[40px] bg-gradient-to-br from-purple-600/10 to-pink-600/10 border border-purple-500/20 shadow-2xl flex flex-col sm:flex-row items-center gap-8 relative overflow-hidden group">
            <div class="absolute -right-8 -bottom-8 w-48 h-48 bg-purple-500/10 blur-[60px] rounded-full group-hover:scale-150 transition-transform duration-1000"></div>
            <div class="w-20 h-20 rounded-[28px] bg-purple-500/20 flex items-center justify-center border border-purple-500/30 text-purple-500 shadow-xl shrink-0 group-hover:rotate-12 transition-transform duration-500">
              <Gift :size="40" stroke-width="3" />
            </div>
            <div class="flex-1 text-center sm:text-left space-y-3 relative z-10">
              <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500 text-white text-[9px] font-black uppercase tracking-widest">
                <Heart :size="10" fill="currentColor" /> 发现彩蛋宝藏
              </div>
              <h4 class="text-2xl font-black text-text-primary uppercase tracking-tight italic">获得千万级 Token 奖励？</h4>
              <p class="text-sm text-text-tertiary font-medium opacity-80 leading-relaxed">
                在设置中开启「好友模式」，解锁专属邀请码。每位新朋友加入，你们都将获得巨额 Tokens 奖励！
              </p>
            </div>
            <button @click="router.push('/settings')" 
              class="px-8 py-4 rounded-2xl bg-purple-500 text-white text-xs font-black uppercase tracking-[0.2em] shadow-xl shadow-purple-500/30 hover:scale-105 active:scale-95 transition-all relative z-10 whitespace-nowrap">
              立即去开启
            </button>
          </div>
        </Transition>

        <!-- Footer -->
        <footer class="pt-10 pb-20 text-center space-y-6">
          <button @click="router.push('/settings')" 
            class="inline-flex items-center gap-2 text-[11px] font-black text-accent uppercase tracking-widest hover:opacity-80 transition-opacity">
            已有 API Key？去设置 →
          </button>
          <div class="h-px w-20 bg-white/10 mx-auto"></div>
          <div class="flex flex-col items-center gap-1 opacity-30">
            <p class="text-[10px] font-black text-text-tertiary uppercase tracking-[0.3em]">SparkRing Kinetic Industries</p>
            <p class="text-[8px] font-black text-text-tertiary uppercase tracking-widest">Designed for the Next Era of Intelligence</p>
          </div>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.provider-list-move {
  transition: transform 0.6s cubic-bezier(0.32, 0.72, 0, 1);
}

/* New Snappy Phase Transition */
.hub-phase-enter-active, .hub-phase-leave-active {
  transition: all 0.4s cubic-bezier(0.32, 0.72, 0, 1);
}
.hub-phase-enter-from { opacity: 0; transform: translateY(20px) scale(0.98); }
.hub-phase-leave-to { opacity: 0; transform: translateY(-10px) scale(1.02); }

.animate-fade-in {
  animation: fadeIn 0.8s cubic-bezier(0.32, 0.72, 0, 1);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>