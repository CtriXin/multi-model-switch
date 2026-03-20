<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { 
  FlaskConical, Flame, Soup, Sparkles, Clapperboard, 
  Shield, ChevronRight, ArrowLeft, Zap, Info
} from 'lucide-vue-next'

const router = useRouter()

const labFeatures = [
  {
    id: 'challenge',
    name: '每日论战',
    desc: '今日话题对战，锻炼批判性思维',
    icon: Flame,
    path: '/challenge',
    color: 'from-orange-500 to-red-600',
    tag: '竞技',
    difficulty: '中等'
  },
  {
    id: 'turtle-soup',
    name: '海龟汤',
    desc: '离奇案件卷宗，通过提问还原真相',
    icon: Soup,
    path: '/turtle-soup',
    color: 'from-emerald-500 to-teal-600',
    tag: '推理',
    difficulty: '困难'
  },
  {
    id: 'story-lite',
    name: '假如模拟器',
    desc: '设定一个假设场景，看 AI 如何演绎',
    icon: Sparkles,
    path: '/story-lite',
    color: 'from-blue-500 to-indigo-600',
    tag: '创意',
    difficulty: '入门'
  },
  {
    id: 'story-live',
    name: '剧情共演',
    desc: '实时接戏，与导演组共同推进剧情',
    icon: Clapperboard,
    path: '/story-live',
    color: 'from-purple-500 to-fuchsia-600',
    tag: '互动',
    difficulty: '极高'
  },
  {
    id: 'multi-life',
    name: '多重人生',
    desc: '三位角色各执一词，还原你的真相',
    icon: Shield,
    path: '/multi-life',
    color: 'from-cyan-500 to-blue-600',
    tag: '叙事',
    difficulty: '中等'
  }
]

function handleEnter(path: string) {
  router.push(path)
}
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">
    <!-- Group 1: Page-Level Action Header (Function Row) -->
    <div class="sticky top-0 z-30 px-4 pt-2 pb-2 shrink-0">
      <header
        class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2 transition-all duration-500 shadow-xl relative flex items-center justify-between border border-white/10">

        <!-- Left: Context Info -->
        <div class="flex items-center gap-2 sm:gap-3 min-w-0">
          <button @click="router.push('/')" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors shrink-0">
            <ArrowLeft :size="20" stroke-width="3.5" />
          </button>
          <div class="flex items-center justify-center w-8 h-8 rounded-full bg-accent text-white shadow-lg shrink-0">
            <FlaskConical :size="16" stroke-width="3.5" />
          </div>
          <div class="min-w-0">
            <h1 class="text-sm font-black text-text-primary truncate tracking-tight uppercase">互动实验室</h1>
          </div>
        </div>
      </header>
    </div>

    <!-- Main Lab Container -->
    <div class="w-full max-w-6xl mx-auto flex-1 flex flex-col p-3 sm:p-4 lg:p-6">
      <div class="w-full h-full flex flex-col glass-v3 rounded-[32px] lg:rounded-[40px] shadow-2xl border border-white/10 overflow-hidden relative">
      
      <!-- Background Aurora -->
      <div class="absolute inset-0 pointer-events-none overflow-hidden">
        <div class="absolute -top-24 -left-24 w-96 h-96 bg-accent/10 blur-[100px] rounded-full"></div>
        <div class="absolute top-1/2 -right-24 w-80 h-80 bg-purple-500/10 blur-[100px] rounded-full"></div>
      </div>

      <!-- Grid Content -->
      <main class="flex-1 overflow-y-auto custom-scrollbar relative z-10">
        <div class="p-6 sm:p-10 space-y-10">
          <!-- Intro Section -->
          <section class="max-w-2xl">
            <h2 class="text-3xl sm:text-4xl font-black text-text-primary tracking-tight leading-tight mb-4">
              欢迎来到<span class="text-accent">创意中心</span>
            </h2>
            <p class="text-sm text-text-tertiary leading-loose opacity-80">
              这里是 SparkRing 的灵感孵化场。每一个“实验”都代表一种全新的 AI 交互方式，从硬核辩论到实时叙事共演，探索大模型的边界。
            </p>
          </section>

          <!-- Features Grid -->
          <section class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-10">
            <button 
              v-for="item in labFeatures" 
              :key="item.id"
              @click="handleEnter(item.path)"
              class="group relative flex flex-col p-8 rounded-[36px] glass-v3 border border-white/5 shadow-xl transition-all duration-500 hover:-translate-y-2 hover:border-accent/30 text-left overflow-hidden active:scale-95"
            >
              <!-- Hover Gradient -->
              <div class="absolute -right-4 -top-4 w-32 h-32 blur-[60px] opacity-0 group-hover:opacity-20 transition-opacity" :class="`bg-gradient-to-br ${item.color}`"></div>
              
              <div class="flex items-start justify-between mb-8">
                <div class="w-14 h-14 rounded-2xl flex items-center justify-center text-white shadow-2xl transition-transform duration-500 group-hover:scale-110 group-hover:rotate-3" :class="`bg-gradient-to-br ${item.color}`">
                  <component :is="item.icon" :size="28" stroke-width="3.5" />
                </div>
                <div class="flex flex-col items-end gap-2">
                  <span class="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-[8px] font-black uppercase tracking-widest text-text-tertiary">
                    {{ item.tag }}
                  </span>
                  <span class="text-[7px] font-black uppercase tracking-widest text-text-quaternary opacity-40">
                    难易度: {{ item.difficulty }}
                  </span>
                </div>
              </div>

              <div class="space-y-2 mt-auto">
                <h3 class="text-xl font-black text-text-primary tracking-tight uppercase group-hover:text-accent transition-colors">{{ item.name }}</h3>
                <p class="text-xs text-text-tertiary font-medium leading-relaxed opacity-60 group-hover:opacity-90 transition-opacity">
                  {{ item.desc }}
                </p>
              </div>

              <div class="mt-8 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="w-1.5 h-1.5 rounded-full bg-accent animate-pulse"></div>
                  <span class="text-[9px] font-black uppercase tracking-widest text-text-quaternary">Ready for Test</span>
                </div>
                <div class="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center group-hover:bg-accent group-hover:text-white transition-all">
                  <ChevronRight :size="16" stroke-width="4" />
                </div>
              </div>
            </button>
          </section>

          <!-- Experimental Note -->
          <div class="p-6 rounded-[28px] bg-accent/5 border border-accent/10 flex items-start gap-4">
            <div class="p-2 rounded-xl bg-accent/10 text-accent">
              <Info :size="18" stroke-width="3.5" />
            </div>
            <div class="space-y-1">
              <p class="text-xs font-black text-text-primary uppercase tracking-widest">实验性提示</p>
              <p class="text-[11px] text-text-tertiary leading-relaxed">
                互动实验室中的功能正在快速迭代。如果你遇到任何生成逻辑上的问题，或者有更有趣的“假如”点子，欢迎在设置中反馈给我们。
              </p>
            </div>
          </div>
        </div>
      </main>

      <!-- Mobile Floating Navigation Placeholder -->
      <footer class="sm:hidden h-16 shrink-0 border-t border-white/5 flex items-center justify-center">
        <p class="text-[9px] font-black text-text-quaternary uppercase tracking-[0.3em] opacity-40">Kinetic Interactive Hub</p>
      </footer>
    </div>
    </div>
  </div>
</template>

<style scoped>
:deep(svg) { stroke-width: 3.5px !important; }

.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.1);
}
</style>