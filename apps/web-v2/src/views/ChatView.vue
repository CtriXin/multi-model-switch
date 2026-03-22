<script setup lang="ts">
import { ref, nextTick, computed, inject, reactive, watch, onMounted, onUnmounted } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore, getModelColor } from '@/stores/app'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toast'
import { useTheme } from '@/composables/useTheme'
import InputBar from '@/components/chat/InputBar.vue'
import ModelChipBar from '@/components/chat/ModelChipBar.vue'
import ModelResponseCard from '@/components/chat/ModelResponseCard.vue'
import ChatSummary from '@/components/ChatSummary.vue'
import InlineDiscuss from '@/components/InlineDiscuss.vue'
import { startWindowDrag } from '@/utils/windowDrag'
import type { ImageAttachment } from '@/stores/chat'
import { getExperienceMode } from '@/utils/experienceMode'
import { CHAT_PROMPT_EXAMPLES } from '@/data/inputExamples'
import { useRotatingPrompt } from '@/composables/useRotatingPrompt'
import { Sparkles, LayoutGrid, List, GalleryHorizontalEnd, MessageSquare, Plus, TextQuote, Check, ChevronDown, CheckCircle2, Menu, Sun, Moon, Layers, Zap, Target, History } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const chatStore = useChatStore()
const sessionStore = useSessionStore()
const toast = useToastStore()
const { theme, toggle: toggleTheme } = useTheme()
const platform = inject<import('vue').Ref<string>>('platform')
const restoredDraft = ref('')
const experienceMode = ref(getExperienceMode())

const scrollContainer = ref<HTMLElement>()
const hasRounds = computed(() => chatStore.currentRound && !chatStore.streaming)

// --- Dynamic layout mode ---
// 'single': 1 model, centered chat
// 'grid': 2-3 models, side-by-side
// 'horizontal': 4+ models, scroll
const layoutMode = computed(() => {
  const count = chatStore.activeModelIds.length || appStore.selectedModelIds.length
  if (count === 1) return 'single'
  if (count <= 3) return 'grid'
  return 'horizontal'
})

function syncActiveModels(modelIds: string[]) {
  if (
    modelIds.length === chatStore.activeModelIds.length
    && modelIds.every((id, index) => chatStore.activeModelIds[index] === id)
  ) {
    return
  }

  chatStore.initActiveModels(modelIds)
}

// Keep next-round chat models in sync with the chip selection.
watch(() => [...appStore.selectedModelIds], (newIds) => {
  syncActiveModels(newIds)
}, { immediate: true })

// Mobile view mode: 'horizontal' (carousel) or 'vertical'
type MobileViewMode = 'horizontal' | 'vertical'
const mobileViewMode = ref<MobileViewMode>('horizontal')

// --- Header state ---
const showContextMenu = ref(false)
const headerContextMenuRef = ref<HTMLElement | null>(null)

onClickOutside(headerContextMenuRef, () => {
  showContextMenu.value = false
})

function openDrawer() {
  window.dispatchEvent(new CustomEvent('open-drawer'))
}

function openModels() {
  window.dispatchEvent(new CustomEvent('open-models'))
}

// --- Inline discuss state ---
const inlineDiscussRound = ref<string | null>(null)
const summaryActiveRound = reactive<Record<string, boolean>>({})

function startNewChat() {
  sessionStore.createSession('chat')
  chatStore.rounds.length = 0
  router.push('/chat')
}

function startInlineDiscuss(roundId: string) {
  inlineDiscussRound.value = roundId
  // Don't scroll — keep user at their current position.
  // After DOM update, gently scroll the discuss panel into view without jumping.
  nextTick(() => {
    const el = document.getElementById(`inline-discuss-${roundId}`)
    if (el) {
      // Only scroll if the discuss panel is below the viewport
      const rect = el.getBoundingClientRect()
      const container = scrollContainer.value
      if (container && rect.top > container.clientHeight) {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
    }
  })
}

// Either summary or discuss has been expanded for this round
function isAnyPanelActive(roundId: string): boolean {
  const round = chatStore.rounds.find((item) => item.id === roundId)
  return !!summaryActiveRound[roundId] || !!round?.judge?.content || inlineDiscussRound.value === roundId
}

function hasInlineDiscussState(round: typeof chatStore.rounds[0]): boolean {
  return !!round.inlineDiscuss && round.inlineDiscuss.phase > 0
}

// --- Tab bar viewing state (separate from selection) ---
// After user selects a model, clicking other tabs only changes viewing, not selection
const viewingModelId = reactive<Record<string, string | null>>({})

function getViewingModelId(round: typeof chatStore.rounds[0]): string {
  // Show the viewing override if set, otherwise show selected
  const viewingId = viewingModelId[round.id]
  if (viewingId && round.responses.has(viewingId)) return viewingId
  return round.activeModelId ?? Array.from(round.responses.keys())[0] ?? ''
}

function switchViewingModel(roundId: string, modelId: string) {
  viewingModelId[roundId] = modelId
}

// --- Auto-scroll: follow content growth, pause when user scrolls up ---
let userScrolledUp = false
let lastScrollTop = 0
let lastScrollHeight = 0
let observer: MutationObserver | null = null

function scrollToBottom() {
  const el = scrollContainer.value
  if (!el) return
  userScrolledUp = false
  el.scrollTop = el.scrollHeight
}

function onScroll() {
  const el = scrollContainer.value
  if (!el) return
  // User scrolled up intentionally
  if (el.scrollTop < lastScrollTop - 30) {
    userScrolledUp = true
  }
  // User scrolled back near bottom → resume
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
    userScrolledUp = false
  }
  lastScrollTop = el.scrollTop
}

// Start observer as soon as scroll container exists
onMounted(() => {
  const el = scrollContainer.value
  if (!el) return

  observer = new MutationObserver(() => {
    if (!el) return
    const newHeight = el.scrollHeight
    // Only auto-scroll if content actually grew (not just DOM re-render)
    if (newHeight > lastScrollHeight && !userScrolledUp) {
      el.scrollTop = newHeight
      lastScrollTop = newHeight
    }
    lastScrollHeight = newHeight
  })
  observer.observe(el, { childList: true, subtree: true, characterData: true })
})

