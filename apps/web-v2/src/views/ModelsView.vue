<script setup lang="ts">
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore, getModelColor, type ModelMeta, type ModelPoolTag } from '@/stores/app'
import { 
  Cpu, Zap, Brain, Eye, Code, Loader2, AlertCircle, EyeOff, DollarSign, Image, 
  RotateCcw, ToggleLeft, ToggleRight, Check, Database, Gauge, Activity, Globe
} from 'lucide-vue-next'

const appStore = useAppStore()
const router = useRouter()

// Platform detection for mobile layout
const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isMobile = computed(() => platform.value === 'ios')

// Filter state
const filterVision = ref(false)
const filterFree = ref(appStore.preferFree)
const tierFilters = ref<ModelPoolTag[]>([])

const suppressedCount = computed(() => appStore.getSuppressedModelIds().length)

const filteredModels = computed(() => {
  return appStore.filterModels({
    tags: tierFilters.value,
    requireFree: filterFree.value,
    requireVision: filterVision.value,
  })
})

const modelsByProvider = computed(() => {
  const map: Record<string, ModelMeta[]> = {}
  for (const m of filteredModels.value) {
    ;(map[m.provider] ??= []).push(m)
  }
  return map
})

const providers = computed(() => Object.keys(modelsByProvider.value))

function tierLabel(tier: number): string {
  return tier === 2 ? 'Premium' : tier === 1 ? 'Standard' : 'Basic'
}

function tierClass(tier: number, isActive: boolean): string {
  if (tier === 2) {
    return isActive 
      ? 'bg-amber-500 text-black border-amber-500 shadow-lg shadow-amber-500/20' 
      : 'bg-amber-500/10 text-amber-500 border-amber-500/20'
  }
  if (tier === 1) {
    return isActive
      ? 'bg-blue-500 text-white border-blue-500 shadow-lg shadow-blue-500/20'
      : 'bg-blue-500/10 text-blue-500 border-blue-500/20'
  }
  return isActive
    ? 'bg-emerald-500 text-white border-emerald-500 shadow-lg shadow-emerald-500/20'
    : 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
}

function formatContext(n: number): string {
  return n >= 1_000_000 ? `${n / 1_000_000}M` : `${n / 1000}K`
}

function formatPrice(n: number): string {
  return `$${n}`
}

const tagIcons: Record<string, any> = {
  reasoning: Brain,
  coding: Code,
  vision: Eye,
  fast: Zap,
}

function goToSettings() {
  router.push('/settings')
}

function toggleTierFilter(tag: ModelPoolTag) {
  const next = new Set(tierFilters.value)
  if (next.has(tag)) next.delete(tag)
  else next.add(tag)
  tierFilters.value = Array.from(next)
}

function hasTierFilter(tag: ModelPoolTag) {
  return tierFilters.value.includes(tag)
}

function clearFilters() {
  tierFilters.value = []
  filterFree.value = false
  filterVision.value = false
}

