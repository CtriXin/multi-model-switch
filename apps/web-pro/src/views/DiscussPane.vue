<template>
  <div class="h-full flex flex-col">
    <!-- Content -->
    <div class="flex-1 overflow-y-auto">
      <!-- Empty State -->
      <div v-if="!store.isActive && !store.isStreaming" class="h-full flex flex-col items-center justify-center px-6">
        <div class="text-center max-w-md animate-fade-in">
          <div class="w-12 h-12 rounded-2xl bg-purple-50 flex items-center justify-center mx-auto mb-4">
            <Users class="w-6 h-6 text-purple-600" />
          </div>
          <h2 class="text-lg font-semibold text-gray-900 mb-1.5">多模型深度讨论</h2>
          <p class="text-sm text-gray-500 mb-6">
            三阶段结构化讨论：独立方案 → 交叉审查 → 综合结论
          </p>

          <!-- Phase Indicators -->
          <div class="flex items-center justify-center gap-3 mb-6">
            <div v-for="(phase, i) in phases" :key="i" class="flex items-center gap-2">
              <div class="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-semibold"
                :class="phase.bgClass">
                {{ i + 1 }}
              </div>
              <span class="text-xs text-gray-600">{{ phase.name }}</span>
              <ChevronRight v-if="i < 2" class="w-3 h-3 text-gray-300" />
            </div>
          </div>
        </div>
      </div>

      <!-- Active Discussion -->
      <div v-else class="max-w-5xl mx-auto px-4 py-6">
        <!-- Phase Timeline -->
        <div class="relative">
          <!-- Timeline Line -->
          <div class="absolute left-5 top-0 bottom-0 w-px bg-gray-200" />

          <!-- User Prompt -->
          <div class="relative flex items-start gap-4 mb-8 animate-slide-up">
            <div class="w-10 h-10 rounded-full bg-purple-600 flex items-center justify-center flex-shrink-0 z-10 shadow-sm">
              <MessageSquare class="w-4 h-4 text-white" />
            </div>
            <div class="flex-1 bg-purple-50 rounded-xl px-4 py-3 mt-1 border border-purple-100">
              <p class="text-sm font-medium text-purple-900">{{ store.prompt }}</p>
            </div>
          </div>

          <!-- Phase 1: Independent Summaries -->
          <PhaseSection
            :phase="1"
            title="独立方案"
            :current="store.currentPhase"
            :status="store.currentPhase > 1 ? 'done' : store.currentPhase === 1 ? 'running' : 'waiting'"
            color-class="bg-purple-500"
          >
            <div class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
              <SummaryCard
                v-for="summary in store.phase1Summaries"
                :key="summary.model"
                :summary="summary"
                :model-name="appStore.getModelName(summary.model)"
              />
            </div>
          </PhaseSection>

          <!-- Phase 2: Cross Reviews -->
          <PhaseSection
            v-if="store.currentPhase >= 2 || store.phase2Reviews.length > 0"
            :phase="2"
            title="交叉审查"
            :current="store.currentPhase"
            :status="store.currentPhase > 2 ? 'done' : store.currentPhase === 2 ? 'running' : 'waiting'"
            color-class="bg-pink-500"
          >
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <ReviewCard
                v-for="(review, i) in store.phase2Reviews"
                :key="i"
                :review="review"
                :reviewer-name="appStore.getModelName(review.reviewer)"
                :target-name="appStore.getModelName(review.target)"
              />
            </div>
          </PhaseSection>

          <!-- Phase 3: Synthesis -->
          <PhaseSection
            v-if="store.currentPhase >= 3 || store.phase3Content"
            :phase="3"
            title="综合结论"
            :subtitle="store.synthesizer ? `by ${appStore.getModelName(store.synthesizer)}` : ''"
            :current="store.currentPhase"
            :status="store.phaseStatus === 'completed' ? 'done' : 'running'"
            color-class="bg-amber-500"
          >
            <div class="bg-white rounded-xl border border-amber-200 shadow-card overflow-hidden">
              <div class="px-5 py-4 prose-chat text-sm" v-html="renderedSynthesis" />
              <div v-if="store.isStreaming && store.currentPhase === 3" class="px-5 pb-3">
                <span class="inline-flex gap-1">
                  <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-typing" style="animation-delay:0s" />
                  <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-typing" style="animation-delay:0.2s" />
                  <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-typing" style="animation-delay:0.4s" />
                </span>
              </div>
            </div>
          </PhaseSection>
        </div>

        <div class="h-8" />
      </div>
    </div>

    <!-- Input / Actions Area -->
    <div class="border-t border-gray-200/60 bg-white safe-bottom">
      <!-- Before start -->
      <div v-if="!store.isActive && !store.isStreaming" class="px-4 py-3">
        <div class="max-w-3xl mx-auto">
          <!-- Model Chips -->
          <div class="flex items-center gap-1.5 flex-wrap mb-2">
            <ModelChip
              v-for="model in appStore.discussSelectedModelObjects"
              :key="model.id"
              :model="model"
              removable
              @remove="appStore.toggleModel('discuss', model.id)"
            />
            <button
              @click="showModelSheet = true"
              class="inline-flex items-center gap-1 px-2 py-1 text-[11px] text-purple-600 hover:bg-purple-50 rounded-md transition-colors"
            >
              <Plus class="w-3 h-3" />
              模型
            </button>
          </div>
          <div class="flex items-end gap-2">
            <div class="flex-1 bg-gray-50 rounded-xl border border-gray-200 focus-within:border-purple-400 focus-within:ring-2 focus-within:ring-purple-100 transition-all">
              <textarea
                v-model="inputText"
                placeholder="输入讨论主题，例如：如何设计一个高性能的 API 网关？"
                rows="2"
                class="w-full px-4 py-2.5 bg-transparent text-sm resize-none focus:outline-none max-h-[100px]"
                @keydown="handleKeydown"
              />
            </div>
            <button
              @click="handleSubmit"
              :disabled="!canSubmit"
              class="px-4 py-2.5 bg-purple-600 text-white text-sm font-medium rounded-xl hover:bg-purple-700 disabled:opacity-40 transition-colors flex items-center gap-1.5"
            >
              <Sparkles class="w-3.5 h-3.5" />
              开始讨论
            </button>
          </div>
        </div>
      </div>

      <!-- After complete -->
      <div v-else-if="store.isActive && !store.isStreaming" class="px-4 py-3">
        <div class="max-w-5xl mx-auto flex items-center justify-between">
          <div class="flex items-center gap-2 text-sm text-gray-500">
            <CheckCircle class="w-4 h-4 text-green-500" />
            讨论完成
          </div>
          <div class="flex items-center gap-2">
            <button
              @click="continueToChat"
              class="px-3 py-1.5 text-sm font-medium text-accent-600 hover:bg-accent-50 rounded-lg transition-colors flex items-center gap-1.5"
            >
              <MessageSquare class="w-3.5 h-3.5" />
              继续对话
            </button>
            <button
              @click="store.clearSession()"
              class="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            >
              结束
            </button>
            <button
              @click="startNew"
              class="px-3 py-1.5 text-sm font-medium text-purple-600 bg-purple-50 hover:bg-purple-100 rounded-lg transition-colors"
            >
              新讨论
            </button>
          </div>
        </div>
      </div>

      <!-- Streaming indicator -->
      <div v-else class="px-4 py-3">
        <div class="max-w-5xl mx-auto flex items-center gap-3 text-sm text-gray-500">
          <Loader2 class="w-4 h-4 animate-spin text-purple-500" />
          <span>{{ phaseNames[store.currentPhase] }}中...</span>
          <span class="text-xs text-gray-400">
            {{ store.phaseProgress.current }}/{{ store.phaseProgress.total }}
          </span>
        </div>
      </div>
    </div>

    <ModelSheet v-model:open="showModelSheet" mode="discuss" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import MarkdownIt from 'markdown-it'
