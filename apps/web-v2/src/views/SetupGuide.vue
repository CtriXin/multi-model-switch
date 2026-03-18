<script setup lang="ts">
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useProviderStore } from '@/stores/provider'
import { useTheme } from '@/composables/useTheme'
import { 
  Sparkles, MessageSquare, GitMerge, Users, Zap, Check, ChevronRight, 
  Settings, Package, Shield, ExternalLink, Key, Menu, ArrowRight
} from 'lucide-vue-next'

const appStore = useAppStore()
const providerStore = useProviderStore()
const router = useRouter()
const { theme } = useTheme()

const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isMobile = computed(() => platform.value === 'ios')

const configuredCount = computed(() => 
  providerStore.providers.filter(p => providerStore.keyStatus[p.id]).length
)

function openDrawer() {
  window.dispatchEvent(new CustomEvent('open-drawer'))
}

const showFullGuide = ref(false)

const coreTiles = [
  { 
    id: 'chat', 
    name: '并行对话', 
    desc: '多模型同屏 PK，打破单一局限', 
    icon: MessageSquare, 
    path: '/chat',
    color: 'from-blue-500 to-indigo-600',
    stats: () => `${appStore.selectedModelIds.length} 基因激活`
  },
  { 
    id: 'discuss', 
    name: '深度辩论', 
    desc: '三阶段逻辑审查，让结论更靠谱', 
    icon: GitMerge, 
    path: '/discuss',
    color: 'from-purple-500 to-fuchsia-600',
    stats: () => '三阶段逻辑引擎'
  },
  { 
    id: 'advisors', 
    name: 'AI 锦囊团', 
    desc: '12+ 角色预设，多视角决策系统', 
    icon: Users, 
    path: '/advisors',
    color: 'from-emerald-500 to-teal-600',
    stats: () => '12 预设专家'
  },
  { 
    id: 'models', 
    name: '基因管理', 
    desc: '工业级 Registry，筛选最强战力', 
    icon: Package, 
    path: '/models',
    color: 'from-orange-400 to-rose-500',
    stats: () => `${appStore.models.length} 可选模型`
  }
]

