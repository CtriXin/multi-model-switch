<script setup lang="ts">
import { onMounted } from 'vue'
import { useDailyChallengeStore } from '@/stores/dailyChallenge'
import TopicPicker from '@/components/challenge/TopicPicker.vue'
import StanceInput from '@/components/challenge/StanceInput.vue'
import DebateStage from '@/components/challenge/DebateStage.vue'
import ResultCard from '@/components/challenge/ResultCard.vue'
import ChallengeHistory from '@/components/challenge/ChallengeHistory.vue'
import { Flame, History, Home, Zap } from 'lucide-vue-next'

const store = useDailyChallengeStore()

onMounted(() => {
  store.init()
})
</script>

<template>
  <div class="h-full flex flex-col items-center p-3 sm:p-4 lg:p-6 overflow-hidden relative">

    <!-- Cinematic Arena Container -->
    <div class="w-full max-w-6xl flex-1 flex flex-col glass-v3 rounded-[32px] shadow-2xl border border-white/10 overflow-hidden bg-white/70 dark:bg-[#0b0b18]/80 relative z-10 transition-all duration-700">

      <!-- Integrated V3 Header -->
      <header class="flex items-center justify-between px-6 h-16 shrink-0 relative border-b border-black/[0.03] dark:border-white/5">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-xl bg-accent/20 flex items-center justify-center shadow-lg shadow-accent/10">
            <Flame :size="16" stroke-width="3.5" class="text-accent" />
          </div>
          <div class="flex flex-col">
            <h1 class="text-[12px] font-black uppercase tracking-[0.2em] text-text-primary leading-none">每日竞技场</h1>
            <div v-if="store.streak > 0" class="text-[8px] font-black text-accent uppercase tracking-widest mt-1 animate-pulse">
              连续{{ store.streak }}天
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2">
           <button
            @click="store.phase === 'history' ? store.reset() : store.goToHistory()"
            class="flex items-center justify-center w-10 h-10 rounded-xl bg-black/[0.03] dark:bg-white/5 text-text-tertiary hover:text-text-primary transition-all active:scale-90 border border-transparent hover:border-white/10"
          >
            <component :is="store.phase === 'history' ? Home : History" :size="18" stroke-width="3" />
          </button>
        </div>
      </header>

      <!-- Content Area: Absolute Positioning to Prevent Layout Shift -->
      <main class="flex-1 relative overflow-hidden">
        <transition name="ios-swap" mode="out-in">
          <div :key="store.phase" class="absolute inset-0 flex flex-col overflow-hidden px-4 sm:px-8 py-6">
            <div class="mx-auto w-full max-w-3xl flex-1 flex flex-col overflow-hidden">

              <!-- Topic Picker Phase -->
              <TopicPicker
                v-if="store.phase === 'pick_topic'"
                :candidates="store.candidates"
                :categories="store.categories"
                :loading="store.loading"
                @select="store.selectTopic($event)"
                @refresh="store.refreshTopics()"
                @dismiss="store.dismissTopic($event)"
                @update-categories="store.updateCategories($event)"
              />

              <!-- Stance Input Phase -->
              <StanceInput
                v-else-if="store.phase === 'pick_stance'"
                :topic="store.selectedTopic!"
                @submit="store.startDebate($event)"
                @back="store.phase = 'pick_topic'"
              />

              <!-- Debating Stage Phase -->
              <DebateStage
                v-else-if="store.phase === 'debating'"
                :topic="store.selectedTopic!"
                :messages="store.messages"
                :debating="store.debating"
                :error="store.error"
                :user-role="store.userRole"
                :awaiting-user-input="store.awaitingUserInput"
                :awaiting-decision="store.awaitingDecision"
                :current-round="store.currentRound"
                @submit-turn="store.submitUserTurn($event)"
                @continue="store.continueDebate()"
                @finish="store.finishDebate()"
              />

              <!-- Result Card Phase -->
              <ResultCard
                v-else-if="store.phase === 'result'"
                :topic="store.selectedTopic"
                :pro-text="store.proText"
                :con-text="store.conText"
                :takeaway="store.takeaway"
                :snapshot="store.snapshot"
                :current-card="store.currentCard"
                :user-stance="store.userStance"
                :user-reason="store.userReason"
                :streak="store.streak"
                :messages="store.messages"
                @save="store.saveCurrentCard($event)"
                @retry="store.reset()"
                @go-history="store.goToHistory()"
                @go-home="store.reset()"
              />

              <!-- History Archive Phase -->
              <ChallengeHistory
                v-else-if="store.phase === 'history'"
                :cards="store.recentCards"
                :streak="store.streak"
              />

              <!-- Global Loading State -->
              <div v-if="store.phase === 'loading'" class="h-full flex flex-col items-center justify-center gap-6">
                <div class="relative w-16 h-16">
                   <div class="absolute inset-0 rounded-full border-2 border-accent/20 animate-ping"></div>
                   <div class="absolute inset-0 rounded-full border-2 border-accent/40 border-t-accent animate-spin"></div>
                   <div class="absolute inset-0 flex items-center justify-center">
                      <Zap :size="24" stroke-width="3.5" class="text-accent" />
                   </div>
                </div>
                <div class="text-[10px] font-black uppercase tracking-[0.4em] text-text-primary animate-pulse">初始化竞技场</div>
              </div>

            </div>
          </div>
        </transition>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* iOS Style Slide & Fade Transition */
.ios-swap-enter-active { animation: iosIn 0.6s cubic-bezier(0.32, 0.72, 0, 1); }
.ios-swap-leave-active { animation: iosOut 0.5s cubic-bezier(0.32, 0.72, 0, 1); }

@keyframes iosIn {
  from { opacity: 0; transform: translateX(40px) scale(0.98); filter: blur(15px); }
  to { opacity: 1; transform: translateX(0) scale(1); filter: blur(0); }
}

@keyframes iosOut {
  from { opacity: 1; transform: translateX(0); }
  to { opacity: 0; transform: translateX(-40px) scale(0.98); filter: blur(15px); }
}

/* Scrollbar and UI cleaning */
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
