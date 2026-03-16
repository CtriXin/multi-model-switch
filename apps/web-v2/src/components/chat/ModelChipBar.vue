<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore, getModelColor, type ModelMeta } from '@/stores/app'
import { X, Plus, Search, GitMerge, Shuffle, DollarSign, Image, Clock } from 'lucide-vue-next'
import { getSearchHistory, addSearchHistory } from '@/utils/searchHistory'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const popoverOpen = ref(false)
const searchQuery = ref('')
const filterFree = ref(true)
const filterVision = ref(false)
const recentSearches = ref<string[]>([])

const filteredModels = ref<typeof appStore.models>([])

/** Group filtered models by provider for the popover */
const groupedFiltered = computed(() => {
  const map: Record<string, ModelMeta[]> = {}
  for (const m of filteredModels.value) {
    ;(map[m.provider] ??= []).push(m)
  }
  return map
})

function updateFiltered() {
  const q = searchQuery.value.toLowerCase()
  filteredModels.value = appStore.models.filter(m => {
    if (filterFree.value && !m.free) return false
    if (filterVision.value && !m.supportsVision) return false
    if (q && !m.name.toLowerCase().includes(q) && !m.provider.toLowerCase().includes(q) && !m.id.toLowerCase().includes(q)) return false
    return true
  })
}

function togglePopover() {
  popoverOpen.value = !popoverOpen.value
  if (popoverOpen.value) {
    searchQuery.value = ''
    filterFree.value = true
    filterVision.value = false
    recentSearches.value = getSearchHistory()
    updateFiltered()
  }
}

function selectModel(id: string) {
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
  filterFree.value = !filterFree.value
  updateFiltered()
}

