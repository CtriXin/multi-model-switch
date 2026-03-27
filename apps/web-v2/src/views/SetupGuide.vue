<script setup lang="ts">
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useProviderStore } from '@/stores/provider'
import { useTheme } from '@/composables/useTheme'
import {
  MessageSquare, GitMerge, Users, Zap, Check, ChevronRight,
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

const isDarkMode = computed(() => theme.value === 'dark')
// iOS Header 镜像逻辑：白天用白色 Logo，黑夜用黑色 Logo
const logoSrc = computed(() => isDarkMode.value ? '/logos/logo-v5-dark.png' : '/logos/logo-v5-light.png')
const logoBg = computed(() => isDarkMode.value ? 'bg-black/40 border-black/20' : 'bg-white/80 border-white/40')

const isSmallScreen = inject<import('vue').Ref<boolean>>('isSmallScreen', ref(false))

function resolveInitialMode(): 'none' | 'demo' | 'full' {
  const savedMode = getExperienceMode()
  if (savedMode === 'demo') return 'demo'
  if (savedMode === 'byok') return 'full'
  return 'none'
}

const currentMode = ref<'none' | 'demo' | 'full'>(resolveInitialMode())

onMounted(() => {
  providerStore.refreshKeyStatus()
})

function selectMode(mode: 'demo' | 'full') {
  currentMode.value = mode
  setExperienceMode(mode === 'demo' ? 'demo' : 'byok')
}

function openDrawer() { window.dispatchEvent(new CustomEvent('open-drawer')) }

const coreTiles = [
  { id: 'chat', name: '多问几家', desc: '货比三家不吃亏', icon: MessageSquare, path: '/chat', color: 'from-blue-500 to-indigo-600', stats: () => `${appStore.selectedModelIds.length} 选` },
  { id: 'discuss', name: '深度对质', desc: '让 AI 们吵一架', icon: GitMerge, path: '/discuss', color: 'from-purple-500 to-fuchsia-600', stats: () => '3 步' },
  { id: 'advisors', name: '锦囊参谋', desc: '你的私人董事会', icon: Users, path: '/advisors', color: 'from-emerald-500 to-teal-600', stats: () => '12 人' },
  { id: 'lab', name: '创意实验室', desc: '玩转 AI 的新方式', icon: FlaskConical, path: '/lab', color: 'from-orange-400 to-rose-500', stats: () => '5 实验' }
]
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">

    <!-- Unified V3 Capsule Header -->
    <div class="z-40 px-4 pt-4 pb-2 shrink-0">
      <header
        class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-3">
          <button v-if="isSmallScreen" @click="openDrawer"
            class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors">
            <Menu :size="18" stroke-width="3.5" />
          </button>
          <div v-if="isSmallScreen"
            class="flex items-center gap-3 group/logo cursor-pointer select-none"
            @click="router.push('/')">
            <div
              :class="[logoBg, 'w-10 h-10 sm:w-11 sm:h-11 rounded-[10px] flex items-center justify-center border shrink-0 overflow-hidden transition-all duration-300 group-hover/logo:scale-105 shadow-sm']">
              <img :src="logoSrc" alt="SparkRing"
                class="w-10 h-10 sm:w-11 sm:h-11 object-contain" />
            </div>
            <div class="flex flex-col">
              <div
                class="flex items-center text-[14px] sm:text-[15px] font-black uppercase leading-tight tracking-[0.15em] select-none">
                <span
                  :class="[isDarkMode ? 'from-indigo-300 via-blue-400 to-purple-400' : 'from-indigo-950 via-indigo-800 to-purple-700', 'bg-gradient-to-r bg-clip-text text-transparent']">Spark</span>
                <span
                  class="bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">Ring</span>
              </div>
              <div
                class="flex w-full justify-between pr-1 -mt-0.5 text-[10px] sm:text-[11px] font-bold uppercase text-text-tertiary opacity-70">
                <span>思</span><span>路</span><span>集</span>
              </div>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button @click="router.push('/settings')"
            class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all">
            <Settings :size="18" stroke-width="3.5" />
          </button>
        </div>
      </header>
    </div>

    <div class="flex-1 overflow-y-auto custom-scrollbar">
      <div class="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-10">

        <!-- Selection Phase -->
        <section v-if="currentMode === 'none'" class="py-6 sm:py-10 space-y-8 sm:space-y-10">
          <div class="text-center space-y-5 px-2">
            <h2
              class="text-[36px] sm:text-6xl font-black text-text-primary tracking-tighter leading-[1.1]">
              不再纠结<span class="text-accent">该信哪个 AI</span>
            </h2>
            <p
              class="text-text-tertiary text-base sm:text-lg max-w-md mx-auto leading-relaxed opacity-80 font-medium">
              把同一个问题丢给多个顶尖模型，<br v-if="isSmallScreen" />让它们 PK，你坐收渔翁之利。
            </p>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-5 sm:gap-6 max-w-4xl mx-auto">
            <!-- Mode: Demo -->
            <button @click="selectMode('demo')"
              class="group p-7 sm:p-8 rounded-[32px] sm:rounded-[40px] glass-v3 border border-white/10 hover:border-accent/30 transition-all duration-500 text-left overflow-hidden active:scale-[0.98] shadow-2xl relative">
              <div
                class="absolute -right-4 -top-4 w-24 h-24 bg-accent/5 rounded-full blur-3xl group-hover:bg-accent/10 transition-colors">
              </div>

              <div
                class="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center mb-6 shadow-xl shadow-indigo-500/20 relative z-10">
                <Rocket :size="28" stroke-width="3" />
              </div>

              <h3 class="text-2xl font-black text-text-primary mb-2 relative z-10">先试试看</h3>
              <p
                class="text-[13px] text-text-tertiary leading-relaxed mb-8 opacity-70 font-medium relative z-10">
                不用填 Key，直接体验全站功能。<br />适合快速上手感受 AI 对质。
              </p>

              <div
                class="flex items-center bg-accent/10 w-fit px-4 py-2 rounded-full text-accent text-[10px] font-black uppercase tracking-[0.2em] gap-2 group-hover:bg-accent group-hover:text-white transition-all">
                <span>立刻开始</span>
                <ArrowRight :size="14" stroke-width="4" />
              </div>
            </button>

            <!-- Mode: Full -->
            <button @click="selectMode('full')"
              class="group p-7 sm:p-8 rounded-[32px] sm:rounded-[40px] glass-v3 border border-white/10 hover:border-purple-500/30 transition-all duration-500 text-left overflow-hidden active:scale-[0.98] shadow-2xl relative">
              <div
                class="absolute -right-4 -top-4 w-24 h-24 bg-purple-500/5 rounded-full blur-3xl group-hover:bg-purple-500/10 transition-colors">
              </div>

              <div
                class="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-500 to-fuchsia-600 text-white flex items-center justify-center mb-6 shadow-xl shadow-purple-500/20 relative z-10">
                <Key :size="28" stroke-width="3" />
              </div>

              <h3 class="text-2xl font-black text-text-primary mb-2 relative z-10">连接 API</h3>
              <p
                class="text-[13px] text-text-tertiary leading-relaxed mb-8 opacity-70 font-medium relative z-10">
                接入你自己的 API 秘钥，解锁能力。<br />数据本地存储，隐私安全。
              </p>

              <div
                class="flex items-center bg-purple-500/10 w-fit px-4 py-2 rounded-full text-purple-500 text-[10px] font-black uppercase tracking-[0.2em] gap-2 group-hover:bg-purple-500 group-hover:text-white transition-all">
                <span>配置秘钥</span>
                <ArrowRight :size="14" stroke-width="4" />
              </div>
            </button>
          </div>
        </section>

        <!-- Core Dashboard (Refined for iOS) -->
        <section v-else class="space-y-6 sm:space-y-8 animate-in fade-in duration-700">
          <div class="text-center space-y-3">
            <div
              class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-accent/10 border border-accent/20 text-accent text-[9px] font-black uppercase tracking-[0.2em]">
              SparkRing v0.5.1</div>
            <h2
              class="text-3xl sm:text-5xl font-black text-text-primary tracking-tighter uppercase leading-none">
              核心功能</h2>
          </div>

          <!-- Grid Layout optimized for narrow screens -->
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3.5 sm:gap-6">
            <button v-for="tile in coreTiles" :key="tile.id" @click="router.push(tile.path)"
              class="group relative flex flex-col p-4 sm:p-8 rounded-[24px] sm:rounded-[36px] glass-v3 border border-white/5 hover:border-accent/30 transition-all duration-500 text-left overflow-hidden active:scale-95 shadow-xl sm:shadow-2xl">
              <div class="flex items-start justify-between mb-5 sm:mb-8">
                <div
                  class="w-10 h-10 sm:w-12 sm:h-12 rounded-[14px] sm:rounded-2xl flex items-center justify-center text-white shadow-xl"
                  :class="`bg-gradient-to-br ${tile.color}`">
                  <component :is="tile.icon" :size="20" stroke-width="3" class="sm:hidden" />
                  <component :is="tile.icon" :size="24" stroke-width="3" class="hidden sm:block" />
                </div>
                <span
                  class="px-1.5 py-0.5 rounded-md bg-white/5 text-[7px] sm:text-[8px] font-black text-text-tertiary uppercase tracking-widest">{{ tile.stats() }}</span>
              </div>
              <h3
                class="text-[13px] sm:text-xl font-black text-text-primary tracking-tight uppercase group-hover:text-accent transition-colors leading-tight">
                {{ tile.name }}</h3>
              <p
                class="text-[9px] sm:text-[11px] text-text-tertiary font-medium leading-tight opacity-60 mt-1.5">
                {{ tile.desc }}</p>
              <div class="mt-5 sm:mt-8 flex justify-end">
                <div
                  class="w-6 h-6 sm:w-8 sm:h-8 rounded-full bg-white/5 flex items-center justify-center group-hover:bg-accent group-hover:text-white transition-all">
                  <ChevronRight :size="14" stroke-width="4" />
                </div>
              </div>
            </button>
          </div>

          <div
            class="p-4 sm:p-5 rounded-[24px] sm:rounded-[28px] bg-white/5 border border-white/5 flex items-start gap-3 max-w-xl mx-auto opacity-60">
            <Info :size="16" stroke-width="3" class="text-accent shrink-0" />
            <p class="text-[10px] text-text-tertiary leading-relaxed">进入「创意实验室」探索更多玩法。切换模式请前往设置。</p>
          </div>
        </section>

      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(svg) {
  stroke-width: 3.5px !important;
}
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
</style>
