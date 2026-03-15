<template>
  <div class="h-full flex flex-col pt-20 px-4 pb-4 overflow-hidden">
    <!-- Empty State -->
    <div
      v-if="!discussStore.isProcessing && !discussStore.phase3Synthesis"
      class="flex-1 flex flex-col items-center justify-center"
    >
      <div class="w-20 h-20 rounded-2xl bg-gradient-to-br from-pink-100 to-rose-100 dark:from-pink-500/20 dark:to-rose-500/20 flex items-center justify-center mb-6">
        <Users class="w-10 h-10 text-pink-500" />
      </div>
      <h3 class="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-2">
        深度讨论模式
      </h3>
      <p class="text-sm text-gray-500 text-center max-w-xs mb-6">
        三阶段收敛讨论：独立方案 → 交叉审查 → 综合结论
      </p>

      <!-- Phase Preview -->
      <div class="flex items-center gap-3 text-sm">
        <div class="flex items-center gap-2 px-3 py-2 rounded-xl bg-purple-50 dark:bg-purple-500/20">
          <span class="w-5 h-5 rounded-full bg-purple-500 text-white text-xs flex items-center justify-center">1</span>
          <span class="text-purple-600 dark:text-purple-300">方案</span>
        </div>
        <ArrowRight class="w-4 h-4 text-gray-300" />
        <div class="flex items-center gap-2 px-3 py-2 rounded-xl bg-pink-50 dark:bg-pink-500/20">
          <span class="w-5 h-5 rounded-full bg-pink-500 text-white text-xs flex items-center justify-center">2</span>
          <span class="text-pink-600 dark:text-pink-300">审查</span>
        </div>
        <ArrowRight class="w-4 h-4 text-gray-300" />
        <div class="flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-50 dark:bg-amber-500/20">
          <span class="w-5 h-5 rounded-full bg-amber-500 text-white text-xs flex items-center justify-center">3</span>
          <span class="text-amber-600 dark:text-amber-300">结论</span>
        </div>
      </div>
    </div>

    <!-- Active Discussion -->
    <div
      v-else
      class="flex-1 overflow-y-auto hide-scrollbar overscroll-none"
    >
      <!-- Progress Bar -->
      <div class="sticky top-0 z-10 glass rounded-xl p-3 mb-6">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium text-gray-700 dark:text-gray-200">
            {{ discussStore.phaseName }}
          </span>
          <span class="text-xs text-gray-500">{{ Math.round(discussStore.progress) }}%</span>
        </div>
        <div class="h-1.5 bg-gray-200 dark:bg-white/10 rounded-full overflow-hidden">
          <div
            class="h-full rounded-full transition-all duration-500"
            :class="phaseColor"
            :style="{ width: `${discussStore.progress}%` }"
          />
        </div>
      </div>

      <!-- Prompt -->
      <div class="flex justify-center mb-6">
        <div class="px-5 py-3 bg-gradient-to-r from-pink-500 to-rose-600 text-white rounded-2xl shadow-lg shadow-pink-500/20 max-w-lg">
          <p class="text-sm">{{ discussStore.prompt }}</p>
        </div>
      </div>

      <!-- Phase 1: Summaries -->
      <div v-if="discussStore.phase1Summaries.length > 0" class="mb-8">
        <div class="flex items-center gap-2 mb-4">
          <span class="w-6 h-6 rounded-full bg-purple-500 text-white text-xs flex items-center justify-center">1</span>
          <h4 class="font-semibold text-gray-800 dark:text-gray-100">独立方案</h4>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <TransitionGroup name="fade-up">
            <div
              v-for="summary in discussStore.phase1Summaries"
              :key="summary.modelId"
              class="glass rounded-xl border border-white/30 p-4"
            >
              <div class="flex items-center gap-3 mb-3">
                <span class="text-xl">{{ getModelAvatar(summary.modelId) }}</span>
                <div>
                  <p class="font-medium text-gray-800 dark:text-gray-100 text-sm">
                    {{ getModelName(summary.modelId) }}
                  </p>
                  <div class="flex items-center gap-1 mt-0.5">
                    <div
                      class="h-1 rounded-full bg-purple-500"
                      :style="{ width: `${summary.confidence * 100}%` }"
                    ></div>
                    <span class="text-xs text-gray-500">{{ Math.round(summary.confidence * 100) }}%</span>
                  </div>
                </div>
              </div>
              <p class="text-sm text-gray-700 dark:text-gray-200 font-medium mb-1">
                {{ summary.approach }}
              </p>
              <p class="text-xs text-gray-500">
                {{ summary.reasoning }}
              </p>
            </div>
          </TransitionGroup>
        </div>
      </div>

      <!-- Phase 2: Reviews -->
      <div v-if="discussStore.phase2Reviews.length > 0" class="mb-8">
        <div class="flex items-center gap-2 mb-4">
          <span class="w-6 h-6 rounded-full bg-pink-500 text-white text-xs flex items-center justify-center">2</span>
          <h4 class="font-semibold text-gray-800 dark:text-gray-100">交叉审查</h4>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <TransitionGroup name="fade-up">
            <div
              v-for="(review, idx) in discussStore.phase2Reviews"
              :key="idx"
              class="glass rounded-xl border border-white/30 p-4"
            >
              <div class="flex items-center gap-2 mb-3">
                <span class="text-lg">{{ getModelAvatar(review.reviewerId) }}</span>
                <ArrowRight class="w-4 h-4 text-gray-400" />
                <span class="text-lg">{{ getModelAvatar(review.targetId) }}</span>
              </div>
              <p class="text-sm text-gray-700 dark:text-gray-200 mb-2">
                {{ review.critique }}
              </p>
              <div class="space-y-1">
                <p
                  v-for="(suggestion, sidx) in review.suggestions"
                  :key="sidx"
                  class="text-xs text-gray-500 flex items-center gap-1"
                >
                  <span class="w-1 h-1 rounded-full bg-pink-500"></span>
                  {{ suggestion }}
                </p>
              </div>
            </div>
          </TransitionGroup>
        </div>
      </div>

      <!-- Phase 3: Synthesis -->
      <div v-if="discussStore.phase3Synthesis" class="mb-8">
        <div class="flex items-center gap-2 mb-4">
          <span class="w-6 h-6 rounded-full bg-amber-500 text-white text-xs flex items-center justify-center">3</span>
          <h4 class="font-semibold text-gray-800 dark:text-gray-100">综合结论</h4>
          <span class="text-xs text-gray-500 ml-2">
            by {{ getModelName(discussStore.phase3Synthesis.synthesizerId) }}
          </span>
        </div>

        <div class="glass rounded-2xl border-2 border-amber-200 dark:border-amber-500/30 p-6">
          <!-- Consensus -->
          <div class="mb-6">
            <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3 flex items-center gap-2">
              <CheckCircle2 class="w-4 h-4 text-green-500" />
              共识点
            </h5>
            <div class="space-y-2">
              <div
                v-for="(item, idx) in discussStore.phase3Synthesis.consensus"
                :key="idx"
                class="flex items-center gap-2 px-3 py-2 rounded-lg bg-green-50 dark:bg-green-500/10"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>
                <span class="text-sm text-gray-700 dark:text-gray-200">{{ item }}</span>
              </div>
            </div>
          </div>

          <!-- Disagreements -->
          <div class="mb-6">
            <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3 flex items-center gap-2">
              <AlertCircle class="w-4 h-4 text-amber-500" />
              分歧点
            </h5>
            <div class="space-y-2">
              <div
                v-for="(item, idx) in discussStore.phase3Synthesis.disagreements"
                :key="idx"
                class="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-500/10"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                <span class="text-sm text-gray-700 dark:text-gray-200">{{ item }}</span>
              </div>
            </div>
          </div>

          <!-- Recommendation -->
          <div class="bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-500/10 dark:to-orange-500/10 rounded-xl p-4">
            <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2 flex items-center gap-2">
              <Sparkles class="w-4 h-4 text-amber-500" />
              综合建议
            </h5>
            <p class="text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
              {{ discussStore.phase3Synthesis.recommendation }}
            </p>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex items-center justify-center gap-3 mt-6">
          <button
            @click="continueToChat"
            class="native-btn flex items-center gap-2 px-5 py-3 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium shadow-lg shadow-indigo-500/20"
          >
            <MessageSquare class="w-4 h-4" />
            继续对话
          </button>
          <button
            @click="reset"
            class="native-btn px-5 py-3 rounded-xl bg-gray-100 dark:bg-white/10 text-gray-600 dark:text-gray-300 font-medium"
          >
            新讨论
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useDiscussStore } from '@/stores/discuss'
import { useChatStore } from '@/stores/chat'
import { Users, ArrowRight, CheckCircle2, AlertCircle, Sparkles, MessageSquare } from 'lucide-vue-next'

const router = useRouter()
const appStore = useAppStore()
const discussStore = useDiscussStore()
const chatStore = useChatStore()

const phaseColor = computed(() => {
  switch (discussStore.currentPhase) {
    case 1: return 'bg-purple-500'
    case 2: return 'bg-pink-500'
    case 3: return 'bg-amber-500'
    default: return 'bg-gray-300'
  }
})

function getModelName(id: string) {
  return appStore.models.find(m => m.id === id)?.name || id
}

function getModelAvatar(id: string) {
  return appStore.models.find(m => m.id === id)?.avatar || '🤖'
}

function continueToChat() {
  appStore.setMode('chat')
  router.push('/workspace/chat')
}

function reset() {
  discussStore.reset()
}
</script>
