<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useDailyChallengeStore } from '@/stores/dailyChallenge'
import TopicPicker from '@/components/challenge/TopicPicker.vue'
import StanceInput from '@/components/challenge/StanceInput.vue'
import DebateStage from '@/components/challenge/DebateStage.vue'
import ResultCard from '@/components/challenge/ResultCard.vue'
import ChallengeHistory from '@/components/challenge/ChallengeHistory.vue'
import { Flame, History, Home, Zap, FlaskConical, ArrowLeft, ChevronRight } from 'lucide-vue-next'

const router = useRouter()
const appStore = useAppStore()
const store = useDailyChallengeStore()

const isReady = computed(() => appStore.models.length > 0)

onMounted(async () => {
  if (appStore.models.length === 0) await appStore.initialize()
  store.init() 
})

function goBack() { router.push('/lab') }
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-surface-0">
    
    <!-- Unified Header -->
    <div class="z-40 px-4 pt-2 sm:pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-black/5 dark:border-white/10 bg-white/80 dark:bg-white/[0.05]">
        <div class="flex items-center gap-2">
          <button @click="goBack" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors" title="返回实验室"><ArrowLeft :size="18" stroke-width="3.5" /></button>
          <div class="w-8 h-8 rounded-full bg-orange-500/20 flex items-center justify-center shadow-lg shadow-orange-500/10"><Flame :size="14" stroke-width="4" class="text-orange-500" /></div>
          <h1 class="text-xs font-black text-text-primary uppercase tracking-widest">每日论战</h1>
        </div>
        <div class="flex items-center gap-2">
          <button @click="store.phase === 'history' ? store.reset() : store.goToHistory()" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all">
            <component :is="store.phase === 'history' ? Home : History" :size="18" stroke-width="3.5" />
          </button>
        </div>
      </header>
    </div>

    <main class="flex-1 relative overflow-hidden flex flex-col px-3 sm:px-6 pb-3 sm:pb-6 bg-surface-0">
      <div v-if="!isReady" class="flex-1 flex flex-col items-center justify-center gap-6">
        <div class="relative w-16 h-16">
           <div class="absolute inset-0 rounded-full border-2 border-accent/20"></div>
           <div class="absolute inset-0 rounded-full border-2 border-accent/40 border-t-accent animate-spin"></div>
           <div class="absolute inset-0 flex items-center justify-center text-accent"><FlaskConical :size="24" stroke-width="3.5" /></div>
        </div>
        <div class="text-[10px] font-black uppercase tracking-[0.4em] text-text-primary opacity-40">加载论战环境...</div>
      </div>

      <div v-else class="w-full max-w-5xl mx-auto flex-1 flex flex-col glass-v3 rounded-[32px] lg:rounded-[48px] shadow-2xl border border-black/5 dark:border-white/10 overflow-hidden relative bg-white/95 dark:bg-[#0d0f14]/90 transition-none">
        <div class="flex-1 flex flex-col overflow-hidden relative">
          <div class="flex-1 flex flex-col overflow-hidden p-6 sm:p-10">
            <TopicPicker v-if="store.phase === 'pick_topic'" :candidates="store.candidates" :categories="store.categories" :loading="store.loading" @select="store.selectTopic($event)" @refresh="store.refreshTopics()" @dismiss="store.dismissTopic($event)" @update-categories="store.updateCategories($event)" />
            <StanceInput v-else-if="store.phase === 'pick_stance'" :topic="store.selectedTopic!" @submit="store.startDebate($event)" @back="store.phase = 'pick_topic'" />
            <DebateStage v-else-if="store.phase === 'debating'" :topic="store.selectedTopic!" :messages="store.messages" :debating="store.debating" :error="store.error" :user-role="store.userRole" :awaiting-user-input="store.awaitingUserInput" :awaiting-decision="store.awaitingDecision" :current-round="store.currentRound" @submit-turn="store.submitUserTurn($event)" @continue="store.continueDebate()" @finish="store.finishDebate()" />
            <ResultCard v-else-if="store.phase === 'result'" :topic="store.selectedTopic" :pro-text="store.proText" :con-text="store.conText" :takeaway="store.takeaway" :snapshot="store.snapshot" :current-card="store.currentCard" :user-stance="store.userStance" :user-reason="store.userReason" :streak="store.streak" :messages="store.messages" @save="store.saveCurrentCard($event)" @retry="store.reset()" @go-history="store.goToHistory()" @go-home="store.reset()" />
            <ChallengeHistory v-else-if="store.phase === 'history'" :cards="store.recentCards" :streak="store.streak" />
            <div v-if="store.phase === 'loading'" class="h-full flex flex-col items-center justify-center gap-6"><div class="relative w-16 h-16"><div class="absolute inset-0 rounded-full border-2 border-accent/20"></div><div class="absolute inset-0 rounded-full border-2 border-accent/40 border-t-accent animate-spin"></div><div class="absolute inset-0 flex items-center justify-center text-accent"><Zap :size="24" stroke-width="3.5" /></div></div><div class="text-[10px] font-black uppercase tracking-[0.4em] text-text-primary opacity-40">因果律同步中...</div></div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
:deep(svg) { stroke-width: 3.5px !important; }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }
</style>