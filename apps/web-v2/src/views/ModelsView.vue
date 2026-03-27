<script setup lang="ts">
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore, getModelColor, type ModelMeta, type ModelPoolTag } from '@/stores/app'
import { 
  Cpu, Zap, Brain, Eye, Code, Loader2, AlertCircle, EyeOff, DollarSign, Image, 
  RotateCcw, ToggleLeft, ToggleRight, Check, Database, Gauge, Activity, Globe,
  ChevronLeft, Menu
} from 'lucide-vue-next'

const appStore = useAppStore()
const router = useRouter()

const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isMobile = computed(() => platform.value === 'ios')

function openDrawer() { window.dispatchEvent(new CustomEvent('open-drawer')) }

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
  for (const provider of Object.keys(map)) {
    map[provider] = provider === 'sparkring'
      ? [...map[provider]].sort((left, right) => {
          const leftSpeed = appStore.getModelSpeed(left.id)
          const rightSpeed = appStore.getModelSpeed(right.id)
          const leftOk = leftSpeed?.status === 'ok'
          const rightOk = rightSpeed?.status === 'ok'
          if (leftOk !== rightOk) return leftOk ? -1 : 1
          if (leftSpeed?.latencyMs != null && rightSpeed?.latencyMs != null && leftSpeed.latencyMs !== rightSpeed.latencyMs) {
            return leftSpeed.latencyMs - rightSpeed.latencyMs
          }
          if (leftSpeed?.latencyMs != null) return -1
          if (rightSpeed?.latencyMs != null) return 1
          return left.name.localeCompare(right.name)
        })
      : map[provider]
  }
  return map
})

const providers = computed(() => Object.keys(modelsByProvider.value))

