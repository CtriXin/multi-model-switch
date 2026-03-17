<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Rocket, ArrowRight, Sparkles, KeyRound } from 'lucide-vue-next'
import { useProviderStore } from '@/stores/provider'
import { FREE_PROVIDERS, CN_PROVIDERS, INTL_PROVIDERS } from '@/data/freeProviders'
import SetupProviderCard from '@/components/SetupProviderCard.vue'
import { getExperienceMode, setExperienceMode, type ExperienceMode } from '@/utils/experienceMode'

const router = useRouter()
const providerStore = useProviderStore()

const expanded = ref(FREE_PROVIDERS[0].id)
const selectedMode = ref<ExperienceMode | null>(getExperienceMode())
const PRESET_VISIBILITY_KEY = 'mms-setup-presets-hidden'
const hideProviderPresets = ref(loadPresetHidden())

const configuredCount = computed(() =>
  FREE_PROVIDERS.filter(p => providerStore.keyStatus[p.id]).length,
)

const hasAnyKey = computed(() => configuredCount.value > 0)

function toggleExpand(id: string) {
  expanded.value = expanded.value === id ? '' : id
}

function loadPresetHidden() {
  return localStorage.getItem(PRESET_VISIBILITY_KEY) === '1'
}

function persistPresetHidden(hidden: boolean) {
  localStorage.setItem(PRESET_VISIBILITY_KEY, hidden ? '1' : '0')
}

function togglePresetVisibility() {
  hideProviderPresets.value = !hideProviderPresets.value
  persistPresetHidden(hideProviderPresets.value)
}

function enterDemo() {
  selectedMode.value = 'demo'
  setExperienceMode('demo')
  router.push('/chat')
}

function chooseByok() {
  selectedMode.value = 'byok'
  setExperienceMode('byok')
}

function handleProviderConfigured() {
  selectedMode.value = 'byok'
  setExperienceMode('byok')
}

function skipToDemo() {
  enterDemo()
}

function startUsing() {
  if (hasAnyKey.value) {
    selectedMode.value = 'byok'
    setExperienceMode('byok')
  } else {
    selectedMode.value = 'demo'
    setExperienceMode('demo')
  }
  router.push('/chat')
}
</script>

<template>
  <div class="flex-1 overflow-y-auto overscroll-contain" style="-webkit-overflow-scrolling: touch">
    <div class="max-w-2xl mx-auto px-6 py-10">
      <div class="text-center mb-10 animate-fade-in">
        <div
          class="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-400 to-cyan-500
                 flex items-center justify-center mx-auto mb-4 shadow-lg"
        >
          <Rocket :size="24" class="text-white" />
        </div>
        <h1 class="text-xl font-bold text-text-primary mb-2">快速开始</h1>
        <p class="text-sm text-text-tertiary max-w-md mx-auto">
          先配一个能用的免费 API 就能开始。这里更像新手引导，复杂通道管理放到设置里。
        </p>
        <div class="flex items-center justify-center gap-2 mt-5">
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

      <div class="mb-8 rounded-2xl border border-border-default bg-surface-2 p-4">
        <div class="flex items-center justify-between gap-3 mb-3">
          <div class="text-xs font-semibold text-text-tertiary uppercase tracking-wider">体验模式</div>
          <button
            @click="togglePresetVisibility"
            class="text-[11px] px-2.5 py-1 rounded-lg border border-border-default text-text-tertiary hover:text-text-secondary hover:border-text-tertiary/40 transition-colors"
          >
            {{ hideProviderPresets ? '展开 API Key 预设' : '一键隐藏预设' }}
          </button>
        </div>
        <div class="grid gap-3 sm:grid-cols-2">
          <button
            @click="enterDemo"
            class="rounded-xl border px-4 py-3 text-left transition-colors"
            :class="selectedMode === 'demo'
              ? 'border-emerald-500/40 bg-emerald-500/10'
              : 'border-border-default hover:border-emerald-500/30 hover:bg-emerald-500/5'"
          >
            <div class="flex items-center gap-2 text-sm font-semibold text-text-primary">
              <Sparkles :size="16" class="text-emerald-400" />
              立即体验 Demo
            </div>
            <p class="text-xs text-text-tertiary mt-1">不需要 Key，直接体验完整流程与 mock 演示。</p>
          </button>
          <button
            @click="chooseByok"
            class="rounded-xl border px-4 py-3 text-left transition-colors"
            :class="selectedMode === 'byok'
              ? 'border-accent/40 bg-accent/10'
              : 'border-border-default hover:border-accent/30 hover:bg-accent/5'"
          >
            <div class="flex items-center gap-2 text-sm font-semibold text-text-primary">
              <KeyRound :size="16" class="text-accent" />
              连接我的模型（BYOK）
            </div>
            <p class="text-xs text-text-tertiary mt-1">填自己的 API Key，走真实模型；无后端也可长期使用。</p>
          </button>
        </div>
        <p v-if="hideProviderPresets" class="text-xs text-text-tertiary mt-3">
          已隐藏 API Key 预设列表，需要时可点击右上角再次展开。
        </p>
      </div>

      <!-- CN Providers -->
      <div v-if="!hideProviderPresets" class="mb-8">
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
            @configured="handleProviderConfigured"
          />
        </div>
      </div>

      <!-- International Providers -->
      <div v-if="!hideProviderPresets" class="mb-10">
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
            @configured="handleProviderConfigured"
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
