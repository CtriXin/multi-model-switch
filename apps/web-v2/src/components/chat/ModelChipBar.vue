<script setup lang="ts">
import { ref, computed, watch, inject, onMounted, onUnmounted } from 'vue'
import { onClickOutside } from '@vueuse/core'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore, getModelColor, type ModelMeta } from '@/stores/app'
import { X, Plus, Search, Dices, Bot, DollarSign, Image, Clock, Zap, Target, History, ChevronDown, Sparkles, MessageSquare } from 'lucide-vue-next'
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

// Context mode options
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
  filteredModels.value = appStore.models.filter(m => {
    if (appStore.preferFree && !m.free) return false
    if (filterVision.value && !m.supportsVision) return false
    if (q && !m.name.toLowerCase().includes(q) && !m.provider.toLowerCase().includes(q) && !m.id.toLowerCase().includes(q)) return false
    return true
  })
}

function togglePopover() {
  popoverOpen.value = !popoverOpen.value
  if (popoverOpen.value) {
    replacementRequest.value = null
    searchQuery.value = ''
    filterVision.value = false
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

function toggleFilterFree() {
  appStore.preferFree = !appStore.preferFree
  updateFiltered()
}

function toggleFilterVision() {
  filterVision.value = !filterVision.value
  updateFiltered()
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
  return tier === 2 ? 'PRO' : tier === 1 ? 'STD' : 'FREE'
}

function tierClass(tier: number): string {
  return tier === 2
    ? 'bg-amber-500/15 text-amber-400'
    : tier === 1
      ? 'bg-blue-500/15 text-blue-400'
      : 'bg-green-500/15 text-green-400'
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
                class="truncate max-w-[100px] sm:max-w-[80px] text-text-primary">{{ m.name }}</span>
              <span v-if="m.free"
                class="text-[9px] sm:text-[8px] text-green-400 font-medium">$0</span>
              <span v-if="m.supportsVision"
                class="text-[9px] sm:text-[8px] text-purple-400">📷</span>
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

        <!-- Fixed right buttons (Trinity Pod Style) -->
        <div class="flex items-center gap-1 shrink-0 border-l border-white/5 pl-2 ml-1">

          <!-- Dice: 随机模型 -->
          <button @click="appStore.randomPick()"
            class="p-2 rounded-full text-amber-400 hover:bg-amber-500/10 transition-all active:scale-90"
            title="随机换一组模型">
            <Dices :size="18" :stroke-width="3" />
          </button>

          <!-- Models: 模型选择 -->
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

          <!-- Context Mode -->
          <div v-if="route.path === '/chat' && chatStore.rounds.length > 0" ref="contextMenuRef" class="relative">
            <button @click="contextMenuOpen = !contextMenuOpen"
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest
                       text-text-secondary hover:bg-accent/10 hover:text-accent transition-all border border-transparent" title="上下文策略">
              <component :is="getContextModeIcon(chatStore.contextMode)" :size="16"
                :stroke-width="3" class="text-accent" />
              <span class="hidden sm:inline">{{ getContextModeLabel(chatStore.contextMode) }}</span>
            </button>

            <Transition name="popover">
              <div
                v-if="contextMenuOpen"
                class="absolute right-0 bottom-full mb-3 w-44 shadow-[0_20px_50px_rgba(0,0,0,0.3)] rounded-[28px] overflow-hidden bg-white dark:bg-[#1a1a24] border border-white/10 dark:border-white/5 z-50 p-1.5 flex flex-col gap-1"
              >
                <div class="px-3 py-2 text-[9px] font-black text-text-tertiary uppercase tracking-[0.2em] border-b border-white/5 mb-1">
                  Context Strategy
                </div>
                <button v-for="mode in contextModes" :key="mode.key"
                  @click="chatStore.contextMode = mode.key; contextMenuOpen = false"
                  class="w-full px-3 py-2.5 text-left flex items-center gap-3 rounded-[20px] transition-all"
                  :class="chatStore.contextMode === mode.key
                      ? 'bg-accent text-white shadow-lg'
                      : 'text-text-secondary hover:bg-white/5'">
                  <component :is="mode.icon" :size="14" :stroke-width="3" />
                  <div class="flex-1 min-w-0">
                    <div class="text-[11px] font-bold leading-tight">{{ mode.label }}</div>
                    <div class="text-[9px] opacity-50 font-medium tracking-tight uppercase">
                      {{ mode.description }}</div>
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
        <div
          ref="modelPopoverPanelRef"
          class="relative max-w-5xl mx-auto shadow-[0_30px_80px_rgba(0,0,0,0.4)] rounded-[24px] max-h-80 flex flex-col overflow-hidden bg-white dark:bg-[#1a1a24] border border-white/10 dark:border-white/5">
          <!-- Search + Filter -->
          <div class="px-3 py-2 border-b border-border-subtle space-y-2">
            <div v-if="replacementRequest" class="rounded-xl border border-orange-500/20 bg-orange-500/8 px-3 py-2 text-[11px] text-orange-300">
              正在替换
              <span class="font-semibold">{{ appStore.getModel(replacementRequest.oldModelId)?.name ?? replacementRequest.oldModelId }}</span>
              ，仅本次卡片会换成你新选的模型。
            </div>
            <div class="flex items-center gap-2">
              <Search :size="14" class="text-text-tertiary shrink-0" />
              <input type="text" :value="searchQuery" @input="handleSearch" placeholder="搜索模型..."
                class="flex-1 bg-transparent text-sm text-text-primary placeholder-text-tertiary outline-none"
                autofocus />
            </div>
            <!-- Filter chips -->
            <div class="flex items-center gap-1.5">
              <button @click="toggleFilterFree"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-all border"
                :class="appStore.preferFree
                  ? 'bg-green-500/15 text-green-400 border-green-500/30'
                  : 'text-text-tertiary border-border-subtle hover:bg-surface-3'">
                <DollarSign :size="10" />
                免费
              </button>
              <button @click="toggleFilterVision"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-all border"
                :class="filterVision
                  ? 'bg-purple-500/15 text-purple-400 border-purple-500/30'
                  : 'text-text-tertiary border-border-subtle hover:bg-surface-3'">
                <Image :size="10" />
                图片
              </button>
              <span class="text-[10px] text-text-tertiary ml-auto">{{ filteredModels.length }}
                个模型</span>
            </div>
            <!-- Recent searches -->
            <div v-if="!searchQuery && recentSearches.length"
              class="flex items-center gap-1 overflow-x-auto no-scrollbar">
              <Clock :size="10" class="text-text-tertiary shrink-0" />
              <button v-for="kw in recentSearches" :key="kw" @click="applyRecentSearch(kw)"
                class="shrink-0 px-2 py-0.5 rounded-full text-[10px] text-text-tertiary
                       bg-surface-3 hover:bg-surface-2 hover:text-text-secondary transition-colors">{{ kw }}</button>
            </div>
          </div>

          <!-- Model list grouped by provider -->
          <div class="overflow-y-auto flex-1 p-1.5">
            <template v-for="(models, provider) in groupedFiltered" :key="provider">
              <div class="flex items-center gap-2 px-2.5 pt-2.5 pb-1">
                <span class="w-2 h-2 rounded-full shrink-0"
                  :style="{ backgroundColor: getModelColor(provider) }" />
                <span
                  class="text-[10px] font-bold uppercase tracking-wider text-text-tertiary">{{ provider }}</span>
                <span class="text-[10px] text-text-tertiary">({{ models.length }})</span>
              </div>
              <div v-for="model in models" :key="model.id" @click="selectModel(model.id)"
                class="flex items-center gap-2.5 px-2.5 py-2 rounded-lg cursor-pointer transition-all text-sm"
                :class="replacementRequest
                  ? (isReplacementDisabled(model.id)
                    ? 'opacity-35 cursor-not-allowed text-text-tertiary'
                    : model.id === replacementRequest.oldModelId
                      ? 'bg-orange-500/10 text-orange-300'
                      : 'text-text-secondary hover:bg-white/5 hover:text-text-primary')
                  : appStore.selectedModelIds.includes(model.id)
                  ? 'bg-accent/10 text-accent'
                  : 'text-text-secondary hover:bg-white/5 hover:text-text-primary'">
                <span class="flex-1 truncate">{{ model.name }}</span>
                <span v-if="model.free"
                  class="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-green-500/15 text-green-400">FREE</span>
                <span v-if="model.supportsVision"
                  class="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-purple-500/15 text-purple-400">VISION</span>
                <span class="text-[9px] font-medium px-1.5 py-0.5 rounded-full"
                  :class="tierClass(model.tier)">{{ tierLabel(model.tier) }}</span>
                <span v-if="replacementRequest && model.id === replacementRequest.oldModelId"
                  class="text-orange-400 text-xs">当前</span>
                <span v-else-if="replacementRequest && isReplacementDisabled(model.id)"
                  class="text-text-tertiary text-xs">已选</span>
                <span v-else-if="appStore.selectedModelIds.includes(model.id)"
                  class="text-accent text-xs">✓</span>
              </div>
            </template>

            <p v-if="!filteredModels.length" class="text-xs text-text-tertiary text-center py-4">
              未找到匹配的模型
            </p>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.no-scrollbar::-webkit-scrollbar {
  display: none;
}

.popover-enter-active {
  animation: popIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.popover-leave-active {
  animation: popOut 0.15s ease-in;
}
@keyframes popIn {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
@keyframes popOut {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
    transform: translateY(4px);
  }
}
</style>
