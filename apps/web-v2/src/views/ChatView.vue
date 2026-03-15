<script setup lang="ts">
import { ref, nextTick, computed, inject, reactive, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore, getModelColor } from '@/stores/app'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toast'
import InputBar from '@/components/chat/InputBar.vue'
import ModelChipBar from '@/components/chat/ModelChipBar.vue'
import ModelResponseCard from '@/components/chat/ModelResponseCard.vue'
import ChatSummary from '@/components/ChatSummary.vue'
import InlineDiscuss from '@/components/InlineDiscuss.vue'
import type { ImageAttachment } from '@/stores/chat'
import { Sparkles, LayoutGrid, List, GalleryHorizontalEnd, MessageSquare } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const chatStore = useChatStore()
const sessionStore = useSessionStore()
const toast = useToastStore()
const platform = inject<import('vue').Ref<string>>('platform')
const restoredDraft = ref('')

const scrollContainer = ref<HTMLElement>()
const hasModels = computed(() => appStore.selectedModels.length >= 2)
const hasRounds = computed(() => chatStore.currentRound && !chatStore.streaming)

// --- View mode ---
type ViewMode = 'grid' | 'vertical' | 'horizontal'
// Desktop: ≤3 models → grid (side-by-side), ≥4 → horizontal scroll
// Mobile: horizontal (carousel) default, vertical available
const viewMode = ref<ViewMode>(appStore.selectedModels.length > 3 ? 'horizontal' : 'grid')

// Auto-switch default when model count changes
watch(() => appStore.selectedModels.length, (count) => {
  if (count <= 3 && viewMode.value === 'horizontal') viewMode.value = 'grid'
  else if (count > 3 && viewMode.value === 'grid') viewMode.value = 'horizontal'
})

// Mobile view mode: 'horizontal' (carousel) or 'vertical'
type MobileViewMode = 'horizontal' | 'vertical'
const mobileViewMode = ref<MobileViewMode>('horizontal')

// --- Inline discuss state ---
const inlineDiscussRound = ref<string | null>(null)
const summaryActiveRound = reactive<Record<string, boolean>>({})

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
  return !!summaryActiveRound[roundId] || inlineDiscussRound.value === roundId
}

// --- Tab bar viewing state (separate from selection) ---
// After user selects a model, clicking other tabs only changes viewing, not selection
const viewingModelId = reactive<Record<string, string | null>>({})

