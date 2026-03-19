<script setup lang="ts">
import type { TopicCandidate, UserDebateRole } from '@/features/challenge/types'
import { ArrowLeft, Send, Swords, Scale, ShieldQuestion, Zap } from 'lucide-vue-next'
import { ref, computed } from 'vue'

const props = defineProps<{ topic: TopicCandidate }>()
const emit = defineEmits<{
  submit: [payload: { role: UserDebateRole; argument: string }]
  back: []
}>()

const role = ref<UserDebateRole>('pro')
const argument = ref('')

const roleMeta = computed(() => {
  if (role.value === 'pro') return {
    label: '正方一辩 / PRO',
    placeholder: '请陈述你的核心论点...',
    status: '由你先行发言',
    icon: Swords
  }
  if (role.value === 'con') return {
    label: '反方一辩 / CON',
    placeholder: '请准备反驳对方...',
    status: 'AI 将先行陈述',
    icon: ShieldQuestion
  }
  return {
    label: '裁判视角 / JUDGE',
    placeholder: '你想看到哪些层面的对垒？',
    status: '你将在最后总结',
    icon: Scale
  }
})

function submit() {
  if (!argument.value.trim()) return
  emit('submit', { role: role.value, argument: argument.value.trim() })
}
</script>

<template>
  <div class="flex flex-col h-full space-y-6">
    <!-- 顶部导航 -->
    <div class="flex items-center justify-between px-2 shrink-0">
      <button @click="emit('back')" class="flex items-center gap-2 text-[11px] font-black uppercase tracking-widest text-text-tertiary hover:text-accent transition-all active:scale-90">
        <ArrowLeft :size="14" stroke-width="4" /> 返回
      </button>
      <div class="flex items-center gap-2">
         <span class="text-[9px] font-black uppercase tracking-[0.2em] text-text-tertiary opacity-40">Tactical Deployment</span>
      </div>
    </div>

    <!-- 辩题卡片 -->
    <div class="p-6 rounded-[28px] glass-v3 border-white/10 bg-accent/5 shrink-0 relative overflow-hidden">
      <div class="absolute -top-10 -right-10 w-32 h-32 bg-accent/10 blur-[60px] rounded-full"></div>
      <h2 class="text-base font-black text-text-primary leading-tight relative z-10">{{ topic.title }}</h2>
      <p class="text-[12px] text-text-secondary mt-3 leading-relaxed opacity-70 line-clamp-2 relative z-10">
        {{ topic.prompt }}
      </p>
    </div>

    <!-- 分段角色选择器 -->
    <div class="p-1.5 rounded-[24px] bg-black/10 dark:bg-white/5 flex gap-1.5 shrink-0">
      <button
        v-for="r in (['pro', 'con', 'judge'] as UserDebateRole[])"
        :key="r"
        @click="role = r"
        class="flex-1 py-3.5 rounded-[18px] text-[11px] font-black uppercase tracking-widest transition-all duration-500 flex items-center justify-center gap-2"
        :class="role === r 
          ? 'bg-text-primary text-surface-1 shadow-xl scale-[1.02] z-10' 
          : 'text-text-tertiary hover:text-text-secondary'"
      >
        <component :is="r === 'pro' ? Swords : r === 'con' ? ShieldQuestion : Scale" :size="16" stroke-width="3" />
        <span>{{ r === 'pro' ? '正方' : r === 'con' ? '反方' : '裁判' }}</span>
      </button>
    </div>

    <!-- 输入终端 -->
    <div class="flex-1 flex flex-col min-h-0 relative group">
      <!-- 输入框主体: 强化了默认边框，增加了聚焦时的绿色光效 -->
      <textarea
        v-model="argument"
        :placeholder="roleMeta.placeholder"
        class="w-full h-full px-7 py-6 rounded-[32px] bg-black/5 dark:bg-black/20 border border-black/10 dark:border-white/20
               text-sm text-text-primary placeholder:text-text-tertiary/30
               focus:outline-none focus:border-green-500/60 focus:ring-4 focus:ring-green-500/5 focus:bg-white/20 dark:focus:bg-black/30 
               transition-all duration-500 resize-none no-scrollbar shadow-sm"
        @keydown.meta.enter="submit"
      />
      
      <!-- 内部集成状态栏 -->
      <div class="absolute bottom-5 left-6 right-5 flex items-center justify-between pointer-events-none">
        
        <!-- 左侧状态指示 -->
        <div class="flex items-center gap-3 bg-black/20 dark:bg-white/10 backdrop-blur-xl px-4 py-2 rounded-full border border-white/10 shadow-lg">
           <div class="w-1.5 h-1.5 rounded-full bg-accent animate-pulse shadow-[0_0_8px_#6366f1]"></div>
           <span class="text-[10px] font-bold text-text-secondary tracking-wide">{{ roleMeta.status }}</span>
           <div class="h-3 w-[1px] bg-white/10 mx-1"></div>
           <span class="text-[9px] font-black text-text-tertiary uppercase tracking-tighter opacity-40">
             {{ argument.length }} / 500
           </span>
        </div>

        <!-- 右侧动作按钮 -->
        <button
          @click="submit"
          :disabled="!argument.trim()"
          class="pointer-events-auto w-14 h-14 rounded-[22px] transition-all duration-500 shadow-2xl flex items-center justify-center active:scale-90"
          :class="argument.trim()
            ? 'bg-accent text-white shadow-accent/30 hover:shadow-accent/50 hover:-translate-y-1'
            : 'bg-white/5 text-text-tertiary opacity-20 cursor-not-allowed'"
        >
          <Send :size="24" stroke-width="3.5" />
        </button>
      </div>

      <!-- 装饰性 Meta 标识 -->
      <div class="absolute top-4 right-8 pointer-events-none opacity-5">
         <Zap :size="40" stroke-width="3" class="text-accent" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