function scrollToProvider(provider: string) {
  const el = document.getElementById(`provider-section-${provider}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

function toggleModel(id: string) {
  appStore.toggleModel(id)
}

onMounted(() => {
  if (!appStore.models.length) appStore.refreshModels()
})
</script>

<template>
  <div class="flex-1 flex flex-col lg:flex-row overflow-hidden">
    <!-- Mobile top bar -->
    <div v-if="isMobile" class="sticky top-0 z-[30] flex items-center justify-between px-4 py-3 bg-white/80 dark:bg-[#0b0b18]/80 backdrop-blur-md border-b border-white/5 safe-top shrink-0">
      <div class="flex items-center gap-3">
        <button @click="router.back()" class="p-1.5 -ml-1 rounded-lg active:bg-surface-3 transition-colors">
          <ChevronLeft :size="22" class="text-text-primary" />
        </button>
        <span class="text-base font-black uppercase tracking-tight text-text-primary">模型基因库</span>
      </div>
      <div class="p-2 bg-text-primary dark:bg-white rounded-lg shadow-lg">
        <Cpu :size="16" class="text-surface-1 dark:text-black" stroke-width="3" />
      </div>
    </div>

    <!-- Quick Jump Rail (The V3 Navigation Fix) -->
    <aside v-if="providers.length > 3" class="hidden lg:flex flex-col items-center py-8 gap-4 w-20 bg-black/5 dark:bg-white/2 border-r border-white/5 overflow-y-auto no-scrollbar shrink-0">
      <div class="p-2 bg-accent rounded-xl mb-4 shadow-lg shadow-accent/20">
        <Database :size="20" class="text-white" stroke-width="3" />
      </div>
      <button
        v-for="provider in providers"
        :key="provider"
        @click="scrollToProvider(provider)"
        class="w-12 h-12 rounded-2xl flex flex-col items-center justify-center transition-all duration-300 group relative active:scale-90 bg-white/5 hover:bg-white/10"
      >
        <span class="text-[10px] font-black uppercase leading-none text-text-tertiary group-hover:text-text-primary">{{ provider.slice(0, 2) }}</span>
        <div class="absolute left-16 px-3 py-1.5 rounded-lg bg-text-primary text-surface-1 text-[10px] font-black uppercase tracking-widest opacity-0 group-hover:opacity-100 pointer-events-none transition-all -translate-x-2 group-hover:translate-x-0 whitespace-nowrap shadow-xl z-50">
          {{ provider }}
        </div>
      </button>
    </aside>

    <!-- Main Content -->
    <div class="flex-1 overflow-y-auto custom-scrollbar scroll-smooth">
      <div class="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6 sm:space-y-10">
        <!-- Header Trinity Bar (Desktop Only or Unified) -->
        <div v-if="!isMobile" class="glass-v3 rounded-[32px] p-6 border border-white/10 shadow-2xl flex flex-wrap items-center justify-between gap-6">
          <div class="flex items-center gap-4">
            <div class="p-3 bg-text-primary dark:bg-white rounded-2xl shadow-xl">
              <Cpu :size="24" class="text-surface-1 dark:text-black" stroke-width="3" />
            </div>
            <div>
              <h1 class="text-2xl font-black text-text-primary tracking-tighter uppercase">模型基因库</h1>
              <p class="text-[10px] text-text-tertiary font-black uppercase tracking-[0.2em] opacity-50">
                <template v-if="appStore.loading">Syncing Registry...</template>
                <template v-else>{{ filteredModels.length }} / {{ appStore.models.length }} Models Active</template>
              </p>
            </div>
          </div>

          <!-- Controls Panel (Desktop) -->
          <div v-if="appStore.models.length" class="flex flex-wrap items-center gap-2 bg-black/[0.03] dark:bg-black/20 p-2 rounded-[20px] border border-black/5 dark:border-white/5">
            <button @click="filterFree = !filterFree" class="flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border shadow-sm"
                    :class="filterFree ? 'bg-emerald-500 text-white border-emerald-500 shadow-emerald-500/20' : 'bg-white dark:bg-white/5 text-text-tertiary border-black/5 dark:border-white/5 hover:border-accent/30 hover:text-text-primary'">
              <DollarSign :size="12" stroke-width="4" /> 免费 
              <component :is="filterFree ? ToggleRight : ToggleLeft" :size="14" stroke-width="3" />
            </button>
            <div class="w-px h-4 bg-black/5 dark:bg-white/10 mx-1"></div>
            <button v-for="tag in (['basic', 'std', 'pro'] as const)" :key="tag" @click="toggleTierFilter(tag)"
                    class="px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border shadow-sm"
                    :class="hasTierFilter(tag) ? 'bg-accent text-white border-accent shadow-accent/20' : 'bg-white dark:bg-white/5 text-text-tertiary border-black/5 dark:border-white/5 hover:border-accent/30 hover:text-text-primary'">
              {{ tag === 'pro' ? '旗舰' : tag === 'std' ? '主力' : '基础' }}
            </button>
            <div class="w-px h-4 bg-black/5 dark:bg-white/10 mx-1"></div>
            <button @click="filterVision = !filterVision" class="flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border shadow-sm"
                    :class="filterVision ? 'bg-purple-500 text-white border-purple-500 shadow-purple-500/20' : 'bg-white dark:bg-white/5 text-text-tertiary border-black/5 dark:border-white/5 hover:border-accent/30 hover:text-text-primary'">
              <Image :size="12" stroke-width="3" /> 视觉
            </button>
          </div>
        </div>

        <!-- Mobile Controls Panel -->
        <div v-else-if="appStore.models.length" class="flex flex-col gap-3 px-1">
          <div class="flex items-center justify-between">
            <p class="text-[10px] font-black text-text-tertiary uppercase tracking-widest opacity-50">{{ filteredModels.length }} / {{ appStore.models.length }} Models</p>
            <button @click="clearFilters" class="text-[9px] font-black text-accent uppercase tracking-widest underline decoration-2 underline-offset-4">Reset All</button>
          </div>
          <div class="flex flex-wrap gap-2">
            <button @click="filterFree = !filterFree" class="flex items-center gap-2 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border shadow-sm"
                    :class="filterFree ? 'bg-emerald-500 text-white border-emerald-500' : 'bg-white dark:bg-white/5 text-text-tertiary border-black/5 dark:border-white/5'">
              <DollarSign :size="12" stroke-width="4" /> 免费 
              <component :is="filterFree ? ToggleRight : ToggleLeft" :size="14" stroke-width="3" />
            </button>
            <button v-for="tag in (['basic', 'std', 'pro'] as const)" :key="tag" @click="toggleTierFilter(tag)"
                    class="px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border shadow-sm"
                    :class="hasTierFilter(tag) ? 'bg-accent text-white border-accent' : 'bg-white dark:bg-white/5 text-text-tertiary border-black/5 dark:border-white/5'">
              {{ tag === 'pro' ? '旗舰' : tag === 'std' ? '主力' : '基础' }}
            </button>
            <button @click="filterVision = !filterVision" class="flex items-center gap-2 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border shadow-sm"
                    :class="filterVision ? 'bg-purple-500 text-white border-purple-500' : 'bg-white dark:bg-white/5 text-text-tertiary border-black/5 dark:border-white/5'">
              <Image :size="12" stroke-width="3" /> 视觉
            </button>
          </div>
        </div>

        <!-- Loading / Empty States -->
        <div v-if="appStore.loading" class="py-20 flex flex-col items-center justify-center space-y-4">
          <Loader2 :size="40" class="text-accent animate-spin" stroke-width="3" />
          <p class="text-sm font-black text-text-tertiary uppercase tracking-[0.3em] animate-pulse">Synchronizing Genes...</p>
        </div>

        <div v-else-if="!appStore.models.length" class="glass-v3 rounded-[40px] p-16 text-center space-y-6 border border-white/10">
          <div class="w-20 h-20 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-4 border border-white/5 shadow-inner">
            <AlertCircle :size="40" class="text-text-tertiary opacity-30" />
          </div>
          <div>
            <p class="text-xl font-black text-text-primary uppercase">{{ appStore.error || '未检测到 API 链路' }}</p>
            <p class="text-xs text-text-tertiary mt-2 uppercase tracking-widest">请先在设置中心配置有效的 Provider 与密钥</p>
          </div>
          <button @click="goToSettings" class="px-10 py-4 rounded-2xl bg-accent text-white text-[11px] font-black uppercase tracking-[0.2em] shadow-2xl shadow-accent/30 hover:scale-105 active:scale-95 transition-all">前往系统配置</button>
        </div>

        <!-- Grouped Model Grid -->
        <div v-else class="space-y-16 pb-20">
          <div v-for="provider in providers" :id="'provider-section-' + provider" :key="provider" class="scroll-mt-10">
            <!-- Provider Section Header (Improved V3 Coverage) -->
            <div class="flex items-center gap-4 mb-8 sticky top-0 py-6 bg-surface-0/95 backdrop-blur-xl z-20 -mx-6 px-6 border-b border-white/5">
              <div class="w-12 h-12 rounded-2xl flex items-center justify-center text-xl font-black text-white shadow-xl shrink-0" :style="{ backgroundColor: getModelColor(provider) }">
                {{ provider.charAt(0).toUpperCase() }}
              </div>
              <div class="min-w-0">
                <h2 class="text-xl font-black text-text-primary uppercase tracking-tight truncate">{{ provider }}</h2>
                <div class="flex items-center gap-2 mt-1">
                  <span class="text-[10px] font-black text-text-tertiary uppercase tracking-widest opacity-60">{{ modelsByProvider[provider].length }} 模型基因就绪</span>
                </div>
              </div>
              <div class="h-px flex-1 bg-white/5 ml-4"></div>
            </div>

            <!-- Model Cards Grid -->
            <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              <div
                v-for="model in modelsByProvider[provider]"
                :key="model.id"
                @click="toggleModel(model.id)"
                class="group relative flex flex-col p-6 rounded-[32px] border transition-all duration-500 cursor-pointer active:scale-[0.98]"
                :class="appStore.selectedModelIds.includes(model.id) 
                  ? 'bg-accent/10 border-accent/40 shadow-[0_20px_50px_rgba(99,102,241,0.15)] ring-1 ring-accent/20' 
                  : 'bg-white/5 border-white/10 hover:border-white/20 hover:bg-white/8 shadow-xl'"
              >
                <!-- Select Checkmark -->
                <div class="absolute top-6 right-6 w-6 h-6 rounded-full flex items-center justify-center border transition-all"
                     :class="appStore.selectedModelIds.includes(model.id) ? 'bg-accent border-accent text-white scale-110 shadow-lg shadow-accent/20' : 'border-white/10 opacity-30'">
                  <Check v-if="appStore.selectedModelIds.includes(model.id)" :size="14" stroke-width="4" />
                </div>

                <!-- Card Header -->
                <div class="mb-6">
                  <div class="flex items-center gap-2 mb-2">
                    <h3 class="text-base font-black text-text-primary uppercase tracking-tight truncate pr-8">{{ model.name }}</h3>
                  </div>
                  <div class="flex flex-wrap gap-1.5">
                    <span class="px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-wider border transition-colors"
                          :class="tierClass(model.tier, appStore.selectedModelIds.includes(model.id))">{{ tierLabel(model.tier) }}</span>
                    <span v-if="model.free" class="px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-wider bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">Free</span>
                    <span v-if="model.supportsVision" class="px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-wider bg-purple-500/10 text-purple-500 border border-purple-500/20">Vision</span>
                  </div>
                </div>

                <!-- Industrial Dashboard Stats -->
                <div class="grid grid-cols-3 gap-2 p-4 rounded-2xl bg-black/[0.03] dark:bg-black/20 border border-black/5 dark:border-white/5 mb-6 transition-colors group-hover:bg-black/[0.06] dark:group-hover:bg-black/30">
                  <div class="text-center space-y-1">
                    <p class="text-[8px] font-black text-text-tertiary uppercase tracking-widest opacity-70">Context</p>
                    <div class="flex items-center justify-center gap-1">
                      <Gauge :size="10" class="text-accent opacity-40" />
                      <span class="text-[11px] font-mono font-bold text-text-primary">{{ formatContext(model.contextWindow) }}</span>
                    </div>
                  </div>
                  <div class="text-center space-y-1 border-x border-black/5 dark:border-white/5">
                    <p class="text-[8px] font-black text-text-tertiary uppercase tracking-widest opacity-70">In (1M)</p>
                    <span class="text-[11px] font-mono font-bold text-text-primary">{{ formatPrice(model.priceInput) }}</span>
                  </div>
                  <div class="text-center space-y-1">
                    <p class="text-[8px] font-black text-text-tertiary uppercase tracking-widest opacity-70">Out (1M)</p>
                    <span class="text-[11px] font-mono font-bold text-text-primary">{{ formatPrice(model.priceOutput) }}</span>
                  </div>
                </div>

                <!-- Technical ID Footer -->
                <div class="flex items-center justify-between mt-auto pt-2">
                  <div class="flex items-center gap-2 min-w-0">
                    <Globe :size="12" class="text-text-tertiary opacity-40" />
                    <span class="text-[9px] font-mono font-medium text-text-tertiary truncate uppercase tracking-tighter opacity-50">{{ model.id }}</span>
                  </div>
                  <div class="flex gap-1 shrink-0">
                    <component v-for="tag in model.tags.slice(0, 2)" :key="tag" :is="tagIcons[tag] ?? Cpu" :size="12" class="text-text-tertiary opacity-40" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Global Sync Info -->
        <div v-if="appStore.error && appStore.models.length" class="p-4 rounded-2xl bg-red-500/5 border border-red-500/20 flex items-center gap-3">
          <Activity :size="16" class="text-red-400" />
          <p class="text-[10px] font-black text-red-400 uppercase tracking-widest">Synchronization Error: {{ appStore.error }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
