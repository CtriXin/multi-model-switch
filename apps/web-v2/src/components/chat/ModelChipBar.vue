<script setup lang="ts">
import { ref, computed, watch, inject, onMounted, onUnmounted } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore, getModelColor, type ModelMeta, type ModelPoolTag } from '@/stores/app'
import { X, Plus, Search, Dices, Bot, DollarSign, Image, Clock, Zap, Target, History, ChevronDown, Sparkles, MessageSquare, ToggleLeft, ToggleRight, Check } from 'lucide-vue-next'
import { useChatStore, type ContextMode } from '@/stores/chat'
import { useSessionStore } from '@/stores/session'
import { useToastStore } from '@/stores/toast'
import { getSearchHistory, addSearchHistory } from '@/utils/searchHistory'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const chatStore = useChatStore()
const sessionStore = useSessionStore()
const toast = useToastStore()
const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isMobile = computed(() => platform?.value === 'ios')
const popoverOpen = ref(false)
const searchQuery = ref('')
const filterVision = ref(false)
const filterFree = ref(appStore.preferFree)
const tierFilters = ref<ModelPoolTag[]>([])
const recentSearches = ref<string[]>([])
const contextMenuOpen = ref(false)
const modelPopoverButtonRef = ref<HTMLElement | null>(null)
const modelPopoverPanelRef = ref<HTMLElement | null>(null)
const contextMenuRef = ref<HTMLElement | null>(null)
const replacementRequest = ref<{
  mode: 'replace'
  roundId: string
  oldModelId: string
  requireVision?: boolean
} | null>(null)

const contextModes: { key: ContextMode; label: string; description: string; icon: any }[] = [
  { key: 'summary', label: '摘要模式', description: '每轮回答摘要', icon: Zap },
  { key: 'selected', label: '仅选中模式', description: '仅选中模型', icon: Target },
  { key: 'full', label: '全文模式', description: '完整对话历史', icon: History },
]

function getContextModeLabel(key: ContextMode): string {
  return contextModes.find(m => m.key === key)?.label ?? '摘要模式'
}

function getContextModeIcon(key: ContextMode): any {
  return contextModes.find(m => m.key === key)?.icon ?? Zap
}

const filteredModels = ref<typeof appStore.models>([])

const groupedFiltered = computed(() => {
  const map: Record<string, ModelMeta[]> = {}
  for (const m of filteredModels.value) {
    ; (map[m.provider] ??= []).push(m)
  }
  return map
})

function updateFiltered() {
  const q = searchQuery.value.toLowerCase()
  filteredModels.value = appStore.filterModels({
    tags: tierFilters.value,
    requireFree: filterFree.value,
    requireVision: filterVision.value,
  }).filter(m => {
    if (q && !m.name.toLowerCase().includes(q) && !m.provider.toLowerCase().includes(q) && !m.id.toLowerCase().includes(q)) return false
    return true
  })
}

function togglePopover() {
  popoverOpen.value = !popoverOpen.value
  if (popoverOpen.value) {
    replacementRequest.value = null
    searchQuery.value = ''
    recentSearches.value = getSearchHistory()
    updateFiltered()
  }
}

async function selectModel(id: string) {
  if (replacementRequest.value) {
    const request = replacementRequest.value
    if (id === request.oldModelId) return
    if (isReplacementDisabled(id)) return

    appStore.replaceSelectedModel(request.oldModelId, id)
    await chatStore.retryModel(request.roundId, request.oldModelId, { replaceWith: id })
    sessionStore.saveCurrentSession()
    replacementRequest.value = null
    popoverOpen.value = false
    toast.info('已替换当前卡片模型')
    return
  }

  appStore.toggleModel(id)
}

function removeModel(id: string) {
  appStore.toggleModel(id)
}

function handleSearch(e: Event) {
  searchQuery.value = (e.target as HTMLInputElement).value
  updateFiltered()
}

function commitSearch() {
  if (searchQuery.value.trim()) {
    addSearchHistory(searchQuery.value.trim())
  }
}

function applyRecentSearch(keyword: string) {
  searchQuery.value = keyword
  updateFiltered()
}

function toggleTierFilter(tag: ModelPoolTag) {
  const next = new Set(tierFilters.value)
  if (next.has(tag)) next.delete(tag)
  else next.add(tag)
  tierFilters.value = Array.from(next)
  updateFiltered()
}

function toggleFilterVision() {
  filterVision.value = !filterVision.value
  updateFiltered()
}