onUnmounted(() => { observer?.disconnect() })

// --- Context from discuss "继续对话" ---
onMounted(() => {
  const ctx = route.query.context as string
  if (ctx && hasActiveModels.value) {
    // Clear query param to avoid re-submit on refresh
    router.replace({ path: '/chat', query: {} })
    nextTick(() => handleSubmit(ctx))
  }
})

// --- Desktop horizontal mode active card ---
const desktopHActive = reactive<Record<string, number>>({})

function getDesktopHActive(roundId: string): number {
  return desktopHActive[roundId] ?? 0
}

function isRoundDone(round: typeof chatStore.rounds[0]): boolean {
  return Array.from(round.responses.values()).every(msg => !!msg.elapsed)
}

// --- Swipe carousel state ---
const CARD_WIDTH_PCT = 100 // card occupies full width
const activeCardIndex = reactive<Record<string, number>>({})
const dragOffset = reactive<Record<string, number>>({}) // px offset during drag
const isDragging = reactive<Record<string, boolean>>({})

// Per-round touch state (not reactive — perf)
const touchState: Record<string, { startX: number; startY: number; startTime: number; locked: boolean | null }> = {}

function getActiveIndex(roundId: string): number {
  return activeCardIndex[roundId] ?? 0
}

function setActiveIndex(roundId: string, idx: number) {
  activeCardIndex[roundId] = idx
}

function getTransform(roundId: string): string {
  const idx = getActiveIndex(roundId)
  const drag = dragOffset[roundId] ?? 0
  return `translateX(calc(${-idx * CARD_WIDTH_PCT}% + ${drag}px))`
}

function onTouchStart(roundId: string, e: TouchEvent) {
  const t = e.touches[0]
  touchState[roundId] = { startX: t.clientX, startY: t.clientY, startTime: Date.now(), locked: null }
  dragOffset[roundId] = 0
  isDragging[roundId] = false
}

function onTouchMove(roundId: string, e: TouchEvent, totalCards: number) {
  const state = touchState[roundId]
  if (!state) return

  const t = e.touches[0]
  const dx = t.clientX - state.startX
  const dy = t.clientY - state.startY

  // First significant movement: decide if horizontal or vertical scroll
  if (state.locked === null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
    state.locked = Math.abs(dx) > Math.abs(dy) // true = horizontal swipe
  }

  if (state.locked !== true) return // let vertical scroll happen

  isDragging[roundId] = true
  const current = getActiveIndex(roundId)

  // Rubber-band at edges
  let offset = dx
  if ((current === 0 && dx > 0) || (current === totalCards - 1 && dx < 0)) {
    offset = dx * 0.25 // dampen overscroll
  }

  dragOffset[roundId] = offset
}

function onTouchEnd(roundId: string, totalCards: number) {
  const state = touchState[roundId]
  if (!state) return

  const dx = dragOffset[roundId] ?? 0
  const dt = Date.now() - state.startTime
  const current = getActiveIndex(roundId)

  // Determine swipe: threshold 40px or fast flick (25px in < 250ms)
  const isSwipe = Math.abs(dx) > 40 || (Math.abs(dx) > 25 && dt < 250)

  if (isSwipe) {
    if (dx < 0 && current < totalCards - 1) {
      setActiveIndex(roundId, current + 1)
    } else if (dx > 0 && current > 0) {
      setActiveIndex(roundId, current - 1)
    }
  }

  // Reset drag
  dragOffset[roundId] = 0
  // Small delay before removing dragging flag so transition plays
  setTimeout(() => { isDragging[roundId] = false }, 20)
  delete touchState[roundId]
}

// --- Other ---
const contextTip = ref('')
let contextTipTimer: ReturnType<typeof setTimeout> | null = null

function showContextTip(msg: string) {
  contextTip.value = msg
  if (contextTipTimer) clearTimeout(contextTipTimer)
  contextTipTimer = setTimeout(() => { contextTip.value = '' }, 3500)
}

const previewImage = ref<string | null>(null)

function openImagePreview(src: string) {
  previewImage.value = src
}

const hasActiveModels = computed(() => chatStore.activeModelIds.length > 0)
const canUseSamplePrompt = computed(() =>
  hasActiveModels.value
  && !chatStore.streaming
  && (experienceMode.value === 'demo' || chatStore.rounds.length === 0),
)
const rotatingChatPrompt = useRotatingPrompt(CHAT_PROMPT_EXAMPLES, canUseSamplePrompt)
const samplePrompt = computed(() => canUseSamplePrompt.value ? rotatingChatPrompt.value : '')

const inputPlaceholder = computed(() => {
  if (!hasActiveModels.value) return '请先选择模型...'
  if (samplePrompt.value) return `试试：${samplePrompt.value}`
  if (chatStore.isSingleChat) return '和 AI 聊聊...'
  return `发给 ${chatStore.activeModelIds.length} 个模型...`
})

// Keep viewMode for multi-chat layout (grid/horizontal/vertical)
type ViewMode = 'grid' | 'horizontal' | 'vertical'
const viewMode = ref<ViewMode>(layoutMode.value === 'horizontal' ? 'horizontal' : 'grid')

// Watch for layout mode changes to sync viewMode
watch(layoutMode, (mode) => {
  if (mode === 'grid') viewMode.value = 'grid'
  else if (mode === 'horizontal') viewMode.value = 'horizontal'
})

