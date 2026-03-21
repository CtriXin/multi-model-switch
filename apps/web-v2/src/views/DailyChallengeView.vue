<script setup lang="ts">
import { onMounted, computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useDailyChallengeStore } from '@/stores/dailyChallenge'
import TopicPicker from '@/components/challenge/TopicPicker.vue'
import StanceInput from '@/components/challenge/StanceInput.vue'
import DebateStage from '@/components/challenge/DebateStage.vue'
import ResultCard from '@/components/challenge/ResultCard.vue'
import ChallengeHistory from '@/components/challenge/ChallengeHistory.vue'
import type { TopicCandidate, UserDebateRole } from '@/features/challenge/types'
import { Flame, History, Home, Zap, FlaskConical, ArrowLeft } from 'lucide-vue-next'

const router = useRouter()
const appStore = useAppStore()
const store = useDailyChallengeStore()
const defaultRole = ref<UserDebateRole>('pro')

// INITIALIZATION LOCK: Ensure appStore is ready
const isReady = computed(() => appStore.models.length > 0)

onMounted(async () => {
  if (appStore.models.length === 0) {
    await appStore.initialize()
  }
  store.init() 
})

function goBack() { router.push('/lab') }

function handleTopicSelect(payload: { topic: TopicCandidate; role: UserDebateRole }) {
  defaultRole.value = payload.role
  store.selectTopic(payload.topic)
}
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-surface-0">
    
    <!-- Unified V3 Capsule Header -->
    <div class="z-40 px-4 pt-2 sm:pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-2">
          <button @click="goBack" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors" title="返回实验室"><ArrowLeft :size="18" stroke-width="3.5" /></button>
          <div class="w-8 h-8 rounded-full bg-orange-500/20 flex items-center justify-center shadow-lg shadow-orange-500/10"><Flame :size="14" stroke-width="4" class="text-orange-500" /></div>
          <div class="min-w-0"><h1 class="text-sm font-black text-text-primary truncate uppercase">每日论战</h1></div>
        </div>
        <div class="flex items-center gap-2">
          <button @click="store.phase === 'history' ? store.reset() : store.goToHistory()" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-all">
            <component :is="store.phase === 'history' ? Home : History" :size="18" stroke-width="3.5" />
          </button>
        </div>
      </header>
    </div>

    <main class="flex-1 relative overflow-hidden flex flex-col p-3 sm:p-4 lg:p-6 bg-surface-0">
      <div v-if="!isReady" class="flex-1 flex flex-col items-center justify-center gap-6 animate-in fade-in duration-500">
        <div class="relative w-16 h-16">
           <div class="absolute inset-0 rounded-full border-2 border-accent/20 animate-ping"></div>
           <div class="absolute inset-0 rounded-full border-2 border-accent/40 border-t-accent animate-spin"></div>
           <div class="absolute inset-0 flex items-center justify-center text-accent"><FlaskConical :size="24" stroke-width="3.5" /></div>
        </div>
        <div class="text-[10px] font-black uppercase tracking-[0.4em] text-text-primary animate-pulse opacity-40">初始化模型库...</div>
      </div>

      <div v-else class="w-full max-w-5xl mx-auto flex-1 flex flex-col glass-v3 rounded-[32px] lg:rounded-[40px] shadow-2xl border border-white/10 overflow-hidden relative">
        <div class="flex-1 flex flex-col overflow-hidden relative">
            <div class="mx-auto w-full max-w-3xl flex-1 flex flex-col overflow-hidden p-6 sm:p-10">
              <TopicPicker v-if="store.phase === 'pick_topic'" :candidates="store.candidates" :categories="store.categories" :loading="store.loading" @select="handleTopicSelect($event)" @refresh="store.refreshTopics()" @dismiss="store.dismissTopic($event)" @update-categories="store.updateCategories($event)" />
              <StanceInput v-else-if="store.phase === 'pick_stance'" :topic="store.selectedTopic!" :default-role="defaultRole" @submit="store.startDebate($event)" @back="store.phase = 'pick_topic'" />
              <DebateStage v-else-if="store.phase === 'debating'" :topic="store.selectedTopic!" :messages="store.messages" :debating="store.debating" :error="store.error" :user-role="store.userRole" :awaiting-user-input="store.awaitingUserInput" :awaiting-decision="store.awaitingDecision" :current-round="store.currentRound" class="lab-flowing-text" @submit-turn="store.submitUserTurn($event)" @continue="store.continueDebate()" @finish="store.finishDebate()" />
              <ResultCard v-else-if="store.phase === 'result'" :topic="store.selectedTopic" :pro-text="store.proText" :con-text="store.conText" :takeaway="store.takeaway" :snapshot="store.snapshot" :current-card="store.currentCard" :user-stance="store.userStance" :user-reason="store.userReason" :streak="store.streak" :messages="store.messages" @save="store.saveCurrentCard($event)" @retry="store.reset()" @go-history="store.goToHistory()" @go-home="store.reset()" />
              <ChallengeHistory v-else-if="store.phase === 'history'" :cards="store.recentCards" :streak="store.streak" />
              <div v-if="store.phase === 'loading'" class="h-full flex flex-col items-center justify-center gap-6"><div class="relative w-16 h-16"><div class="absolute inset-0 rounded-full border-2 border-accent/20 animate-ping"></div><div class="absolute inset-0 rounded-full border-2 border-accent/40 border-t-accent animate-spin"></div><div class="absolute inset-0 flex items-center justify-center text-accent"><FlaskConical :size="24" stroke-width="3.5" /></div></div><div class="text-[10px] font-black uppercase tracking-[0.4em] text-text-primary animate-pulse opacity-40">初始化论战现场</div></div>
            </div>
          </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
:deep(svg) { stroke-width: 3.5px !important; }
.lab-flowing-text { animation: flowingText 0.8s cubic-bezier(0.215, 0.61, 0.355, 1) forwards; }
@keyframes flowingText { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }
</style>
