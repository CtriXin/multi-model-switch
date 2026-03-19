<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { useAppStore, getModelColor, type ModelMeta, type ModelSelectionMode, type ModelPoolTag } from '@/stores/app'
import { useChatStore } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toast'
import { Search, Check, DollarSign, Image, Clock, X, Dice5, ToggleLeft, ToggleRight } from 'lucide-vue-next'
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
const filterFree = ref(appStore.preferFree)
const tierFilters = ref<ModelPoolTag[]>([])
const filterVision = ref(false)
const recentSearches = ref<string[]>([])
const sheetRef = ref<HTMLElement>()
const detent = ref<'half' | 'full'>('half')
const transitioning = ref(false)

// Drag state
const dragging = ref(false)
const dragStartY = ref(0)
const dragCurrentY = ref(0)
const sheetTranslateY = ref(0)

const HALF_HEIGHT = 55 
const FULL_HEIGHT = 92 
const MAX_SELECTION = 5

const selectedIds = computed(() => (
  props.mode === 'committee' ? appStore.committeeSelectedModelIds : appStore.selectedModelIds
))

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  return appStore.filterModels({
    tags: tierFilters.value,
    requireFree: filterFree.value,
    requireVision: filterVision.value,
  }).filter(m => {
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
  return tier === 2 ? 'premium' : tier === 1 ? 'standard' : 'basic'
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

function toggleTierFilter(tag: ModelPoolTag) {
  const next = new Set(tierFilters.value)
  if (next.has(tag)) next.delete(tag)
  else next.add(tag)
  tierFilters.value = Array.from(next)
}
function toggleFilterFree() { filterFree.value = !filterFree.value }
function toggleFilterVision() { filterVision.value = !filterVision.value }
function hasTierFilter(tag: ModelPoolTag) { return tierFilters.value.includes(tag) }
function randomPick() {
  appStore.randomPick(3, props.mode, {
    tags: tierFilters.value,
    requireFree: filterFree.value,
    requireVision: filterVision.value,
    useAllWhenNoTags: true,
  })
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
    toast.info('换好了')
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
    if (delta < -60) detent.value = 'full'
    else if (delta > 80) emit('close')
  } else {
    if (delta > 100) detent.value = 'half'
  }
  sheetTranslateY.value = 0
}

function onMouseDown(e: MouseEvent) {
  if (!isMobile.value) return
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
  if (detent.value === 'half' && delta < 0) sheetTranslateY.value = delta * 0.4
  else if (delta > 0) sheetTranslateY.value = delta
}

function onMouseUp() {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  onTouchEnd()
}

// Reset on open
watch(() => props.open, async (val) => {
  if (val) {
    detent.value = 'half'
    search.value = ''
    filterFree.value = appStore.preferFree
    filterVision.value = !!props.request?.requireVision
    sheetTranslateY.value = 0
    recentSearches.value = getSearchHistory()
    // 确保模型列表已加载
    await appStore.ensureModelsLoaded()
  }
})

const sheetHeight = computed(() => detent.value === 'full' ? FULL_HEIGHT : HALF_HEIGHT)

const sheetStyle = computed(() => {
  if (!isMobile.value) return {}
  const baseTranslate = sheetTranslateY.value
  return {
    height: `${sheetHeight.value}vh`,
    transform: baseTranslate ? `translateY(${baseTranslate}px)` : undefined,
    transition: dragging.value ? 'none' : 'height 0.5s cubic-bezier(0.32, 0.72, 0, 1), transform 0.5s cubic-bezier(0.32, 0.72, 0, 1)',
  }
})

function modelTags(model: ModelMeta): string[] {
  return model.tags.filter(t => ['reasoning', 'fast', 'coding', 'vision'].includes(t))
}

function scrollToProviderSection(provider: string) {
  const el = document.getElementById('section-' + provider)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-show="open || transitioning" class="fixed inset-0 z-[9997] flex items-center justify-center overflow-hidden">
      <!-- Backdrop -->
      <Transition 
        name="sheet-backdrop"
        @before-enter="transitioning = true"
        @after-leave="transitioning = false"
      >
        <div v-if="open" class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="emit('close')" />
      </Transition>

      <!-- Sheet / Modal -->
      <Transition :name="isMobile ? 'sheet-content' : 'modal-slide'">
        <div
          v-if="open"
          ref="sheetRef"
          :class="[
            isMobile 
              ? 'absolute bottom-0 left-0 right-0 rounded-t-[32px] shadow-[0_-20px_50px_rgba(0,0,0,0.3)]' 
              : 'relative w-full max-w-4xl max-h-[80vh] rounded-[32px] shadow-[0_40px_100px_rgba(0,0,0,0.4)] border border-white/10',
            'flex flex-col bg-white dark:bg-[#0b0b18] overflow-hidden'
          ]"
          :style="isMobile ? sheetStyle : {}"
        >
          <!-- Drag Handle / Header Control -->
          <div
            class="flex flex-col items-center py-3 shrink-0"
            :class="isMobile ? 'cursor-grab active:cursor-grabbing' : ''"
            @touchstart.passive="onTouchStart"
            @touchmove.passive="onTouchMove"
            @touchend="onTouchEnd"
            @mousedown="onMouseDown"
          >
            <div v-if="isMobile" class="w-10 h-1 rounded-full bg-text-tertiary/40" />
            <div v-else class="w-full flex justify-end px-8 pt-4">
               <button @click="emit('close')" class="p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/5 transition-all">
                 <X :size="24" class="text-text-tertiary" />
               </button>
            </div>
          </div>

          <!-- Header -->
          <div class="flex items-center justify-between px-8 pb-6 shrink-0">
            <div>
              <h2 class="text-2xl font-black tracking-tight text-text-primary uppercase">{{ replacementMode ? '替换当前模型基因' : '选择模型基因' }}</h2>
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

          <!-- Filter chips & Random -->
          <div class="flex items-center gap-3 px-8 pb-4 shrink-0 overflow-x-auto no-scrollbar scroll-smooth">
            <button @click="toggleFilterFree" class="shrink-0 flex items-center gap-2 px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest transition-all border whitespace-nowrap"
                    :class="filterFree ? 'bg-emerald-500 text-white border-emerald-500 shadow-lg shadow-emerald-500/20' : 'text-text-tertiary border-white/5 hover:bg-white/5'">
              <DollarSign :size="12" /> 免费基因
              <component :is="filterFree ? ToggleRight : ToggleLeft" :size="12" />
            </button>
            <button @click="toggleTierFilter('basic')" class="shrink-0 flex items-center gap-2 px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest transition-all border whitespace-nowrap"
                    :class="hasTierFilter('basic') ? 'bg-blue-500/15 text-blue-400 border-blue-500/30' : 'text-text-tertiary border-white/5 hover:bg-white/5'">
              基础
            </button>
            <button @click="toggleTierFilter('std')" class="shrink-0 flex items-center gap-2 px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest transition-all border whitespace-nowrap"
                    :class="hasTierFilter('std') ? 'bg-blue-500/15 text-blue-400 border-blue-500/30' : 'text-text-tertiary border-white/5 hover:bg-white/5'">
              主力
            </button>
            <button @click="toggleTierFilter('pro')" class="shrink-0 flex items-center gap-2 px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest transition-all border whitespace-nowrap"
                    :class="hasTierFilter('pro') ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' : 'text-text-tertiary border-white/5 hover:bg-white/5'">
              旗舰
            </button>
            <button @click="toggleFilterVision" class="shrink-0 flex items-center gap-2 px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest transition-all border whitespace-nowrap"
                    :class="filterVision ? 'bg-purple-500/15 text-purple-400 border-purple-500/30' : 'text-text-tertiary border-white/5 hover:bg-white/5'">
              <Image :size="12" /> 视觉支持
            </button>
            <button v-if="!replacementMode" @click="randomPick" class="shrink-0 flex items-center gap-2 px-4 py-2 rounded-full text-[10px] font-black uppercase tracking-widest transition-all border whitespace-nowrap text-amber-400 border-white/5 hover:bg-amber-500/10">
              <Dice5 :size="12" /> 随机抽取
            </button>
            <div class="shrink-0 w-8"></div> <!-- Spacer for scroll end -->
          </div>

          <!-- Search -->
          <div class="px-8 pb-4 shrink-0">
            <div class="flex items-center gap-3 px-4 py-3 rounded-2xl bg-black/5 dark:bg-white/5 border border-white/5 focus-within:border-accent/30 transition-all">
              <Search :size="18" class="text-text-tertiary" />
              <input v-model="search" placeholder="搜索模型基因 ID..." class="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary/40 outline-none font-medium" />
            </div>
          </div>

          <!-- Main Body: Rail + Grid -->
          <div class="flex-1 flex overflow-hidden">
            <!-- Provider Quick Rail -->
            <aside v-if="filtered.length > 8" class="w-16 flex flex-col items-center py-4 gap-3 bg-black/5 dark:bg-white/2 border-r border-white/5 overflow-y-auto no-scrollbar shrink-0">
              <button
                v-for="provider in Array.from(new Set(filtered.map(m => m.provider)))"
                :key="provider"
                @click="scrollToProviderSection(provider)"
                class="w-10 h-10 rounded-xl flex items-center justify-center bg-white/5 text-text-tertiary hover:bg-accent/20 hover:text-accent transition-all active:scale-90 shrink-0 border border-transparent hover:border-accent/30"
                :title="provider"
              >
                <span class="text-[10px] font-black uppercase leading-none">{{ provider.slice(0, 2) }}</span>
              </button>
            </aside>

            <!-- Model Grid -->
            <div class="flex-1 overflow-y-auto px-8 pb-10 custom-scrollbar scroll-smooth">
              <template v-for="provider in Array.from(new Set(filtered.map(m => m.provider)))" :key="provider">
                <div :id="'section-' + provider" class="flex items-center gap-2 py-6 sticky top-0 bg-white/90 dark:bg-[#0b0b18]/90 backdrop-blur-md z-10">
                  <div class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: getModelColor(provider) }"></div>
                  <span class="text-[10px] font-black uppercase tracking-[0.2em] text-text-tertiary">{{ provider }}</span>
                  <div class="h-px flex-1 bg-white/5 ml-2"></div>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <button v-for="model in filtered.filter(m => m.provider === provider)" :key="model.id" @click="handleModelPress(model.id)"
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
                    <div class="w-12 h-12 rounded-2xl flex items-center justify-center text-lg font-black text-white mb-3 shadow-lg" :style="{ backgroundColor: getModelColor(model.provider) }">
                      {{ modelInitial(model) }}
                    </div>
                    <span class="text-sm font-black text-text-primary leading-tight pr-8 uppercase tracking-tight">{{ model.name }}</span>
                    <span class="text-[10px] font-bold text-text-tertiary mt-1 uppercase tracking-widest opacity-60">{{ model.provider }}</span>
                    <div class="flex flex-wrap gap-1 mt-3">
                      <span class="px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider" :class="tierColor(model.tier)">{{ tierLabel(model.tier) }}</span>
                      <span v-if="model.free" class="px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider bg-green-500/10 text-green-400">$0</span>
                      <span v-if="model.supportsVision" class="px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider bg-purple-500/10 text-purple-400">VIS</span>
                    </div>
                  </button>
                </div>
              </template>
              <p v-if="!filtered.length" class="text-xs font-bold text-text-tertiary text-center py-12 uppercase tracking-[0.2em]">没有匹配的模型基因</p>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </Teleport>
