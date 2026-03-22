<script setup lang="ts">
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { 
  FlaskConical, Flame, Soup, Sparkles, Clapperboard, 
  Shield, ChevronRight, ArrowLeft, Zap, Info, Menu
} from 'lucide-vue-next'

const router = useRouter()
const isSmallScreen = inject<import('vue').Ref<boolean>>('isSmallScreen', ref(false))

const labFeatures = [
  {
    id: 'challenge',
    name: '每日论战',
    desc: '今日话题对战，锻炼批判思维',
    icon: Flame,
    path: '/challenge',
    color: 'from-orange-500 to-red-600',
    tag: '竞技'
  },
  {
    id: 'turtle-soup',
    name: '海龟汤',
    desc: '离奇案件卷宗，通过提问解密',
    icon: Soup,
    path: '/turtle-soup',
    color: 'from-emerald-500 to-teal-600',
    tag: '推理'
  },
  {
    id: 'story-lite',
    name: '假如模拟器',
    desc: '设定一个场景，看 AI 如何演绎',
    icon: Sparkles,
    path: '/story-lite',
    color: 'from-blue-500 to-indigo-600',
    tag: '创意'
  },
  {
    id: 'story-live',
    name: '剧情共演',
    desc: '实时接戏，与导演组共同推进',
    icon: Clapperboard,
    path: '/story-live',
    color: 'from-purple-500 to-fuchsia-600',
    tag: '互动'
  },
  {
    id: 'multi-life',
    name: '多重人生',
    desc: '三个角色各执一词，还原真相',
    icon: Shield,
    path: '/multi-life',
    color: 'from-cyan-500 to-blue-600',
    tag: '叙事'
  }
]

function handleEnter(path: string) {
  router.push(path)
}

function goHome() {
  router.push('/')
}
</script>

