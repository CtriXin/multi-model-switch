<script setup lang="ts">
import { ref, computed, onMounted, watch, inject } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useProviderStore, type ProviderConfig } from '@/stores/provider'
import { useToastStore } from '@/stores/toast'
import { useTheme } from '@/composables/useTheme'
import ProviderAccountItem from '@/components/settings/ProviderAccountItem.vue'
import {
  ChevronLeft, Menu, Sun, Moon, SunMoon, Sidebar, DollarSign, Sparkles, Key, Package, Plus, Globe, Trash2, Cpu, X, Check, Upload, Shield, Download, Info, Zap, ShieldOff, ToggleLeft, ToggleRight, Settings, Rocket, Home, Users, Copy
} from 'lucide-vue-next'
import { getCurrentTier } from '@/services/provision'

const router = useRouter()
const appStore = useAppStore()
const providerStore = useProviderStore()
const { theme, themeMode, toggle: toggleTheme, setThemeMode, v3Config } = useTheme()

const sidebarExpanded = ref(localStorage.getItem('mms-sidebar-expanded') !== 'false')
watch(sidebarExpanded, (val) => {
  localStorage.setItem('mms-sidebar-expanded', String(val))
})

const providerListCollapsed = ref(true)
const editingProviderId = ref<string | null>(null)
const baseUrlInput = ref('')
const saving = ref(false)

const showImport = ref(false)
const importText = ref('')

const showExport = ref(false)
const exportOutput = ref('')
const exportCopied = ref(false)

const showAddProvider = ref(false)
const newProvider = ref({ id: '', name: '', baseUrl: '' })

const showShareExport = ref(false)
const sharePassword = ref('')
const shareExpiryDays = ref(7)
const shareSelectedAccountIds = ref<string[]>([])
const shareGenerating = ref(false)
const shareBundleOutput = ref('')
const shareCopied = ref(false)

const showShareImport = ref(false)
const shareImportText = ref('')
const shareImportPassword = ref('')
const shareImporting = ref(false)

const addingModelProvider = ref<string | null>(null)
const newModelId = ref('')

// Easter egg: tap version 10 times → reveal Max mode
const versionTapCount = ref(0)
const showMaxMode = ref(false)
const maxActivating = ref(false)
const maxMessage = ref('')
let versionTapTimer: ReturnType<typeof setTimeout> | null = null

function onVersionTap() {
  versionTapCount.value += 1
  if (versionTapTimer) clearTimeout(versionTapTimer)
  versionTapTimer = setTimeout(() => { versionTapCount.value = 0 }, 2000)

  if (versionTapCount.value >= 10 && !showMaxMode.value) {
    showMaxMode.value = true
    maxMessage.value = '被你发现了！给你开个后门吧。'
    versionTapCount.value = 0
  }
}

async function doActivateMax() {
  maxActivating.value = true
  const ok = await appStore.activateMaxChannel()
  maxActivating.value = false
  if (ok) {
    maxMessage.value = '已解锁，尽情享用 🍜'
  }
}

const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isMobile = computed(() => platform.value === 'ios')

const providers = computed(() => providerStore.providers)
const visibleProviders = computed(() => {
  const filtered = providers.value
  if (!providerListCollapsed.value) return filtered
  return filtered.filter(p => p.enabled || providerStore.keyStatus[p.id])
})

const recommendedConfiguredCount = computed(() =>
  providerStore.providers.filter(p => p.builtIn && providerStore.keyStatus[p.id]).length
)

const shareableAccounts = computed(() =>
  providerStore.accounts.filter(a => providerStore.accountKeyStatus[a.id])
)

function openDrawer() {
  window.dispatchEvent(new CustomEvent('open-drawer'))
}

// 好友模式开启时，自动关闭优先免费模型和模拟数据，并显示 SparkRing 体验通道
watch(() => appStore.showFriendsMode, async (val) => {
  if (val) {
    // 关闭优先免费模型
    appStore.preferFree = false
    // 关闭模拟数据（demo provider）
    const demoProvider = providerStore.getProvider('demo')
    if (demoProvider?.enabled) {
      providerStore.updateProvider('demo', { enabled: false })
    }
    useToastStore().info('好友模式已开启，已自动关闭优先免费模型和模拟数据，解锁 SparkRing 体验通道')
  } else {
    useToastStore().info('好友模式已关闭，SparkRing 体验通道已隐藏')
  }
})

async function handleExport() {
  const json = providerStore.exportConfig()
  exportOutput.value = json
  try {
    await navigator.clipboard.writeText(json)
    exportCopied.value = true
    useToastStore().success('配置已复制到剪贴板')
    setTimeout(() => { exportCopied.value = false }, 3000)
  } catch {
    useToastStore().error('复制失败，请手动复制')
  }
}

async function toggleProviderEnabled(id: string) {
  const p = providerStore.getProvider(id)
  if (p) {
    const nextEnabled = !p.enabled
    // 如果启用但没有 API Key，提示用户配置
    if (nextEnabled && !providerStore.keyStatus[id] && p.type !== 'mock') {
      useToastStore().info(`${p.name} 尚未配置 API Key，请在下方账户池中添加`)
    }
    providerStore.updateProvider(id, { enabled: nextEnabled })
  }
}