</template>

<style scoped>
.sheet-backdrop-enter-active, .sheet-backdrop-leave-active { 
  transition: opacity 0.5s cubic-bezier(0.32, 0.72, 0, 1), backdrop-filter 0.5s cubic-bezier(0.32, 0.72, 0, 1); 
}
.sheet-backdrop-enter-from, .sheet-backdrop-leave-to { opacity: 0; backdrop-filter: blur(0); }

.sheet-content-enter-active { animation: sheetIn 0.6s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-content-leave-active { animation: sheetOut 0.5s cubic-bezier(0.32, 0.72, 0, 1) forwards; }

.modal-slide-enter-active { animation: modalIn 0.7s cubic-bezier(0.23, 1, 0.32, 1); }
.modal-slide-leave-active { animation: modalOut 0.4s cubic-bezier(0.32, 0.72, 0, 1) forwards; }

@keyframes sheetIn { from { transform: translateY(100%); } to { transform: translateY(0); } }
@keyframes sheetOut { from { transform: translateY(0); opacity: 1; } to { transform: translateY(100%); opacity: 0; } }
@keyframes modalIn { from { opacity: 0; transform: scale(0.9) translateY(100px); } to { opacity: 1; transform: scale(1) translateY(0); } }
@keyframes modalOut { from { opacity: 1; transform: scale(1) translateY(0); } to { opacity: 0; transform: scale(0.95) translateY(40px); } }

.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
</style>
