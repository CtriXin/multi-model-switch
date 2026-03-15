<script setup lang="ts">
import { computed, ref } from 'vue'
import { Plus, Search, Shuffle, Copy, X } from 'lucide-vue-next'
import { getModelColor, useAppStore } from '@/stores/app'

const appStore = useAppStore()
const popoverOpen = ref(false)
const searchQuery = ref('')

const filteredModels = computed(() => {
  const q = searchQuery.value.toLowerCase()
  return appStore.models.filter((model) =>
    !q
    || model.name.toLowerCase().includes(q)
    || model.provider.toLowerCase().includes(q)
    || model.id.toLowerCase().includes(q)
  )
})

function togglePopover() {
  popoverOpen.value = !popoverOpen.value
  if (!popoverOpen.value) searchQuery.value = ''
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
  <div class="relative rounded-[1.5rem] border border-border-default bg-surface-2/60 p-5">
    <div class="flex items-center justify-between gap-3">
      <div>
        <div class="text-[11px] font-semibold uppercase tracking-[0.24em] text-text-tertiary">Model Pool</div>
        <div class="mt-2 text-lg font-semibold text-text-primary">绑定模型池</div>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="appStore.copySelection('chat', 'committee')"
          class="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-surface-1 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-default hover:text-text-primary"
        >
          <Copy :size="13" />
          导入聊天已选
        </button>
        <button
          @click="togglePopover"
          class="inline-flex items-center gap-1 rounded-full border border-accent/25 bg-surface-1 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
        >
          <Plus :size="13" />
          绑定模型
        </button>
      </div>
    </div>

    <div class="mt-4 flex flex-wrap gap-2 min-h-9">
      <button
        v-for="model in appStore.committeeSelectedModels"
        :key="model.id"
        @click="appStore.toggleModel(model.id, 'committee')"
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
        <X :size="11" class="text-text-tertiary" />
      </button>
      <span v-if="!appStore.committeeSelectedModels.length" class="text-sm text-text-tertiary">
        还没绑定模型。至少选 1 个，锦囊团才能开会。
      </span>
    </div>

    <div class="mt-5 rounded-[1.25rem] border border-border-default bg-surface-1 p-4">
      <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-text-tertiary">当前运行</div>
      <div class="mt-3 grid gap-3 sm:grid-cols-2">
        <div class="rounded-2xl border border-border-subtle bg-surface-2 p-3">
          <div class="text-xs text-text-tertiary">模型池</div>
          <div class="mt-1 text-2xl font-semibold text-text-primary">{{ appStore.committeeSelectedModels.length }}</div>
        </div>
        <div class="rounded-2xl border border-border-subtle bg-surface-2 p-3">
          <div class="text-xs text-text-tertiary">说明</div>
          <div class="mt-1 text-sm font-semibold text-text-primary">关键角色优先拿强模型</div>
        </div>
      </div>
      <div class="mt-4 flex items-center gap-2">
        <button
          @click="appStore.randomPick(3, 'committee')"
          class="inline-flex items-center gap-1 rounded-full border border-border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-default hover:text-text-primary"
        >
          <Shuffle :size="12" />
          随机来一组
        </button>
        <button
          @click="appStore.clearSelection('committee')"
          class="inline-flex items-center gap-1 rounded-full border border-border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-border-default hover:text-text-primary"
        >
          清空
        </button>
      </div>
      <p class="mt-4 text-xs leading-6 text-text-tertiary">
        这里维护的是锦囊团独立模型池；“导入聊天已选”会把 Chat 当前勾选的模型复制过来，不会反向改动聊天页选择。
      </p>
    </div>

    <Transition name="popover">
      <div
        v-if="popoverOpen"
        class="absolute left-0 right-0 top-full mt-3 z-20"
      >
        <div class="fixed inset-0" @click="popoverOpen = false" />
        <div class="relative rounded-[1.4rem] border border-border-default bg-surface-1 shadow-xl max-h-80 flex flex-col overflow-hidden">
          <div class="flex items-center gap-2 px-4 py-3 border-b border-border-subtle">
            <Search :size="14" class="text-text-tertiary shrink-0" />
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索模型..."
              class="flex-1 bg-transparent text-sm text-text-primary placeholder-text-tertiary outline-none"
              autofocus
            />
          </div>

          <div class="overflow-y-auto p-2">
            <button
              v-for="model in filteredModels"
              :key="model.id"
              @click="appStore.toggleModel(model.id, 'committee')"
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
              <span class="text-[9px] font-medium px-1.5 py-0.5 rounded-full" :class="tierClass(model.tier)">
                {{ tierLabel(model.tier) }}
              </span>
              <span v-if="appStore.committeeSelectedModelIds.includes(model.id)" class="text-accent text-xs">✓</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
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
