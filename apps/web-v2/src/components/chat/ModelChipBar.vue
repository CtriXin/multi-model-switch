<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore, getModelColor } from '@/stores/app'
import { X, Plus, Search, GitMerge, Shuffle } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const popoverOpen = ref(false)
const searchQuery = ref('')

const filteredModels = ref<typeof appStore.models>([])

function updateFiltered() {
  const q = searchQuery.value.toLowerCase()
  filteredModels.value = appStore.models.filter(m =>
    !q || m.name.toLowerCase().includes(q) || m.provider.toLowerCase().includes(q)
  )
}

function togglePopover() {
  popoverOpen.value = !popoverOpen.value
  if (popoverOpen.value) {
    searchQuery.value = ''
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
</script>

<template>
  <div class="relative border-t border-border-subtle bg-surface-1">
    <div class="max-w-3xl mx-auto flex items-center h-10">
      <!-- Scrollable chips area -->
      <div class="flex-1 min-w-0 overflow-x-auto no-scrollbar">
        <div class="flex items-center gap-1.5 px-3 py-1.5 w-max">
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
      <div class="flex items-center gap-1 pr-3 shrink-0 border-l border-border-subtle pl-2">
        <button
          @click="appStore.randomPick()"
          class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs
                 text-amber-400 hover:bg-amber-500/10 active:scale-95 transition-all whitespace-nowrap"
          title="手气不错 — 随机选模型"
        >
          <Shuffle :size="12" />
          手气
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

    <!-- Popover dropdown -->
    <Transition name="popover">
      <div
        v-if="popoverOpen"
        class="absolute left-0 right-0 bottom-full mb-1 z-50 px-3"
      >
        <div class="fixed inset-0" @click="popoverOpen = false" />

        <div class="relative max-w-3xl mx-auto card shadow-xl max-h-72 flex flex-col">
          <!-- Search -->
          <div class="flex items-center gap-2 px-3 py-2 border-b border-border-subtle">
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

          <!-- Model list -->
          <div class="overflow-y-auto flex-1 p-1.5">
            <div
              v-for="model in filteredModels"
              :key="model.id"
              @click="selectModel(model.id)"
              class="flex items-center gap-2.5 px-2.5 py-2 rounded-lg cursor-pointer transition-all text-sm"
              :class="appStore.selectedModelIds.includes(model.id)
                ? 'bg-accent/10 text-accent'
                : 'text-text-secondary hover:bg-white/5 hover:text-text-primary'"
            >
              <span
                class="w-2.5 h-2.5 rounded-full shrink-0"
                :style="{ backgroundColor: getModelColor(model.provider) }"
              />
              <span class="flex-1 truncate">{{ model.name }}</span>
              <span
                class="text-[9px] font-medium px-1.5 py-0.5 rounded-full"
                :class="tierClass(model.tier)"
              >{{ tierLabel(model.tier) }}</span>
              <span v-if="appStore.selectedModelIds.includes(model.id)" class="text-accent text-xs">✓</span>
            </div>

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
