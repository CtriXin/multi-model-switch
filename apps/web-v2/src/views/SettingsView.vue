<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'
import { useProviderStore } from '@/stores/provider'
import { useAppStore } from '@/stores/app'
import ProviderAccountItem from '@/components/settings/ProviderAccountItem.vue'
import { Sun, Moon, Sidebar, Info, Key, Plus, Upload, Trash2, X, Cpu } from 'lucide-vue-next'
import { ref, onMounted } from 'vue'

const { theme, toggle: toggleTheme } = useTheme()
const sidebarExpanded = ref(true)
const providerStore = useProviderStore()
const appStore = useAppStore()

// Provider editing state
const editingProviderId = ref<string | null>(null)
const baseUrlInput = ref('')
const saving = ref(false)

// Import state
const showImport = ref(false)
const importText = ref('')
const importFileInput = ref<HTMLInputElement | null>(null)

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

async function clearAllKeys() {
  await providerStore.clearAllCredentials()
  await appStore.refreshModels()
}
</script>

<template>
  <div class="flex-1 overflow-y-auto">
    <div class="max-w-2xl mx-auto px-6 py-8 space-y-6">
      <h1 class="text-lg font-semibold text-text-primary">设置</h1>

      <!-- Appearance -->
      <div class="card p-5 space-y-4">
        <h2 class="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Sun :size="16" class="text-text-tertiary" />
          外观
        </h2>

        <!-- Theme -->
        <div class="flex items-center justify-between">
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
        <div class="flex items-center justify-between">
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
      </div>

      <!-- API Providers -->
      <div class="card p-5 space-y-4">
        <h2 class="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Key :size="16" class="text-text-tertiary" />
          API 通道
        </h2>

        <!-- Provider list -->
        <div class="space-y-2">
          <div
            v-for="provider in providerStore.providers"
            :key="provider.id"
            class="rounded-lg border p-3 space-y-3 transition-opacity"
            :class="provider.enabled
              ? 'border-border-default'
              : 'border-border-default/50 opacity-60'"
          >
            <!-- Provider header row -->
            <div class="flex items-center justify-between">
              <div class="min-w-0 flex items-center gap-2">
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
              <div class="flex items-center gap-2">
                <button
                  v-if="provider.type !== 'mock' && !provider.builtIn && editingProviderId !== provider.id"
                  @click="startEdit(provider.id)"
                  class="text-xs text-accent hover:text-accent/80 px-2 py-1 rounded hover:bg-surface-3 transition-colors"
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
              class="rounded-xl border border-border-subtle bg-surface-2/40 p-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="text-xs font-medium text-text-secondary">账户池</p>
                  <p class="mt-1 text-[11px] text-text-tertiary">同一 provider 可挂多个 key，失败时会在可用账户间自动 fallback。</p>
                </div>
                <button
                  @click="addAccount(provider.id)"
                  class="inline-flex items-center gap-1 rounded-lg border border-border-default px-2.5 py-1.5 text-xs text-text-secondary transition-colors hover:bg-surface-3"
                >
                  <Plus :size="12" />
                  新增账户
                </button>
              </div>

              <div class="mt-3 space-y-2">
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
      <div class="card p-5 space-y-3">
        <h2 class="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Info :size="16" class="text-text-tertiary" />
          关于
        </h2>
        <div class="space-y-2 text-sm">
          <div class="flex items-center justify-between">
            <span class="text-text-secondary">应用名称</span>
            <span class="text-text-primary font-medium">MMS Pro</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-text-secondary">版本</span>
            <span class="text-text-tertiary font-mono text-xs">v0.2.0</span>
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
