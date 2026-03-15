<template>
  <div class="h-[calc(100vh-4rem)] flex flex-col">
    <!-- Main Content Area -->
    <div class="flex-1 overflow-hidden">
      <!-- Empty State -->
      <div v-if="!isActive && !isStreaming" class="h-full flex flex-col items-center justify-center px-4">
        <div class="text-center max-w-lg">
          <div class="w-16 h-16 bg-purple-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
            <Users class="w-8 h-8 text-purple-600" />
          </div>
          <h2 class="text-2xl font-semibold text-gray-900 mb-2">多模型深度讨论</h2>
          <p class="text-gray-600 mb-6">
            {{ selectedModels.length > 0
              ? `已选择 ${selectedModels.length} 个模型，输入主题开始三阶段讨论`
              : '请先选择模型，输入讨论主题' }}
          </p>
          <div class="space-y-3">
            <div class="flex items-center justify-center gap-4 text-sm text-gray-500">
              <div class="flex items-center gap-2">
                <span class="w-6 h-6 bg-purple-100 text-purple-600 rounded-full flex items-center justify-center text-xs font-medium">1</span>
                方案摘要
              </div>
              <ArrowRight class="w-4 h-4" />
              <div class="flex items-center gap-2">
                <span class="w-6 h-6 bg-pink-100 text-pink-600 rounded-full flex items-center justify-center text-xs font-medium">2</span>
                交叉审查
              </div>
              <ArrowRight class="w-4 h-4" />
              <div class="flex items-center gap-2">
                <span class="w-6 h-6 bg-amber-100 text-amber-600 rounded-full flex items-center justify-center text-xs font-medium">3</span>
                综合结论
              </div>
            </div>
          </div>
          <button
            v-if="selectedModels.length === 0"
            @click="showPicker = true"
            class="mt-6 px-6 py-3 bg-purple-600 text-white rounded-xl font-medium hover:bg-purple-700 transition-colors"
          >
            选择模型
          </button>
        </div>
      </div>

      <!-- Active Discussion -->
      <div v-else class="h-full overflow-y-auto">
        <!-- Phase Progress Bar -->
        <div class="sticky top-0 z-10 bg-white/80 backdrop-blur border-b border-gray-200 px-4 py-3">
          <div class="max-w-6xl mx-auto">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-medium text-gray-900">{{ phaseNames[currentPhase] }}</h3>
              <span class="text-xs text-gray-500">
                {{ phaseProgress.current }} / {{ phaseProgress.total }}
              </span>
            </div>
            <div class="h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                class="h-full transition-all duration-300 rounded-full"
                :class="phaseColors[currentPhase]"
                :style="{ width: `${(phaseProgress.current / phaseProgress.total) * 100}%` }"
              />
            </div>
          </div>
        </div>

        <div class="max-w-6xl mx-auto p-4 space-y-6">
          <!-- User Prompt -->
          <div class="flex justify-center">
            <div class="max-w-2xl bg-purple-600 text-white rounded-2xl px-6 py-4 text-center">
              <p class="font-medium">{{ prompt }}</p>
            </div>
          </div>

          <!-- Phase 1: Summaries -->
          <div v-if="currentPhase >= 1" class="space-y-4">
            <h3 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <span class="w-8 h-8 bg-purple-100 text-purple-600 rounded-lg flex items-center justify-center text-sm">1</span>
              独立方案
            </h3>
            <div class="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
              <Phase1Card
                v-for="summary in phase1Summaries"
                :key="summary.model"
                :summary="summary"
              />
            </div>
          </div>

          <!-- Phase 2: Cross Reviews -->
          <div v-if="currentPhase >= 2 || phase2Reviews.length > 0" class="space-y-4">
            <h3 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <span class="w-8 h-8 bg-pink-100 text-pink-600 rounded-lg flex items-center justify-center text-sm">2</span>
              交叉审查
            </h3>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Phase2Card
                v-for="review in phase2Reviews"
                :key="`${review.reviewer}-${review.target}`"
                :review="review"
              />
            </div>
          </div>

          <!-- Phase 3: Synthesis -->
          <div v-if="currentPhase >= 3 || phase3Content" class="space-y-4">
            <h3 class="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <span class="w-8 h-8 bg-amber-100 text-amber-600 rounded-lg flex items-center justify-center text-sm">3</span>
              综合结论
              <span v-if="synthesizer" class="text-sm font-normal text-gray-500 ml-2">
                by {{ getModelName(synthesizer) }}
              </span>
            </h3>
            <div class="bg-white rounded-xl border border-amber-200 shadow-sm">
              <div class="p-6 prose prose-sm max-w-none markdown-body" v-html="renderedSynthesis"></div>
            </div>
          </div>

          <div class="h-8"></div>
        </div>
      </div>
    </div>

    <!-- Input Area -->
    <div v-if="!isActive && !isStreaming" class="border-t border-gray-200 bg-white p-4">
      <div class="max-w-2xl mx-auto">
        <div class="flex items-end gap-3">
          <div class="flex-1">
            <textarea
              v-model="inputText"
              placeholder="输入讨论主题，例如：如何设计一个高性能的API网关？"
              rows="3"
              class="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              @keydown.enter.prevent="handleSubmit"
            ></textarea>
          </div>
          <button
            @click="handleSubmit"
            :disabled="!canSubmit"
            class="px-6 py-3 bg-purple-600 text-white rounded-xl font-medium hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <Send class="w-4 h-4" />
            开始讨论
          </button>
        </div>
        <p v-if="selectedModels.length < 2" class="text-xs text-amber-600 mt-2">
          请至少选择 2 个模型进行讨论
        </p>
      </div>
    </div>

    <!-- Bottom Actions -->
    <div v-if="isActive && !isStreaming" class="border-t border-gray-200 bg-white p-4">
      <div class="max-w-6xl mx-auto flex items-center justify-between">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm text-gray-500">当前模型:</span>
          <span
            v-for="model in selectedModelObjects"
            :key="model.id"
            class="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded-lg"
          >
            {{ model.name }}
            <button
              @click="toggleModel(model.id)"
              class="text-gray-400 hover:text-red-500"
            >
              <X class="w-3 h-3" />
            </button>
          </span>
          <button
            @click="showPicker = true"
            class="text-xs text-purple-600 hover:text-purple-700 font-medium"
          >
            + 添加
          </button>
        </div>
        <div class="flex items-center gap-3">
          <button
            v-if="phase3Content"
            @click="continueToChat"
            class="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition-colors"
          >
            <MessageSquare class="w-4 h-4" />
            继续对话
          </button>
          <button
            @click="clearSession"
            class="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            结束讨论
          </button>
          <button
            @click="startNew"
            class="px-4 py-2 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 transition-colors"
          >
            新讨论
          </button>
        </div>
      </div>
    </div>

    <!-- Model Picker Modal -->
    <ModelPicker
      v-model:show="showPicker"
      :models="appStore.models"
      :selected="selectedModels"
      :presets="appStore.presets"
      @toggle="toggleModel"
      @apply-preset="applyPreset"
      @clear="clearSelection"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Users, ArrowRight, Send, X, MessageSquare } from 'lucide-vue-next'
