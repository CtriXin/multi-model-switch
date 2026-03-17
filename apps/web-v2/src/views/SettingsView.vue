<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useTheme } from '@/composables/useTheme'
import { useProviderStore } from '@/stores/provider'
import { useAppStore } from '@/stores/app'
import { useToastStore } from '@/stores/toast'
import { FREE_PROVIDERS } from '@/data/freeProviders'
import ProviderAccountItem from '@/components/settings/ProviderAccountItem.vue'
import { Sun, Moon, Sidebar, Info, Key, Plus, Upload, Trash2, X, Cpu, Shield, Copy, Download, Check, Rocket, ChevronLeft, Menu, Sparkles, DollarSign } from 'lucide-vue-next'
import { ref, inject, onMounted, computed } from 'vue'

const platform = inject<import('vue').Ref<string>>('platform', ref('macos'))
const isMobile = computed(() => platform.value === 'ios')

function openDrawer() { window.dispatchEvent(new CustomEvent('open-drawer')) }

const router = useRouter()
const { theme, toggle: toggleTheme, v3Config } = useTheme()
const sidebarExpanded = ref(true)
const providerStore = useProviderStore()
const appStore = useAppStore()
const toast = useToastStore()
const providerListCollapsed = ref(false)

// Provider editing state
const editingProviderId = ref<string | null>(null)
const baseUrlInput = ref('')
const saving = ref(false)

// Import state
const showImport = ref(false)
const importText = ref('')
const importFileInput = ref<HTMLInputElement | null>(null)

// Secure share bundle state
const showShareExport = ref(false)
const showShareImport = ref(false)
const shareSelectedAccountIds = ref<string[]>([])
const sharePassword = ref('')
const shareExpiryDays = ref<'7' | '30' | '90' | 'never'>('30')
const shareBundleOutput = ref('')
const shareGenerating = ref(false)
const shareCopied = ref(false)
const shareImportText = ref('')
const shareImportPassword = ref('')
const shareImportFileInput = ref<HTMLInputElement | null>(null)
const shareImporting = ref(false)
const shareExpiryOptions = [
  { value: '7', label: '7 天' },
  { value: '30', label: '30 天' },
  { value: '90', label: '90 天' },
  { value: 'never', label: '不过期' },
] as const

// Add custom provider state
const showAddProvider = ref(false)
const newProvider = ref({
  id: '',
  name: '',
  type: 'openai-compatible' as const,
  baseUrl: '',
})

// Manual model addition
const addingModelProvider = ref<string | null>(null)
const newModelId = ref('')

onMounted(async () => {
  await providerStore.refreshKeyStatus()
  resetShareSelection()
})

function startEdit(providerId: string) {
  editingProviderId.value = providerId
  const p = providerStore.getProvider(providerId)
  baseUrlInput.value = p?.baseUrl ?? ''
}

function cancelEdit() {
  editingProviderId.value = null
  baseUrlInput.value = ''
}

async function saveProviderBaseUrl() {
  if (!editingProviderId.value) return
  saving.value = true
  try {
    const p = providerStore.getProvider(editingProviderId.value)
    if (p && baseUrlInput.value && baseUrlInput.value !== p.baseUrl) {
      providerStore.updateProvider(editingProviderId.value, { baseUrl: baseUrlInput.value })
    }
    cancelEdit()
    await appStore.refreshModels()
  } finally {
    saving.value = false
  }
}

async function toggleProviderEnabled(providerId: string) {
  const p = providerStore.getProvider(providerId)
  if (!p) return
  providerStore.updateProvider(providerId, { enabled: !p.enabled })
  await appStore.refreshModels()
}

function startAddModel(providerId: string) {
  addingModelProvider.value = providerId
  newModelId.value = ''
}

function addCustomModel() {
  if (!addingModelProvider.value || !newModelId.value.trim()) return
  const p = providerStore.getProvider(addingModelProvider.value)
  if (!p) return
  const existing = p.customModels ?? []
  if (!existing.includes(newModelId.value.trim())) {
    providerStore.updateProvider(addingModelProvider.value, {
      customModels: [...existing, newModelId.value.trim()],
    })
  }
  newModelId.value = ''
  addingModelProvider.value = null
  appStore.refreshModels()
}

function removeCustomModel(providerId: string, modelId: string) {
  const p = providerStore.getProvider(providerId)
  if (!p?.customModels) return
  providerStore.updateProvider(providerId, {
    customModels: p.customModels.filter(m => m !== modelId),
  })
  appStore.refreshModels()
}