async function handleSubmit(text: string, attachments: ImageAttachment[] = []) {
  restoredDraft.value = ''
  if (!hasActiveModels.value) {
    toast.info('先选个模型呗')
    return
  }
  // Warn if previous round has no selection
  if (chatStore.rounds.length > 0 && chatStore.isMultiChat) {
    const lastRound = chatStore.rounds[chatStore.rounds.length - 1]
    if (!lastRound.activeModelId && isRoundDone(lastRound)) {
      if (chatStore.contextMode === 'selected') {
        showContextTip('上一轮未选择回答，该轮不纳入上下文')
      } else {
        showContextTip('上一轮未选择，自动使用首个模型回答')
      }
    }
  }
  if (!sessionStore.currentSessionId) {
    sessionStore.createSession('chat')
  }
  // Fire and don't await — scroll immediately after DOM update
  chatStore.sendMessage(text, chatStore.activeModelIds, attachments).then(() => {
    sessionStore.saveCurrentSession()
  })
  // Scroll to the new message after it appears in DOM
  await nextTick()
  scrollToBottom()
}

function handleStopAndEdit() {
  restoredDraft.value = chatStore.stopAndRestoreDraft()
}

async function restorePrompt(prompt: string) {
  restoredDraft.value = ''
  await nextTick()
  restoredDraft.value = prompt
  toast.info('内容已恢复，改改再发')
}

async function retryRoundModel(round: typeof chatStore.rounds[0], modelId: string) {
  await chatStore.retryModel(round.id, modelId)
  sessionStore.saveCurrentSession()
}

async function replaceRoundModel(round: typeof chatStore.rounds[0], oldModelId: string) {
  window.dispatchEvent(new CustomEvent('open-model-picker', {
    detail: {
      mode: 'replace',
      roundId: round.id,
      oldModelId,
      requireVision: !!round.attachments?.length,
    },
  }))
}

async function randomReplaceModel(round: typeof chatStore.rounds[0], oldModelId: string) {
  // Collect already-successful model IDs in this round
  const successfulIds = Array.from(round.responses.entries())
    .filter(([, msg]) => msg.elapsed && !msg.error)
    .map(([id]) => id)

  const newModelId = appStore.pickReplacementModel({
    excludeIds: [...successfulIds, oldModelId],
    requireVision: !!round.attachments?.length,
  })

  if (!newModelId) {
    toast.info('暂无可用的模型换')
    return
  }

  await chatStore.retryModel(round.id, oldModelId, { replaceWith: newModelId })
  sessionStore.saveCurrentSession()
}

function getModelName(id: string): string {
  return appStore.models.find(m => m.id === id)?.name ?? id
}

function getProvider(id: string): string {
  return appStore.models.find(m => m.id === id)?.provider ?? 'unknown'
}

function getTier(id: string): number {
  return appStore.models.find(m => m.id === id)?.tier ?? 0
}

// A round has a selection if activeModelId is set and responses are done
function hasSelection(round: typeof chatStore.rounds[0]): boolean {
  return !!round.activeModelId && isRoundDone(round)
}

// Get model IDs for a round (backward compatible with old data)
function getRoundModelIds(round: typeof chatStore.rounds[0]): string[] {
  // Use saved modelIds if available, otherwise fallback to responses keys
  return round.modelIds?.length ? round.modelIds : Array.from(round.responses.keys())
}

const gridClass = computed(() => {
  const count = appStore.selectedModels.length
  if (count <= 2) return 'grid-cols-1 sm:grid-cols-2'
  if (count <= 3) return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
  return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
})

const isMobile = computed(() => platform?.value === 'ios')

// --- Archive: settled rounds collapse to selected card + dots ---
function isSettled(ri: number): boolean {
  return isMobile.value && ri < chatStore.rounds.length - 1
}

function getDisplayedModelId(round: typeof chatStore.rounds[0]): string {
  return round.activeModelId ?? Array.from(round.responses.keys())[0]
}

function getArchivedModels(round: typeof chatStore.rounds[0]): string[] {
  const displayed = getDisplayedModelId(round)
  return Array.from(round.responses.keys()).filter(id => id !== displayed)
}

function switchArchivedModel(round: typeof chatStore.rounds[0], modelId: string) {
  chatStore.setActiveModel(round.id, modelId)
}

