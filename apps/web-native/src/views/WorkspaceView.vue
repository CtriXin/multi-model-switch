<template>
  <div class="h-screen flex flex-col bg-surface-light dark:bg-surface-dark overflow-hidden">
    <!-- Top Navigation Bar -->
    <header class="glass border-b border-white/10 px-4 py-3 flex items-center justify-between z-50"
            style="padding-top: max(12px, var(--safe-area-top))">
      <!-- Left: Back & Title -->
      <div class="flex items-center gap-3">
        <button
          @click="goBack"
          class="native-btn p-2 rounded-xl hover:bg-white/10"
        >
          <ArrowLeft class="w-5 h-5 text-gray-600 dark:text-gray-300" />
        </button>
        <div>
          <h1 class="font-semibold text-gray-900 dark:text-white">
            {{ modeTitle }}
          </h1>
          <p class="text-xs text-gray-500">
            {{ selectedCount }} 个模型已选
          </p>
        </div>
      </div>

      <!-- Center: Mode Switcher -->
      <div class="flex items-center glass rounded-full p-1">
        <button
          @click="switchMode('chat')"
          :class="[
            'px-4 py-1.5 rounded-full text-sm font-medium transition-all',
            currentMode === 'chat'
              ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30'
              : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
          ]"
        >
          Chat
        </button>
        <button
          @click="switchMode('discuss')"
          :class="[
            'px-4 py-1.5 rounded-full text-sm font-medium transition-all',
            currentMode === 'discuss'
              ? 'bg-pink-500 text-white shadow-lg shadow-pink-500/30'
              : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
          ]"
        >
          Discuss
        </button>
      </div>

      <!-- Right: Actions -->
      <div class="flex items-center gap-2">
        <button
          @click="showModelSheet = true"
          class="native-btn flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/50 dark:bg-white/10 border border-white/20"
        >
          <Plus class="w-4 h-4 text-indigo-500" />
          <span class="text-sm text-gray-700 dark:text-gray-200">模型</span>
        </button>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="flex-1 overflow-hidden relative">
      <!-- Selected Models Pills (Floating) -->
      <div
        v-if="selectedModels.length > 0"
        class="absolute top-4 left-4 right-4 z-40 flex items-center gap-2 overflow-x-auto hide-scrollbar px-1"
      >
        <TransitionGroup name="fade-up">
          <div
            v-for="model in selectedModelObjects"
            :key="model.id"
            class="flex-shrink-0 flex items-center gap-2 px-3 py-2 rounded-full glass border border-white/30 native-btn"
            @click="removeModel(model.id)"
          >
            <span class="text-lg">{{ model.avatar }}</span>
            <span class="text-sm font-medium text-gray-800 dark:text-gray-100">{{ model.name }}</span>
            <X class="w-3.5 h-3.5 text-gray-400 hover:text-red-500" />
          </div>
        </TransitionGroup>
      </div>

      <!-- Router View for Chat/Discuss Panes -->
      <router-view v-slot="{ Component }">
        <transition name="fade-up" mode="out-in">
          <component :is="Component" :key="currentMode" />
        </transition>
      </router-view>
    </main>

    <!-- Floating Input Bar -->
    <div
      class="px-4 pb-4 z-50"
      style="padding-bottom: max(16px, var(--safe-area-bottom))"
    >
      <div class="glass rounded-2xl border border-white/20 p-2 shadow-xl shadow-black/5">
        <div class="flex items-end gap-2">
          <textarea
            v-model="inputText"
            :placeholder="inputPlaceholder"
            :disabled="isProcessing"
            rows="1"
            class="flex-1 bg-transparent px-3 py-2 text-gray-800 dark:text-gray-100 placeholder-gray-400 resize-none focus:outline-none"
            @keydown.enter.exact.prevent="submit"
            @input="autoResize"
            ref="textareaRef"
          ></textarea>
          <button
            @click="submit"
            :disabled="!canSubmit"
            :class="[
              'native-btn p-3 rounded-xl font-medium transition-all',
              canSubmit
                ? 'bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-lg shadow-indigo-500/30'
                : 'bg-gray-200 dark:bg-white/10 text-gray-400'
            ]"
          >
            <Send class="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>

    <!-- Model Selection Sheet -->
    <Teleport to="body">
      <Transition name="fade-up">
        <div
          v-if="showModelSheet"
          class="fixed inset-0 z-50 flex items-end justify-center"
        >
          <!-- Backdrop -->
          <div
            class="absolute inset-0 bg-black/30 backdrop-blur-sm"
            @click="showModelSheet = false"
          ></div>

          <!-- Sheet -->
          <div class="relative w-full max-w-lg glass rounded-t-3xl p-6 pb-8 max-h-[70vh] overflow-y-auto">
            <div class="w-12 h-1 bg-gray-300 dark:bg-gray-600 rounded-full mx-auto mb-6"></div>
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">选择模型</h3>

            <div class="grid grid-cols-2 gap-3">
              <button
                v-for="model in appStore.models"
                :key="model.id"
                @click="toggleModel(model.id)"
                :class="[
                  'native-btn p-4 rounded-2xl border-2 transition-all text-left',
                  selectedModels.includes(model.id)
                    ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/20'
                    : 'border-gray-200 dark:border-white/10 hover:border-gray-300 dark:hover:border-white/20'
                ]"
              >
                <div class="flex items-center gap-3">
                  <span class="text-2xl">{{ model.avatar }}</span>
                  <div>
                    <p class="font-medium text-gray-900 dark:text-white">{{ model.name }}</p>
                    <p class="text-xs text-gray-500">{{ model.provider }}</p>
                  </div>
                </div>
                <div class="mt-2 flex items-center gap-2">
                  <span
                    :class="[
                      'text-xs px-2 py-0.5 rounded-full',
                      model.tier === 'premium' ? 'bg-amber-100 text-amber-700' :
                      model.tier === 'standard' ? 'bg-blue-100 text-blue-700' :
                      'bg-green-100 text-green-700'
                    ]"
                  >
                    {{ model.tier }}
                  </span>
                  <span v-if="model.role" class="text-xs text-gray-400">
                    {{ model.role }}
                  </span>
                </div>
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ArrowLeft, Plus, X, Send } from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'
import { useChatStore } from '@/stores/chat'
import { useDiscussStore } from '@/stores/discuss'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const chatStore = useChatStore()
const discussStore = useDiscussStore()