function toggleFilterFree() {
  filterFree.value = !filterFree.value
  updateFiltered()
}

function hasTierFilter(tag: ModelPoolTag) {
  return tierFilters.value.includes(tag)
}

function randomPickFromFilters() {
  appStore.randomPick(3, 'chat', {
    tags: tierFilters.value,
    requireFree: filterFree.value,
    requireVision: filterVision.value,
    useAllWhenNoTags: true,
  })
}

function isReplacementDisabled(id: string) {
  if (!replacementRequest.value) return false
  if (id === replacementRequest.value.oldModelId) return false
  return appStore.selectedModelIds.includes(id)
}

function openReplacementPicker(event: Event) {
  if (isMobile.value) return
  const detail = (event as CustomEvent<typeof replacementRequest.value>).detail
  if (!detail || detail.mode !== 'replace') return

  replacementRequest.value = detail
  popoverOpen.value = true
  searchQuery.value = ''
  filterVision.value = !!detail.requireVision
  recentSearches.value = getSearchHistory()
  updateFiltered()
}

function tierLabel(tier: number): string {
  return tier === 2 ? 'PRO' : tier === 1 ? 'STD' : 'BASIC'
}

function tierClass(tier: number): string {
  return tier === 2 ? 'bg-amber-500/15 text-amber-400' : tier === 1 ? 'bg-blue-500/15 text-blue-400' : 'bg-green-500/15 text-green-400'
}