function hasModelError(round: typeof chatStore.rounds[0], modelId: string): boolean {
  return !!round.responses.get(modelId)?.error
}
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">
    <!-- Group 1: Floating Capsule Header (V3 SPEC Style) -->
    <div class="z-40 px-4 pt-4 pb-2 shrink-0">
      <header
        data-tauri-drag-region
        class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10"
        @mousedown.left="startWindowDrag">

        <!-- Left: Sidebar Breadcrumb & Info -->
        <div class="flex items-center gap-1 sm:gap-3 min-w-0">
          <button @click="openDrawer"
            class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors sm:hidden">
            <Menu :size="18" />
          </button>

          <div class="flex items-center gap-3 min-w-0 ml-1">
            <div
              class="flex items-center justify-center w-8 h-8 rounded-full bg-accent text-white shadow-lg shrink-0">
              <MessageSquare :size="16" />
            </div>
            <div class="min-w-0">
              <h1 class="text-sm font-black text-text-primary truncate tracking-tight">
                {{ sessionStore.currentSession?.title || '聊天' }}
              </h1>
              <p
                class="text-[9px] text-text-tertiary font-black uppercase tracking-widest opacity-50 hidden sm:block">
                聊过 {{ chatStore.rounds.length }} 轮 · {{ chatStore.activeModelIds.length }} 个模型
                <span v-if="chatStore.isSingleChat" class="text-accent">(单聊)</span>
                <span v-else-if="chatStore.isMultiChat" class="text-accent">(对比)</span>
              </p>
            </div>
          </div>
        </div>

        <!-- Right: Control Suite -->
        <div class="flex items-center gap-2">
          <!-- Model Library -->
          <button @click="openModels"
            class="relative p-2 sm:px-3 sm:py-2 rounded-full bg-white/5 text-text-secondary flex items-center gap-2 hover:bg-white/10 transition-all border border-white/5">
            <Layers :size="18" class="text-accent" />
            <span
              class="hidden sm:inline text-[10px] font-black uppercase tracking-widest ml-0.5">选模型</span>
            <span v-if="appStore.selectedModels.length"
              class="absolute -top-1.5 -right-1.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-accent px-1 text-[9px] font-black text-white shadow-sm ring-2 ring-surface-1">
              {{ appStore.selectedModels.length }}
            </span>
          </button>

          <!-- Context Mode -->
          <div ref="headerContextMenuRef" class="relative">
            <button @click="showContextMenu = !showContextMenu"
              class="flex items-center gap-1.5 p-2 sm:px-3 sm:py-2 rounded-full text-[10px] font-black uppercase tracking-widest
                     bg-white/5 text-text-secondary hover:bg-white/10 transition-all border border-white/5">
              <component
                :is="{ summary: Zap, selected: Target, full: History }[chatStore.contextMode]"
                :size="18" :stroke-width="3" class="text-accent" />
              <span
                class="hidden sm:inline ml-0.5">{{ { summary: '只带重点', selected: '只带选中的回答', full: '全带上' }[chatStore.contextMode] }}</span>
              <ChevronDown :size="10" class="opacity-40" />
            </button>

            <Transition name="popover">
              <div v-if="showContextMenu"
                class="absolute right-0 top-full mt-3 w-40 rounded-[28px] border border-white/10 bg-surface-1 shadow-2xl z-50 p-1.5 flex flex-col gap-1">
                <button
                  v-for="mode in [{k:'summary',l:'只带重点',i:Zap},{k:'selected',l:'只带选中的回答',i:Target},{k:'full',l:'全带上',i:History}]"
                  :key="mode.k"
                  @click="chatStore.contextMode = mode.k as any; showContextMenu = false"
                  class="w-full px-4 py-2.5 text-left flex items-center gap-3 rounded-[20px] transition-all"
                  :class="chatStore.contextMode === mode.k ? 'bg-accent/10 text-accent' : 'text-text-secondary hover:bg-white/5'">
                  <component :is="mode.i" :size="16" :stroke-width="3" />
                  <span class="text-[10px] font-black uppercase tracking-widest">{{ mode.l }}</span>
                </button>
              </div>
            </Transition>
          </div>

          <!-- New Chat -->
          <button @click="startNewChat"
            class="p-2 sm:px-4 sm:py-2 rounded-full bg-accent text-white shadow-xl shadow-accent/30 hover:scale-105 active:scale-95 transition-all flex items-center gap-2">
            <Plus :size="18" :stroke-width="4" />
            <span
              class="hidden sm:inline text-[10px] font-black uppercase tracking-widest">新开一个</span>
          </button>
        </div>
      </header>
    </div>

    <!-- Current selection bar (Desktop inline) -->
    <div v-if="chatStore.activeModelIds.length > 0"
      class="max-w-6xl mx-auto w-full px-4 flex items-center justify-between gap-4 mt-2 mb-2">

      <!-- Left: Models List -->
      <div class="flex items-center gap-2 overflow-x-auto no-scrollbar min-w-0">
        <span
          class="text-[10px] font-black text-text-tertiary uppercase tracking-widest shrink-0 opacity-40">
          {{ chatStore.isSingleChat ? '正在聊:' : '正在用:' }}
        </span>
        <div class="flex items-center gap-1.5">
          <span v-for="modelId in chatStore.activeModelIds" :key="modelId"
            class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[10px] font-black uppercase tracking-tight whitespace-nowrap shrink-0 border border-white/5"
            :style="{ backgroundColor: getModelColor(getProvider(modelId)) + '10', color: getModelColor(getProvider(modelId)) }">
            <span class="w-1.5 h-1.5 rounded-full"
              :style="{ backgroundColor: getModelColor(getProvider(modelId)) }" />
            {{ getModelName(modelId) }}
          </span>
          <!-- Add hint for single chat -->
          <span v-if="chatStore.isSingleChat && chatStore.canAddModel()"
            class="text-[10px] text-text-tertiary opacity-60 italic">
            （点击底部 + 添加模型对比）
          </span>
        </div>
      </div>

      <!-- Right: View mode toggle (only for multi-chat) -->
      <div v-if="chatStore.isMultiChat" class="inline-flex items-center gap-0.5 rounded-xl shrink-0">
        <!-- Desktop: grid / horizontal / vertical -->
        <template v-if="!isMobile">
          <button v-for="mode in (['grid', 'horizontal', 'vertical'] as const)" :key="mode"
            @click="viewMode = mode" class="p-1.5 rounded-lg transition-all"
            :class="viewMode === mode ? 'bg-surface-2 shadow-sm text-text-primary' : 'text-text-tertiary hover:text-text-secondary hover:bg-surface-2/50'"
            :title="mode === 'grid' ? '并排' : mode === 'horizontal' ? '横向滑动' : '纵向'">
            <component
              :is="mode === 'grid' ? LayoutGrid : mode === 'horizontal' ? GalleryHorizontalEnd : List"
              :size="14" />
          </button>
        </template>
        <!-- Mobile: horizontal / vertical -->
        <template v-else>
          <button v-for="mode in (['horizontal', 'vertical'] as const)" :key="mode"
            @click="mobileViewMode = mode" class="p-1.5 rounded-lg transition-all"
            :class="mobileViewMode === mode ? 'bg-surface-2 shadow-sm text-text-primary' : 'text-text-tertiary hover:text-text-secondary hover:bg-surface-2/50'">
            <component :is="mode === 'horizontal' ? GalleryHorizontalEnd : List" :size="14" />
          </button>
        </template>
      </div>
    </div>

    <!-- Chat history -->
    <div ref="scrollContainer" class="flex-1 overflow-y-auto" @scroll.passive="onScroll">
      <!-- Empty state -->
      <div v-if="!chatStore.rounds.length"
        class="flex flex-col items-center justify-center h-[calc(100vh-14rem)] text-center px-6">
        <div
          class="w-16 h-16 rounded-[32px] bg-accent/10 flex items-center justify-center mb-6 animate-v3-fade-in shadow-2xl shadow-accent/20">
          <Sparkles :size="32" class="text-accent" />
        </div>
        <h2 class="text-2xl font-black text-text-primary mb-3 tracking-tighter">
          {{ chatStore.isSingleChat ? '问 AI' : '问一次，最多五份答卷' }}
        </h2>
        <p class="text-sm text-text-secondary max-w-sm opacity-60 leading-relaxed mx-auto">
          {{ chatStore.isSingleChat
            ? '和一个 AI 深度对话，随时点击 + 添加更多模型对比答案。'
            : '同一个问题交给多个模型，并排比较后选出最佳回答。选中后还能继续追问，上下文自动接力。'
          }}
        </p>
      </div>

      <!-- Rounds -->
      <div v-else class="mx-auto py-4 space-y-10"
        :class="isMobile ? 'max-w-lg px-4' : 'max-w-6xl px-4'">
        <div v-for="(round, ri) in chatStore.rounds" :key="round.id" :id="'round-' + round.id"
          class="animate-slide-up" :style="{ animationDelay: ri * 30 + 'ms' }">
          <!-- User prompt -->
          <div class="flex justify-end mb-4">
            <div class="max-w-[85%]">
              <!-- Attached images -->
              <div v-if="round.attachments?.length" class="flex gap-1.5 justify-end mb-1.5">
                <img v-for="img in round.attachments" :key="img.id" :src="img.dataUrl"
                  :alt="img.name"
                  class="h-20 w-20 object-cover rounded-lg border border-white/10 cursor-pointer hover:opacity-80 transition-opacity"
                  @click="openImagePreview(img.dataUrl)" />
              </div>
              <div class="px-4 py-2.5 rounded-2xl rounded-br-md bg-accent text-white text-sm">
                {{ round.prompt }}
              </div>
            </div>
          </div>

          <!-- Desktop responses -->
          <template v-if="!isMobile">
            <!-- Single chat mode: centered, full-width conversation -->
            <div v-if="getRoundModelIds(round).length === 1" class="max-w-3xl mx-auto">
              <div
                v-for="[singleModelId, msg] of round.responses"
                :key="singleModelId"
              >
                <ModelResponseCard
                  :model-id="singleModelId"
                  :model-name="getModelName(singleModelId)"
                  :provider="getProvider(singleModelId)"
                  :tier="getTier(singleModelId)"
                  :content="msg.content"
                  :elapsed="msg.elapsed"
                  :error="msg.error"
                  :error-code="msg.errorCode"
                  :brief="msg.brief"
                  :streaming="!!msg.streaming"
                  :single-mode="true"
                  @retry="retryRoundModel(round, singleModelId)"
                  @replace="replaceRoundModel(round, singleModelId)"
                  @random-replace="randomReplaceModel(round, singleModelId)"
                />
              </div>
              <!-- Summary for single chat (no discuss) -->
              <template v-if="isRoundDone(round)">
                <div class="mt-4">
                  <ChatSummary
                    :round-id="round.id"
                    :prompt="round.prompt"
                    :responses="round.responses"
                    :judge="round.judge"
                    :show-discuss="false"
                    :selected-model-id="chatStore.activeModelIds[0]"
                    @activate="summaryActiveRound[round.id] = true"
                  />
                </div>
              </template>
            </div>

            <!-- After selection (any mode): tab bar + viewed card full width -->
            <div v-else-if="hasSelection(round)">
              <!-- Model tab bar -->
              <div class="flex items-stretch gap-1 mb-3 rounded-lg bg-surface-2 p-1">
                <button v-for="[modelId] of round.responses" :key="modelId"
                  @click="switchViewingModel(round.id, modelId)"
                  class="flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium transition-all flex-1 min-w-0"
                  :class="getViewingModelId(round) === modelId
                    ? 'bg-surface-1 shadow-sm'
                    : 'hover:bg-surface-3 opacity-60 hover:opacity-90'">
                  <div
                    class="w-5 h-5 rounded-md flex items-center justify-center text-[9px] font-bold text-white shrink-0"
                    :style="{ backgroundColor: getModelColor(getProvider(modelId)) }">
                    {{ getModelName(modelId).charAt(0) }}
                  </div>
                  <span class="truncate">{{ getModelName(modelId) }}</span>
                  <span v-if="hasModelError(round, modelId)" class="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                  <span v-if="round.activeModelId === modelId" class="ml-auto text-[9px] shrink-0"
                    :style="{ color: getModelColor(getProvider(modelId)) }">
                    ✓ 已选
                  </span>
                  <span v-else class="ml-auto text-[9px] text-text-tertiary shrink-0">
                    {{ round.responses.get(modelId)?.elapsed?.toFixed(1) }}s
                  </span>
                </button>
              </div>

              <!-- Viewed card full width -->
              <ModelResponseCard :model-id="getViewingModelId(round)"
                :model-name="getModelName(getViewingModelId(round))"
                :provider="getProvider(getViewingModelId(round))"
                :tier="getTier(getViewingModelId(round))"
                :content="round.responses.get(getViewingModelId(round))?.content ?? ''"
                :elapsed="round.responses.get(getViewingModelId(round))?.elapsed"
                :error-code="round.responses.get(getViewingModelId(round))?.errorCode"
                :error="round.responses.get(getViewingModelId(round))?.error"
                :brief="round.responses.get(getViewingModelId(round))?.brief"
                :streaming="!!round.responses.get(getViewingModelId(round))?.streaming"
                :active="getViewingModelId(round) === round.activeModelId"
                :selected="getViewingModelId(round) === round.activeModelId"
                @select="chatStore.setActiveModel(round.id, getViewingModelId(round))"
                @discuss="startInlineDiscuss(round.id)"
                @retry="retryRoundModel(round, getViewingModelId(round))"
                @replace="replaceRoundModel(round, getViewingModelId(round))"
                @random-replace="randomReplaceModel(round, getViewingModelId(round))" />
            </div>

            <!-- Before selection: layout depends on viewMode -->

            <!-- Grid mode — whole card clickable to select -->
            <div v-else-if="viewMode === 'grid'" class="grid gap-3" :class="gridClass">
              <div v-for="[modelId, msg] of round.responses" :key="modelId"
                class="max-h-[clamp(360px,58vh,600px)] flex flex-col min-h-0"
                @click="chatStore.setActiveModel(round.id, modelId)">
                <ModelResponseCard :model-id="modelId" :model-name="getModelName(modelId)"
                  :provider="getProvider(modelId)" :tier="getTier(modelId)" :content="msg.content"
                  :elapsed="msg.elapsed" :error="msg.error" :error-code="msg.errorCode" :brief="msg.brief"
                  :streaming="!!msg.streaming"
                  :selected="round.activeModelId === modelId"
                  @select="chatStore.setActiveModel(round.id, modelId)"
                  @discuss="startInlineDiscuss(round.id)"
                  @retry="retryRoundModel(round, modelId)"
                  @replace="replaceRoundModel(round, modelId)"
                  @random-replace="randomReplaceModel(round, modelId)" />
              </div>
            </div>

            <!-- Vertical mode -->
            <div v-else-if="viewMode === 'vertical'" class="space-y-3 max-w-3xl mx-auto">
              <ModelResponseCard v-for="[modelId, msg] of round.responses" :key="modelId"
                :model-id="modelId" :model-name="getModelName(modelId)"
                :provider="getProvider(modelId)" :tier="getTier(modelId)" :content="msg.content"
                :elapsed="msg.elapsed" :error="msg.error" :error-code="msg.errorCode" :brief="msg.brief"
                :streaming="!!msg.streaming"
                :selected="round.activeModelId === modelId"
                @select="chatStore.setActiveModel(round.id, modelId)"
                @discuss="startInlineDiscuss(round.id)"
                @retry="retryRoundModel(round, modelId)"
                @replace="replaceRoundModel(round, modelId)"
                @random-replace="randomReplaceModel(round, modelId)" />
            </div>

            <!-- Horizontal mode — single card full width with tab bar -->
            <div v-else>
              <!-- Tab bar to switch between cards -->
              <div class="flex items-stretch gap-1 mb-3 rounded-lg bg-surface-2 p-1">
                <button v-for="([modelId], cardIdx) of Array.from(round.responses.entries())"
                  :key="modelId" @click="desktopHActive[round.id] = cardIdx"
                  class="flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium transition-all flex-1 min-w-0"
                  :class="getDesktopHActive(round.id) === cardIdx
                    ? 'bg-surface-1 shadow-sm'
                    : 'hover:bg-surface-3 opacity-60 hover:opacity-90'">
                  <div
                    class="w-5 h-5 rounded-md flex items-center justify-center text-[9px] font-bold text-white shrink-0"
                    :style="{ backgroundColor: getModelColor(getProvider(modelId)) }">
                    {{ getModelName(modelId).charAt(0) }}
                  </div>
                  <span class="truncate">{{ getModelName(modelId) }}</span>
                  <span v-if="hasModelError(round, modelId)" class="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                  <span v-if="round.responses.get(modelId)?.elapsed"
                    class="ml-auto text-[9px] text-text-tertiary shrink-0">
                    {{ round.responses.get(modelId)!.elapsed!.toFixed(1) }}s
                  </span>
                </button>
              </div>

              <!-- Single visible card -->
              <div v-for="([modelId, msg], cardIdx) of Array.from(round.responses.entries())"
                :key="modelId" v-show="getDesktopHActive(round.id) === cardIdx"
                @click="chatStore.setActiveModel(round.id, modelId)">
                <ModelResponseCard :model-id="modelId" :model-name="getModelName(modelId)"
                  :provider="getProvider(modelId)" :tier="getTier(modelId)" :content="msg.content"
                  :elapsed="msg.elapsed" :error="msg.error" :error-code="msg.errorCode" :brief="msg.brief"
                  :streaming="!!msg.streaming" :active="true"
                  :selected="round.activeModelId === modelId"
                  @select="chatStore.setActiveModel(round.id, modelId)"
                  @discuss="startInlineDiscuss(round.id)"
                  @retry="retryRoundModel(round, modelId)"
                  @replace="replaceRoundModel(round, modelId)"
                  @random-replace="randomReplaceModel(round, modelId)" />
              </div>
            </div>

            <!-- Summary + Discuss actions (after all responses done) - only for multi-chat -->
            <template v-if="isRoundDone(round) && getRoundModelIds(round).length >= 2">
              <!-- Initial: 50/50 side by side. After click: vertical full width -->
              <div class="mt-4"
                :class="isAnyPanelActive(round.id) ? 'space-y-2' : 'flex items-stretch gap-2'">
                <ChatSummary
                  :class="isAnyPanelActive(round.id) ? 'w-full' : (round.activeModelId ? 'w-1/2' : 'w-full')"
                  :round-id="round.id"
                  :prompt="round.prompt" :responses="round.responses"
                  :judge="round.judge"
                  :show-discuss="!!round.activeModelId" :selected-model-id="round.activeModelId"
                  @discuss="startInlineDiscuss(round.id)"
                  @activate="summaryActiveRound[round.id] = true"
                  @select="(mid: string) => { chatStore.setActiveModel(round.id, mid); viewingModelId[round.id] = mid }" />

                <button v-if="round.activeModelId && inlineDiscussRound !== round.id"
                  @click="startInlineDiscuss(round.id)" class="flex items-center justify-center gap-2 px-4 py-3
                         rounded-xl border border-purple-500/20 bg-surface-1
                         hover:bg-purple-500/5 transition-colors group"
                  :class="isAnyPanelActive(round.id) ? 'w-full' : 'w-1/2'">
                  <MessageSquare :size="14"
                    class="text-purple-400 group-hover:scale-110 transition-transform" />
                  <span
                    class="text-sm text-text-secondary group-hover:text-text-primary transition-colors">
                    {{ hasInlineDiscussState(round) ? '继续查看辩论' : '深入辩论' }}
                  </span>
                </button>
              </div>

              <InlineDiscuss v-if="inlineDiscussRound === round.id"
                :id="'inline-discuss-' + round.id" :round-id="round.id" :prompt="round.prompt"
                :responses="round.responses" :selected-model="round.activeModelId"
                :model-ids="Array.from(round.responses.keys())" :state="round.inlineDiscuss"
                @close="inlineDiscussRound = null" />
            </template>
          </template>

          <!-- Mobile: archived settled round -->
          <div v-else-if="isSettled(ri)" class="archived-round flex items-start gap-2">
            <!-- Left: stacked dots for non-selected models -->
            <div v-if="getArchivedModels(round).length"
              class="flex flex-col items-center gap-1.5 pt-4 shrink-0">
              <button v-for="archivedId in getArchivedModels(round)" :key="archivedId"
                @click="switchArchivedModel(round, archivedId)" class="archived-dot group relative"
                :style="{ backgroundColor: getModelColor(getProvider(archivedId)) }"
                :title="getModelName(archivedId)">
                <span class="archived-tooltip">{{ getModelName(archivedId) }}</span>
              </button>
            </div>

            <!-- Right: the selected card -->
            <div class="flex-1 min-w-0">
              <ModelResponseCard :carousel="true" :model-id="getDisplayedModelId(round)"
                :model-name="getModelName(getDisplayedModelId(round))"
                :provider="getProvider(getDisplayedModelId(round))"
                :tier="getTier(getDisplayedModelId(round))"
                :content="round.responses.get(getDisplayedModelId(round))?.content ?? ''"
                :elapsed="round.responses.get(getDisplayedModelId(round))?.elapsed"
                :error="round.responses.get(getDisplayedModelId(round))?.error"
                :error-code="round.responses.get(getDisplayedModelId(round))?.errorCode"
                :brief="round.responses.get(getDisplayedModelId(round))?.brief"
                :streaming="!!round.responses.get(getDisplayedModelId(round))?.streaming"
                :active="true" :selected="round.activeModelId === getDisplayedModelId(round)"
                class="card"
                @retry="retryRoundModel(round, getDisplayedModelId(round))"
                @replace="replaceRoundModel(round, getDisplayedModelId(round))"
                @random-replace="randomReplaceModel(round, getDisplayedModelId(round))" />
            </div>
          </div>

          <!-- Mobile: current round -->
          <template v-else-if="isMobile">
            <!-- Mobile single chat mode -->
            <div v-if="getRoundModelIds(round).length === 1" class="max-w-3xl mx-auto">
              <div v-for="[singleModelId, msg] of round.responses" :key="singleModelId">
                <ModelResponseCard
                  :model-id="singleModelId"
                  :model-name="getModelName(singleModelId)"
                  :provider="getProvider(singleModelId)"
                  :tier="getTier(singleModelId)"
                  :content="msg.content"
                  :elapsed="msg.elapsed"
                  :error="msg.error"
                  :error-code="msg.errorCode"
                  :brief="msg.brief"
                  :streaming="!!msg.streaming"
                  :single-mode="true"
                  @retry="retryRoundModel(round, singleModelId)"
                  @replace="replaceRoundModel(round, singleModelId)"
                  @random-replace="randomReplaceModel(round, singleModelId)"
                />
              </div>
              <!-- Summary for single chat (no discuss) -->
              <template v-if="isRoundDone(round)">
                <div class="mt-4">
                  <ChatSummary
                    :round-id="round.id"
                    :prompt="round.prompt"
                    :responses="round.responses"
                    :judge="round.judge"
                    :show-discuss="false"
                    :selected-model-id="chatStore.activeModelIds[0]"
                    @activate="summaryActiveRound[round.id] = true"
                  />
                </div>
              </template>
            </div>

            <!-- Mobile vertical mode -->
            <div v-else-if="mobileViewMode === 'vertical'" class="space-y-3">
              <ModelResponseCard v-for="[modelId, msg] of round.responses" :key="modelId"
                :model-id="modelId" :model-name="getModelName(modelId)"
                :provider="getProvider(modelId)" :tier="getTier(modelId)" :content="msg.content"
                :elapsed="msg.elapsed" :error="msg.error" :error-code="msg.errorCode" :brief="msg.brief"
                :streaming="!!msg.streaming"
                :selected="round.activeModelId === modelId"
                @select="chatStore.setActiveModel(round.id, modelId)"
                @discuss="startInlineDiscuss(round.id)"
                @retry="retryRoundModel(round, modelId)"
                @replace="replaceRoundModel(round, modelId)"
                @random-replace="randomReplaceModel(round, modelId)" />
            </div>

            <!-- Mobile horizontal carousel (multi-chat only) -->
            <div v-else>
              <!-- Tab bar for mobile -->
              <div v-if="round.responses.size > 1"
                class="flex items-stretch gap-1 mb-2 rounded-lg bg-surface-2 p-1">
                <button v-for="([modelId], cardIdx) of Array.from(round.responses.entries())"
                  :key="modelId" @click="setActiveIndex(round.id, cardIdx)"
                  class="flex items-center gap-1.5 px-2 py-1.5 rounded-md text-[11px] font-medium transition-all flex-1 min-w-0"
                  :class="getActiveIndex(round.id) === cardIdx
                    ? 'bg-surface-1 shadow-sm'
                    : 'opacity-50'">
                  <span
                    class="w-4 h-4 rounded flex items-center justify-center text-[8px] font-bold text-white shrink-0"
                    :style="{ backgroundColor: getModelColor(getProvider(modelId)) }">{{ getModelName(modelId).charAt(0) }}</span>
                  <span class="truncate">{{ getModelName(modelId) }}</span>
                  <span v-if="hasModelError(round, modelId)" class="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                </button>
              </div>

              <div class="carousel-wrapper">
                <div class="overflow-hidden"
                  @touchstart.passive="(e: TouchEvent) => onTouchStart(round.id, e)"
                  @touchmove.passive="(e: TouchEvent) => onTouchMove(round.id, e, round.responses.size)"
                  @touchend="() => onTouchEnd(round.id, round.responses.size)">
                  <div class="flex items-start"
                    :class="isDragging[round.id] ? '' : 'carousel-snap'"
                    :style="{ transform: getTransform(round.id) }">
                    <div v-for="([modelId, msg], cardIdx) in Array.from(round.responses.entries())"
                      :key="modelId" class="w-full shrink-0 flex items-start"
                      :style="{ width: CARD_WIDTH_PCT + '%' }">
                      <div class="w-full rounded-xl transition-all duration-300"
                        :class="getActiveIndex(round.id) === cardIdx ? 'carousel-active' : 'carousel-inactive'">
                        <ModelResponseCard :carousel="true" :model-id="modelId"
                          :model-name="getModelName(modelId)" :provider="getProvider(modelId)"
                          :tier="getTier(modelId)" :content="msg.content" :elapsed="msg.elapsed"
                          :error="msg.error" :error-code="msg.errorCode" :brief="msg.brief" :streaming="!!msg.streaming"
                          :active="getActiveIndex(round.id) === cardIdx"
                          :selected="round.activeModelId === modelId"
                          class="mobile-response-card"
                          @select="chatStore.setActiveModel(round.id, modelId)"
                          @retry="retryRoundModel(round, modelId)"
                          @replace="replaceRoundModel(round, modelId)"
                          @random-replace="randomReplaceModel(round, modelId)" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- Summary + Inline Discuss (mobile, after responses done) - only for multi-chat -->
          <template v-if="isMobile && isRoundDone(round) && getRoundModelIds(round).length >= 2">
            <div class="mt-4"
              :class="isAnyPanelActive(round.id) ? 'space-y-2' : 'flex items-stretch gap-2'">
              <ChatSummary
                :class="isAnyPanelActive(round.id) ? 'w-full' : (round.activeModelId ? 'w-1/2' : 'w-full')"
                :round-id="round.id"
                :prompt="round.prompt" :responses="round.responses"
                :judge="round.judge"
                :show-discuss="!!round.activeModelId" :selected-model-id="round.activeModelId"
                @discuss="startInlineDiscuss(round.id)"
                @activate="summaryActiveRound[round.id] = true"
                @select="(mid: string) => { chatStore.setActiveModel(round.id, mid); viewingModelId[round.id] = mid }" />

              <button v-if="round.activeModelId && inlineDiscussRound !== round.id"
                @click="startInlineDiscuss(round.id)" class="flex flex-col items-center justify-center gap-1.5
                       rounded-xl border border-purple-500/20 bg-surface-1
                       hover:bg-purple-500/5 transition-colors group"
                :class="isAnyPanelActive(round.id) ? 'w-full py-3' : 'w-1/2'">
                <MessageSquare :size="14" class="text-purple-400" />
                <span class="text-xs text-text-secondary">
                  {{ hasInlineDiscussState(round) ? '继续查看辩论' : '深入辩论' }}
                </span>
              </button>
            </div>

            <InlineDiscuss v-if="inlineDiscussRound === round.id" :round-id="round.id" :prompt="round.prompt"
              :responses="round.responses" :selected-model="round.activeModelId"
              :model-ids="Array.from(round.responses.keys())" :state="round.inlineDiscuss"
              @close="inlineDiscussRound = null" />
          </template>
        </div>
      </div>
    </div>

    <!-- Group 3: Trinity Control Pod (Modern Floating Style) -->
    <div class="z-30 px-4 pb-3 pt-1 shrink-0">
      <div
        class="max-w-6xl mx-auto glass-v3 rounded-[36px] shadow-[0_32px_64px_-12px_rgba(0,0,0,0.5)] transition-all duration-500 relative flex flex-col overflow-visible border border-white/10">
        <div class="px-2 pt-1">
          <ModelChipBar
            class="!border-none !bg-white/5 !dark:bg-white/5 !rounded-[28px] !shadow-none" />
        </div>

        <InputBar class="!bg-transparent !pb-1.5 !pt-0.5" :disabled="!hasActiveModels"
          :streaming="chatStore.streaming"
          :placeholder="inputPlaceholder"
          :sample-prompt="samplePrompt"
          :restore-text="restoredDraft" @submit="handleSubmit" @stop="chatStore.stopStreaming"
          @stop-and-edit="handleStopAndEdit" />
      </div>
    </div>

    <!-- Image lightbox -->
    <Teleport to="body">
      <div v-if="previewImage"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 cursor-pointer"
        @click="previewImage = null">
        <img :src="previewImage"
          class="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl" />
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.carousel-snap {
  transition: transform 0.35s cubic-bezier(0.25, 1, 0.5, 1);
}