function startEdit(id: string) {
  const p = providers.value.find(x => x.id === id)
  if (p) {
    editingProviderId.value = id
    baseUrlInput.value = p.baseUrl
  }
}

function cancelEdit() {
  editingProviderId.value = null
  baseUrlInput.value = ''
}

async function saveProviderBaseUrl() {
  if (!editingProviderId.value) return
  saving.value = true
  try {
    providerStore.updateProvider(editingProviderId.value, { baseUrl: baseUrlInput.value })
    editingProviderId.value = null
  } finally {
    saving.value = false
  }
}

async function removeProvider(id: string) {
  if (confirm('确认要删除此自定义通道吗？相关的账号信息也将被移除。')) {
    await providerStore.removeProvider(id)
  }
}

async function addCustomProvider() {
  if (!newProvider.value.id || !newProvider.value.baseUrl) return
  await providerStore.addProvider({
    id: newProvider.value.id,
    name: newProvider.value.name || newProvider.value.id,
    type: 'openai-compatible',
    baseUrl: newProvider.value.baseUrl,
    enabled: true
  })
  showAddProvider.value = false
  newProvider.value = { id: '', name: '', baseUrl: '' }
}

function addAccount(providerId: string) {
  providerStore.addAccount(providerId)
}

function getProviderAccounts(providerId: string) {
  return providerStore.accounts.filter(a => a.providerId === providerId)
}

function getProviderSummary(providerId: string) {
  const accs = getProviderAccounts(providerId)
  const configured = accs.filter(a => providerStore.accountKeyStatus[a.id]).length
  return `${accs.length} 个账户 (${configured} 已接入)`
}

function startAddModel(providerId: string) {
  addingModelProvider.value = providerId
  newModelId.value = ''
}

async function addCustomModel() {
  if (!addingModelProvider.value || !newModelId.value.trim()) return
  const p = providerStore.getProvider(addingModelProvider.value)
  await providerStore.updateProvider(addingModelProvider.value, {
    customModels: [...(p?.customModels || []), newModelId.value.trim()]
  })
  addingModelProvider.value = null
  newModelId.value = ''
}

async function removeCustomModel(providerId: string, modelId: string) {
  const p = providerStore.getProvider(providerId)
  if (p?.customModels) {
    providerStore.updateProvider(providerId, {
      customModels: p.customModels.filter(m => m !== modelId)
    })
  }
}

function canAddManualModel(providerId: string) {
  const p = providers.value.find(x => x.id === providerId)
  return p && !p.builtIn
}

async function enableAllProviders() {
  providers.value.forEach(p => { if (!p.enabled) providerStore.updateProvider(p.id, { enabled: true }) })
}

async function disableAllProviders() {
  providers.value.forEach(p => { if (p.enabled) providerStore.updateProvider(p.id, { enabled: false }) })
}

async function handleImport() {
  const text = importText.value.trim()
  if (!text) return
  const ok = await providerStore.importConfig(text)
  if (ok) {
    importText.value = ''
    showImport.value = false
    await providerStore.refreshKeyStatus()
    // 不自动刷新模型列表，用户切换到模型页面时再按需拉取
  }
}

function resetShareSelection() {
  shareSelectedAccountIds.value = shareableAccounts.value.map(a => a.id)
}

async function handleShareImport() {
  const text = shareImportText.value.trim()
  if (!text) return
  shareImporting.value = true
  try {
    const ok = await providerStore.importShareBundle(text, shareImportPassword.value)
    if (ok) {
      shareImportText.value = ''
      shareImportPassword.value = ''
      showShareImport.value = false
      await providerStore.refreshKeyStatus()
      resetShareSelection()
      // 不自动刷新模型列表，用户切换到模型页面时再按需拉取
    }
  } finally {
    shareImporting.value = false
  }
}

async function clearAllKeys() {
  await providerStore.clearAllCredentials()
  shareBundleOutput.value = ''
  resetShareSelection()
  // 不自动刷新模型列表，用户切换到模型页面时再按需拉取
}

