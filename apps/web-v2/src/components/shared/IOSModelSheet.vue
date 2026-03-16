<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useAppStore, getModelColor, type ModelMeta, type ModelSelectionMode } from '@/stores/app'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toast'
import { Search, Check, DollarSign, Image, Clock, X, Dice5 } from 'lucide-vue-next'
import { getSearchHistory, addSearchHistory } from '@/utils/searchHistory'

const props = withDefaults(defineProps<{
  open: boolean
  mode?: ModelSelectionMode
  request?: {
    mode?: 'replace'
    roundId?: string
    oldModelId?: string
    requireVision?: boolean
  } | null
}>(), {
  mode: 'chat',
  request: null,
})
const emit = defineEmits<{ close: [] }>()

const appStore = useAppStore()
const chatStore = useChatStore()
const sessionStore = useSessionStore()
const toast = useToastStore()
const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isMobile = computed(() => platform.value === 'ios')
const search = ref('')
const filterFree = ref(true)
const filterVision = ref(false)
const recentSearches = ref<string[]>([])
const sheetRef = ref<HTMLElement>()
const detent = ref<'half' | 'full'>('half')

// Drag state
const dragging = ref(false)
const dragStartY = ref(0)
const dragCurrentY = ref(0)
const sheetTranslateY = ref(0)
const handleAnimating = ref(false)

const HALF_HEIGHT = 55 // vh
const FULL_HEIGHT = 92 // vh
const MAX_SELECTION = 5

const selectedIds = computed(() => (
  props.mode === 'committee' ? appStore.committeeSelectedModelIds : appStore.selectedModelIds
))

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  return appStore.models.filter(m => {
    if (filterFree.value && !m.free) return false
    if (filterVision.value && !m.supportsVision) return false
    if (q && !m.name.toLowerCase().includes(q)
        && !m.category.toLowerCase().includes(q)
        && !m.provider.toLowerCase().includes(q)
        && !m.id.toLowerCase().includes(q)) return false
    return true
  })
})

const selectedCount = computed(() => selectedIds.value.length)
const replacementMode = computed(() =>
  props.mode === 'chat'
  && props.request?.mode === 'replace'
  && !!props.request.oldModelId
  && !!props.request.roundId,
)

const presetIcons: Record<string, string> = {
  'preset-coding': '🏆',
  'preset-reasoning': '🧠',
  'preset-fast': '⚡',
  'preset-balanced': '🎯',
  'preset-economy': '💰',
}

function tierLabel(tier: number): string {
  return tier === 2 ? 'premium' : tier === 1 ? 'standard' : 'free'
}

function tierColor(tier: number): string {
  return tier === 2 ? 'text-amber-500 bg-amber-500/10' : tier === 1 ? 'text-accent bg-accent/10' : 'text-emerald-500 bg-emerald-500/10'
}

function modelInitial(model: ModelMeta): string {
  return model.provider.charAt(0).toUpperCase()
}

function isSelected(id: string) {
  return selectedIds.value.includes(id)
}

function clearAll() {
  appStore.clearSelection(props.mode)
}

function done() {
  if (search.value.trim()) addSearchHistory(search.value.trim())
  emit('close')
}

function applyRecentSearch(keyword: string) {
  search.value = keyword
}

function toggleFilterFree() {
  filterFree.value = !filterFree.value
}

function isReplacementDisabled(id: string) {
  if (!replacementMode.value || !props.request?.oldModelId) return false
  if (id === props.request.oldModelId) return false
  return selectedIds.value.includes(id)
}

async function handleModelPress(id: string) {
  if (replacementMode.value && props.request?.oldModelId && props.request.roundId) {
    if (id === props.request.oldModelId || isReplacementDisabled(id)) return
    appStore.replaceSelectedModel(props.request.oldModelId, id)
    await chatStore.retryModel(props.request.roundId, props.request.oldModelId, { replaceWith: id })
    sessionStore.saveCurrentSession()
    toast.info('已替换当前卡片模型')
    done()
    return
  }

  appStore.toggleModel(id, props.mode)
}

