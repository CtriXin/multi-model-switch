<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { Plus, Search, Shuffle, Copy, X, DollarSign, Image, Clock } from 'lucide-vue-next'
import { getModelColor, useAppStore } from '@/stores/app'
import { getSearchHistory, addSearchHistory } from '@/utils/searchHistory'

const emit = defineEmits<{
  openSheet: []
}>()

const appStore = useAppStore()
const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const popoverOpen = ref(false)
const searchQuery = ref('')
const filterFree = ref(true)
const filterVision = ref(false)
const recentSearches = ref<string[]>([])
const MAX_SELECTION = 5

const selectedCount = computed(() => appStore.committeeSelectedModels.length)
const isMobile = computed(() => platform.value === 'ios')

const filteredModels = computed(() => {
  const q = searchQuery.value.toLowerCase()
  return [...appStore.models]
    .filter((model) => {
      if (filterFree.value && !model.free) return false
      if (filterVision.value && !model.supportsVision) return false
      if (q && !model.name.toLowerCase().includes(q)
          && !model.provider.toLowerCase().includes(q)
          && !model.id.toLowerCase().includes(q)) return false
      return true
    })
    .sort((left, right) => {
      const leftSelected = appStore.committeeSelectedModelIds.includes(left.id) ? 1 : 0
      const rightSelected = appStore.committeeSelectedModelIds.includes(right.id) ? 1 : 0
      if (leftSelected !== rightSelected) return rightSelected - leftSelected
      if (left.tier !== right.tier) return right.tier - left.tier
      return left.name.localeCompare(right.name)
    })
})

function togglePopover() {
  if (isMobile.value) {
    emit('openSheet')
    return
  }
  popoverOpen.value = !popoverOpen.value
  if (popoverOpen.value) {
    searchQuery.value = ''
    filterFree.value = true
    filterVision.value = false
    recentSearches.value = getSearchHistory()
  } else {
    if (searchQuery.value.trim()) addSearchHistory(searchQuery.value.trim())
  }
}

function applyRecentSearch(keyword: string) {
  searchQuery.value = keyword
}

function tierLabel(tier: number) {
  if (tier === 2) return '旗舰'
  if (tier === 1) return '主力'
  return '经济'
}

function tierClass(tier: number) {
  if (tier === 2) return 'bg-amber-500/15 text-amber-400'
  if (tier === 1) return 'bg-blue-500/15 text-blue-400'
  return 'bg-green-500/15 text-green-400'
}
</script>