async function handleImport() {
  const text = importText.value.trim()
  if (!text) return
  const ok = await providerStore.importConfig(text)
  if (ok) {
    importText.value = ''
    showImport.value = false
    await appStore.refreshModels()
  }
}

function handleFileUpload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (e) => {
    importText.value = e.target?.result as string
  }
  reader.readAsText(file)
}

function addCustomProvider() {
  if (!newProvider.value.id || !newProvider.value.baseUrl) return
  providerStore.addProvider({
    id: newProvider.value.id,
    name: newProvider.value.name || newProvider.value.id,
    type: newProvider.value.type,
    baseUrl: newProvider.value.baseUrl,
    enabled: true,
  })
  showAddProvider.value = false
  newProvider.value = { id: '', name: '', type: 'openai-compatible', baseUrl: '' }
}

function addAccount(providerId: string) {
  providerStore.addAccount(providerId)
}

async function removeProvider(providerId: string) {
  await providerStore.removeProvider(providerId)
  await appStore.refreshModels()
}

function getProviderAccounts(providerId: string) {
  return providerStore.getAccountsByProvider(providerId)
}

function getProviderSummary(providerId: string) {
  const provider = providerStore.getProvider(providerId)
  if (!provider || provider.type === 'mock') return '仅用于本地演示，不需要配置账户'

  const accounts = getProviderAccounts(providerId)
  const availableCount = providerStore.getRuntimeAccounts(providerId).length
  const defaultAccount = providerStore.getDefaultAccount(providerId)

  if (!accounts.length) {
    return '还没有账户，新增后可分别绑定不同 API Key'
  }

  return `${accounts.length} 个账户 · ${availableCount} 个可用 · 默认 ${defaultAccount?.name ?? '未设置'}`
}

function canAddManualModel(providerId: string) {
  const provider = providerStore.getProvider(providerId)
  if (!provider || provider.type === 'mock') return false
  return providerStore.keyStatus[providerId] || !!provider.customModels?.length
}

const recommendedConfiguredCount = computed(() =>
  FREE_PROVIDERS.filter((provider) => providerStore.keyStatus[provider.id]).length,
)

const visibleProviders = computed(() =>
  providerStore.providers.filter((provider) => (
    !providerListCollapsed.value
    || provider.enabled
    || !!providerStore.keyStatus[provider.id]
  )),
)

function canBulkEnable(providerId: string) {
  const provider = providerStore.getProvider(providerId)
  if (!provider) return false
  return provider.type === 'mock'
    || !provider.builtIn
    || provider.enabled
    || !!providerStore.keyStatus[providerId]
}

async function enableAllProviders() {
  for (const provider of providerStore.providers) {
    if (canBulkEnable(provider.id) && !provider.enabled) {
      providerStore.updateProvider(provider.id, { enabled: true })
    }
  }
  await appStore.refreshModels()
}

async function disableAllProviders() {
  for (const provider of providerStore.providers) {
    if (provider.enabled) {
      providerStore.updateProvider(provider.id, { enabled: false })
    }
  }
  await appStore.refreshModels()
}

const shareableAccounts = computed(() =>
  providerStore.accounts.filter((account) => {
    const provider = providerStore.getProvider(account.providerId)
    return !!provider
      && provider.type !== 'mock'
      && !!providerStore.accountKeyStatus[account.id]
  }),
)

function getShareAccountProviderName(providerId: string) {
  return providerStore.getProvider(providerId)?.name ?? providerId
}

function resetShareSelection() {
  shareSelectedAccountIds.value = shareableAccounts.value.map((account) => account.id)
}

function toggleShareAccount(accountId: string) {
  const index = shareSelectedAccountIds.value.indexOf(accountId)
  if (index >= 0) {
    shareSelectedAccountIds.value.splice(index, 1)
  } else {
    shareSelectedAccountIds.value.push(accountId)
  }
}

async function generateShareBundle() {
  if (!shareSelectedAccountIds.value.length) return
  shareGenerating.value = true
  try {
    const expiresAt = shareExpiryDays.value === 'never'
      ? null
      : new Date(Date.now() + Number(shareExpiryDays.value) * 24 * 60 * 60 * 1000).toISOString()
    shareBundleOutput.value = await providerStore.exportShareBundle(
      shareSelectedAccountIds.value,
      sharePassword.value,
      { expiresAt },
    )
  } catch (error: any) {
    toast.error(error.message || '生成分享包失败')
  } finally {
    shareGenerating.value = false
  }
}

async function copyShareBundle() {
  if (!shareBundleOutput.value) return
  await navigator.clipboard.writeText(shareBundleOutput.value)
  shareCopied.value = true
  setTimeout(() => { shareCopied.value = false }, 1500)
}