function toggleFilterVision() {
  filterVision.value = !filterVision.value
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

// Watch for popover close to commit search
watch(popoverOpen, (val) => {
  if (!val) commitSearch()
})
</script>

<template>
  <div class="relative border-t border-border-subtle bg-surface-1">
    <div class="max-w-5xl mx-auto px-4">
      <div class="flex items-center h-10">
      <!-- Scrollable chips area -->
      <div class="flex-1 min-w-0 overflow-x-auto no-scrollbar">
        <div class="flex items-center gap-1.5 py-1.5 w-max min-w-full">
          <span
            v-for="m in appStore.selectedModels"
            :key="m.id"
            class="inline-flex items-center gap-1.5 pl-1 pr-1.5 py-1 rounded-full text-xs
                   whitespace-nowrap shrink-0 group border transition-colors"
            :style="{
              backgroundColor: getModelColor(m.provider) + '12',
              borderColor: getModelColor(m.provider) + '25',
            }"
          >
            <span
              class="w-2 h-2 rounded-full shrink-0"
              :style="{ backgroundColor: getModelColor(m.provider) }"
            />
            <span class="truncate max-w-[80px] text-text-primary">{{ m.name }}</span>
            <span v-if="m.free" class="text-[8px] text-green-400 font-medium">$0</span>
            <span v-if="m.supportsVision" class="text-[8px] text-purple-400">📷</span>
            <button
              @click.stop="removeModel(m.id)"
              class="p-0.5 rounded-full hover:bg-white/10 opacity-40 group-hover:opacity-100 transition-opacity"
            >
              <X :size="10" />
            </button>
          </span>
          <span v-if="!appStore.selectedModels.length" class="text-xs text-text-tertiary whitespace-nowrap">
            未选择模型
          </span>
        </div>
      </div>

      <!-- Fixed right buttons -->
      <div class="flex items-center gap-1 shrink-0 border-l border-border-subtle pl-3">
        <button
          @click="appStore.randomPick()"
          class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs
                 text-amber-400 hover:bg-amber-500/10 active:scale-95 transition-all whitespace-nowrap"
          title="随机换一组模型"
        >
          <Shuffle :size="12" />
          换一组
        </button>
        <button
          @click="togglePopover"
          class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs
                 text-accent hover:bg-accent/10 active:scale-95 transition-all whitespace-nowrap"
        >
          <Plus :size="12" />
          模型
        </button>
        <button
          v-if="route.path === '/chat'"
          @click="router.push('/discuss')"
          class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs
                 text-purple-400 hover:bg-purple-500/10 active:scale-95 transition-all whitespace-nowrap"
        >
          <GitMerge :size="12" />
          讨论
        </button>
      </div>
      </div>
    </div>

    <!-- Popover dropdown -->
    <Transition name="popover">
      <div
        v-if="popoverOpen"
        class="absolute left-0 right-0 bottom-full mb-1 z-50 px-4"
      >
        <div class="fixed inset-0" @click="popoverOpen = false" />

        <div class="relative max-w-5xl mx-auto card shadow-xl max-h-80 flex flex-col">
          <!-- Search + Filter -->
          <div class="px-3 py-2 border-b border-border-subtle space-y-2">
            <div class="flex items-center gap-2">
              <Search :size="14" class="text-text-tertiary shrink-0" />
              <input
                type="text"
                :value="searchQuery"
                @input="handleSearch"
                placeholder="搜索模型..."
                class="flex-1 bg-transparent text-sm text-text-primary placeholder-text-tertiary outline-none"
                autofocus
              />
            </div>
            <!-- Filter chips -->
            <div class="flex items-center gap-1.5">
              <button
                @click="toggleFilterFree"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-all border"
                :class="filterFree
                  ? 'bg-green-500/15 text-green-400 border-green-500/30'
                  : 'text-text-tertiary border-border-subtle hover:bg-surface-3'"
              >
                <DollarSign :size="10" />
                免费
              </button>
              <button
                @click="toggleFilterVision"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-all border"
                :class="filterVision
                  ? 'bg-purple-500/15 text-purple-400 border-purple-500/30'
                  : 'text-text-tertiary border-border-subtle hover:bg-surface-3'"
              >
                <Image :size="10" />
                图片
              </button>
              <span class="text-[10px] text-text-tertiary ml-auto">{{ filteredModels.length }} 个模型</span>
            </div>
            <!-- Recent searches -->
            <div v-if="!searchQuery && recentSearches.length" class="flex items-center gap-1 overflow-x-auto no-scrollbar">
              <Clock :size="10" class="text-text-tertiary shrink-0" />
              <button
                v-for="kw in recentSearches"
                :key="kw"
                @click="applyRecentSearch(kw)"
                class="shrink-0 px-2 py-0.5 rounded-full text-[10px] text-text-tertiary
                       bg-surface-3 hover:bg-surface-2 hover:text-text-secondary transition-colors"
              >{{ kw }}</button>
            </div>
          </div>

          <!-- Model list grouped by provider -->
          <div class="overflow-y-auto flex-1 p-1.5">
            <template v-for="(models, provider) in groupedFiltered" :key="provider">
              <div class="flex items-center gap-2 px-2.5 pt-2.5 pb-1">
                <span
                  class="w-2 h-2 rounded-full shrink-0"
                  :style="{ backgroundColor: getModelColor(provider) }"
                />
                <span class="text-[10px] font-bold uppercase tracking-wider text-text-tertiary">{{ provider }}</span>
                <span class="text-[10px] text-text-tertiary">({{ models.length }})</span>
              </div>
              <div
                v-for="model in models"
                :key="model.id"
                @click="selectModel(model.id)"
                class="flex items-center gap-2.5 px-2.5 py-2 rounded-lg cursor-pointer transition-all text-sm"
                :class="appStore.selectedModelIds.includes(model.id)
                  ? 'bg-accent/10 text-accent'
                  : 'text-text-secondary hover:bg-white/5 hover:text-text-primary'"
              >
                <span class="flex-1 truncate">{{ model.name }}</span>
                <span
                  v-if="model.free"
                  class="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-green-500/15 text-green-400"
                >FREE</span>
                <span
                  v-if="model.supportsVision"
                  class="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-purple-500/15 text-purple-400"
                >VISION</span>
                <span
                  class="text-[9px] font-medium px-1.5 py-0.5 rounded-full"
                  :class="tierClass(model.tier)"
                >{{ tierLabel(model.tier) }}</span>
                <span v-if="appStore.selectedModelIds.includes(model.id)" class="text-accent text-xs">✓</span>
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
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
.no-scrollbar::-webkit-scrollbar { display: none; }

.popover-enter-active { animation: popIn 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
.popover-leave-active { animation: popOut 0.15s ease-in; }
@keyframes popIn {
  from { opacity: 0; transform: translateY(8px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes popOut {
  from { opacity: 1; }
  to { opacity: 0; transform: translateY(4px); }
}
</style>