<template>
  <div class="relative isolate rounded-4xl border border-border-default bg-surface-2/60 p-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-text-tertiary">Model Pool</div>
        <div class="mt-2 text-lg font-semibold text-text-primary">绑定模型池</div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          @click="appStore.copySelection('chat', 'committee')"
          type="button"
          class="inline-flex h-9 items-center gap-1 rounded-full border border-border-subtle bg-surface-1 px-3.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-default hover:text-text-primary"
        >
          <Copy :size="13" />
          导入聊天已选
        </button>
        <button
          @click.stop="togglePopover"
          type="button"
          :aria-expanded="popoverOpen"
          class="inline-flex h-9 items-center gap-1.5 rounded-full border bg-surface-1 px-3.5 text-xs font-medium transition-colors"
          :class="popoverOpen
            ? 'border-accent/35 bg-accent/10 text-accent'
            : 'border-accent/25 text-accent hover:bg-accent/10'"
        >
          <Plus :size="13" />
          绑定模型
          <span class="rounded-full bg-current/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none">
            {{ selectedCount }}/{{ MAX_SELECTION }}
          </span>
        </button>
      </div>
    </div>

    <div class="mt-4 flex flex-wrap gap-2 min-h-9">
      <button
        v-for="model in appStore.committeeSelectedModels"
        :key="model.id"
        @click="appStore.toggleModel(model.id, 'committee')"
        type="button"
        class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors"
        :style="{
          backgroundColor: getModelColor(model.provider) + '14',
          borderColor: getModelColor(model.provider) + '30',
        }"
      >
        <span
          class="w-4 h-4 rounded flex items-center justify-center text-[8px] font-bold text-white"
          :style="{ backgroundColor: getModelColor(model.provider) }"
        >
          {{ model.name.charAt(0) }}
        </span>
        <span class="text-text-primary">{{ model.name }}</span>
        <span v-if="model.free" class="text-[8px] text-green-400 font-medium">$0</span>
        <span v-if="model.supportsVision" class="text-[8px] text-purple-400">📷</span>
        <X :size="11" class="text-text-tertiary" />
      </button>
      <span v-if="!appStore.committeeSelectedModels.length" class="text-sm text-text-tertiary">
        还没绑定模型。至少选 1 个，锦囊团才能开会。
      </span>
    </div>

    <div class="mt-5 rounded-3xl border border-border-default bg-surface-1 p-4">
      <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-text-tertiary">当前运行</div>
      <div class="mt-3 grid gap-3 sm:grid-cols-2">
        <div class="rounded-2xl border border-border-subtle bg-surface-2 p-3">
          <div class="text-xs text-text-tertiary">模型池</div>
          <div class="mt-1 text-2xl font-semibold text-text-primary">{{ selectedCount }}</div>
        </div>
        <div class="rounded-2xl border border-border-subtle bg-surface-2 p-3">
          <div class="text-xs text-text-tertiary">说明</div>
          <div class="mt-1 text-sm font-semibold text-text-primary">关键角色优先拿强模型</div>
        </div>
      </div>
      <div class="mt-4 flex items-center gap-2">
        <button
          @click="appStore.randomPick(3, 'committee')"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-default hover:text-text-primary"
        >
          <Shuffle :size="12" />
          换一组
        </button>
        <button
          @click="appStore.clearSelection('committee')"
          type="button"
          class="inline-flex items-center gap-1 rounded-full border border-border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-default hover:text-text-primary"
        >
          清空
        </button>
      </div>
      <p class="mt-4 text-xs leading-6 text-text-tertiary">
        这里维护的是锦囊团独立模型池；"导入聊天已选"会把 Chat 当前勾选的模型复制过来，不会反向改动聊天页选择。
      </p>
    </div>

    <Teleport v-if="!isMobile" to="body">
        <div
          v-if="popoverOpen"
          class="fixed inset-0 z-[9990] flex items-start justify-center pt-[12vh]"
        >
          <div class="absolute inset-0 bg-black/40" @click="popoverOpen = false" />
          <div
            class="relative z-10 w-full max-w-lg max-h-[70vh] overflow-hidden rounded-2xl border border-border-default bg-surface-1 shadow-2xl"
            @click.stop
          >
          <div class="border-b border-border-subtle px-4 py-3">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-text-primary">选择模型</div>
                <div class="mt-1 text-[11px] text-text-tertiary">{{ selectedCount }} / {{ MAX_SELECTION }} 已选</div>
              </div>
              <button
                v-if="selectedCount"
                @click="appStore.clearSelection('committee')"
                type="button"
                class="rounded-full border border-border-subtle px-2.5 py-1 text-[11px] font-medium text-text-secondary transition-colors hover:border-border-default hover:text-text-primary"
              >
                清空
              </button>
            </div>

            <div class="mt-3 flex items-center gap-2 rounded-xl border border-border-subtle bg-surface-2 px-3 py-2">
              <Search :size="14" class="text-text-tertiary shrink-0" />
              <input
                v-model="searchQuery"
                type="text"
                placeholder="搜索模型..."
                class="flex-1 bg-transparent text-sm text-text-primary placeholder-text-tertiary outline-none"
                autofocus
              />
            </div>

            <!-- Filter chips -->
            <div class="mt-2 flex items-center gap-1.5">
              <button
                @click="filterFree = !filterFree"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-all border"
                :class="filterFree
                  ? 'bg-green-500/15 text-green-400 border-green-500/30'
                  : 'text-text-tertiary border-border-subtle hover:bg-surface-3'"
              >
                <DollarSign :size="10" />
                免费
              </button>
              <button
                @click="filterVision = !filterVision"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-all border"
                :class="filterVision
                  ? 'bg-purple-500/15 text-purple-400 border-purple-500/30'
                  : 'text-text-tertiary border-border-subtle hover:bg-surface-3'"
              >
                <Image :size="10" />
                图片
              </button>
              <span class="text-[10px] text-text-tertiary ml-auto">{{ filteredModels.length }} 个</span>
            </div>

            <!-- Recent searches -->
            <div v-if="!searchQuery && recentSearches.length" class="mt-2 flex items-center gap-1 overflow-x-auto no-scrollbar">
              <Clock :size="10" class="text-text-tertiary shrink-0" />
              <button
                v-for="kw in recentSearches"
                :key="kw"
                @click="applyRecentSearch(kw)"
                class="shrink-0 px-2 py-0.5 rounded-full text-[10px] text-text-tertiary
                       bg-surface-3 hover:bg-surface-2 transition-colors"
              >{{ kw }}</button>
            </div>
          </div>

          <div
            v-if="selectedCount"
            class="border-b border-border-subtle px-4 py-3"
          >
            <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-text-tertiary">当前已选</div>
            <div class="mt-2 flex flex-wrap gap-2">
              <button
                v-for="model in appStore.committeeSelectedModels"
                :key="model.id"
                @click="appStore.toggleModel(model.id, 'committee')"
                type="button"
                class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors"
                :style="{
                  backgroundColor: getModelColor(model.provider) + '14',
                  borderColor: getModelColor(model.provider) + '30',
                }"
              >
                <span
                  class="h-4 w-4 rounded flex items-center justify-center text-[8px] font-bold text-white"
                  :style="{ backgroundColor: getModelColor(model.provider) }"
                >
                  {{ model.name.charAt(0) }}
                </span>
                <span class="max-w-[11rem] truncate text-text-primary">{{ model.name }}</span>
                <X :size="11" class="text-text-tertiary" />
              </button>
            </div>
          </div>

          <div class="overflow-y-auto p-2">
            <button
              v-for="model in filteredModels"
              :key="model.id"
              @click="appStore.toggleModel(model.id, 'committee')"
              type="button"
              class="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-all text-sm"
              :class="appStore.committeeSelectedModelIds.includes(model.id)
                ? 'bg-accent/10 text-accent'
                : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'"
            >
              <span
                class="w-2.5 h-2.5 rounded-full shrink-0"
                :style="{ backgroundColor: getModelColor(model.provider) }"
              />
              <span class="flex-1 truncate">{{ model.name }}</span>
              <span
                v-if="model.free"
                class="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-green-500/15 text-green-400"
              >FREE</span>
              <span
                v-if="model.supportsVision"
                class="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-purple-500/15 text-purple-400"
              >VISION</span>
              <span class="text-[9px] font-medium px-1.5 py-0.5 rounded-full" :class="tierClass(model.tier)">
                {{ tierLabel(model.tier) }}
              </span>
              <span v-if="appStore.committeeSelectedModelIds.includes(model.id)" class="text-accent text-xs">✓</span>
            </button>

            <p v-if="!filteredModels.length" class="text-xs text-text-tertiary text-center py-4">
              没有符合条件的模型
            </p>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