function downloadShareBundle() {
  if (!shareBundleOutput.value) return
  const blob = new Blob([shareBundleOutput.value], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `mms-share-bundle-${new Date().toISOString().slice(0, 10)}.json`
  link.click()
  URL.revokeObjectURL(url)
}

function handleShareImportFileUpload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (e) => {
    shareImportText.value = e.target?.result as string
  }
  reader.readAsText(file)
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
      await appStore.refreshModels()
      resetShareSelection()
    }
  } finally {
    shareImporting.value = false
  }
}

async function clearAllKeys() {
  await providerStore.clearAllCredentials()
  await appStore.refreshModels()
  shareBundleOutput.value = ''
  resetShareSelection()
}
</script>

<template>
  <div class="flex-1 overflow-y-auto">
    <!-- Mobile top bar -->
    <div v-if="isMobile" class="sticky top-0 z-10 flex items-center gap-3 px-4 py-3 bg-white/80 dark:bg-[#0b0b18]/80 backdrop-blur-md border-b border-border-subtle safe-top">
      <button @click="router.back()" class="p-1.5 -ml-1 rounded-lg active:bg-surface-3 transition-colors">
        <ChevronLeft :size="22" class="text-text-primary" />
      </button>
      <span class="text-base font-semibold text-text-primary">设置</span>
      <button @click="openDrawer" class="ml-auto p-1.5 rounded-lg active:bg-surface-3 transition-colors">
        <Menu :size="20" class="text-text-tertiary" />
      </button>
    </div>
    <div class="max-w-2xl mx-auto px-6 py-8 space-y-6">
      <h1 v-if="!isMobile" class="text-lg font-semibold text-text-primary">设置</h1>
      <div class="glass-v3 rounded-2xl p-5 flex items-center justify-between gap-4 border border-white/10">
        <div class="min-w-0">
          <div class="flex items-center gap-2.5">
            <span class="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-orange-400 to-rose-500 text-base shadow-lg">🚀</span>
            <p class="text-sm font-semibold text-text-primary">快速开始</p>
          </div>
          <p class="mt-2 text-xs text-text-tertiary">
            新手先从这里配免费 API。你当前已配置 {{ recommendedConfiguredCount }} 个推荐通道。
          </p>
        </div>
        <button
          @click="router.push('/setup')"
          class="shrink-0 rounded-full px-4 py-2 text-xs font-bold uppercase tracking-widest
                 bg-accent text-white shadow-lg shadow-accent/30 hover:scale-105 active:scale-95 transition-all"
        >
          打开
        </button>
      </div>

      <!-- Appearance -->
      <div class="glass-v3 rounded-2xl p-5 space-y-4 border border-white/10">
        <h2 class="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Sun :size="16" class="text-text-tertiary" />
          外观
        </h2>

        <!-- Theme -->
        <div class="flex items-center justify-between py-2">
          <div>
            <p class="text-sm text-text-primary">主题</p>
            <p class="text-xs text-text-tertiary">切换深色 / 浅色模式</p>
          </div>
          <button
            @click="toggleTheme"
            class="relative w-14 h-7 rounded-full transition-colors duration-200"
            :class="theme === 'dark' ? 'bg-accent' : 'bg-surface-4'"
          >
            <span
              class="absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform duration-200
                     flex items-center justify-center"
              :class="theme === 'dark' ? 'translate-x-7' : 'translate-x-0.5'"
            >
              <Moon v-if="theme === 'dark'" :size="12" class="text-accent" />
              <Sun v-else :size="12" class="text-amber-500" />
            </span>
          </button>
        </div>

        <!-- Sidebar default -->
        <div class="flex items-center justify-between py-2">
          <div>
            <p class="text-sm text-text-primary">侧边栏默认展开</p>
            <p class="text-xs text-text-tertiary">macOS 模式下是否默认展开侧边栏</p>
          </div>
          <button
            @click="sidebarExpanded = !sidebarExpanded"
            class="relative w-14 h-7 rounded-full transition-colors duration-200"
            :class="sidebarExpanded ? 'bg-accent' : 'bg-surface-4'"
          >
            <span
              class="absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform duration-200
                     flex items-center justify-center"
              :class="sidebarExpanded ? 'translate-x-7' : 'translate-x-0.5'"
            >
              <Sidebar :size="12" class="text-text-tertiary" />
            </span>
          </button>
        </div>

        <!-- Default free优先 -->
        <div class="flex items-center justify-between py-2">
          <div>
            <p class="text-sm text-text-primary">默认免费优先</p>
            <p class="text-xs text-text-tertiary">优先展示免费模型</p>
          </div>
          <button
            @click="appStore.preferFree = !appStore.preferFree"
            class="relative w-14 h-7 rounded-full transition-colors duration-200"
            :class="appStore.preferFree ? 'bg-accent' : 'bg-surface-4'"
          >
            <span
              class="absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform duration-200
                     flex items-center justify-center"
              :class="appStore.preferFree ? 'translate-x-7' : 'translate-x-0.5'"
            >
              <DollarSign :size="12" class="text-text-tertiary" />
            </span>
          </button>
        </div>

        <div class="h-px bg-border-subtle" />

        <div class="space-y-4 pt-4">
          <div>
            <p class="text-sm font-semibold text-text-primary flex items-center gap-2 mb-1">
              <Sparkles :size="14" class="text-accent" />
              SparkRing V3 物理引擎 (Cinematic Fluid)
            </p>
            <p class="text-xs text-text-tertiary">实时调节界面的物理玻璃质感与生命力。</p>
          </div>

          <div class="space-y-4 bg-white/5 dark:bg-white/5 p-4 rounded-xl border border-white/10">
            <!-- Blur -->
            <div class="space-y-2">
              <div class="flex justify-between text-xs">
                <span class="text-text-secondary">模糊强度 (Blur)</span>
                <span class="text-text-tertiary font-mono">{{ v3Config.blurAmount }}px</span>
              </div>
              <input type="range" v-model="v3Config.blurAmount" min="0" max="80" class="w-full accent-accent" />
            </div>

            <!-- Saturation -->
            <div class="space-y-2">
              <div class="flex justify-between text-xs">
                <span class="text-text-secondary">色彩饱和 (Saturate)</span>
                <span class="text-text-tertiary font-mono">{{ v3Config.saturation }}%</span>
              </div>
              <input type="range" v-model="v3Config.saturation" min="0" max="200" class="w-full accent-accent" />
            </div>

            <!-- Stroke -->
            <div class="space-y-2">
              <div class="flex justify-between text-xs">
                <span class="text-text-secondary">高光边框 (Stroke)</span>
                <span class="text-text-tertiary font-mono">{{ v3Config.borderOpacity }}%</span>
              </div>
              <input type="range" v-model="v3Config.borderOpacity" min="0" max="100" class="w-full accent-accent" />
            </div>

            <!-- Grain -->
            <div class="space-y-2">
              <div class="flex justify-between text-xs">
                <span class="text-text-secondary">胶片颗粒 (Grain Noise)</span>
                <span class="text-text-tertiary font-mono">{{ v3Config.noiseOpacity }}%</span>
              </div>
              <input type="range" v-model="v3Config.noiseOpacity" min="0" max="20" class="w-full accent-accent" />
            </div>
          </div>

          <!-- Aurora Toggle - Separate from slider container -->
          <div class="flex items-center justify-between pt-2">
            <span class="text-xs text-text-secondary">底层极光引擎 (Aurora)</span>
            <button
              @click="v3Config.showAurora = !v3Config.showAurora"
              class="relative w-10 h-5 rounded-full transition-colors duration-200"
              :class="v3Config.showAurora ? 'bg-accent' : 'bg-surface-4'"
            >
              <span
                class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200"
                :class="v3Config.showAurora ? 'translate-x-5' : 'translate-x-0.5'"
              />
            </button>
          </div>
        </div>
      </div>

      <!-- API Providers -->
      <div class="glass-v3 rounded-2xl p-5 space-y-4 border border-white/10">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Key :size="16" class="text-text-tertiary" />
            API 通道
          </h2>
          <div class="flex flex-wrap items-center gap-2">
            <button
              @click="providerListCollapsed = !providerListCollapsed"
              class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 transition-colors"
            >
              {{ providerListCollapsed ? '显示全部' : '收起未配置' }}
            </button>
            <button
              @click="enableAllProviders"
              class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 transition-colors"
            >
              一键全开
            </button>
            <button
              @click="disableAllProviders"
              class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-white/10 hover:bg-white/5 transition-colors"
            >
              一键全关
            </button>
          </div>
        </div>
        <p class="text-[11px] text-text-tertiary">
          收起后只显示已绑定 API Key 或当前已打开的通道。
        </p>

        <!-- Provider list -->
        <div class="space-y-2">
          <div
            v-for="provider in visibleProviders"
            :key="provider.id"
            class="rounded-lg border p-3 space-y-3 transition-opacity"
            :class="provider.enabled
              ? 'border-white/10 bg-white/5'
              : 'border-white/5 bg-white/2'"
          >
            <!-- Provider header row -->
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="min-w-0 flex items-center gap-2 flex-1">
                <button
                  @click="toggleProviderEnabled(provider.id)"
                  class="relative w-8 h-[18px] rounded-full transition-colors duration-200 shrink-0"
                  :class="provider.enabled ? 'bg-accent' : 'bg-surface-4'"
                  :title="provider.enabled ? '点击禁用' : '点击启用'"
                >
                  <span
                    class="absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white shadow-sm transition-transform duration-200"
                    :class="provider.enabled ? 'translate-x-[14px]' : 'translate-x-0'"
                  />
                </button>
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="truncate text-sm font-medium text-text-primary">{{ provider.name }}</span>
                    <span v-if="provider.builtIn" class="text-[10px] text-text-tertiary bg-surface-3 px-1.5 py-0.5 rounded">内置</span>
                    <span v-if="provider.type === 'mock'" class="text-[10px] text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded">Demo</span>
                  </div>
                  <p class="mt-1 text-xs text-text-tertiary">
                    {{ getProviderSummary(provider.id) }}
                  </p>
                </div>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <button
                  v-if="provider.type !== 'mock' && !provider.builtIn && editingProviderId !== provider.id"
                  @click="startEdit(provider.id)"
                  class="text-xs text-accent hover:text-accent/80 px-2 py-1 rounded hover:bg-surface-3 transition-colors whitespace-nowrap"
                >
                  编辑通道
                </button>
                <button
                  v-if="!provider.builtIn && editingProviderId !== provider.id"
                  @click="removeProvider(provider.id)"
                  class="text-xs text-red-400 hover:text-red-300 p-1 rounded hover:bg-surface-3 transition-colors"
                  title="删除通道"
                >
                  <X :size="12" />
                </button>
              </div>
            </div>

            <div
              v-if="provider.type !== 'mock'"
              class="rounded-xl border border-border-subtle bg-surface-2/40 p-3 pt-4"
            >
              <div class="flex items-center justify-between gap-3 px-1 mb-4">
                <div class="space-y-1">
                  <div class="flex items-center gap-2">
                    <p class="text-xs font-black text-text-primary uppercase tracking-widest">账户池</p>
                    <div class="h-1 w-1 rounded-full bg-text-tertiary/30"></div>
                    <span class="text-[10px] font-bold text-text-tertiary uppercase tracking-tight">Account Pool</span>
                  </div>
                  <p class="text-[10px] text-text-tertiary/60 leading-relaxed font-medium">支持多 Key 轮询与自动故障转移</p>
                </div>
                <button
                  @click="addAccount(provider.id)"
                  class="inline-flex items-center gap-1.5 rounded-xl bg-text-primary text-white dark:bg-white dark:text-black px-4 py-2 text-[11px] font-black uppercase tracking-widest shadow-lg shadow-black/10 transition-all hover:scale-105 active:scale-95 active:shadow-none"
                >
                  <Plus :size="12" :stroke-width="3" />
                  新增账户
                </button>
              </div>

              <div class="space-y-2">
                <ProviderAccountItem
                  v-for="account in getProviderAccounts(provider.id)"
                  :key="account.id"
                  :provider="provider"
                  :account="account"
                  :can-delete="getProviderAccounts(provider.id).length > 1"
                />
              </div>
            </div>

            <!-- Custom models display -->
            <div v-if="provider.customModels?.length" class="flex flex-wrap gap-1.5">
              <span class="text-[10px] text-text-tertiary self-center">手动模型：</span>
              <span
                v-for="m in provider.customModels"
                :key="m"
                class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 bg-surface-3 text-text-tertiary rounded group"
              >
                {{ m }}
                <button
                  @click="removeCustomModel(provider.id, m)"
                  class="opacity-0 group-hover:opacity-100 p-0.5 hover:text-red-400 transition-all"
                >
                  <X :size="8" />
                </button>
              </span>
            </div>

            <!-- Add manual model -->
            <div v-if="addingModelProvider === provider.id" class="flex gap-2 items-center">
              <input
                v-model="newModelId"
                placeholder="模型 ID，如 deepseek-chat"
                class="flex-1 text-xs bg-surface-1 border border-border-default rounded px-2 py-1.5
                       text-text-primary font-mono focus:outline-none focus:border-accent"
                @keydown.enter="addCustomModel"
              />
              <button @click="addCustomModel" :disabled="!newModelId.trim()"
                class="text-xs bg-accent text-white px-2 py-1.5 rounded disabled:opacity-50">添加</button>
              <button @click="addingModelProvider = null"
                class="text-xs text-text-tertiary px-2 py-1.5 rounded hover:bg-surface-3">取消</button>
            </div>
            <button
              v-else-if="canAddManualModel(provider.id)"
              @click="startAddModel(provider.id)"
              class="text-[10px] text-text-tertiary hover:text-accent flex items-center gap-1 transition-colors"
            >
              <Cpu :size="10" />
              手动添加模型
            </button>

            <div v-if="editingProviderId === provider.id" class="space-y-3 pt-2 border-t border-border-default">
              <div>
                <label class="text-xs text-text-tertiary block mb-1">Base URL</label>
                <input
                  v-model="baseUrlInput"
                  type="url"
                  placeholder="https://api.example.com/v1"
                  class="w-full text-sm bg-surface-2 border border-border-default rounded-lg px-3 py-2
                         text-text-primary placeholder:text-text-tertiary/50
                         focus:outline-none focus:border-accent transition-colors font-mono"
                />
              </div>
              <div class="flex gap-2">
                <button
                  @click="saveProviderBaseUrl"
                  :disabled="!baseUrlInput.trim() || saving"
                  class="text-xs bg-accent text-white px-3 py-1.5 rounded-lg
                         hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed
                         transition-colors flex items-center gap-1"
                >
                  保存
                </button>
                <button
                  @click="cancelEdit"
                  class="text-xs text-text-tertiary px-3 py-1.5 rounded-lg
                         hover:bg-surface-3 transition-colors flex items-center gap-1"
                >
                  取消
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Action buttons -->
        <div class="flex flex-wrap gap-2 pt-2">
          <button
            @click="showImport = !showImport"
            class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-border-default
                   hover:bg-surface-3 transition-colors flex items-center gap-1"
          >
            <Upload :size="12" />
            导入配置
          </button>
          <button
            @click="showAddProvider = !showAddProvider"
            class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-border-default
                   hover:bg-surface-3 transition-colors flex items-center gap-1"
          >
            <Plus :size="12" />
            添加自定义通道
          </button>
          <button
            @click="showShareExport = !showShareExport"
            class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-border-default
                   hover:bg-surface-3 transition-colors flex items-center gap-1"
          >
            <Shield :size="12" />
            导出私密分享包
          </button>
          <button
            @click="showShareImport = !showShareImport"
            class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-border-default
                   hover:bg-surface-3 transition-colors flex items-center gap-1"
          >
            <Upload :size="12" />
            导入私密分享包
          </button>
          <button
            v-if="Object.keys(providerStore.accountKeyStatus).length > 0"
            @click="clearAllKeys"
            class="text-xs text-red-400 px-3 py-1.5 rounded-lg border border-red-500/20
                   hover:bg-red-500/10 transition-colors flex items-center gap-1"
          >
            <Trash2 :size="12" />
            清除所有 Key
          </button>
        </div>

        <!-- Import panel -->
        <div v-if="showImport" class="space-y-3 p-3 rounded-lg bg-surface-2 border border-border-default">
          <p class="text-xs text-text-tertiary">粘贴 JSON 配置或选择 .json 文件</p>
          <textarea
            v-model="importText"
            rows="5"
            placeholder='{"version":1,"providers":[{"id":"openrouter","baseUrl":"https://openrouter.ai/api/v1","apiKey":"sk-or-..."}]}'
            class="w-full text-xs bg-surface-1 border border-border-default rounded-lg px-3 py-2
                   text-text-primary placeholder:text-text-tertiary/30 font-mono
                   focus:outline-none focus:border-accent transition-colors resize-none"
          />
          <div class="flex gap-2">
            <button
              @click="handleImport"
              :disabled="!importText.trim()"
              class="text-xs bg-accent text-white px-3 py-1.5 rounded-lg
                     hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              导入
            </button>
            <label class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-border-default
                          hover:bg-surface-3 transition-colors cursor-pointer">
              选择文件
              <input
                ref="importFileInput"
                type="file"
                accept=".json"
                class="hidden"
                @change="handleFileUpload"
              />
            </label>
            <button
              @click="showImport = false; importText = ''"
              class="text-xs text-text-tertiary px-3 py-1.5 rounded-lg hover:bg-surface-3 transition-colors"
            >
              取消
            </button>
          </div>
        </div>

        <div v-if="showShareExport" class="space-y-3 p-3 rounded-lg bg-surface-2 border border-border-default">
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="text-sm font-medium text-text-primary">私密分享包导出</p>
              <p class="mt-1 text-xs text-text-tertiary">
                导出内容包含真实 API Key。文件本身会用分享密码加密，密码请走单独渠道发送。
              </p>
            </div>
            <button
              @click="resetShareSelection"
              class="text-[11px] text-text-tertiary px-2 py-1 rounded hover:bg-surface-3 transition-colors"
            >
              全选
            </button>
          </div>

          <div
            v-if="shareableAccounts.length"
            class="max-h-48 overflow-y-auto rounded-lg border border-border-subtle bg-surface-1 p-2 space-y-1.5"
          >
            <label
              v-for="account in shareableAccounts"
              :key="account.id"
              class="flex items-start gap-3 rounded-lg px-2 py-2 cursor-pointer hover:bg-surface-2 transition-colors"
            >
              <input
                :checked="shareSelectedAccountIds.includes(account.id)"
                type="checkbox"
                class="mt-0.5"
                @change="toggleShareAccount(account.id)"
              />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="text-sm text-text-primary">{{ account.name }}</span>
                  <span class="text-[10px] text-text-tertiary bg-surface-3 px-1.5 py-0.5 rounded">
                    {{ getShareAccountProviderName(account.providerId) }}
                  </span>
                  <span
                    v-if="account.isDefault"
                    class="text-[10px] text-accent bg-accent/10 px-1.5 py-0.5 rounded"
                  >
                    默认
                  </span>
                </div>
                <div class="mt-1 text-[11px] text-text-tertiary">
                  只导出当前账户；接收方导入后会落到自己的本地 keychain
                </div>
              </div>
            </label>
          </div>
          <p v-else class="text-xs text-text-tertiary">
            暂无可分享账户。只有已保存真实 Key 的账户才会出现在这里。
          </p>

          <div>
            <label class="text-xs text-text-tertiary block mb-1">分享密码</label>
            <input
              v-model="sharePassword"
              type="password"
              placeholder="至少 8 位，建议单独通过 IM 发送"
              class="w-full text-sm bg-surface-1 border border-border-default rounded-lg px-3 py-2
                     text-text-primary placeholder:text-text-tertiary/40
                     focus:outline-none focus:border-accent transition-colors"
            />
          </div>

          <div>
            <label class="text-xs text-text-tertiary block mb-1">有效期</label>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="option in shareExpiryOptions"
                :key="option.value"
                @click="shareExpiryDays = option.value"
                class="text-xs px-3 py-1.5 rounded-lg border transition-colors"
                :class="shareExpiryDays === option.value
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-border-default text-text-secondary hover:bg-surface-3'"
              >
                {{ option.label }}
              </button>
            </div>
            <p class="mt-1 text-[11px] text-text-tertiary">
              过期后导入会被拒绝。它只能降低旧包长期滞留风险，不能替代权限回收。
            </p>
          </div>

          <div class="flex flex-wrap gap-2">
            <button
              @click="generateShareBundle"
              :disabled="sharePassword.trim().length < 8 || !shareSelectedAccountIds.length || shareGenerating"
              class="text-xs bg-accent text-white px-3 py-1.5 rounded-lg
                     hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              {{ shareGenerating ? '生成中...' : '生成加密分享包' }}
            </button>
            <button
              @click="showShareExport = false"
              class="text-xs text-text-tertiary px-3 py-1.5 rounded-lg hover:bg-surface-3 transition-colors"
            >
              收起
            </button>
          </div>

          <div v-if="shareBundleOutput" class="space-y-2">
            <textarea
              :value="shareBundleOutput"
              readonly
              rows="8"
              class="w-full text-xs bg-surface-1 border border-border-default rounded-lg px-3 py-2
                     text-text-primary font-mono focus:outline-none resize-none"
            />
            <div class="flex flex-wrap gap-2">
              <button
                @click="copyShareBundle"
                class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-border-default
                       hover:bg-surface-3 transition-colors inline-flex items-center gap-1"
              >
                <component :is="shareCopied ? Check : Copy" :size="12" />
                {{ shareCopied ? '已复制' : '复制' }}
              </button>
              <button
                @click="downloadShareBundle"
                class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-border-default
                       hover:bg-surface-3 transition-colors inline-flex items-center gap-1"
              >
                <Download :size="12" />
                下载 JSON
              </button>
            </div>
          </div>
        </div>

        <div v-if="showShareImport" class="space-y-3 p-3 rounded-lg bg-surface-2 border border-border-default">
          <div>
            <p class="text-sm font-medium text-text-primary">私密分享包导入</p>
            <p class="mt-1 text-xs text-text-tertiary">
              只导入可信来源的分享包。若分享包包含自定义 Base URL，请先确认来源可靠。
            </p>
          </div>

          <textarea
            v-model="shareImportText"
            rows="6"
            placeholder='{"type":"provider-share-bundle", ... }'
            class="w-full text-xs bg-surface-1 border border-border-default rounded-lg px-3 py-2
                   text-text-primary placeholder:text-text-tertiary/30 font-mono
                   focus:outline-none focus:border-accent transition-colors resize-none"
          />

          <div>
            <label class="text-xs text-text-tertiary block mb-1">分享密码</label>
            <input
              v-model="shareImportPassword"
              type="password"
              placeholder="输入分享方单独发给你的密码"
              class="w-full text-sm bg-surface-1 border border-border-default rounded-lg px-3 py-2
                     text-text-primary placeholder:text-text-tertiary/40
                     focus:outline-none focus:border-accent transition-colors"
            />
          </div>
          <p class="text-[11px] text-text-tertiary">
            如果分享包已过期，导入会被直接拒绝，需要分享方重新生成。
          </p>

          <div class="flex flex-wrap gap-2">
            <button
              @click="handleShareImport"
              :disabled="!shareImportText.trim() || shareImportPassword.trim().length < 8 || shareImporting"
              class="text-xs bg-accent text-white px-3 py-1.5 rounded-lg
                     hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              {{ shareImporting ? '导入中...' : '导入分享包' }}
            </button>
            <label class="text-xs text-text-secondary px-3 py-1.5 rounded-lg border border-border-default
                          hover:bg-surface-3 transition-colors cursor-pointer inline-flex items-center gap-1">
              <Upload :size="12" />
              选择文件
              <input
                ref="shareImportFileInput"
                type="file"
                accept=".json"
                class="hidden"
                @change="handleShareImportFileUpload"
              />
            </label>
            <button
              @click="showShareImport = false; shareImportText = ''; shareImportPassword = ''"
              class="text-xs text-text-tertiary px-3 py-1.5 rounded-lg hover:bg-surface-3 transition-colors"
            >
              取消
            </button>
          </div>
        </div>

        <!-- Add custom provider panel -->
        <div v-if="showAddProvider" class="space-y-3 p-3 rounded-lg bg-surface-2 border border-border-default">
          <p class="text-xs text-text-tertiary">添加 OpenAI 兼容的自定义通道</p>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="text-[10px] text-text-tertiary block mb-1">ID (唯一标识)</label>
              <input v-model="newProvider.id" placeholder="my-provider"
                class="w-full text-xs bg-surface-1 border border-border-default rounded px-2 py-1.5
                       text-text-primary font-mono focus:outline-none focus:border-accent" />
            </div>
            <div>
              <label class="text-[10px] text-text-tertiary block mb-1">显示名称</label>
              <input v-model="newProvider.name" placeholder="My Provider"
                class="w-full text-xs bg-surface-1 border border-border-default rounded px-2 py-1.5
                       text-text-primary focus:outline-none focus:border-accent" />
            </div>
          </div>
          <div>
            <label class="text-[10px] text-text-tertiary block mb-1">Base URL</label>
            <input v-model="newProvider.baseUrl" placeholder="https://api.example.com/v1"
              class="w-full text-xs bg-surface-1 border border-border-default rounded px-2 py-1.5
                     text-text-primary font-mono focus:outline-none focus:border-accent" />
          </div>
          <div class="flex gap-2">
            <button
              @click="addCustomProvider"
              :disabled="!newProvider.id || !newProvider.baseUrl"
              class="text-xs bg-accent text-white px-3 py-1.5 rounded-lg
                     hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              添加
            </button>
            <button
              @click="showAddProvider = false"
              class="text-xs text-text-tertiary px-3 py-1.5 rounded-lg hover:bg-surface-3 transition-colors"
            >
              取消
            </button>
          </div>
        </div>
      </div>

      <!-- About -->
      <div class="glass-v3 rounded-2xl p-5 space-y-3 border border-white/10">
        <h2 class="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Info :size="16" class="text-text-tertiary" />
          关于
        </h2>
        <div class="space-y-2 text-sm">
          <div class="flex items-center justify-between">
            <span class="text-text-secondary">应用名称</span>
            <span class="text-text-primary font-medium">SparkRing</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-text-secondary">版本</span>
            <span class="text-text-tertiary font-mono text-xs">v0.3.3</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-text-secondary">描述</span>
            <span class="text-text-tertiary text-xs">多模型协作工作台</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.safe-top { padding-top: env(safe-area-inset-top); }

.glass-v3 {
  backdrop-filter: blur(32px) saturate(150%);
  -webkit-backdrop-filter: blur(32px) saturate(150%);
  background: rgba(255, 255, 255, 0.03);
}

html.light .glass-v3 {
  background: rgba(255, 255, 255, 0.6);
}
</style>
