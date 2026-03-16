<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Rocket, ArrowRight } from 'lucide-vue-next'
import { useProviderStore } from '@/stores/provider'
import { FREE_PROVIDERS, CN_PROVIDERS, INTL_PROVIDERS } from '@/data/freeProviders'
import SetupProviderCard from '@/components/SetupProviderCard.vue'

const router = useRouter()
const providerStore = useProviderStore()

const expanded = ref(FREE_PROVIDERS[0].id)

const configuredCount = computed(() =>
  FREE_PROVIDERS.filter(p => providerStore.keyStatus[p.id]).length,
)

const hasAnyKey = computed(() => configuredCount.value > 0)

function toggleExpand(id: string) {
  expanded.value = expanded.value === id ? '' : id
}

function skipToDemo() {
  router.push('/chat')
}

function startUsing() {
  router.push('/chat')
}
</script>

<template>
  <div class="flex-1 overflow-y-auto overscroll-contain" style="-webkit-overflow-scrolling: touch">
    <header class="sticky top-0 z-10 border-b border-border-default bg-surface-1/95 backdrop-blur-sm px-6 py-4">
      <div class="max-w-2xl mx-auto flex items-center gap-3">
        <div
          class="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-cyan-500 shadow-lg"
        >
          <Rocket :size="20" class="text-white" />
        </div>
        <div class="min-w-0">
          <h1 class="text-lg font-semibold text-text-primary">快速开始</h1>
          <p class="mt-1 text-xs text-text-tertiary">
            先配一个能用的免费 API 就能开始，复杂通道管理放到设置里。
          </p>
        </div>
        <div class="ml-auto flex items-center gap-2">
          <div class="flex gap-1">
            <div
              v-for="p in FREE_PROVIDERS"
              :key="p.id"
              class="w-2 h-2 rounded-full transition-colors duration-300"
              :class="providerStore.keyStatus[p.id] ? 'bg-emerald-400' : 'bg-surface-4'"
            />
          </div>
          <span class="text-xs text-text-tertiary">
            {{ configuredCount }} / {{ FREE_PROVIDERS.length }} 已配置
          </span>
        </div>
      </div>
    </header>

    <div class="max-w-2xl mx-auto px-6 py-10">
      <div class="text-center mb-10 animate-fade-in">
        <div
          class="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-400 to-cyan-500
                 flex items-center justify-center mx-auto mb-4 shadow-lg"
        >
          <Rocket :size="24" class="text-white" />
        </div>
        <h2 class="text-xl font-bold text-text-primary mb-2">三分钟开始使用</h2>
        <p class="text-sm text-text-tertiary max-w-md mx-auto">
          选一个顺手的免费通道先跑起来，后面需要多账户、分享包或高级配置再去设置里管。
        </p>
      </div>

      <!-- CN Providers -->
      <div class="mb-8">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-xs font-semibold text-text-tertiary uppercase tracking-wider">国产服务商</span>
          <span class="text-[10px] text-text-tertiary/60">国内直连，无需代理</span>
        </div>
        <div class="space-y-3">
          <SetupProviderCard
            v-for="p in CN_PROVIDERS"
            :key="p.id"
            :provider="p"
            :expanded="expanded === p.id"
            @toggle-expand="toggleExpand(p.id)"
          />
        </div>
      </div>

      <!-- International Providers -->
      <div class="mb-10">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-xs font-semibold text-text-tertiary uppercase tracking-wider">国际服务商</span>
          <span class="text-[10px] text-text-tertiary/60">需科学上网</span>
        </div>
        <div class="space-y-3">
          <SetupProviderCard
            v-for="p in INTL_PROVIDERS"
            :key="p.id"
            :provider="p"
            :expanded="expanded === p.id"
            @toggle-expand="toggleExpand(p.id)"
          />
        </div>
      </div>

      <!-- Bottom Actions -->
      <div class="flex items-center justify-between pb-8">
        <button
          @click="skipToDemo"
          class="text-sm text-text-tertiary hover:text-text-secondary transition-colors"
        >
          {{ hasAnyKey ? '返回首页' : '跳过，先体验 Demo →' }}
        </button>
        <button
          v-if="hasAnyKey"
          @click="startUsing"
          class="inline-flex items-center gap-1.5 px-5 py-2.5 text-sm font-medium text-white
                 bg-accent rounded-xl hover:bg-accent/90 transition-colors shadow-sm"
        >
          开始使用
          <ArrowRight :size="14" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.animate-fade-in {
  animation: fadeIn 0.5s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
