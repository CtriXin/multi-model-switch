<script setup lang="ts">
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useProviderStore } from '@/stores/provider'
import { useTheme } from '@/composables/useTheme'
import {
  Sparkles, MessageSquare, GitMerge, Users, Zap, Check, ChevronRight,
  Settings, Package, Shield, ExternalLink, Key, Menu, ArrowRight,
  ChevronLeft, Globe, Compass, Rocket, Info, ArrowLeft, Heart, Gift,
  FlaskConical
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

const currentMode = ref<'none' | 'demo' | 'full'>('none')

onMounted(() => {
  const savedMode = getExperienceMode()
  if (savedMode === 'demo') currentMode.value = 'demo'
  else if (savedMode === 'byok') currentMode.value = 'full'
  providerStore.refreshKeyStatus()
})

function selectMode(mode: 'demo' | 'full') {
  currentMode.value = mode
  setExperienceMode(mode === 'demo' ? 'demo' : 'byok')
}

function openDrawer() { window.dispatchEvent(new CustomEvent('open-drawer')) }

const coreTiles = [
  { id: 'chat', name: '多问几家', desc: '一问多证', icon: MessageSquare, path: '/chat', color: 'from-blue-500 to-indigo-600', stats: () => `${appStore.selectedModelIds.length} 选` },
  { id: 'discuss', name: '对质一下', desc: '互相挑刺', icon: GitMerge, path: '/discuss', color: 'from-purple-500 to-fuchsia-600', stats: () => '3 步' },
  { id: 'advisors', name: '找人商量', desc: '12 角色', icon: Users, path: '/advisors', color: 'from-emerald-500 to-teal-600', stats: () => '12 人' },
  { id: 'lab', name: '互动实验室', desc: '创意玩法', icon: FlaskConical, path: '/lab', color: 'from-orange-400 to-rose-500', stats: () => '5 实验' }
]
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">
    
    <!-- Unified V3 Capsule Header -->
    <div class="z-40 px-4 pt-2 sm:pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-2">
          <button @click="openDrawer" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors"><Menu :size="18" stroke-width="3.5" /></button>
          <div class="hidden sm:flex items-center justify-center w-8 h-8 rounded-full bg-accent text-white shadow-lg shrink-0"><Sparkles :size="16" stroke-width="3.5" /></div>
        </div>
        <div class="flex items-center gap-2.5 min-w-0">
          <div class="sm:hidden flex items-center justify-center w-7 h-7 rounded-full bg-accent text-white shadow-lg shrink-0"><Sparkles :size="14" stroke-width="3.5" /></div>
          <h1 class="text-sm font-black text-text-primary truncate uppercase">SparkRing Hub</h1>
        </div>
        <div class="flex items-center gap-2">
          <button @click="router.push('/settings')" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all"><Settings :size="18" stroke-width="3.5" /></button>
        </div>
      </header>
    </div>

    <div class="flex-1 overflow-y-auto custom-scrollbar">
      <div class="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-10">
        
        <transition name="fade-slide" mode="out-in">
          <!-- Selection Phase -->
          <section v-if="currentMode === 'none'" class="py-10 space-y-10">
            <div class="text-center space-y-4">
              <h2 class="text-4xl sm:text-6xl font-black text-text-primary tracking-tighter">开启你的<span class="text-accent">AI 实验室</span></h2>
              <p class="text-text-tertiary text-sm max-w-md mx-auto leading-relaxed">连接大模型，开启充满电影感的协作流。</p>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
              <button @click="selectMode('demo')" class="group p-8 rounded-[40px] glass-v3 border border-white/5 hover:border-accent/30 transition-all duration-500 text-left overflow-hidden active:scale-95 shadow-2xl">
                <div class="w-14 h-14 rounded-2xl bg-accent text-white flex items-center justify-center mb-8 shadow-xl"><Rocket :size="28" stroke-width="3.5" /></div>
                <h3 class="text-2xl font-black text-text-primary mb-3">先试试看</h3>
                <p class="text-xs text-text-tertiary leading-relaxed mb-8 opacity-70">无需配置，直接体验精选模型。适合快速探索。</p>
                <div class="flex items-center text-accent text-[10px] font-black uppercase tracking-widest gap-2"><span>立刻开始</span><ArrowRight :size="14" stroke-width="4" /></div>
              </button>
              <button @click="selectMode('full')" class="group p-8 rounded-[40px] glass-v3 border border-white/5 hover:border-purple-500/30 transition-all duration-500 text-left overflow-hidden active:scale-95 shadow-2xl">
                <div class="w-14 h-14 rounded-2xl bg-purple-500 text-white flex items-center justify-center mb-8 shadow-xl"><Key :size="28" stroke-width="3.5" /></div>
                <h3 class="text-2xl font-black text-text-primary mb-3">连接 API</h3>
                <p class="text-xs text-text-tertiary leading-relaxed mb-8 opacity-70">支持国内外主流模型。释放完整生产力。</p>
                <div class="flex items-center text-purple-400 text-[10px] font-black uppercase tracking-widest gap-2"><span>配置秘钥</span><ArrowRight :size="14" stroke-width="4" /></div>
              </button>
            </div>
          </section>

          <!-- Core Dashboard (Refined for iOS) -->
          <section v-else class="space-y-8 animate-in fade-in duration-700">
            <div class="text-center space-y-2">
              <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 border border-accent/20 text-accent text-[9px] font-black uppercase tracking-widest">CONTROL CENTER</div>
              <h2 class="text-3xl sm:text-5xl font-black text-text-primary tracking-tighter uppercase leading-none">核心任务中枢</h2>
            </div>

            <!-- Grid Layout optimized for narrow screens -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6">
              <button v-for="tile in coreTiles" :key="tile.id" @click="router.push(tile.path)" class="group relative flex flex-col p-5 sm:p-8 rounded-[28px] sm:rounded-[36px] glass-v3 border border-white/5 hover:border-accent/30 transition-all duration-500 text-left overflow-hidden active:scale-95 shadow-xl sm:shadow-2xl">
                <div class="flex items-start justify-between mb-6 sm:mb-8">
                  <div class="w-10 h-10 sm:w-12 sm:h-12 rounded-xl sm:rounded-2xl flex items-center justify-center text-white shadow-xl" :class="`bg-gradient-to-br ${tile.color}`">
                    <component :is="tile.icon" :size="20" stroke-width="3.5" class="sm:hidden" />
                    <component :is="tile.icon" :size="24" stroke-width="3.5" class="hidden sm:block" />
                  </div>
                  <span class="px-1.5 py-0.5 rounded-md bg-white/5 text-[7px] sm:text-[8px] font-black text-text-tertiary uppercase tracking-widest">{{ tile.stats() }}</span>
                </div>
                <h3 class="text-sm sm:text-xl font-black text-text-primary tracking-tight uppercase group-hover:text-accent transition-colors">{{ tile.name }}</h3>
                <p class="text-[9px] sm:text-[11px] text-text-tertiary font-medium leading-tight opacity-60 mt-1">{{ tile.desc }}</p>
                <div class="mt-6 sm:mt-8 flex justify-end">
                  <div class="w-6 h-6 sm:w-8 sm:h-8 rounded-full bg-white/5 flex items-center justify-center group-hover:bg-accent group-hover:text-white transition-all"><ChevronRight :size="14" stroke-width="4" /></div>
                </div>
              </button>
            </div>

            <div class="p-5 rounded-[28px] bg-white/5 border border-white/5 flex items-start gap-3 max-w-xl mx-auto opacity-60">
              <Info :size="16" stroke-width="3.5" class="text-accent shrink-0 mt-0.5" />
              <p class="text-[10px] text-text-tertiary leading-relaxed">进入“互动实验室”探索全新模式。切换模式请前往设置。</p>
            </div>
          </section>
        </transition>

      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(svg) { stroke-width: 3.5px !important; }
.fade-slide-enter-active, .fade-slide-leave-active { transition: all 0.4s cubic-bezier(0.32, 0.72, 0, 1); }
.fade-slide-enter-from { opacity: 0; transform: translateY(10px); }
.fade-slide-leave-to { opacity: 0; transform: translateY(-10px); }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
</style>