function scrollToProviderSection(provider: string) {
  const el = document.getElementById('chipbar-section-' + provider)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

watch(popoverOpen, (val) => {
  if (!val) commitSearch()
})

onClickOutside(contextMenuRef, () => {
  contextMenuOpen.value = false
})

onClickOutside(modelPopoverPanelRef, () => {
  popoverOpen.value = false
  replacementRequest.value = null
}, {
  ignore: [modelPopoverButtonRef],
})

onMounted(() => {
  window.addEventListener('open-model-picker', openReplacementPicker)
})

onUnmounted(() => {
  window.removeEventListener('open-model-picker', openReplacementPicker)
})
</script>

<template>
  <div class="relative transition-all duration-500">
    <div class="max-w-5xl mx-auto px-3 sm:px-4">
      <div class="flex items-center h-11 sm:h-10">
        <!-- Scrollable chips area -->
        <div class="flex-1 min-w-0 overflow-x-auto no-scrollbar">
          <div class="flex items-center gap-2 sm:gap-1.5 py-2 sm:py-1.5 w-max min-w-full">
            <span v-for="m in appStore.selectedModels" :key="m.id" class="inline-flex items-center gap-1.5 pl-1.5 sm:pl-1 pr-2 sm:pr-1.5 py-1.5 sm:py-1 rounded-full text-xs
                       whitespace-nowrap shrink-0 group border transition-colors" :style="{
                  backgroundColor: getModelColor(m.provider) + '12',
                  borderColor: getModelColor(m.provider) + '25',
                }">
              <span class="w-2.5 h-2.5 sm:w-2 sm:h-2 rounded-full shrink-0"
                :style="{ backgroundColor: getModelColor(m.provider) }" />
              <span
                class="truncate max-w-[100px] sm:max-w-[80px] text-text-primary uppercase font-black tracking-tight">{{ m.name }}</span>
              <button @click.stop="removeModel(m.id)"
                class="p-1 sm:p-0.5 rounded-full hover:bg-white/10 opacity-40 group-hover:opacity-100 transition-opacity">
                <X class="w-3.5 h-3.5 sm:w-3 sm:h-3" />
              </button>
            </span>
            <span v-if="!appStore.selectedModels.length"
              class="text-xs text-text-tertiary whitespace-nowrap">
              未选择模型
            </span>
          </div>
        </div>

        <div class="flex items-center gap-1 shrink-0 border-l border-white/5 pl-2 ml-1">
          <button @click="randomPickFromFilters"
            class="p-2 rounded-full text-amber-400 hover:bg-amber-500/10 transition-all active:scale-90"
            title="随机换一组模型">
            <Dices :size="18" :stroke-width="3" />
          </button>

          <button ref="modelPopoverButtonRef" @click="togglePopover"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all border"
            :class="replacementRequest
                ? 'bg-orange-500/10 text-orange-400 border-orange-500/20 hover:bg-orange-500/15'
                : appStore.selectedModels.length > 0 
                ? 'bg-accent/5 text-accent border-accent/20 hover:bg-accent/10' 
                : 'text-text-tertiary border-white/5 hover:bg-white/5'">
            <Bot :size="16" :stroke-width="3" />
            <span class="hidden sm:inline">{{ replacementRequest ? '替换模型' : '模型基因' }}</span>
          </button>

          <div v-if="route.path === '/chat' && chatStore.rounds.length > 0" ref="contextMenuRef" class="relative">
            <button @click="contextMenuOpen = !contextMenuOpen"
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest
                       text-text-secondary hover:bg-accent/10 hover:text-accent transition-all border border-transparent" title="上下文策略">
              <component :is="getContextModeIcon(chatStore.contextMode)" :size="16"
                :stroke-width="3" class="text-accent" />
              <span class="hidden sm:inline">{{ getContextModeLabel(chatStore.contextMode) }}</span>
            </button>

            <Transition name="popover">
              <div v-if="contextMenuOpen" class="absolute right-0 bottom-full mb-3 w-44 shadow-[0_20px_50px_rgba(0,0,0,0.3)] rounded-[28px] overflow-hidden bg-white dark:bg-[#1a1a24] border border-white/10 z-50 p-1.5 flex flex-col gap-1">
                <div class="px-3 py-2 text-[9px] font-black text-text-tertiary uppercase tracking-[0.2em] border-b border-white/5 mb-1">Context Strategy</div>
                <button v-for="mode in contextModes" :key="mode.key" @click="chatStore.contextMode = mode.key; contextMenuOpen = false"
                  class="w-full px-3 py-2.5 text-left flex items-center gap-3 rounded-[20px] transition-all"
                  :class="chatStore.contextMode === mode.key ? 'bg-accent text-white shadow-lg' : 'text-text-secondary hover:bg-white/5'">
                  <component :is="mode.icon" :size="14" :stroke-width="3" />
                  <div class="flex-1 min-w-0">
                    <div class="text-[11px] font-bold leading-tight">{{ mode.label }}</div>
                    <div class="text-[9px] opacity-50 font-medium tracking-tight uppercase">{{ mode.description }}</div>
                  </div>
                </button>
              </div>
            </Transition>
          </div>
        </div>
      </div>
    </div>

    <!-- Popover dropdown -->
    <Transition name="popover">
      <div v-if="popoverOpen" class="absolute left-0 right-0 bottom-full mb-4 z-50 px-4">
        <div ref="modelPopoverPanelRef" class="relative max-w-5xl mx-auto shadow-[0_30px_80px_rgba(0,0,0,0.4)] rounded-[32px] max-h-[400px] flex flex-col overflow-hidden bg-white dark:bg-[#1a1a24] border border-white/10">
          <!-- Search + Filter -->
          <div class="px-4 py-3 border-b border-white/5 space-y-3 bg-white/2">
            <div v-if="replacementRequest" class="rounded-xl border border-orange-500/20 bg-orange-500/8 px-3 py-2 text-[11px] text-orange-300">
              正在替换 <span class="font-semibold">{{ appStore.getModel(replacementRequest.oldModelId)?.name }}</span>
            </div>
            <div class="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-black/5 dark:bg-white/5 border border-white/5">
              <Search :size="16" class="text-text-tertiary shrink-0" />
              <input type="text" :value="searchQuery" @input="handleSearch" placeholder="快速搜索模型基因..." class="flex-1 bg-transparent text-sm text-text-primary outline-none" autofocus />
            </div>
            <div class="flex items-center gap-3 overflow-x-auto no-scrollbar scroll-smooth px-1">
              <button @click="toggleFilterFree" class="shrink-0 inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[9px] font-black uppercase tracking-widest transition-all border whitespace-nowrap" :class="filterFree ? 'bg-emerald-500 text-white border-emerald-500 shadow-emerald-500/20' : 'bg-black/[0.03] dark:bg-white/5 text-text-tertiary border-black/5 dark:border-white/5 hover:bg-white/5'">
                免费 <component :is="filterFree ? ToggleRight : ToggleLeft" :size="12" />
              </button>
              <button v-for="tag in (['basic', 'std', 'pro'] as const)" :key="tag" @click="toggleTierFilter(tag)" class="shrink-0 px-3 py-1.5 rounded-full text-[9px] font-black uppercase tracking-widest transition-all border whitespace-nowrap" :class="hasTierFilter(tag) ? 'bg-accent text-white border-accent shadow-accent/20' : 'bg-black/[0.03] dark:bg-white/5 text-text-tertiary border-black/5 dark:border-white/5 hover:bg-white/5'">
                {{ tag === 'pro' ? '旗舰' : tag === 'std' ? '主力' : '基础' }}
              </button>
              <button @click="toggleFilterVision" class="shrink-0 inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[9px] font-black uppercase tracking-widest transition-all border whitespace-nowrap" :class="filterVision ? 'bg-purple-500 text-white border-purple-500 shadow-purple-500/20' : 'bg-black/[0.03] dark:bg-white/5 text-text-tertiary border-black/5 dark:border-white/5 hover:bg-white/5'">
                图片
              </button>
              <div class="shrink-0 w-4"></div>
            </div>
          </div>

          <!-- Provider Tabs -->
          <div v-if="Object.keys(groupedFiltered).length > 1" class="flex gap-1 px-4 py-2 border-b border-white/5 overflow-x-auto no-scrollbar bg-white/2">
            <button v-for="provider in Object.keys(groupedFiltered)" :key="provider" @click="scrollToProviderSection(provider)" class="px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest bg-white/5 text-text-tertiary hover:text-text-primary transition-all border border-transparent hover:border-white/10 shrink-0">{{ provider }}</button>
          </div>

          <!-- Model Grid -->
          <div class="overflow-y-auto flex-1 p-4 custom-scrollbar scroll-smooth" id="chipbar-model-scroll">
            <template v-for="(models, provider) in groupedFiltered" :key="provider">
              <div :id="'chipbar-section-' + provider" class="flex items-center gap-2 py-4 sticky top-0 bg-white/90 dark:bg-[#1a1a24]/90 backdrop-blur-md z-10">
                <div class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: getModelColor(provider) }"></div>
                <span class="text-[9px] font-black uppercase tracking-[0.2em] text-text-tertiary">{{ provider }}</span>
                <div class="h-px flex-1 bg-white/5 ml-2"></div>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 pb-6">
                <button v-for="model in models" :key="model.id" @click="selectModel(model.id)"
                  class="flex flex-col items-start p-4 rounded-2xl border transition-all duration-300 text-left relative active:scale-95 group"
                  :class="replacementRequest ? (isReplacementDisabled(model.id) ? 'opacity-35 cursor-not-allowed border-white/5 bg-white/2' : model.id === replacementRequest.oldModelId ? 'border-orange-500/50 bg-orange-500/5' : 'border-white/5 bg-white/5 hover:border-white/20') : appStore.selectedModelIds.includes(model.id) ? 'border-accent/50 bg-accent/5 shadow-inner' : 'border-white/5 bg-white/5 hover:border-white/20'">
                  <div class="flex items-center justify-between w-full mb-3">
                    <span class="text-[11px] font-black uppercase tracking-tight text-text-primary truncate pr-6">{{ model.name }}</span>
                    <div class="w-5 h-5 rounded-full flex items-center justify-center border border-white/10 transition-all" :class="appStore.selectedModelIds.includes(model.id) ? 'bg-accent border-accent text-white scale-110' : ''"><Check v-if="appStore.selectedModelIds.includes(model.id)" :size="12" stroke-width="4" /></div>
                  </div>
                  <div class="flex flex-wrap gap-1">
                    <span class="text-[8px] font-black px-1.5 py-0.5 rounded-md uppercase tracking-wider" :class="tierClass(model.tier)">{{ tierLabel(model.tier) }}</span>
                    <span v-if="model.free" class="text-[8px] font-black px-1.5 py-0.5 rounded-md uppercase tracking-wider bg-emerald-500/10 text-emerald-400">$0</span>
                    <span v-if="model.supportsVision" class="text-[8px] font-black px-1.5 py-0.5 rounded-md uppercase tracking-wider bg-purple-500/10 text-purple-400">VIS</span>
                  </div>
                  <span v-if="replacementRequest && model.id === replacementRequest.oldModelId" class="absolute bottom-3 right-4 text-[8px] font-black uppercase text-orange-400">Active</span>
                </button>
              </div>
            </template>
            <p v-if="!filteredModels.length" class="text-xs font-black text-text-tertiary text-center py-12 uppercase tracking-widest opacity-40">没有发现匹配的模型基因</p>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
.popover-enter-active { animation: popIn 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
.popover-leave-active { animation: popOut 0.2s ease-in; }
@keyframes popIn { from { opacity: 0; transform: translateY(12px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes popOut { from { opacity: 1; } to { opacity: 0; transform: translateY(8px); } }
</style>