onMounted(() => {
  providerStore.refreshKeyStatus()
})
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">
    <!-- V3 Standard Floating Header -->
    <div class="z-40 px-4 pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-2.5">
          <div class="flex items-center justify-center w-8 h-8 rounded-full bg-accent text-white shadow-lg shrink-0">
            <Sparkles :size="16" stroke-width="3" />
          </div>
          <div class="min-w-0">
            <h1 class="text-sm font-black text-text-primary truncate tracking-tight uppercase">SparkRing Hub</h1>
            <p class="text-[9px] text-text-tertiary font-black uppercase tracking-widest opacity-50 hidden sm:block">Cinematic Model Workbench</p>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button @click="router.push('/settings')" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all">
            <Settings :size="18" stroke-width="3" />
          </button>
          <button @click="openDrawer" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors sm:hidden">
            <Menu :size="18" stroke-width="3" />
          </button>
        </div>
      </header>
    </div>

    <div class="flex-1 overflow-y-auto custom-scrollbar">
      <div class="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-10">
        <!-- Hero Section -->
        <section class="text-center py-6 sm:py-12 space-y-4">
          <div class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-accent/10 border border-accent/20 text-accent text-[10px] font-black uppercase tracking-[0.2em] animate-fade-in">
            <Zap :size="12" fill="currentColor" /> Welcome to V3 Cinema
          </div>
          <h2 class="text-4xl sm:text-6xl font-black text-text-primary tracking-tighter uppercase italic leading-[0.9] sm:leading-[0.9]">
            The Ultimate <br/> 
            <span class="text-transparent bg-clip-text bg-gradient-to-r from-accent to-purple-500">Multi-Model</span> Engine
          </h2>
          <p class="text-sm sm:text-base text-text-tertiary font-medium max-w-xl mx-auto opacity-60">
            集成全球顶级 AI 基因，打破单一对话局限。并行分析、深度辩论、专家决策，一切皆在掌握。
          </p>
        </section>

        <!-- Feature Grid (The Launchpad) -->
        <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
          <button v-for="tile in coreTiles" :key="tile.id" @click="router.push(tile.path)"
            class="group relative flex flex-col p-6 rounded-[40px] glass-v3 border border-white/10 shadow-2xl transition-all duration-500 hover:-translate-y-2 hover:border-white/20 active:scale-95 text-left overflow-hidden">
            <!-- Background Glow -->
            <div class="absolute -right-4 -top-4 w-32 h-32 blur-[60px] opacity-0 group-hover:opacity-20 transition-opacity" :class="`bg-gradient-to-br ${tile.color}`"></div>
            
            <div class="flex items-center justify-between mb-8">
              <div class="w-12 h-12 rounded-2xl flex items-center justify-center text-white shadow-xl" :class="`bg-gradient-to-br ${tile.color}`">
                <component :is="tile.icon" :size="24" stroke-width="3" />
              </div>
              <ArrowRight :size="20" class="text-text-tertiary opacity-0 -translate-x-4 group-hover:opacity-100 group-hover:translate-x-0 transition-all" stroke-width="3" />
            </div>
            
            <div class="space-y-1">
              <h3 class="text-xl font-black text-text-primary uppercase tracking-tight">{{ tile.name }}</h3>
              <p class="text-xs text-text-tertiary font-medium leading-relaxed">{{ tile.desc }}</p>
            </div>
            
            <div class="mt-6 pt-4 border-t border-white/5 flex items-center gap-2">
              <div class="w-1 h-1 rounded-full animate-pulse" :class="tile.id === 'chat' && configuredCount === 0 ? 'bg-red-500' : 'bg-accent'"></div>
              <span class="text-[9px] font-black uppercase tracking-widest text-text-tertiary opacity-50">{{ tile.stats() }}</span>
            </div>
          </button>
        </section>

        <!-- Quick Setup Integration (Collapsible) -->
        <section class="glass-v3 rounded-[40px] border border-white/10 overflow-hidden shadow-2xl">
          <button @click="showFullGuide = !showFullGuide" 
            class="w-full flex items-center justify-between p-8 text-left hover:bg-white/2 transition-colors group">
            <div class="flex items-center gap-6">
              <div class="w-14 h-14 rounded-3xl bg-black/[0.03] dark:bg-white/5 flex items-center justify-center border border-black/5 dark:border-white/10 shadow-inner">
                <Key :size="28" class="text-accent" stroke-width="3" />
              </div>
              <div>
                <h3 class="text-xl font-black text-text-primary uppercase tracking-tight">API 快速配通导引</h3>
                <p class="text-sm text-text-tertiary font-medium opacity-60">新手必看：如何快速获得 10+ 免费模型基因</p>
              </div>
            </div>
            <div class="flex items-center gap-4">
              <div v-if="configuredCount > 0" class="hidden sm:flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 text-[10px] font-black uppercase tracking-widest">
                <Check :size="12" stroke-width="4" /> {{ configuredCount }} 厂商已就绪
              </div>
              <div class="p-3 rounded-full bg-white/5 group-hover:bg-accent group-hover:text-white transition-all">
                <ChevronRight :size="20" stroke-width="3" :class="showFullGuide ? 'rotate-90' : ''" class="transition-transform" />
              </div>
            </div>
          </button>

          <Transition name="expand">
            <div v-if="showFullGuide" class="p-8 pt-0 border-t border-white/5 bg-black/[0.01] space-y-8">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mt-8">
                <div class="space-y-4">
                  <div class="flex items-center gap-2 text-[10px] font-black text-accent uppercase tracking-widest">Step 01</div>
                  <h4 class="text-lg font-black text-text-primary uppercase tracking-tight">连接模拟基因 (Demo Mode)</h4>
                  <p class="text-sm text-text-secondary leading-relaxed">
                    无需任何 API Key，立即在侧边栏点击“对话模式”即可体验完整的交互流程。
                  </p>
                </div>
                <div class="space-y-4">
                  <div class="flex items-center gap-2 text-[10px] font-black text-purple-500 uppercase tracking-widest">Step 02</div>
                  <h4 class="text-lg font-black text-text-primary uppercase tracking-tight">绑定正式基因 (BYOK)</h4>
                  <p class="text-sm text-text-secondary leading-relaxed">
                    前往 <button @click="router.push('/settings')" class="text-accent underline font-bold underline-offset-4">设置中心</button> 填入你的厂商密钥。推荐从 <strong>SiliconFlow (硅基流动)</strong> 开始，注册即送海量免费额度。
                  </p>
                </div>
              </div>
              
              <div class="p-6 rounded-3xl bg-accent/5 border border-accent/10 flex items-start gap-4">
                <Shield :size="20" class="text-accent shrink-0" stroke-width="3" />
                <div class="space-y-1">
                  <p class="text-xs font-black text-text-primary uppercase tracking-tight">隐私安全承诺</p>
                  <p class="text-[11px] text-text-tertiary leading-relaxed">SparkRing 采用全本地端存储，您的 API 密钥永远不会上传至我们的服务器。</p>
                </div>
              </div>
            </div>
          </Transition>
        </section>

        <!-- Footer Footer -->
        <footer class="pt-10 pb-20 text-center space-y-4">
          <div class="h-px w-20 bg-white/10 mx-auto"></div>
          <p class="text-[10px] font-black text-text-tertiary uppercase tracking-[0.3em] opacity-30">© 2026 SparkRing Kinetic Industries</p>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.expand-enter-active, .expand-leave-active { transition: all 0.5s cubic-bezier(0.32, 0.72, 0, 1); max-height: 800px; overflow: hidden; }
.expand-enter-from, .expand-leave-to { max-height: 0; opacity: 0; transform: translateY(-10px); }

.animate-fade-in { animation: fadeIn 1s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>