import MarkdownIt from 'markdown-it'
import { useAppStore, useDiscussStore } from '@/stores'
import type { DiscussPhase } from '@mms/contracts'
import ModelPicker from '@/components/ModelPicker.vue'
import Phase1Card from '@/components/Phase1Card.vue'
import Phase2Card from '@/components/Phase2Card.vue'

const appStore = useAppStore()
const discussStore = useDiscussStore()
const router = useRouter()
const route = useRoute()

const showPicker = ref(false)
const inputText = ref('')

// Use computed to maintain reactivity
const models = computed(() => appStore.models)
// Use discuss-specific selection
const selectedModels = computed(() => appStore.discussSelectedModels)
const selectedModelObjects = computed(() => appStore.discussSelectedModelObjects)
const isActive = computed(() => discussStore.isActive)
const isStreaming = computed(() => discussStore.isStreaming)
const currentPhase = computed(() => discussStore.currentPhase)
const phaseProgress = computed(() => discussStore.phaseProgress)
const phase1Summaries = computed(() => discussStore.phase1Summaries)
const phase2Reviews = computed(() => discussStore.phase2Reviews)
const phase3Content = computed(() => discussStore.phase3Content)
const synthesizer = computed(() => discussStore.synthesizer)
const prompt = computed(() => discussStore.prompt)

