<script setup lang="ts">
import { ref, computed } from 'vue'
import type { DailyCategory, TopicCandidate, UserDebateRole } from '@/features/challenge/types'
import { CATEGORY_ICONS } from '@/features/challenge/types'
import {
  RefreshCw, Zap, Cpu, Globe, Briefcase, Activity, Heart, PieChart,
  Orbit, ShieldAlert, Brain, Gamepad2, Leaf, Layers, X, Check, ArrowRight
} from 'lucide-vue-next'

const props = defineProps<{
  candidates: TopicCandidate[]
  categories: DailyCategory[]
  loading?: boolean
}>()

const emit = defineEmits<{
  select: [payload: { topic: TopicCandidate; role: UserDebateRole }]
  refresh: []
  dismiss: [topicId: string]
  updateCategories: [cats: DailyCategory[]]
}>()

const visibleCandidates = computed(() => props.candidates.slice(0, 3))
const topCandidate = computed(() => visibleCandidates.value[0] ?? null)

const categoryMeta: Record<DailyCategory, { icon: any; label: string; desc: string }> = {
  tech: { icon: Cpu, label: '科技', desc: '系统底层' },
  society: { icon: Globe, label: '社会', desc: '群体共识' },
  career: { icon: Briefcase, label: '职场', desc: '逻辑进阶' },
  philosophy: { icon: Activity, label: '伦理', desc: '深度思辨' },
  life: { icon: Heart, label: '生活', desc: '生命感知' },
  economy: { icon: PieChart, label: '经济', desc: '数据驱动' },
  future: { icon: Orbit, label: '未来', desc: '演化推演' },
  grey: { icon: ShieldAlert, label: '暗区', desc: '秩序博弈' },
  mind: { icon: Brain, label: '心智', desc: '意识映射' },
  culture: { icon: Gamepad2, label: '潮流', desc: '数字模因' },
  ecology: { icon: Leaf, label: '生态', desc: '文明契约' }
}

const allCategories: DailyCategory[] = [
  'tech', 'society', 'career', 'philosophy', 'future',
  'grey', 'mind', 'economy', 'culture', 'ecology', 'life'
]

const dragX = ref(0)
const isDragging = ref(false)
const startX = ref(0)

function onTouchStart(e: TouchEvent) {
  startX.value = e.touches[0].clientX
  isDragging.value = true
}

function onTouchMove(e: TouchEvent) {
  if (!isDragging.value) return
  dragX.value = e.touches[0].clientX - startX.value
}

function onTouchEnd(topic: TopicCandidate) {
  isDragging.value = false
  if (dragX.value < -100) {
    emit('select', { topic, role: 'con' })
  } else if (dragX.value > 100) {
    emit('select', { topic, role: 'pro' })
  }
  dragX.value = 0
}

function handleDismiss(id?: string) {
  if (!id) return
  emit('dismiss', id)
  if (props.candidates.length <= 2) emit('refresh')
}

const topCardStyle = computed(() => {
  if (!isDragging.value && dragX.value === 0) return {}
  const rotation = dragX.value / 10
  return {
    transform: `translateX(${dragX.value}px) rotate(${rotation}deg)`,
    transition: isDragging.value ? 'none' : 'all 0.5s cubic-bezier(0.23, 1, 0.32, 1)'
  }
})

function toggleCategory(cat: DailyCategory) {
  const current = [...props.categories]
  const idx = current.indexOf(cat)
  if (idx >= 0) { if (current.length > 1) current.splice(idx, 1) }
  else { current.push(cat) }
  emit('updateCategories', current)
}
</script>