import {
  Users, MessageSquare, ChevronRight, Plus, Sparkles,
  CheckCircle, Loader2,
} from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'
import { useDiscussStore } from '@/stores/discuss'
import type { DiscussPhase } from '@mms/contracts'
import ModelChip from '@/components/ModelChip.vue'
import ModelSheet from '@/components/ModelSheet.vue'
import PhaseSection from '@/components/PhaseSection.vue'
import SummaryCard from '@/components/SummaryCard.vue'
import ReviewCard from '@/components/ReviewCard.vue'

const appStore = useAppStore()
const store = useDiscussStore()
const router = useRouter()

const inputText = ref('')
const showModelSheet = ref(false)

const phases = [
  { name: '方案摘要', bgClass: 'bg-purple-100 text-purple-600' },
  { name: '交叉审查', bgClass: 'bg-pink-100 text-pink-600' },
  { name: '综合结论', bgClass: 'bg-amber-100 text-amber-600' },
]

const phaseNames: Record<DiscussPhase, string> = {
  1: '方案摘要阶段',
  2: '交叉审查阶段',
  3: '综合结论生成',
}

const md = new MarkdownIt()
const renderedSynthesis = computed(() => md.render(store.phase3Content))

const canSubmit = computed(() =>
  inputText.value.trim() && appStore.discussSelectedModels.length >= 2
)

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSubmit()
  }
}

async function handleSubmit() {
  if (!canSubmit.value) return
  const prompt = inputText.value.trim()
  inputText.value = ''
  await store.startDiscuss(prompt, appStore.discussSelectedModels)
}

function continueToChat() {
  appStore.copySelection('discuss', 'chat')
  router.push('/chat')
}

function startNew() {
  store.clearSession()
}
</script>