const phaseNames: Record<DiscussPhase, string> = {
  1: '方案摘要阶段',
  2: '交叉审查阶段',
  3: '综合结论阶段',
}

const phaseColors: Record<DiscussPhase, string> = {
  1: 'bg-purple-500',
  2: 'bg-pink-500',
  3: 'bg-amber-500',
}

const md = new MarkdownIt()

const renderedSynthesis = computed(() => {
  return md.render(phase3Content.value)
})

const canSubmit = computed(() => {
  return inputText.value.trim() && selectedModels.value.length >= 2
})

async function handleSubmit() {
  if (!canSubmit.value) return

  const promptText = inputText.value.trim()
  inputText.value = ''

  await discussStore.startDiscuss(promptText, selectedModels.value)
}

function getModelName(modelId: string): string {
  const model = models.value.find(m => m.id === modelId)
  return model?.name || modelId
}

function toggleModel(modelId: string) {
  appStore.toggleModel('discuss', modelId)
}

function applyPreset(presetId: string) {
  appStore.applyPreset('discuss', presetId)
}

function clearSelection() {
  appStore.clearSelection('discuss')
}

function clearSession() {
  discussStore.clearSession()
}

function startNew() {
  discussStore.clearSession()
  showPicker.value = true
}

function continueToChat() {
  // Copy discuss models to chat
  appStore.copySelection('discuss', 'chat')

  // Build context from discuss results
  const context = buildDiscussContext()

  // Navigate to chat with context
  router.push({
    path: '/chat',
    query: { context: encodeURIComponent(context) }
  })
}

function buildDiscussContext(): string {
  const parts: string[] = []

  // Original prompt
  if (prompt.value) {
    parts.push(`【讨论主题】${prompt.value}\n`)
  }

  // Phase 1 summaries
  if (phase1Summaries.value.length > 0) {
    parts.push('【各模型方案摘要】')
    for (const summary of phase1Summaries.value) {
      const modelName = getModelName(summary.model)
      if (summary.brief) {
        parts.push(`${modelName}：`)
        if (summary.brief.approach) parts.push(`  方案：${summary.brief.approach}`)
        if (summary.brief.reasoning) parts.push(`  理由：${summary.brief.reasoning}`)
      }
    }
    parts.push('')
  }

  // Phase 2 reviews (optional, summarize)
  if (phase2Reviews.value.length > 0) {
    parts.push(`【交叉审查要点】共 ${phase2Reviews.value.length} 条审查意见\n`)
  }

  // Phase 3 synthesis
  if (phase3Content.value) {
    parts.push('【综合结论】')
    parts.push(phase3Content.value.slice(0, 1500))
    if (phase3Content.value.length > 1500) {
      parts.push('...(truncated)')
    }
  }

  parts.push('\n---\n请基于以上讨论结论，继续深入探讨或执行具体方案。')

  return parts.join('\n')
}

// Handle context from Chat
onMounted(() => {
  const contextFromChat = route.query.context as string | undefined
  if (contextFromChat) {
    const decodedContext = decodeURIComponent(contextFromChat)
    // Pre-fill the prompt with context
    inputText.value = decodedContext
    // Clear query params
    router.replace({ path: '/discuss' })
  }
})
</script>