function scrollToProvider(id: string) {
  const el = document.getElementById(`provider-${id}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

onMounted(() => {
  providerStore.refreshKeyStatus()
})
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-transparent">
    <!-- Group 1: Floating Capsule Header (Consistent with Chat/Discuss) -->
    <div class="z-40 px-4 pt-4 pb-2 shrink-0">
      <header
        class="glass-v3 max-w-6xl mx-auto rounded-full px-4 sm:px-6 py-2.5 transition-all duration-500 shadow-2xl relative flex items-center justify-between border border-white/10">
        <div class="flex items-center gap-2.5 min-w-0">
          <button @click="router.back()"
            class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors">
            <ChevronLeft :size="20" stroke-width="3" />
          </button>
          <div class="flex items-center gap-2.5">
            <div
              class="flex items-center justify-center w-8 h-8 rounded-full bg-text-primary text-surface-1 dark:bg-white dark:text-black shadow-lg shrink-0">
              <Settings :size="16" stroke-width="3" />
            </div>
            <div class="min-w-0">
              <h1 class="text-sm font-black text-text-primary truncate tracking-tight uppercase">
                偏好设置</h1>
              <p
                class="text-[9px] text-text-tertiary font-black uppercase tracking-widest opacity-50 hidden sm:block">
                设置与账户</p>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button @click="openDrawer"
            class="p-2 rounded-full hover:bg-white/10 text-text-secondary transition-colors sm:hidden">
            <Menu :size="18" stroke-width="3" />
          </button>
        </div>
      </header>
    </div>

    <div class="flex-1 overflow-y-auto custom-scrollbar">
      <div class="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6 sm:space-y-10">
        <!-- Quick Start Card -->
        <div
          class="glass-v3 rounded-[32px] p-6 flex flex-col sm:flex-row items-center justify-between gap-6 border border-white/10 shadow-2xl transition-all hover:bg-white/5 group/setup">
          <div class="flex items-center gap-4 w-full sm:w-auto">
            <div
              class="w-12 h-12 rounded-2xl bg-gradient-to-br from-orange-400 to-rose-500 flex items-center justify-center shadow-lg shadow-orange-500/20 group-hover/setup:scale-110 transition-transform text-xl shrink-0">
              🚀</div>
            <div class="min-w-0">
              <p class="text-sm font-black text-text-primary uppercase tracking-tight">快速配置导引
                (Setup)</p>
              <p
                class="text-[10px] text-text-tertiary font-bold uppercase tracking-widest opacity-50 truncate">
                已接入 {{ recommendedConfiguredCount }} 个推荐通道</p>
            </div>
          </div>
          <button @click="router.push('/setup')"
            class="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-accent text-white text-[10px] font-black uppercase tracking-widest shadow-xl shadow-accent/30 hover:scale-105 active:scale-95 transition-all whitespace-nowrap">开始配置</button>
        </div>

        <!-- Appearance & Global Defaults -->
        <div class="glass-v3 rounded-[32px] p-6 space-y-6 border border-white/10 shadow-2xl">
          <div class="flex items-center gap-3 px-1">
            <div class="p-2 bg-text-primary dark:bg-white rounded-xl shadow-lg">
              <Sun :size="18" class="text-surface-1 dark:text-black" stroke-width="3" />
            </div>
            <div>
              <h2 class="text-lg font-black text-text-primary tracking-tighter uppercase">外观与偏好</h2>
              <p
                class="text-[9px] text-text-tertiary font-black uppercase tracking-widest opacity-50">
                界面与行为</p>
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <!-- Theme Switcher -->
            <div
              class="flex items-center justify-between p-4 rounded-2xl bg-black/[0.02] dark:bg-white/5 border border-black/5 dark:border-white/5 transition-all hover:bg-black/[0.04] dark:hover:bg-white/10">
              <div>
                <p class="text-[10px] font-black text-text-primary uppercase tracking-widest">主题
                </p>
                <p class="text-[9px] text-text-tertiary font-medium">
                  {{ themeMode === 'light' ? '浅色' : themeMode === 'dark' ? '深色' : '自动' }}
                </p>
              </div>
              <!-- 3-position segmented switch: light | auto | dark -->
              <div class="flex items-center bg-black/10 dark:bg-white/10 rounded-full p-0.5 gap-0.5">
                <button @click="setThemeMode('light')"
                  class="flex items-center justify-center w-8 h-6 rounded-full transition-all duration-200"
                  :class="themeMode === 'light' ? 'bg-amber-400 text-white shadow-sm' : 'text-text-tertiary hover:text-text-secondary'">
                  <Sun :size="10" stroke-width="3" />
                </button>
                <button @click="setThemeMode('auto')"
                  class="flex items-center justify-center w-8 h-6 rounded-full transition-all duration-200"
                  :class="themeMode === 'auto' ? 'bg-white/90 dark:bg-white/25 text-text-primary shadow-sm' : 'text-text-tertiary hover:text-text-secondary'">
                  <SunMoon :size="10" stroke-width="3" />
                </button>
                <button @click="setThemeMode('dark')"
                  class="flex items-center justify-center w-8 h-6 rounded-full transition-all duration-200"
                  :class="themeMode === 'dark' ? 'bg-accent text-white shadow-sm' : 'text-text-tertiary hover:text-text-secondary'">
                  <Moon :size="10" stroke-width="3" />
                </button>
              </div>
            </div>

            <!-- Prefer Free Models Switch -->
            <div class="flex items-center justify-between p-4 rounded-2xl bg-black/[0.02] dark:bg-white/5 border border-black/5 dark:border-white/5 transition-all hover:bg-black/[0.04] dark:hover:bg-white/10">
              <div>
                <p class="text-[10px] font-black text-text-primary uppercase tracking-widest">优先免费模型</p>
                <p class="text-[9px] text-text-tertiary font-medium">过滤掉收费的模型</p>
              </div>
              <button @click="appStore.preferFree = !appStore.preferFree" class="relative w-12 h-6 rounded-full transition-colors duration-300" :class="appStore.preferFree ? 'bg-emerald-500' : 'bg-black/10 dark:bg-white/10'">
                <span class="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-xl transition-transform duration-300 flex items-center justify-center" :class="appStore.preferFree ? 'translate-x-6' : 'translate-x-0.5'">
                  <DollarSign :size="10" :class="appStore.preferFree ? 'text-emerald-500' : 'text-text-tertiary'" stroke-width="4" />
                </span>
              </button>
            </div>

            <!-- Show Home Entry Switch -->
            <div class="flex items-center justify-between p-4 rounded-2xl bg-black/[0.02] dark:bg-white/5 border border-black/5 dark:border-white/5 transition-all hover:bg-black/[0.04] dark:hover:bg-white/10">
              <div>
                <p class="text-[10px] font-black text-text-primary uppercase tracking-widest">显示首页</p>
                <p class="text-[9px] text-text-tertiary font-medium">侧边栏显示首页入口</p>
              </div>
              <button @click="appStore.showHomeEntry = !appStore.showHomeEntry" class="relative w-12 h-6 rounded-full transition-colors duration-300" :class="appStore.showHomeEntry ? 'bg-accent' : 'bg-black/10 dark:bg-white/10'">
                <span class="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-xl transition-transform duration-300 flex items-center justify-center" :class="appStore.showHomeEntry ? 'translate-x-6' : 'translate-x-0.5'">
                  <Home :size="10" :class="appStore.showHomeEntry ? 'text-accent' : 'text-text-tertiary'" stroke-width="4" />
                </span>
              </button>
            </div>

            <!-- Friends Mode Switch -->
            <div class="flex items-center justify-between p-4 rounded-2xl bg-black/[0.02] dark:bg-white/5 border border-black/5 dark:border-white/5 transition-all hover:bg-black/[0.04] dark:hover:bg-white/10">
              <div>
                <p class="text-[10px] font-black text-text-primary uppercase tracking-widest">好友模式</p>
                <p class="text-[9px] text-text-tertiary font-medium">解锁邀请奖励和专属功能</p>
              </div>
              <button @click="appStore.showFriendsMode = !appStore.showFriendsMode" class="relative w-12 h-6 rounded-full transition-colors duration-300" :class="appStore.showFriendsMode ? 'bg-purple-500' : 'bg-black/10 dark:bg-white/10'">
                <span class="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-xl transition-transform duration-300 flex items-center justify-center" :class="appStore.showFriendsMode ? 'translate-x-6' : 'translate-x-0.5'">
                  <Users :size="10" :class="appStore.showFriendsMode ? 'text-purple-500' : 'text-text-tertiary'" stroke-width="4" />
                </span>
              </button>
            </div>
            </div>

          <!-- Engine Controls -->
          <div class="space-y-4 pt-2 border-t border-white/5">
            <div class="px-1">
              <p class="text-[10px] font-black text-accent uppercase tracking-[0.2em] mb-1">
                SparkRing V3 Cinematic Fluid</p>
              <p class="text-[10px] text-text-tertiary">调整界面磨砂玻璃效果和视觉深度</p>
            </div>
            <div
              class="grid grid-cols-1 gap-3 bg-black/[0.02] dark:bg-black/20 p-5 rounded-[24px] border border-black/5 dark:border-white/5 shadow-inner">
              <div class="space-y-3">
                <div class="flex justify-between text-[9px] font-black uppercase tracking-widest">
                  <span class="text-text-secondary">模糊强度</span><span
                    class="text-accent font-mono">{{ v3Config.blurAmount }}px</span></div>
                <input type="range" v-model="v3Config.blurAmount" min="0" max="80"
                  class="w-full h-1 bg-black/10 dark:bg-white/10 rounded-full appearance-none cursor-pointer accent-accent" />
              </div>
              <div class="space-y-3">
                <div class="flex justify-between text-[9px] font-black uppercase tracking-widest">
                  <span class="text-text-secondary">色彩饱和度</span><span
                    class="text-accent font-mono">{{ v3Config.saturation }}%</span></div>
                <input type="range" v-model="v3Config.saturation" min="0" max="200"
                  class="w-full h-1 bg-black/10 dark:bg-white/10 rounded-full appearance-none cursor-pointer accent-accent" />
              </div>
              <div class="space-y-3">
                <div class="flex justify-between text-[9px] font-black uppercase tracking-widest">
                  <span class="text-text-secondary">边框亮度</span><span
                    class="text-accent font-mono">{{ v3Config.borderOpacity }}%</span></div>
                <input type="range" v-model="v3Config.borderOpacity" min="0" max="100"
                  class="w-full h-1 bg-black/10 dark:bg-white/10 rounded-full appearance-none cursor-pointer accent-accent" />
              </div>
            </div>
          </div>
        </div>

        <!-- API Providers (Cinematic V3 Refactor) -->
        <div
          class="glass-v3 rounded-[32px] p-6 space-y-6 border border-white/10 shadow-2xl min-h-[400px]">
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center gap-3">
              <div class="p-2 bg-accent rounded-xl shadow-lg shadow-accent/20">
                <Key :size="18" class="text-white" stroke-width="3" />
              </div>
              <div>
                <h2 class="text-lg font-black text-text-primary tracking-tighter uppercase">模型通道
                </h2>
                <p
                  class="text-[9px] text-text-tertiary font-black uppercase tracking-widest opacity-50">
                  API 配置管理</p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button @click="providerListCollapsed = !providerListCollapsed"
                class="text-[10px] font-black uppercase tracking-widest text-text-secondary px-4 py-2 rounded-xl bg-black/[0.02] dark:bg-white/5 border border-black/5 dark:border-white/5 hover:bg-black/[0.05] dark:hover:bg-white/10 transition-all shadow-sm active:scale-95">{{ providerListCollapsed ? '展开全部' : '收起视图' }}</button>
              <div class="h-4 w-px bg-white/10 mx-1"></div>
              <button @click="enableAllProviders"
                class="p-2 text-text-tertiary hover:text-emerald-400 transition-all active:scale-90"
                title="开启全部">
                <Zap :size="16" stroke-width="3" />
              </button>
              <button @click="disableAllProviders"
                class="p-2 text-text-tertiary hover:text-red-400 transition-all active:scale-90"
                title="关闭全部">
                <ShieldOff :size="16" stroke-width="3" />
              </button>
            </div>
          </div>

          <div class="flex gap-6 relative">
            <!-- Quick Jump Rail -->
            <aside
              class="hidden md:flex flex-col gap-2 sticky top-4 h-fit py-4 px-2 bg-white/40 dark:bg-black/20 backdrop-blur-xl rounded-full border border-black/5 dark:border-white/5 z-20">
              <button v-for="provider in visibleProviders" :key="provider.id"
                @click="scrollToProvider(provider.id)"
                class="w-10 h-10 rounded-full flex flex-col items-center justify-center transition-all duration-300 group relative active:scale-90"
                :class="providerStore.keyStatus[provider.id] ? 'bg-accent text-white shadow-lg' : 'bg-black/[0.05] dark:bg-white/5 text-text-tertiary hover:text-text-primary'">
                <span
                  class="text-[9px] font-black uppercase leading-none">{{ provider.name.slice(0, 2) }}</span>
                <div
                  class="absolute left-14 px-3 py-1.5 rounded-lg bg-text-primary text-surface-1 text-[10px] font-black uppercase tracking-widest opacity-0 group-hover:opacity-100 pointer-events-none transition-all -translate-x-2 group-hover:translate-x-0 whitespace-nowrap shadow-xl z-50">
                  {{ provider.name }}</div>
              </button>
              <div class="h-px bg-black/5 dark:bg-white/5 mx-2 my-1"></div>
              <button @click="showAddProvider = true"
                class="w-10 h-10 rounded-full flex items-center justify-center bg-black/[0.05] dark:bg-white/5 text-text-tertiary hover:bg-accent hover:text-white transition-all active:scale-90">
                <Plus :size="18" stroke-width="3" />
              </button>
            </aside>

            <!-- Provider List (DYNAMIC MARGINS FIX) -->
            <div class="flex-1 space-y-2 min-w-0">
              <div v-for="provider in visibleProviders" :id="'provider-' + provider.id"
                :key="provider.id"
                class="rounded-[24px] border transition-all duration-500 scroll-mt-6 overflow-hidden"
                :class="[
                  provider.enabled ? 'bg-black/[0.02] dark:bg-white/5 border-black/5 dark:border-white/10 shadow-lg p-5 mb-4' : 'bg-black/[0.01] dark:bg-white/2 border-black/[0.03] dark:border-white/5 opacity-60 p-3 mb-1',
                ]">
                <!-- Header -->
                <div class="flex items-start justify-between gap-4"
                  :class="provider.enabled ? 'mb-5' : ''">
                  <div class="flex items-center gap-3.5">
                    <div
                      class="rounded-xl bg-gradient-to-br from-surface-3 to-surface-4 dark:from-white/10 dark:to-white/5 flex items-center justify-center border border-black/5 dark:border-white/10 shadow-inner group transition-all"
                      :class="provider.enabled ? 'w-10 h-10' : 'w-8 h-8'">
                      <span
                        class="font-black text-text-primary group-hover:scale-110 transition-transform"
                        :class="provider.enabled ? 'text-sm' : 'text-xs'">{{ provider.name.slice(0, 1) }}</span>
                    </div>
                    <div class="min-w-0">
                      <div class="flex items-center gap-2">
                        <h3 class="font-black text-text-primary tracking-tight truncate"
                          :class="provider.enabled ? 'text-sm' : 'text-xs'">{{ provider.name }}</h3>
                        <button @click="toggleProviderEnabled(provider.id)"
                          class="relative w-7 h-4 rounded-full transition-colors duration-200 shrink-0"
                          :class="provider.enabled ? 'bg-accent' : 'bg-black/10 dark:bg-white/10'"><span
                            class="absolute top-[2px] left-[2px] w-3 h-3 rounded-full bg-white shadow-sm transition-transform duration-200"
                            :class="provider.enabled ? 'translate-x-3' : 'translate-x-0'" /></button>
                      </div>
                      <p v-if="provider.enabled"
                        class="text-[9px] text-text-tertiary font-medium opacity-60 truncate uppercase tracking-widest">
                        {{ getProviderSummary(provider.id) }}</p>
                    </div>
                  </div>
                  <div class="flex items-center gap-1.5 shrink-0">
                    <button
                      v-if="provider.type !== 'mock' && !provider.builtIn && editingProviderId !== provider.id"
                      @click="startEdit(provider.id)"
                      class="p-2 rounded-lg bg-black/[0.03] dark:bg-white/5 text-text-secondary hover:text-accent transition-all active:scale-90">
                      <Globe :size="14" stroke-width="3" />
                    </button>
                    <button v-if="!provider.builtIn && editingProviderId !== provider.id"
                      @click="removeProvider(provider.id)"
                      class="p-2 rounded-lg bg-black/[0.03] dark:bg-white/5 text-text-tertiary hover:text-red-400 transition-all active:scale-90">
                      <X :size="14" stroke-width="3" />
                    </button>
                  </div>
                </div>
                <!-- Content -->
                <div v-if="provider.enabled"
                  class="space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
                  <div v-if="provider.type !== 'mock'"
                    class="bg-black/[0.03] dark:bg-black/20 rounded-2xl p-4 border border-black/5 dark:border-white/5 space-y-3">
                    <div class="flex items-center justify-between px-1"><span
                        class="text-[9px] font-black uppercase tracking-widest text-text-tertiary opacity-60">账户池
                        Pool</span><button @click="addAccount(provider.id)"
                        class="px-3 py-1 rounded-lg bg-text-primary dark:bg-white text-surface-1 dark:text-black text-[9px] font-black uppercase tracking-widest hover:bg-accent hover:text-white transition-all active:scale-95 shadow-lg shadow-black/20">新增
                        Key</button></div>
                    <div class="space-y-1.5">
                      <ProviderAccountItem v-for="account in getProviderAccounts(provider.id)"
                        :key="account.id" :provider="provider" :account="account"
                        :can-delete="getProviderAccounts(provider.id).length > 1" />
                    </div>
                  </div>
                  <div class="px-1 space-y-3">
                    <div class="flex items-center gap-2">
                      <div class="w-1 h-2 bg-purple-500 rounded-full"></div><span
                        class="text-[9px] font-black uppercase tracking-widest text-text-tertiary opacity-60">可用模型基因
                        Registry</span>
                    </div>
                    <div class="flex flex-wrap gap-1.5">
                      <div v-for="m in provider.customModels" :key="m"
                        class="group flex items-center gap-1.5 px-2.5 py-1 bg-black/[0.03] dark:bg-white/5 border border-black/5 dark:border-white/5 rounded-lg transition-all hover:bg-accent/5">
                        <Cpu :size="10" stroke-width="3" class="text-text-tertiary" /><span
                          class="text-[10px] font-bold text-text-secondary font-mono">{{ m }}</span>
                        <button @click="removeCustomModel(provider.id, m)"
                          class="opacity-0 group-hover:opacity-100 p-0.5 hover:text-red-400 transition-all">
                          <X :size="10" stroke-width="4" />
                        </button>
                      </div>
                      <div v-if="addingModelProvider === provider.id"
                        class="flex gap-1.5 items-center bg-black/5 dark:bg-white/5 p-0.5 rounded-lg border border-accent/30 animate-scale-in">
                        <input v-model="newModelId" placeholder="ID..."
                          class="w-20 text-[10px] bg-transparent border-none px-1.5 py-0.5 text-text-primary font-mono focus:outline-none"
                          @keydown.enter="addCustomModel" />
                        <button @click="addCustomModel" :disabled="!newModelId.trim()"
                          class="p-1 bg-accent text-white rounded active:scale-90 transition-all">
                          <Check :size="10" stroke-width="4" />
                        </button>
                      </div>
                      <button v-else-if="canAddManualModel(provider.id)"
                        @click="startAddModel(provider.id)"
                        class="px-2.5 py-1 rounded-lg border border-dashed border-black/10 dark:border-white/10 text-text-tertiary hover:border-accent hover:text-accent transition-all text-[9px] font-black uppercase tracking-widest">+
                        注册模型</button>
                    </div>
                  </div>
                </div>
                <!-- Endpoint Edit -->
                <div v-if="editingProviderId === provider.id"
                  class="mt-4 p-4 rounded-xl bg-accent/5 border border-accent/20 space-y-3 animate-slide-up">
                  <p class="text-[9px] font-black uppercase tracking-widest text-accent">Base API
                    URL</p>
                  <div class="flex gap-2">
                    <input v-model="baseUrlInput" type="url"
                      class="flex-1 text-xs bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-text-primary font-mono focus:outline-none focus:border-accent" />
                    <button @click="saveProviderBaseUrl" :disabled="!baseUrlInput.trim() || saving"
                      class="bg-accent text-white px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest active:scale-95 transition-all">保存</button>
                    <button @click="cancelEdit"
                      class="text-text-tertiary px-3 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-white/5 transition-all">取消</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Action Grid -->
        <section class="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <button v-for="action in [
            { icon: Upload, label: '导入配置', click: () => showImport = true, color: 'accent' },
            { icon: Copy, label: '导出配置', click: () => { showExport = true; handleExport() }, color: 'blue-500' },
            { icon: Plus, label: '添加通道', click: () => showAddProvider = true, color: 'purple-500' },
            { icon: Shield, label: '私密导出', click: () => showShareExport = true, color: 'amber-500' }
          ]" :key="action.label" @click="action.click"
            class="flex flex-col items-center justify-center gap-3 p-5 rounded-[32px] glass-v3 border border-black/5 dark:border-white/10 hover:border-accent/50 group transition-all duration-500 active:scale-95 shadow-xl">
            <div
              :class="[`p-3 rounded-2xl group-hover:bg-${action.color} group-hover:text-white transition-all shadow-inner`, action.color === 'accent' ? 'bg-accent/10 text-accent' : `bg-${action.color}/10 text-${action.color}`]">
              <component :is="action.icon" :size="18" stroke-width="3" />
            </div>
            <span
              class="text-[10px] font-black uppercase tracking-widest text-text-secondary group-hover:text-text-primary">{{ action.label }}</span>
          </button>
        </section>

        <!-- Danger Zone -->
        <section v-if="Object.keys(providerStore.accountKeyStatus).length > 0"
          class="pt-4 flex justify-center">
          <button @click="clearAllKeys"
            class="group flex items-center gap-3 px-8 py-4 rounded-pill border border-red-500/20 bg-red-500/5 text-red-500/60 hover:bg-red-500 hover:text-white transition-all duration-500 active:scale-95 shadow-xl">
            <Trash2 :size="16" stroke-width="3" /><span
              class="text-xs font-black uppercase tracking-[0.3em]">清除所有敏感数据</span>
          </button>
        </section>

        <!-- Modals -->
        <div v-if="showImport || showAddProvider || showShareExport || showShareImport || showExport"
          class="fixed inset-0 z-[9999] flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-black/60 backdrop-blur-md"
            @click="showImport = showAddProvider = showShareExport = showShareImport = showExport = false" />
          <div
            class="relative w-full max-w-lg glass-v3 rounded-[32px] border border-white/10 p-8 shadow-2xl animate-scale-in">
            <div v-if="showImport" class="space-y-6">
              <h3 class="text-xl font-black text-text-primary uppercase tracking-tight">导入配置 (Import
                JSON)</h3>
              <textarea v-model="importText" rows="8"
                placeholder='{"version":1, "providers": [...]}'
                class="w-full text-xs bg-black/20 border border-white/10 rounded-2xl p-4 text-text-primary font-mono focus:outline-none focus:border-accent resize-none" />
              <div class="flex gap-3">
                <button @click="handleImport" :disabled="!importText.trim()"
                  class="flex-1 bg-accent text-white py-4 rounded-2xl font-black uppercase tracking-widest text-xs active:scale-95 transition-all">确认导入</button>
                <button @click="showImport = false"
                  class="px-8 py-4 rounded-2xl bg-white/5 text-text-tertiary font-black uppercase tracking-widest text-xs">取消</button>
              </div>
            </div>

            <div v-if="showExport" class="space-y-6">
              <h3 class="text-xl font-black text-text-primary uppercase tracking-tight">导出配置 (Export JSON)</h3>
              <p class="text-xs text-text-tertiary">导出所有通道配置（不含 API Key），可用于备份或分享到其他设备。</p>
              <textarea v-model="exportOutput" rows="10" readonly
                class="w-full text-xs bg-black/20 border border-white/10 rounded-2xl p-4 text-text-primary font-mono focus:outline-none resize-none" />
              <div class="flex gap-3">
                <button @click="handleExport"
                  class="flex-1 bg-accent text-white py-4 rounded-2xl font-black uppercase tracking-widest text-xs active:scale-95 transition-all">
                  {{ exportCopied ? '已复制' : '复制配置' }}
                </button>
                <button @click="showExport = false"
                  class="px-8 py-4 rounded-2xl bg-white/5 text-text-tertiary font-black uppercase tracking-widest text-xs">完成</button>
              </div>
            </div>

            <div v-if="showAddProvider" class="space-y-6">
              <h3 class="text-xl font-black text-text-primary uppercase tracking-tight">添加自定义通道</h3>
              <div class="grid grid-cols-1 gap-4">
                <input v-model="newProvider.id" placeholder="唯一标识 (e.g., my-api)"
                  class="w-full text-sm bg-black/20 border border-white/10 rounded-2xl px-5 py-4 text-text-primary font-mono" />
                <input v-model="newProvider.name" placeholder="显示名称 (e.g., 我的转发站)"
                  class="w-full text-sm bg-black/20 border border-white/10 rounded-2xl px-5 py-4 text-text-primary" />
                <input v-model="newProvider.baseUrl"
                  placeholder="Base URL (e.g., https://api.proxy.com/v1)"
                  class="w-full text-sm bg-black/20 border border-white/10 rounded-2xl px-5 py-4 text-text-primary font-mono" />
              </div>
              <div class="flex gap-3">
                <button @click="addCustomProvider"
                  :disabled="!newProvider.id || !newProvider.baseUrl"
                  class="flex-1 bg-accent text-white py-4 rounded-2xl font-black uppercase tracking-widest text-xs active:scale-95 transition-all">创建通道</button>
                <button @click="showAddProvider = false"
                  class="px-8 py-4 rounded-2xl bg-white/5 text-text-tertiary font-black uppercase tracking-widest text-xs">取消</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Friend Program (Conditional) -->
        
          <div v-if="appStore.showFriendsMode" class="glass-v3 rounded-[32px] p-6 space-y-6 border border-purple-500/20 shadow-2xl animate-fade-in">
            <div class="flex items-center gap-3 px-1">
              <div class="p-2 bg-purple-500 rounded-xl shadow-lg">
                <Users :size="18" class="text-white" stroke-width="3" />
              </div>
              <div>
                <h2 class="text-lg font-black text-text-primary tracking-tighter uppercase">好友计划</h2>
                <p class="text-[9px] text-text-tertiary font-black uppercase tracking-widest opacity-50">Rewards & Referral</p>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="p-6 rounded-[24px] bg-purple-500/5 border border-purple-500/10 space-y-4">
                <div class="flex items-center justify-between">
                  <span class="text-[10px] font-black text-purple-500 uppercase tracking-widest">你的邀请码</span>
                  <Rocket :size="16" class="text-purple-500/50" />
                </div>
                <div class="flex items-center justify-between gap-4">
                  <span class="text-2xl font-black text-text-primary tracking-widest font-mono">SPARK-888</span>
                  <button class="px-4 py-2 rounded-xl bg-purple-500 text-white text-[10px] font-black uppercase tracking-widest active:scale-95 transition-all">复制链接</button>
                </div>
              </div>
              <div class="p-6 rounded-[24px] bg-black/[0.02] dark:bg-white/5 border border-white/5 flex flex-col justify-center">
                <p class="text-xs text-text-secondary leading-relaxed font-medium">
                  每邀请一位新朋友加入 SparkRing，你们双方都将获得 <span class="text-purple-500 font-black">100万 Tokens</span> 的额外额度奖励。
                </p>
              </div>
            </div>

            <div class="p-5 rounded-2xl bg-purple-500/5 border border-purple-500/20">
              <div class="flex items-start gap-3">
                <div class="p-2 bg-purple-500 rounded-lg">
                  <Key :size="14" class="text-white" stroke-width="3" />
                </div>
                <div>
                  <p class="text-xs font-bold text-text-primary uppercase tracking-widest">已解锁权益</p>
                  <p class="text-[10px] text-text-secondary mt-1">
                    <span class="text-purple-400 font-semibold">SparkRing 体验通道</span> 已在 API 通道管理中显示。无需配置 API Key，开箱即用，适合新用户快速体验。
                  </p>
                </div>
              </div>
            </div>          </div>
        

        <!-- About (Easter Egg: tap version 10x → Max mode) -->
        <div class="glass-v3 rounded-[32px] p-6 space-y-4 border border-white/10 shadow-2xl">
          <h2
            class="text-sm font-black text-text-primary uppercase tracking-widest flex items-center gap-2">
            <Info :size="16" class="text-text-tertiary" stroke-width="3" />
            关于 SparkRing
          </h2>
          <div class="space-y-3 text-xs">
            <button @click="onVersionTap"
              class="w-full flex items-center justify-between select-none active:scale-[0.99] transition-transform">
              <span class="text-text-tertiary font-black uppercase tracking-widest">版本 Version</span>
              <span class="text-text-primary font-black">v0.5.1</span>
            </button>
            <div class="flex items-center justify-between"><span
                class="text-text-tertiary font-black uppercase tracking-widest">内核 Core</span><span
                class="text-text-primary font-medium italic">Multi-Model Cinematic Switcher</span>
            </div>
          </div>

          <!-- Max Mode Easter Egg -->
          
            <div v-if="showMaxMode" class="pt-4 border-t border-white/5 space-y-4 animate-scale-in">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-lg text-white">
                  <Rocket :size="20" stroke-width="3" />
                </div>
                <div class="min-w-0">
                  <p class="text-sm font-black text-text-primary uppercase tracking-tight">Max 模式</p>
                  <p class="text-[10px] text-text-tertiary font-medium">{{ maxMessage }}</p>
                </div>
              </div>
              <button v-if="getCurrentTier() !== 'max'" @click="doActivateMax" :disabled="maxActivating"
                class="w-full py-4 rounded-2xl font-black uppercase tracking-widest text-xs transition-all active:scale-95 shadow-xl"
                :class="maxActivating
                  ? 'bg-amber-500/50 text-white/60 cursor-wait'
                  : 'bg-gradient-to-r from-amber-400 to-orange-500 text-white hover:shadow-amber-500/30'">
                {{ maxActivating ? '正在激活...' : '谢谢，我要大份的' }}
              </button>
              <div v-else class="flex items-center gap-2 px-4 py-3 rounded-2xl bg-amber-500/10 border border-amber-500/20">
                <Check :size="14" class="text-amber-500" stroke-width="4" />
                <span class="text-[10px] font-black uppercase tracking-widest text-amber-500">Max 模式已激活</span>
              </div>
            </div>
          
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.05);
  border-radius: 10px;
}
.dark .custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
}
.animate-scale-in {
  animation: scaleIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes scaleIn {
  from {
    opacity: 0;
    transform: scale(0.9) translateY(20px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}
@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.animate-slide-up {
  animation: slideUp 0.3s ease-out;
}
</style>