function tierLabel(tier: number): string {
  return tier === 2 ? '旗舰' : tier === 1 ? '标准' : '基础'
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

function goToSettings() { router.push('/settings') }

function toggleTierFilter(tag: ModelPoolTag) {
  const next = new Set(tierFilters.value)
  if (next.has(tag)) next.delete(tag)
  else next.add(tag)
  tierFilters.value = Array.from(next)
}

function hasTierFilter(tag: ModelPoolTag) { return tierFilters.value.includes(tag) }
function clearFilters() {
  tierFilters.value = []
  filterFree.value = false
  filterVision.value = false
}

async function restoreAllModels() {
  await appStore.restoreSuppressedModels()
}

function scrollToProvider(provider: string) {
  const el = document.getElementById(`provider-section-${provider}`)
  if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
}

function toggleModel(id: string) { appStore.toggleModel(id) }

function getModelSpeedMeta(model: ModelMeta) {
  return appStore.getModelSpeed(model.id)
}

function formatLatency(latencyMs: number | null | undefined) {
  return latencyMs == null ? '未测速' : `${latencyMs} ms`
}

function isSpeedDegraded(model: ModelMeta) {
  const speed = getModelSpeedMeta(model)
  return !!speed && speed.status !== 'ok'
}

function speedStatusLabel(model: ModelMeta) {
  const speed = getModelSpeedMeta(model)
  if (!speed) return ''
  return speed.status === 'ok' ? '测速正常' : speed.status.toUpperCase()
}

function speedDotClass(model: ModelMeta) {
  const speed = getModelSpeedMeta(model)
  if (!speed) return 'bg-black/10 dark:bg-white/10'
  if (speed.status === 'ok') return 'bg-cyan-400'
  return 'bg-zinc-400'
}

function formatSpeedTestedAt(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
}

onMounted(() => {
  appStore.refreshModelsIfStale()
})
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">
    <!-- Group 1: Floating Capsule Header (V3 Standard Alignment) -->
    <div class="z-40 px-4 pt-4 pb-2 shrink-0">
      <header class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-2.5 min-w-0">
          <button @click="router.back()" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors">
            <ChevronLeft :size="20" stroke-width="3" />
          </button>
          <div class="flex items-center gap-2.5">
            <div class="flex items-center justify-center w-8 h-8 rounded-full bg-accent text-white shadow-lg shrink-0">
              <Cpu :size="16" stroke-width="3" />
            </div>
            <div class="min-w-0">
              <h1 class="text-sm font-black text-text-primary truncate tracking-tight uppercase">模型库</h1>
              <p class="text-[9px] text-text-tertiary font-black uppercase tracking-widest opacity-50 hidden sm:block">模型管理与接入</p>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button @click="openDrawer" class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors sm:hidden">
            <Menu :size="18" stroke-width="3" />
          </button>
        </div>
      </header>
    </div>

    <div class="flex-1 flex overflow-hidden">
      <!-- Quick Jump Rail (The V3 Navigation Fix) -->
      <aside v-if="providers.length > 3" class="hidden lg:flex flex-col items-center py-8 gap-4 w-20 bg-black/5 dark:bg-white/2 border-r border-white/5 overflow-y-auto no-scrollbar shrink-0">
        <div class="p-2 bg-accent rounded-xl mb-4 shadow-lg shadow-accent/20">
          <Database :size="20" class="text-white" stroke-width="3" />
        </div>
        <button v-for="provider in providers" :key="provider" @click="scrollToProvider(provider)"
          class="w-12 h-12 rounded-2xl flex flex-col items-center justify-center transition-all duration-300 group relative active:scale-90 bg-white/5 hover:bg-white/10">
          <span class="text-[10px] font-black uppercase leading-none text-text-tertiary group-hover:text-text-primary">{{ provider.slice(0, 2) }}</span>
          <div class="absolute left-16 px-3 py-1.5 rounded-lg bg-text-primary text-surface-1 text-[10px] font-black uppercase tracking-widest opacity-0 group-hover:opacity-100 pointer-events-none transition-all -translate-x-2 group-hover:translate-x-0 whitespace-nowrap shadow-xl z-50">{{ provider }}</div>
        </button>
      </aside>

      <!-- Main Content -->
      <div class="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar scroll-smooth">
        <div class="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-10">
          <!-- Filter Controls (Refined V3 Panel) -->
          <div v-if="appStore.models.length" class="flex flex-wrap items-center justify-between gap-6 px-2">
            <div class="flex items-center gap-4">
              <p class="text-[10px] font-black text-text-tertiary uppercase tracking-widest opacity-50">{{ filteredModels.length }} / {{ appStore.models.length }} 个模型匹配</p>
              <button @click="clearFilters" class="text-[9px] font-black text-accent uppercase tracking-widest hover:underline underline-offset-4">重置筛选</button>
              <button v-if="suppressedCount > 0" @click="restoreAllModels" class="text-[9px] font-black text-amber-500 uppercase tracking-widest hover:underline underline-offset-4">恢复 {{ suppressedCount }} 个隐藏模型</button>
            </div>

            <div class="flex flex-wrap items-center gap-2 bg-black/[0.03] dark:bg-white/5 p-2 rounded-[20px] border border-black/5 dark:border-white/5">
              <button @click="filterFree = !filterFree" class="flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border"
                      :class="filterFree ? 'bg-emerald-500 text-white border-emerald-500 shadow-lg shadow-emerald-500/20' : 'bg-white dark:bg-black/20 text-text-tertiary border-black/5 dark:border-white/5 hover:bg-black/5 dark:hover:bg-white/5'">
                <DollarSign :size="12" stroke-width="4" /> 免费 
                <component :is="filterFree ? ToggleRight : ToggleLeft" :size="14" stroke-width="3" />
              </button>
              <div class="w-px h-4 bg-black/5 dark:bg-white/10 mx-1"></div>
              <button v-for="tag in (['basic', 'std', 'pro'] as const)" :key="tag" @click="toggleTierFilter(tag)"
                      class="px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border"
                      :class="hasTierFilter(tag) ? 'bg-accent text-white border-accent shadow-lg shadow-accent/20' : 'bg-white dark:bg-black/20 text-text-tertiary border-black/5 dark:border-white/5 hover:bg-black/5 dark:hover:bg-white/5'">
                {{ tag === 'pro' ? '旗舰' : tag === 'std' ? '标准' : '基础' }}
              </button>
              <div class="w-px h-4 bg-black/5 dark:bg-white/10 mx-1"></div>
              <button @click="filterVision = !filterVision" class="flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border"
                      :class="filterVision ? 'bg-purple-500 text-white border-purple-500 shadow-lg shadow-purple-500/20' : 'bg-white dark:bg-black/20 text-text-tertiary border-black/5 dark:border-white/5 hover:bg-black/5 dark:hover:bg-white/5'">
                <Image :size="12" stroke-width="3" /> 视觉
              </button>
            </div>
          </div>

          <!-- Grouped Model Grid -->
          <div v-if="appStore.models.length" class="space-y-16 pb-20">
            <div v-for="provider in providers" :id="'provider-section-' + provider" :key="provider" class="scroll-mt-10">
              <!-- Provider Section Header -->
              <div class="flex items-center gap-4 mb-8 sticky top-0 py-6 bg-surface-0/95 backdrop-blur-xl z-20 -mx-6 px-6 border-b border-black/5 dark:border-white/5">
                <div class="w-12 h-12 rounded-2xl flex items-center justify-center text-xl font-black text-white shadow-xl shrink-0" :style="{ backgroundColor: getModelColor(provider) }">
                  {{ provider.charAt(0).toUpperCase() }}
                </div>
                <div class="min-w-0">
                  <h2 class="text-xl font-black text-text-primary uppercase tracking-tight truncate">{{ provider }}</h2>
                  <div class="flex items-center gap-2 mt-1">
                    <span class="text-[10px] font-black text-text-tertiary uppercase tracking-widest opacity-60">{{ modelsByProvider[provider].length }} 个模型可用</span>
                    <span v-if="provider === 'sparkring' && appStore.sparkringSpeedTestedAt" class="text-[10px] font-black text-text-tertiary uppercase tracking-widest opacity-50">
                      测速于 {{ formatSpeedTestedAt(appStore.sparkringSpeedTestedAt) }}
                    </span>
                  </div>
                </div>
                <div class="h-px flex-1 bg-black/5 dark:bg-white/5 ml-4"></div>
              </div>

              <!-- Model Cards Grid -->
              <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                <div v-for="model in modelsByProvider[provider]" :key="model.id" @click="toggleModel(model.id)"
                  class="group relative flex flex-col p-6 rounded-[32px] border transition-all duration-500 cursor-pointer active:scale-[0.98]"
                  :class="appStore.selectedModelIds.includes(model.id) 
                    ? 'bg-accent/10 border-accent/40 shadow-[0_20px_50px_rgba(99,102,241,0.15)] ring-1 ring-accent/20' 
                    : isSpeedDegraded(model)
                      ? 'bg-black/[0.03] dark:bg-white/[0.03] border-black/5 dark:border-white/10 opacity-55'
                      : 'bg-white/5 border-black/5 dark:border-white/10 hover:border-black/10 dark:hover:border-white/20 hover:bg-white/8 shadow-xl'">
                  
                  <div class="absolute top-6 right-6 w-6 h-6 rounded-full flex items-center justify-center border transition-all"
                       :class="appStore.selectedModelIds.includes(model.id) ? 'bg-accent border-accent text-white scale-110 shadow-lg shadow-accent/20' : 'border-black/10 dark:border-white/10 opacity-30'">
                    <Check v-if="appStore.selectedModelIds.includes(model.id)" :size="14" stroke-width="4" />
                  </div>

                  <div class="mb-6">
                    <h3 class="text-base font-black text-text-primary uppercase tracking-tight truncate pr-8 mb-2">{{ model.name }}</h3>
                    <div class="flex flex-wrap gap-1.5">
                      <span class="px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-wider border transition-colors"
                            :class="tierClass(model.tier, appStore.selectedModelIds.includes(model.id))">{{ tierLabel(model.tier) }}</span>
                      <span v-if="model.free" class="px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-wider bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">免费</span>
                      <span v-if="model.supportsVision" class="px-2.5 py-1 rounded-lg text-[9px] font-black uppercase tracking-wider bg-purple-500/10 text-purple-400 border border-purple-500/20">视觉</span>
                      <span v-if="model.provider === 'sparkring' && getModelSpeedMeta(model)" class="inline-flex items-center gap-1.5 pl-1">
                        <span class="h-1.5 w-1.5 rounded-full" :class="speedDotClass(model)" />
                        <span class="text-[9px] font-black uppercase tracking-wider"
                              :class="isSpeedDegraded(model) ? 'text-text-tertiary' : 'text-cyan-500'">
                          {{ formatLatency(getModelSpeedMeta(model)?.latencyMs) }}
                        </span>
                        <span v-if="isSpeedDegraded(model)" class="text-[8px] font-black uppercase tracking-widest text-text-quaternary">
                          {{ speedStatusLabel(model) }}
                        </span>
                      </span>
                    </div>
                  </div>

                  <div class="grid grid-cols-3 gap-2 p-4 rounded-2xl bg-black/[0.03] dark:bg-black/20 border border-black/5 dark:border-white/5 mb-6 transition-colors group-hover:bg-black/[0.06] dark:group-hover:bg-black/30">
                    <div class="text-center space-y-1"><p class="text-[8px] font-black text-text-tertiary uppercase tracking-widest opacity-70">上下文</p><div class="flex items-center justify-center gap-1"><Gauge :size="10" class="text-accent opacity-40" /><span class="text-[11px] font-mono font-bold text-text-primary">{{ formatContext(model.contextWindow) }}</span></div></div>
                    <div class="text-center space-y-1 border-x border-black/5 dark:border-white/5"><p class="text-[8px] font-black text-text-tertiary uppercase tracking-widest opacity-70">In (1M)</p><span class="text-[11px] font-mono font-bold text-text-primary">{{ formatPrice(model.priceInput) }}</span></div>
                    <div class="text-center space-y-1"><p class="text-[8px] font-black text-text-tertiary uppercase tracking-widest opacity-70">Out (1M)</p><span class="text-[11px] font-mono font-bold text-text-primary">{{ formatPrice(model.priceOutput) }}</span></div>
                  </div>

                  <div class="flex items-center justify-between mt-auto pt-2">
                    <div class="flex items-center gap-2 min-w-0"><Globe :size="12" class="text-text-tertiary opacity-40" /><span class="text-[9px] font-mono font-medium text-text-tertiary truncate uppercase tracking-tighter opacity-50">{{ model.id }}</span></div>
                    <div class="flex gap-1 shrink-0"><component v-for="tag in model.tags.slice(0, 2)" :key="tag" :is="tagIcons[tag] ?? Cpu" :size="12" class="text-text-tertiary opacity-40" /></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.05); border-radius: 10px; }
.dark .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); }
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