<template>
  <!-- Main Container: Unified background system -->
  <div class="flex flex-col h-full overflow-hidden bg-surface-0 transition-colors duration-500">
    
    <!-- Unified V3 Capsule Header -->
    <div class="z-40 px-4 pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-black/5 dark:border-white/10 bg-white/80 dark:bg-white/[0.05]">
        <div class="flex items-center gap-2">
          <button @click="goHome" class="p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/10 text-text-secondary transition-colors" title="返回首页">
            <ArrowLeft :size="18" stroke-width="3.5" />
          </button>
          <div class="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center shadow-lg shadow-accent/10">
            <FlaskConical :size="16" stroke-width="3.5" class="text-accent" />
          </div>
          <h1 class="text-sm font-black text-text-primary truncate uppercase tracking-widest">互动实验室</h1>
        </div>

        <div class="flex items-center gap-2">
          <div class="hidden sm:flex items-center gap-2 px-3 py-1 rounded-full bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/10">
            <Zap :size="10" stroke-width="4" class="text-accent" />
            <span class="text-[8px] font-black text-text-tertiary uppercase tracking-widest">5 实验就绪</span>
          </div>
        </div>
      </header>
    </div>

    <main class="flex-1 overflow-y-auto custom-scrollbar">
      <div class="max-w-6xl mx-auto p-4 sm:p-10 space-y-8 sm:space-y-12">
        
        <!-- Welcome Section -->
        <section class="max-w-2xl px-2 animate-in fade-in duration-700">
          <h2 class="text-2xl sm:text-4xl font-black text-text-primary tracking-tight leading-tight mb-2 sm:mb-4 uppercase">
            欢迎来到<span class="text-accent">互动实验室</span>
          </h2>
          <p class="text-[11px] sm:text-sm text-text-tertiary leading-loose opacity-80 font-medium">
            在这里，我们探索 AI 交互的无限可能。每一个实验都是一段全新的叙事旅程。
          </p>
        </section>

        <!-- Features Grid: Refined for Light/Dark -->
        <section class="flex items-start gap-3 overflow-x-auto no-scrollbar snap-x snap-mandatory sm:grid sm:grid-cols-2 lg:grid-cols-3 sm:gap-8 sm:overflow-visible pb-10">
          <button 
            v-for="(item, idx) in labFeatures" 
            :key="item.id"
            @click="handleEnter(item.path)"
            class="group relative self-start flex shrink-0 w-[78vw] max-w-[320px] sm:w-auto sm:max-w-none flex-col p-4 sm:p-8 rounded-[28px] sm:rounded-[40px] glass-v3 border border-black/5 dark:border-white/5 shadow-xl transition-all duration-500 hover:-translate-y-2 hover:border-accent/30 text-left overflow-hidden active:scale-95 animate-in fade-in slide-in-from-bottom-4 bg-white/95 dark:bg-white/[0.03]"
            :style="{ animationDelay: `${idx * 50}ms` }"
          >
            <!-- Hover Gradient -->
            <div class="absolute -right-4 -top-4 w-24 h-24 sm:w-32 sm:h-32 blur-[40px] sm:blur-[60px] opacity-0 group-hover:opacity-20 transition-opacity" :class="`bg-gradient-to-br ${item.color}`"></div>
            
            <!-- Aurora Background (Subtle) -->
            <div class="absolute inset-0 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-700 overflow-hidden">
               <div class="absolute -top-10 -left-10 w-32 h-32 blur-[50px] rounded-full bg-accent/10"></div>
            </div>

            <div class="flex items-start justify-between mb-4 sm:mb-10 relative z-10">
              <div class="w-10 h-10 sm:w-14 sm:h-14 rounded-xl sm:rounded-2xl flex items-center justify-center text-white shadow-xl transition-transform duration-500 group-hover:scale-110 group-hover:rotate-3" :class="`bg-gradient-to-br ${item.color}`">
                <component :is="item.icon" :size="20" stroke-width="3.5" class="sm:hidden" />
                <component :is="item.icon" :size="28" stroke-width="3.5" class="hidden sm:block" />
              </div>
              <span class="px-1.5 py-0.5 rounded-md bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/10 text-[7px] sm:text-[8px] font-black uppercase tracking-widest text-text-tertiary">
                {{ item.tag }}
              </span>
            </div>

            <div class="space-y-1 sm:space-y-3 mt-auto relative z-10">
              <h3 class="text-xs sm:text-xl font-black text-text-primary tracking-tight uppercase group-hover:text-accent transition-colors truncate">{{ item.name }}</h3>
              <p class="text-[9px] sm:text-xs text-text-tertiary font-medium leading-tight sm:leading-relaxed opacity-60 group-hover:opacity-90 transition-opacity line-clamp-2">
                {{ item.desc }}
              </p>
            </div>

            <div class="mt-4 sm:mt-10 flex items-center justify-between relative z-10">
              <div class="flex items-center gap-1.5">
                <div class="w-1 h-1 sm:w-1.5 sm:h-1.5 rounded-full bg-accent animate-pulse shadow-[0_0_10px_rgba(var(--color-accent-rgb),0.6)]"></div>
                <span class="text-[7px] sm:text-[9px] font-black uppercase tracking-widest text-text-quaternary opacity-40 group-hover:opacity-100 transition-opacity">Ready</span>
              </div>
              <div class="w-6 h-6 sm:w-9 sm:h-9 rounded-full bg-black/5 dark:bg-white/5 flex items-center justify-center group-hover:bg-accent group-hover:text-white transition-all shadow-inner">
                <ChevronRight :size="14" stroke-width="4" class="sm:hidden" />
                <ChevronRight :size="18" stroke-width="4" class="hidden sm:block" />
              </div>
            </div>
          </button>
        </section>

        <!-- Experimental Note -->
        <div class="p-5 sm:p-6 rounded-[28px] bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5 flex items-start gap-3 sm:gap-4 max-w-2xl mx-auto opacity-60 hover:opacity-100 transition-all">
          <div class="p-1.5 sm:p-2 rounded-lg sm:rounded-xl bg-accent/10 text-accent shrink-0">
            <Info :size="16" stroke-width="3.5" class="sm:hidden" />
            <Info :size="20" stroke-width="3.5" class="hidden sm:block" />
          </div>
          <div class="space-y-0.5 sm:space-y-1">
            <p class="text-[9px] sm:text-xs font-black text-text-primary uppercase tracking-widest leading-none sm:leading-normal">实验协议</p>
            <p class="text-[9px] sm:text-[11px] text-text-tertiary leading-relaxed">
              这些模式处于快速迭代中。任何奇思妙想，欢迎反馈。
            </p>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
:deep(svg) { stroke-width: 3.5px !important; }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(var(--color-text-primary-rgb), 0.05); border-radius: 10px; }
</style>