// --- Touch drag for mobile ---
function onTouchStart(e: TouchEvent) {
  dragging.value = true
  dragStartY.value = e.touches[0].clientY
  dragCurrentY.value = e.touches[0].clientY
}

function onTouchMove(e: TouchEvent) {
  if (!dragging.value) return
  dragCurrentY.value = e.touches[0].clientY
  const delta = dragCurrentY.value - dragStartY.value
  if (detent.value === 'half' && delta < 0) {
    sheetTranslateY.value = delta * 0.4
  } else if (delta > 0) {
    sheetTranslateY.value = delta
  }
}

function onTouchEnd() {
  if (!dragging.value) return
  dragging.value = false
  const delta = dragCurrentY.value - dragStartY.value

  if (detent.value === 'half') {
    if (delta < -60) {
      detent.value = 'full'
    } else if (delta > 80) {
      emit('close')
    }
  } else {
    if (delta > 100) {
      detent.value = 'half'
    }
  }
  sheetTranslateY.value = 0
}

function onMouseDown(e: MouseEvent) {
  dragging.value = true
  dragStartY.value = e.clientY
  dragCurrentY.value = e.clientY
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e: MouseEvent) {
  if (!dragging.value) return
  dragCurrentY.value = e.clientY
  const delta = dragCurrentY.value - dragStartY.value
  if (detent.value === 'half' && delta < 0) {
    sheetTranslateY.value = delta * 0.4
  } else if (delta > 0) {
    sheetTranslateY.value = delta
  }
}

function onMouseUp() {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  onTouchEnd()
}

// Reset on open
watch(() => props.open, (val) => {
  if (val) {
    detent.value = 'half'
    search.value = ''
    filterFree.value = true
    filterVision.value = !!props.request?.requireVision
    sheetTranslateY.value = 0
    recentSearches.value = getSearchHistory()
    handleAnimating.value = false
    setTimeout(() => { handleAnimating.value = true }, 450)
  }
})

const sheetHeight = computed(() => detent.value === 'full' ? FULL_HEIGHT : HALF_HEIGHT)

const sheetStyle = computed(() => {
  const baseTranslate = sheetTranslateY.value
  return {
    height: `${sheetHeight.value}vh`,
    transform: baseTranslate ? `translateY(${baseTranslate}px)` : undefined,
    transition: dragging.value ? 'none' : 'height 0.4s cubic-bezier(0.32, 0.72, 0, 1), transform 0.4s cubic-bezier(0.32, 0.72, 0, 1)',
  }
})