function getViewingModelId(round: typeof chatStore.rounds[0]): string {
  // Show the viewing override if set, otherwise show selected
  return viewingModelId[round.id] ?? round.activeModelId ?? ''
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
  if (ctx && hasModels.value) {
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
const previewImage = ref<string | null>(null)

function openImagePreview(src: string) {
  previewImage.value = src
}

async function handleSubmit(text: string, attachments: ImageAttachment[] = []) {
  restoredDraft.value = ''
  if (!hasModels.value) {
    toast.info('请至少选择 2 个模型')
    return
  }
  if (!sessionStore.currentSessionId) {
    sessionStore.createSession('chat')
  }
  // Fire and don't await — scroll immediately after DOM update
  chatStore.sendMessage(text, appStore.selectedModelIds, attachments).then(() => {
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
  toast.info('已恢复到输入框，可修改后重发')
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

function shouldUseFixedGridHeight(round: typeof chatStore.rounds[0]): boolean {
  return Array.from(round.responses.values()).some((msg) => {
    const content = msg.content || ''
    const lineCount = content.split('\n').length
    const briefCount = Object.keys(msg.brief ?? {}).length
    return !!msg.error || briefCount > 0 || lineCount > 8 || content.length > 420 || (chatStore.streaming && !msg.elapsed)
  })
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
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Chat history -->
    <div ref="scrollContainer" class="flex-1 overflow-y-auto" @scroll.passive="onScroll">
      <!-- Empty state -->
      <div
        v-if="!chatStore.rounds.length"
        class="flex flex-col items-center justify-center h-full text-center px-6"
      >
        <div class="w-16 h-16 rounded-2xl bg-accent/10 flex items-center justify-center mb-4 animate-fade-in">
          <Sparkles :size="28" class="text-accent" />
        </div>
        <h2 class="text-lg font-semibold text-text-primary mb-2 animate-slide-up">
          多模型对话
        </h2>
        <p class="text-sm text-text-secondary max-w-sm animate-slide-up" style="animation-delay: 50ms">
          同时向多个模型发送消息，并排比较它们的回答
        </p>
        <p v-if="!hasModels" class="text-xs text-text-tertiary mt-4 animate-slide-up" style="animation-delay: 100ms">
          从上方模型栏选择 2 个以上模型开始
        </p>
      </div>

      <!-- Rounds -->
      <div v-else class="mx-auto py-4 space-y-6" :class="isMobile ? 'max-w-lg px-4' : 'max-w-5xl px-4'">
        <!-- View mode toggle (desktop only, show when there are rounds) -->
        <div v-if="!isMobile" class="flex justify-end">
          <div class="inline-flex items-center gap-0.5 p-0.5 rounded-lg bg-surface-2">
            <button
              v-for="mode in (['grid', 'horizontal', 'vertical'] as const)"
              :key="mode"
              @click="viewMode = mode"
              class="p-1.5 rounded-md transition-all"
              :class="viewMode === mode ? 'bg-surface-1 shadow-sm text-text-primary' : 'text-text-tertiary hover:text-text-secondary'"
              :title="mode === 'grid' ? '并排' : mode === 'horizontal' ? '横向滑动' : '纵向'"
            >
              <component
                :is="mode === 'grid' ? LayoutGrid : mode === 'horizontal' ? GalleryHorizontalEnd : List"
                :size="14"
              />
            </button>
          </div>
        </div>

        <div
          v-for="(round, ri) in chatStore.rounds"
          :key="round.id"
          :id="'round-' + round.id"
          class="animate-slide-up"
          :style="{ animationDelay: ri * 30 + 'ms' }"
        >
          <!-- User prompt -->
          <div class="flex justify-end mb-4">
            <div class="max-w-[85%]">
              <!-- Attached images -->
              <div v-if="round.attachments?.length" class="flex gap-1.5 justify-end mb-1.5">
                <img
                  v-for="img in round.attachments"
                  :key="img.id"
                  :src="img.dataUrl"
                  :alt="img.name"
                  class="h-20 w-20 object-cover rounded-lg border border-white/10 cursor-pointer hover:opacity-80 transition-opacity"
                  @click="openImagePreview(img.dataUrl)"
                />
              </div>
              <div class="px-4 py-2.5 rounded-2xl rounded-br-md bg-accent text-white text-sm">
                {{ round.prompt }}
              </div>
            </div>
          </div>

          <!-- Desktop responses -->
          <template v-if="!isMobile">
            <!-- After selection (any mode): tab bar + viewed card full width -->
            <div v-if="hasSelection(round)">
              <!-- Model tab bar -->
              <div class="flex items-stretch gap-1 mb-3 rounded-lg bg-surface-2 p-1">
                <button
                  v-for="[modelId] of round.responses"
                  :key="modelId"
                  @click="switchViewingModel(round.id, modelId)"
                  class="flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium transition-all flex-1 min-w-0"
                  :class="getViewingModelId(round) === modelId
                    ? 'bg-surface-1 shadow-sm'
                    : 'hover:bg-surface-3 opacity-60 hover:opacity-90'"
                >
                  <div
                    class="w-5 h-5 rounded-md flex items-center justify-center text-[9px] font-bold text-white shrink-0"
                    :style="{ backgroundColor: getModelColor(getProvider(modelId)) }"
                  >
                    {{ getModelName(modelId).charAt(0) }}
                  </div>
                  <span class="truncate">{{ getModelName(modelId) }}</span>
                  <span
                    v-if="round.activeModelId === modelId"
                    class="ml-auto text-[9px] shrink-0"
                    :style="{ color: getModelColor(getProvider(modelId)) }"
                  >
                    ✓ 已选
                  </span>
                  <span v-else class="ml-auto text-[9px] text-text-tertiary shrink-0">
                    {{ round.responses.get(modelId)?.elapsed?.toFixed(1) }}s
                  </span>
                </button>
              </div>

              <!-- Viewed card full width -->
              <ModelResponseCard
                :model-id="getViewingModelId(round)"
                :model-name="getModelName(getViewingModelId(round))"
                :provider="getProvider(getViewingModelId(round))"
                :tier="getTier(getViewingModelId(round))"
                :content="round.responses.get(getViewingModelId(round))?.content ?? ''"
                :elapsed="round.responses.get(getViewingModelId(round))?.elapsed"
                :brief="round.responses.get(getViewingModelId(round))?.brief"
                :streaming="false"
                :active="getViewingModelId(round) === round.activeModelId"
                :selected="getViewingModelId(round) === round.activeModelId"
                @select="chatStore.setActiveModel(round.id, getViewingModelId(round))"
                @discuss="startInlineDiscuss(round.id)"
                @retry="restorePrompt(round.prompt)"
              />
            </div>

            <!-- Before selection: layout depends on viewMode -->

            <!-- Grid mode — whole card clickable to select -->
              <div v-else-if="viewMode === 'grid'" class="grid gap-3" :class="gridClass">
                <div
                  v-for="[modelId, msg] of round.responses"
                  :key="modelId"
                  :class="shouldUseFixedGridHeight(round) ? 'h-[clamp(360px,58vh,520px)]' : ''"
                  @click="chatStore.setActiveModel(round.id, modelId)"
                >
                <ModelResponseCard
                  :model-id="modelId"
                  :model-name="getModelName(modelId)"
                  :provider="getProvider(modelId)"
                  :tier="getTier(modelId)"
                  :content="msg.content"
                  :elapsed="msg.elapsed"
                  :brief="msg.brief"
                  :streaming="chatStore.streaming && !msg.elapsed"
                  :selected="round.activeModelId === modelId"
                  @select="chatStore.setActiveModel(round.id, modelId)"
                  @discuss="startInlineDiscuss(round.id)"
                  @retry="restorePrompt(round.prompt)"
                />
              </div>
            </div>

            <!-- Vertical mode -->
            <div v-else-if="viewMode === 'vertical'" class="space-y-3 max-w-3xl mx-auto">
              <ModelResponseCard
                v-for="[modelId, msg] of round.responses"
                :key="modelId"
                :model-id="modelId"
                :model-name="getModelName(modelId)"
                :provider="getProvider(modelId)"
                :tier="getTier(modelId)"
                :content="msg.content"
                :elapsed="msg.elapsed"
                :brief="msg.brief"
                :streaming="chatStore.streaming && !msg.elapsed"
                :selected="round.activeModelId === modelId"
                @select="chatStore.setActiveModel(round.id, modelId)"
                @discuss="startInlineDiscuss(round.id)"
                @retry="restorePrompt(round.prompt)"
              />
            </div>

            <!-- Horizontal mode — single card full width with tab bar -->
            <div v-else>
              <!-- Tab bar to switch between cards -->
              <div class="flex items-stretch gap-1 mb-3 rounded-lg bg-surface-2 p-1">
                <button
                  v-for="([modelId], cardIdx) of Array.from(round.responses.entries())"
                  :key="modelId"
                  @click="desktopHActive[round.id] = cardIdx"
                  class="flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium transition-all flex-1 min-w-0"
                  :class="getDesktopHActive(round.id) === cardIdx
                    ? 'bg-surface-1 shadow-sm'
                    : 'hover:bg-surface-3 opacity-60 hover:opacity-90'"
                >
                  <div
                    class="w-5 h-5 rounded-md flex items-center justify-center text-[9px] font-bold text-white shrink-0"
                    :style="{ backgroundColor: getModelColor(getProvider(modelId)) }"
                  >
                    {{ getModelName(modelId).charAt(0) }}
                  </div>
                  <span class="truncate">{{ getModelName(modelId) }}</span>
                  <span v-if="round.responses.get(modelId)?.elapsed" class="ml-auto text-[9px] text-text-tertiary shrink-0">
                    {{ round.responses.get(modelId)!.elapsed!.toFixed(1) }}s
                  </span>
                </button>
              </div>

              <!-- Single visible card -->
              <div
                v-for="([modelId, msg], cardIdx) of Array.from(round.responses.entries())"
                :key="modelId"
                v-show="getDesktopHActive(round.id) === cardIdx"
                @click="chatStore.setActiveModel(round.id, modelId)"
              >
                <ModelResponseCard
                  :model-id="modelId"
                  :model-name="getModelName(modelId)"
                  :provider="getProvider(modelId)"
                  :tier="getTier(modelId)"
                  :content="msg.content"
                  :elapsed="msg.elapsed"
                  :brief="msg.brief"
                  :streaming="chatStore.streaming && !msg.elapsed"
                  :active="true"
                  :selected="round.activeModelId === modelId"
                  @select="chatStore.setActiveModel(round.id, modelId)"
                  @discuss="startInlineDiscuss(round.id)"
                  @retry="restorePrompt(round.prompt)"
                />
              </div>
            </div>

            <!-- Summary + Discuss actions (after all responses done) -->
            <template v-if="isRoundDone(round)">
              <!-- Initial: 50/50 side by side. After click: vertical full width -->
              <div
                class="mt-4"
                :class="isAnyPanelActive(round.id) ? 'space-y-2' : 'flex items-stretch gap-2'"
              >
                <ChatSummary
                  :class="isAnyPanelActive(round.id) ? 'w-full' : (round.activeModelId ? 'w-1/2' : 'w-full')"
                  :prompt="round.prompt"
                  :responses="round.responses"
                  :show-discuss="!!round.activeModelId"
                  :selected-model-id="round.activeModelId"
                  @discuss="startInlineDiscuss(round.id)"
                  @activate="summaryActiveRound[round.id] = true"
                  @select="(mid: string) => chatStore.setActiveModel(round.id, mid)"
                />

                <button
                  v-if="round.activeModelId && inlineDiscussRound !== round.id"
                  @click="startInlineDiscuss(round.id)"
                  class="flex items-center justify-center gap-2 px-4 py-3
                         rounded-xl border border-purple-500/20 bg-surface-1
                         hover:bg-purple-500/5 transition-colors group"
                  :class="isAnyPanelActive(round.id) ? 'w-full' : 'w-1/2'"
                >
                  <MessageSquare :size="14" class="text-purple-400 group-hover:scale-110 transition-transform" />
                  <span class="text-sm text-text-secondary group-hover:text-text-primary transition-colors">
                    深入讨论
                  </span>
                </button>
              </div>

              <InlineDiscuss
                v-if="inlineDiscussRound === round.id"
                :id="'inline-discuss-' + round.id"
                :prompt="round.prompt"
                :responses="round.responses"
                :selected-model="round.activeModelId"
                :model-ids="Array.from(round.responses.keys())"
                @close="inlineDiscussRound = null"
              />
            </template>
          </template>

          <!-- Mobile: archived settled round -->
          <div v-else-if="isSettled(ri)" class="archived-round flex gap-2">
            <!-- Left: stacked dots for non-selected models -->
            <div
              v-if="getArchivedModels(round).length"
              class="flex flex-col items-center gap-1.5 pt-4 shrink-0"
            >
              <button
                v-for="archivedId in getArchivedModels(round)"
                :key="archivedId"
                @click="switchArchivedModel(round, archivedId)"
                class="archived-dot group relative"
                :style="{ backgroundColor: getModelColor(getProvider(archivedId)) }"
                :title="getModelName(archivedId)"
              >
                <span class="archived-tooltip">{{ getModelName(archivedId) }}</span>
              </button>
            </div>

            <!-- Right: the selected card -->
            <div class="flex-1 min-w-0">
              <ModelResponseCard
                :carousel="true"
                :model-id="getDisplayedModelId(round)"
                :model-name="getModelName(getDisplayedModelId(round))"
                :provider="getProvider(getDisplayedModelId(round))"
                :tier="getTier(getDisplayedModelId(round))"
                :content="round.responses.get(getDisplayedModelId(round))?.content ?? ''"
                :elapsed="round.responses.get(getDisplayedModelId(round))?.elapsed"
                :brief="round.responses.get(getDisplayedModelId(round))?.brief"
                :streaming="false"
                :active="true"
                :selected="round.activeModelId === getDisplayedModelId(round)"
                class="card"
                @retry="restorePrompt(round.prompt)"
              />
            </div>
          </div>

          <!-- Mobile: current round with view mode toggle -->
          <template v-else-if="isMobile">
            <!-- Mobile view mode toggle -->
            <div v-if="round.responses.size > 1" class="flex justify-end mb-2">
              <div class="inline-flex items-center gap-0.5 p-0.5 rounded-lg bg-surface-2">
                <button
                  v-for="mode in (['horizontal', 'vertical'] as const)"
                  :key="mode"
                  @click="mobileViewMode = mode"
                  class="p-1.5 rounded-md transition-all"
                  :class="mobileViewMode === mode ? 'bg-surface-1 shadow-sm text-text-primary' : 'text-text-tertiary hover:text-text-secondary'"
                  :title="mode === 'horizontal' ? '横向滑动' : '纵向'"
                >
                  <component :is="mode === 'horizontal' ? GalleryHorizontalEnd : List" :size="14" />
                </button>
              </div>
            </div>

            <!-- Mobile vertical mode -->
            <div v-if="mobileViewMode === 'vertical'" class="space-y-3">
              <ModelResponseCard
                v-for="[modelId, msg] of round.responses"
                :key="modelId"
                :model-id="modelId"
                :model-name="getModelName(modelId)"
                :provider="getProvider(modelId)"
                :tier="getTier(modelId)"
                :content="msg.content"
                :elapsed="msg.elapsed"
                :brief="msg.brief"
                :streaming="chatStore.streaming && !msg.elapsed"
                :selected="round.activeModelId === modelId"
                @select="chatStore.setActiveModel(round.id, modelId)"
                @discuss="startInlineDiscuss(round.id)"
                @retry="restorePrompt(round.prompt)"
              />
            </div>

            <!-- Mobile horizontal carousel -->
            <div v-else>
              <!-- Tab bar for mobile -->
              <div v-if="round.responses.size > 1" class="flex items-stretch gap-1 mb-2 rounded-lg bg-surface-2 p-1">
                <button
                  v-for="([modelId], cardIdx) of Array.from(round.responses.entries())"
                  :key="modelId"
                  @click="setActiveIndex(round.id, cardIdx)"
                  class="flex items-center gap-1.5 px-2 py-1.5 rounded-md text-[11px] font-medium transition-all flex-1 min-w-0"
                  :class="getActiveIndex(round.id) === cardIdx
                    ? 'bg-surface-1 shadow-sm'
                    : 'opacity-50'"
                >
                  <span
                    class="w-4 h-4 rounded flex items-center justify-center text-[8px] font-bold text-white shrink-0"
                    :style="{ backgroundColor: getModelColor(getProvider(modelId)) }"
                  >{{ getModelName(modelId).charAt(0) }}</span>
                  <span class="truncate">{{ getModelName(modelId) }}</span>
                </button>
              </div>

              <div class="carousel-wrapper">
              <div
                class="overflow-hidden"
                @touchstart.passive="(e: TouchEvent) => onTouchStart(round.id, e)"
                @touchmove.passive="(e: TouchEvent) => onTouchMove(round.id, e, round.responses.size)"
                @touchend="() => onTouchEnd(round.id, round.responses.size)"
              >
                <div
                  class="flex items-stretch"
                  :class="isDragging[round.id] ? '' : 'carousel-snap'"
                  :style="{ transform: getTransform(round.id) }"
                >
                  <div
                    v-for="([modelId, msg], cardIdx) in Array.from(round.responses.entries())"
                    :key="modelId"
                    class="w-full shrink-0 flex"
                    :style="{ width: CARD_WIDTH_PCT + '%' }"
                  >
                    <div
                      class="w-full rounded-xl transition-all duration-300"
                      :class="getActiveIndex(round.id) === cardIdx ? 'carousel-active' : 'carousel-inactive'"
                    >
                      <ModelResponseCard
                        :carousel="true"
                        :model-id="modelId"
                        :model-name="getModelName(modelId)"
                        :provider="getProvider(modelId)"
                        :tier="getTier(modelId)"
                        :content="msg.content"
                        :elapsed="msg.elapsed"
                        :brief="msg.brief"
                        :streaming="chatStore.streaming && !msg.elapsed"
                        :active="getActiveIndex(round.id) === cardIdx"
                        :selected="round.activeModelId === modelId"
                        @select="chatStore.setActiveModel(round.id, modelId)"
                        @retry="restorePrompt(round.prompt)"
                      />
                    </div>
                  </div>
                </div>
              </div>
              </div>
            </div>
          </template>

          <!-- Summary + Inline Discuss (mobile, after responses done) -->
          <template v-if="isMobile && isRoundDone(round)">
            <div
              class="mt-4"
              :class="isAnyPanelActive(round.id) ? 'space-y-2' : 'flex items-stretch gap-2'"
            >
              <ChatSummary
                :class="isAnyPanelActive(round.id) ? 'w-full' : (round.activeModelId ? 'w-1/2' : 'w-full')"
                :prompt="round.prompt"
                :responses="round.responses"
                :show-discuss="!!round.activeModelId"
                @discuss="startInlineDiscuss(round.id)"
                @activate="summaryActiveRound[round.id] = true"
              />

              <button
                v-if="round.activeModelId && inlineDiscussRound !== round.id"
                @click="startInlineDiscuss(round.id)"
                class="flex flex-col items-center justify-center gap-1.5
                       rounded-xl border border-purple-500/20 bg-surface-1
                       hover:bg-purple-500/5 transition-colors group"
                :class="isAnyPanelActive(round.id) ? 'w-full py-3' : 'w-1/2'"
              >
                <MessageSquare :size="14" class="text-purple-400" />
                <span class="text-xs text-text-secondary">深入讨论</span>
              </button>
            </div>

            <InlineDiscuss
              v-if="inlineDiscussRound === round.id"
              :prompt="round.prompt"
              :responses="round.responses"
              :selected-model="round.activeModelId"
              :model-ids="Array.from(round.responses.keys())"
              @close="inlineDiscussRound = null"
            />
          </template>
        </div>
      </div>
    </div>

    <!-- Model chip bar -->
    <ModelChipBar />

    <!-- Input -->
    <InputBar
      :disabled="!hasModels"
      :streaming="chatStore.streaming"
      :placeholder="hasModels ? undefined : '请先选择 2 个以上模型...'"
      :restore-text="restoredDraft"
      @submit="handleSubmit"
      @stop="chatStore.stopStreaming"
      @stop-and-edit="handleStopAndEdit"
    />

    <!-- Image lightbox -->
    <Teleport to="body">
      <div
        v-if="previewImage"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 cursor-pointer"
        @click="previewImage = null"
      >
        <img :src="previewImage" class="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl" />
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

/* Active card: accent border, full opacity, lifted */
.carousel-active {
  border: 2px solid #6366f1;
  box-shadow: 0 2px 12px rgba(99, 102, 241, 0.15);
  opacity: 1;
}

/* Inactive/peek card: subtle border, faded, shrunk */
.carousel-inactive {
  border: 1.5px solid var(--c-border-subtle);
  opacity: 0.4;
  transform: scale(0.96);
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

.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
.no-scrollbar::-webkit-scrollbar { display: none; }
</style>