.carousel-card {
  padding-right: 8px;
}

/* Active card: full opacity, lifted */
.carousel-active {
  box-shadow: 0 2px 12px rgba(99, 102, 241, 0.15);
  opacity: 1;
}

/* Inactive/peek card: faded, shrunk */
.carousel-inactive {
  opacity: 0.4;
  transform: scale(0.96);
}

.mobile-response-card {
  height: auto !important;
}

/* Archived round dots */
.archived-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  cursor: pointer;
  transition: all 0.2s ease;
  opacity: 0.5;
}
.archived-dot:hover {
  opacity: 1;
  transform: scale(1.4);
}

/* Tooltip on hover/long-press */
.archived-tooltip {
  display: none;
  position: absolute;
  left: calc(100% + 8px);
  top: 50%;
  transform: translateY(-50%);
  white-space: nowrap;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--c-surface-3);
  color: var(--c-text-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  z-index: 10;
}
.archived-dot:hover .archived-tooltip {
  display: block;
}

/* Archived round card gets a subtle left accent */
.archived-round .card {
  border-left: 2px solid #6366f1;
}

.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.no-scrollbar::-webkit-scrollbar {
  display: none;
}

.tip-fade-enter-active {
  transition: all 0.2s ease;
}
.tip-fade-leave-active {
  transition: all 0.3s ease;
}
.tip-fade-enter-from,
.tip-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