<template>
  <div class="flex flex-col h-full space-y-6 overflow-hidden">

    <!-- 顶部调谐器 -->
    <div class="shrink-0 space-y-3">
      <div class="flex items-center justify-between px-2">
        <div class="flex items-center gap-2">
           <Layers :size="14" stroke-width="3" class="text-text-tertiary" />
           <h3 class="text-[11px] font-black uppercase tracking-[0.4em] text-text-tertiary">领域激活矩阵</h3>
        </div>
        <button @click="emit('refresh')" class="p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/5 transition-all">
           <RefreshCw :size="14" stroke-width="3" class="text-text-tertiary" :class="loading ? 'animate-spin text-accent' : ''" />
        </button>
      </div>

      <div class="flex gap-2.5 overflow-x-auto no-scrollbar px-2 py-2">
        <button
          v-for="cat in allCategories"
          :key="cat"
          @click="toggleCategory(cat)"
          class="relative shrink-0 w-[64px] h-[76px] flex flex-col items-center justify-center rounded-[20px] transition-all duration-500 border group"
          :class="categories.includes(cat)
            ? 'glass-v3 border-accent/40 bg-accent/10 shadow-xl shadow-accent/10 -translate-y-1'
            : 'bg-black/5 dark:bg-white/5 border-transparent grayscale opacity-40 hover:grayscale-0'"
        >
          <component :is="categoryMeta[cat].icon" :size="20" :stroke-width="3" class="mb-1.5 transition-all group-active:scale-90" :class="categories.includes(cat) ? 'text-accent' : 'text-text-tertiary'" />
          <span class="text-[9px] font-black tracking-widest leading-none text-text-primary">{{ categoryMeta[cat].label }}</span>
        </button>
      </div>
    </div>

    <!-- 卡片堆叠区域 -->
    <div class="flex-1 relative mt-4 flex items-center justify-center">

      <div v-if="loading && !visibleCandidates.length" class="flex flex-col items-center gap-4">
        <div class="w-16 h-16 rounded-[32px] border-2 border-dashed border-accent/30 animate-spin"></div>
        <span class="text-[10px] font-black uppercase tracking-[0.4em] text-text-tertiary animate-pulse">Syncing Arena...</span>
      </div>

      <div v-else-if="!visibleCandidates.length" class="text-center p-10 rounded-[40px] border-2 border-dashed border-black/5 dark:border-white/5">
         <Zap :size="32" class="mx-auto text-text-tertiary opacity-20 mb-4" />
         <p class="text-[11px] font-black uppercase tracking-widest text-text-tertiary">暂时没有更多辩题</p>
         <button @click="emit('refresh')" class="mt-6 px-6 py-3 bg-accent text-white rounded-2xl text-[10px] font-black uppercase tracking-widest active:scale-95 transition-all">重新载入</button>
      </div>

      <div v-else class="relative w-full h-full max-h-[460px]">
        <div
          v-for="(topic, index) in visibleCandidates"
          :key="topic.id"
          class="absolute inset-0 transition-all duration-500"
          :style="{
            zIndex: visibleCandidates.length - index,
            transform: index === 0 ? '' : `translateY(${index * 12}px) scale(${1 - index * 0.05})`,
            opacity: 1 - index * 0.3
          }"
        >
          <div
            v-if="index === 0"
            @touchstart="onTouchStart"
            @touchmove="onTouchMove"
            @touchend="onTouchEnd(topic)"
            @click="emit('select', { topic, role: 'pro' })"
            :style="topCardStyle"
            class="relative w-full h-full p-8 rounded-[48px] border-2 border-black/5 dark:border-white/5 bg-white dark:bg-[#1a1d24] shadow-2xl flex flex-col justify-between overflow-hidden group select-none"
          >
            <!-- 反馈覆盖层 -->
            <div class="absolute inset-0 pointer-events-none transition-opacity duration-300 flex items-center justify-center z-50"
                 :style="{ opacity: Math.min(Math.abs(dragX) / 100, 0.8), backgroundColor: dragX < 0 ? 'rgba(239, 68, 68, 0.2)' : 'rgba(99, 102, 241, 0.2)' }">
               <div v-if="dragX < -20" class="p-4 rounded-full border-4 border-red-500 text-red-500 rotate-[-12deg] font-black text-2xl">CON</div>
               <div v-if="dragX > 20" class="p-4 rounded-full border-4 border-accent text-accent rotate-[12deg] font-black text-2xl">PRO</div>
            </div>

            <div class="flex items-center justify-between relative z-10">
              <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-2xl bg-black/5 dark:bg-white/5 flex items-center justify-center text-2xl">
                  {{ CATEGORY_ICONS[topic.category] }}
                </div>
                <div class="flex flex-col">
                  <span class="text-[10px] font-black uppercase tracking-widest text-accent">{{ categoryMeta[topic.category].label }}</span>
                  <span class="text-[12px] font-bold text-text-primary uppercase tracking-tighter">PROTO-{{ topic.id.slice(0,4).toUpperCase() }}</span>
                </div>
              </div>
              <div class="px-3 py-1 rounded-full bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/10">
                <span class="text-[10px] font-black text-text-secondary uppercase tracking-widest">
                  {{ topic.difficulty === 'casual' ? '日常挑战' : '深度模式' }}
                </span>
              </div>
            </div>

            <div class="flex-1 flex flex-col justify-center py-8 relative z-10">
               <h2 class="text-2xl font-black text-text-primary leading-tight tracking-tight break-words">
                 {{ topic.title }}
               </h2>
               <p class="mt-6 text-sm text-text-secondary leading-relaxed font-medium italic opacity-80">
                 「{{ topic.hook || topic.prompt }}」
               </p>
            </div>

            <div class="pt-6 border-t border-black/[0.03] dark:border-white/5 flex items-center justify-between relative z-10">
               <div class="flex flex-col gap-1 text-left">
                  <span class="text-[9px] font-black text-text-tertiary uppercase tracking-widest">Swipe / Pick A Side</span>
                  <span class="text-[11px] font-bold text-text-secondary">右滑正方 · 左滑反方</span>
               </div>
               <div class="w-12 h-12 rounded-2xl bg-accent text-white flex items-center justify-center shadow-lg active:scale-90 transition-all">
                  <ArrowRight :size="20" stroke-width="4" />
               </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部操作按钮 -->
    <div class="flex items-center justify-center gap-6 py-4 shrink-0">
       <button @click="handleDismiss(topCandidate?.id)" class="flex flex-col items-center gap-2 group">
          <div class="w-12 h-12 rounded-full border-2 border-red-500/20 dark:border-red-500/40 flex items-center justify-center text-red-500 active:scale-90 transition-all hover:bg-red-500 hover:text-white">
             <X :size="20" stroke-width="4" />
          </div>
          <span class="text-[8px] font-black uppercase tracking-widest text-text-tertiary">不感兴趣</span>
       </button>
       <button @click="topCandidate && emit('select', { topic: topCandidate, role: 'pro' })" class="flex flex-col items-center gap-2 group">
          <div class="w-12 h-12 rounded-full border-2 border-emerald-500/20 dark:border-emerald-500/40 flex items-center justify-center text-emerald-500 active:scale-90 transition-all hover:bg-emerald-500 hover:text-white">
             <Check :size="20" stroke-width="4" />
          </div>
          <span class="text-[8px] font-black uppercase tracking-widest text-text-tertiary">我是正方</span>
       </button>
       <button @click="topCandidate && emit('select', { topic: topCandidate, role: 'con' })" class="flex flex-col items-center gap-2 group">
          <div class="w-12 h-12 rounded-full border-2 border-amber-500/20 dark:border-amber-500/40 flex items-center justify-center text-amber-500 active:scale-90 transition-all hover:bg-amber-500 hover:text-white">
             <ArrowRight :size="20" stroke-width="4" class="rotate-180" />
          </div>
          <span class="text-[8px] font-black uppercase tracking-widest text-text-tertiary">我是反方</span>
       </button>
    </div>

  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