const showModelSheet = ref(false)
const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement>()

const currentMode = computed(() => appStore.currentMode)
const selectedModels = computed(() => appStore.selectedModels)
const selectedModelObjects = computed(() => appStore.selectedModelObjects)
const selectedCount = computed(() => selectedModels.value.length)

const modeTitle = computed(() =>
  currentMode.value === 'chat' ? '多模型对话' : '深度讨论'
)

const inputPlaceholder = computed(() => {
  if (selectedModels.value.length < 2) return '至少选择 2 个模型...'
  if (currentMode.value === 'chat') return '向所有模型提问...'
  return '输入讨论主题...'
})

const isProcessing = computed(() =>
  currentMode.value === 'chat' ? chatStore.isStreaming : discussStore.isProcessing
)

const canSubmit = computed(() =>
  inputText.value.trim() &&
  selectedModels.value.length >= 2 &&
  !isProcessing.value
)

function switchMode(mode: 'chat' | 'discuss') {
  appStore.setMode(mode)
  router.replace({ path: `/workspace/${mode}` })
}

function toggleModel(id: string) {
  appStore.toggleModel(id)
}

function removeModel(id: string) {
  appStore.toggleModel(id)
}

function goBack() {
  chatStore.clear()
  discussStore.reset()
  appStore.selectedModels = []
  router.push('/')
}

function autoResize() {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 120) + 'px'
  }
}

async function submit() {
  if (!canSubmit.value) return

  const prompt = inputText.value.trim()
  inputText.value = ''

  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }

  if (currentMode.value === 'chat') {
    await chatStore.startStreaming(selectedModels.value, prompt)
  } else {
    await discussStore.startDiscussion(selectedModels.value, prompt)
  }
}

onMounted(() => {
  const mode = route.query.mode as string
  if (mode === 'chat' || mode === 'discuss') {
    appStore.setMode(mode)
  }
  router.replace({ path: `/workspace/${currentMode.value}` })
  nextTick(() => textareaRef.value?.focus())
})
</script>