function modelTags(model: ModelMeta): string[] {
  return model.tags.filter(t => ['reasoning', 'fast', 'coding', 'vision'].includes(t))
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[9997]">
      <Transition name="sheet-backdrop">
        <div v-if="open" class="absolute inset-0 bg-black/40" @click="emit('close')" />
      </Transition>

      <Transition name="sheet-content">
        <div
          v-if="open"
          ref="sheetRef"
          class="absolute bottom-0 left-0 right-0 flex flex-col
                 bg-surface-1 rounded-t-[14px] overflow-hidden"
          :style="sheetStyle"
        >
          <!-- Drag Handle -->
          <div
            class="flex flex-col items-center py-2.5 shrink-0 cursor-grab active:cursor-grabbing"
            @touchstart.passive="onTouchStart"
            @touchmove.passive="onTouchMove"
            @touchend="onTouchEnd"
            @mousedown="onMouseDown"
          >
            <div
              class="w-9 h-[5px] rounded-full bg-text-tertiary/30"
              :class="{ 'handle-breathe': handleAnimating }"
            />
          </div>

          <!-- Header -->
          <div class="flex items-center justify-between px-5 pb-3 shrink-0">
            <div>
              <h2 class="text-2xl font-black tracking-tight text-text-primary uppercase">{{ replacementMode ? '替换当前模型' : '选择模型基因' }}</h2>
              <p class="text-[10px] font-black text-text-tertiary mt-1 uppercase tracking-[0.2em]">
                {{ replacementMode
                  ? `正在替换 ${appStore.getModel(props.request?.oldModelId || '')?.name ?? ''}`
                  : `${selectedCount} / ${MAX_SELECTION} 已激活` }}
              </p>
            </div>
            <div class="flex items-center gap-4">
              <button v-if="!replacementMode && selectedCount > 0" @click="clearAll" class="text-[10px] font-black text-text-tertiary hover:text-red-400 uppercase tracking-widest transition-colors">重置</button>
              <button @click="done" class="px-8 py-3 rounded-2xl bg-accent text-white text-xs font-black uppercase tracking-widest shadow-xl shadow-accent/20 hover:scale-105 active:scale-95 transition-all">{{ replacementMode ? '取消替换' : '确认进化' }}</button>
            </div>
          </div>

          <!-- Presets -->
          <div v-if="!replacementMode" class="flex gap-2 px-8 pb-4 overflow-x-auto shrink-0 no-scrollbar">
            <button v-for="p in appStore.presets" :key="p.id" @click="appStore.applyPreset(p, props.mode)"
                    class="shrink-0 inline-flex items-center gap-2 px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest border border-white/5 bg-black/5 dark:bg-white/5 text-text-primary hover:border-accent/30 active:scale-95 transition-all">
              <span>{{ presetIcons[p.id] || '⚡' }}</span> <span>{{ p.name }}</span>
            </button>
          </div>

          <!-- Filter chips -->
          <div class="flex items-center gap-1.5 px-5 pb-2 shrink-0">
            <button
              @click="toggleFilterFree"
              class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all border"
              :class="filterFree
                ? 'bg-green-500/15 text-green-400 border-green-500/30'
                : 'text-text-tertiary border-border-subtle hover:bg-surface-3'"
            >
              <DollarSign :size="11" />
              免费
            </button>
            <button
              @click="toggleFilterVision"
              class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all border"
              :class="filterVision
                ? 'bg-purple-500/15 text-purple-400 border-purple-500/30'
                : 'text-text-tertiary border-border-subtle hover:bg-surface-3'"
            >
              <Image :size="11" />
              图片
            </button>
            <button v-if="!replacementMode" @click="randomPick" class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all border"
                    :class="'text-amber-400 border-white/5 hover:bg-amber-500/10'">
              <Dice5 :size="12" /> 随机
            </button>
            <span class="text-[9px] font-black text-text-tertiary ml-auto uppercase tracking-widest opacity-40">{{ filtered.length }} 个可用</span>
          </div>

          <!-- Search -->
          <div class="px-5 pb-2 shrink-0">
            <div class="flex items-center gap-2 px-3 py-2 rounded-xl bg-surface-2 border border-border-default">
              <Search :size="15" class="text-text-tertiary shrink-0" />
              <input
                v-model="search"
                placeholder="搜索模型..."
                class="flex-1 bg-transparent text-sm text-text-primary placeholder-text-tertiary outline-none"
              />
            </div>
          </div>

          <!-- Recent searches -->
          <div v-if="!search && recentSearches.length" class="flex items-center gap-1.5 px-5 pb-2 overflow-x-auto no-scrollbar shrink-0">
            <Clock :size="11" class="text-text-tertiary shrink-0" />
            <button
              v-for="kw in recentSearches"
              :key="kw"
              @click="applyRecentSearch(kw)"
              class="shrink-0 px-2 py-0.5 rounded-full text-[10px] text-text-tertiary
                     bg-surface-3 hover:bg-surface-2 transition-colors"
            >{{ kw }}</button>
          </div>

          <!-- Model Grid -->
          <div class="flex-1 overflow-y-auto px-8 pb-10">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button v-for="model in filtered" :key="model.id" @click="handleModelPress(model.id)"
                      class="relative flex flex-col items-start p-4 rounded-2xl border text-left active:scale-[0.98] transition-all duration-300 group"
                      :class="replacementMode
                        ? (isReplacementDisabled(model.id)
                          ? 'border-white/5 bg-black/5 dark:bg-white/5 opacity-35'
                          : model.id === props.request?.oldModelId
                            ? 'border-orange-500/50 bg-orange-500/5 shadow-inner'
                            : 'border-white/5 bg-black/5 dark:bg-white/5 hover:border-white/20')
                        : (isSelected(model.id) ? 'border-accent/50 bg-accent/5 shadow-inner' : 'border-white/5 bg-black/5 dark:bg-white/5 hover:border-white/20')">
                <div class="absolute top-4 right-4 w-6 h-6 rounded-full flex items-center justify-center transition-all border"
                     :class="replacementMode
                      ? (model.id === props.request?.oldModelId
                        ? 'bg-orange-500 border-orange-500 text-white scale-110'
                        : 'border-white/10')
                      : (isSelected(model.id) ? 'bg-accent border-accent text-white scale-110' : 'border-white/10')">
                  <Check v-if="replacementMode ? model.id === props.request?.oldModelId : isSelected(model.id)" :size="14" :stroke-width="4" />
                </div>

                <!-- Avatar -->
                <div
                  class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold text-white mb-2"
                  :style="{ backgroundColor: getModelColor(model.provider) }"
                >
                  {{ modelInitial(model) }}
                </div>

                <!-- Name -->
                <span class="text-sm font-medium text-text-primary leading-tight pr-6">{{ model.name }}</span>
                <span class="text-[11px] text-text-tertiary mt-0.5">{{ model.provider }}</span>

                <!-- Tags -->
                <div class="flex flex-wrap gap-1 mt-2">
                  <span
                    class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                    :class="tierColor(model.tier)"
                  >{{ tierLabel(model.tier) }}</span>
                  <span
                    v-if="model.free"
                    class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-500/10 text-green-400"
                  >free</span>
                  <span
                    v-if="model.supportsVision"
                    class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-500/10 text-purple-400"
                  >vision</span>
                  <span
                    v-for="tag in modelTags(model)"
                    :key="tag"
                    class="px-1.5 py-0.5 rounded text-[10px] text-text-tertiary bg-surface-3"
                  >{{ tag }}</span>
                </div>
                <span v-if="replacementMode && model.id === props.request?.oldModelId" class="mt-3 text-[10px] font-black uppercase tracking-widest text-orange-400">当前模型</span>
                <span v-else-if="replacementMode && isReplacementDisabled(model.id)" class="mt-3 text-[10px] font-black uppercase tracking-widest text-text-tertiary">已在模型池</span>
              </button>
            </div>

            <p v-if="!filtered.length" class="text-xs text-text-tertiary text-center py-6">
              没有符合条件的模型
            </p>
          </div>
        </div>
      </Transition>
    </div>
  </Teleport>
</template>

<style scoped>
.sheet-backdrop-enter-active,
.sheet-backdrop-leave-active { transition: opacity 0.3s ease; }
.sheet-backdrop-enter-from,
.sheet-backdrop-leave-to { opacity: 0; }

.sheet-content-enter-active { animation: sheetIn 0.4s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-content-leave-active { animation: sheetOut 0.3s cubic-bezier(0.32, 0.72, 0, 1) forwards; }

@keyframes sheetIn {
  from { transform: translateY(100%); }
  to   { transform: translateY(0); }
}
@keyframes sheetOut {
  from { transform: translateY(0); opacity: 1; }
  to   { transform: translateY(100%); opacity: 0; }
}

.handle-breathe {
  animation: handleFloat 1.2s ease-in-out 3;
}

@keyframes handleFloat {
  0%   { transform: translateY(0) scaleX(1);    opacity: 0.3; }
  40%  { transform: translateY(-3px) scaleX(0.85); opacity: 0.6; }
  70%  { transform: translateY(-3px) scaleX(0.85); opacity: 0.6; }
  100% { transform: translateY(0) scaleX(1);    opacity: 0.3; }
}

.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
