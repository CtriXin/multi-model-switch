import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { clearAll as clearAllKeys, deleteApiKey, getApiKey, listCredentialIds, saveApiKey } from '@/services/keychain'
import { normalizeSparkringBaseUrl } from '@/services/provision'
import { createShareBundle, readShareBundle } from '@/services/shareBundle'
import { useToastStore } from './toast'

export interface ProviderConfig {
  id: string
  name: string
  type: 'openrouter' | 'openai-compatible' | 'anthropic-compatible' | 'mock'
  baseUrl: string
  enabled: boolean
  builtIn: boolean
  models?: string[]
  customModels?: string[]
}

export interface ProviderAccount {
  id: string
  providerId: string
  name: string
  enabled: boolean
  isDefault: boolean
  createdAt: number
  lastUsedAt: number | null
  lastErrorAt: number | null
  lastErrorType: string | null
  suppressedUntil: number | null
}

interface ImportAccountInput extends Partial<ProviderAccount> {
  apiKey?: string
}

interface ImportProviderInput extends Partial<ProviderConfig> {
  id: string
  baseUrl: string
  accounts?: ImportAccountInput[]
  apiKey?: string
}

interface ImportPayload {
  version: number
  providers: ImportProviderInput[]
}

interface ShareImportPayload extends ImportPayload {
  exportedAt: string
  expiresAt?: string | null
}

const BUILTIN_PROVIDERS: ProviderConfig[] = [
  {
    id: 'siliconflow',
    name: '硅基流动',
    type: 'openai-compatible',
    baseUrl: 'https://api.siliconflow.cn/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'zhipu',
    name: '智谱 AI',
    type: 'openai-compatible',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    type: 'openai-compatible',
    baseUrl: 'https://api.deepseek.com',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'dashscope',
    name: '通义千问',
    type: 'openai-compatible',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'moonshot',
    name: '月之暗面 Kimi',
    type: 'openai-compatible',
    baseUrl: 'https://api.moonshot.cn/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'lingyiwanwu',
    name: '零一万物',
    type: 'openai-compatible',
    baseUrl: 'https://api.lingyiwanwu.com/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'baichuan',
    name: '百川智能',
    type: 'openai-compatible',
    baseUrl: 'https://api.baichuan-ai.com/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'stepfun',
    name: '阶跃星辰',
    type: 'openai-compatible',
    baseUrl: 'https://api.stepfun.com/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'minimax',
    name: 'MiniMax',
    type: 'openai-compatible',
    baseUrl: 'https://api.minimax.chat/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'cerebras',
    name: 'Cerebras',
    type: 'openai-compatible',
    baseUrl: 'https://api.cerebras.ai/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'google',
    name: 'Google AI Studio',
    type: 'openai-compatible',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'groq',
    name: 'Groq',
    type: 'openai-compatible',
    baseUrl: 'https://api.groq.com/openai/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'nvidia',
    name: 'NVIDIA NIM',
    type: 'openai-compatible',
    baseUrl: 'https://integrate.api.nvidia.com/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'mistral',
    name: 'Mistral AI',
    type: 'openai-compatible',
    baseUrl: 'https://api.mistral.ai/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'together',
    name: 'Together AI',
    type: 'openai-compatible',
    baseUrl: 'https://api.together.xyz/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'fireworks',
    name: 'Fireworks AI',
    type: 'openai-compatible',
    baseUrl: 'https://api.fireworks.ai/inference/v1',
    enabled: false,
    builtIn: true,
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    type: 'openrouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    enabled: false,
    builtIn: true,
  },
  { id: 'demo', name: 'Demo (模拟数据)', type: 'mock', baseUrl: '', enabled: true, builtIn: true },
]

// SparkRing provider config (hidden by default, shown after provision)
export const SPARKRING_PROVIDER: ProviderConfig = {
  id: 'sparkring',
  name: 'SparkRing 体验通道',
  type: 'openai-compatible',
  baseUrl: 'http://82.156.121.141:4001/v1',
  enabled: false,
  builtIn: true,
}

const STORAGE_KEY = 'mms-providers'
const ACCOUNTS_STORAGE_KEY = 'mms-provider-accounts'
const DEFAULT_ACCOUNT_NAME = '默认账户'

function migrateLegacyProviderBaseUrl(provider: ProviderConfig): ProviderConfig {
  if (provider.id !== 'sparkring') return provider

  const nextBaseUrl = normalizeSparkringBaseUrl(provider.baseUrl)
  if (nextBaseUrl === provider.baseUrl) return provider
  return { ...provider, baseUrl: nextBaseUrl }
}

function loadProviders(): ProviderConfig[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const friendsMode = localStorage.getItem('mms-show-friends') === 'true'

    // 好友模式开启时才添加 sparkring 通道
    const providersToLoad = friendsMode
      ? [...BUILTIN_PROVIDERS, SPARKRING_PROVIDER]
      : BUILTIN_PROVIDERS

    if (!raw) return providersToLoad.map((provider) => ({ ...provider }))
    const saved: ProviderConfig[] = JSON.parse(raw)
    let changed = false

    const result = providersToLoad.map((builtin) => {
      const override = saved.find((item) => item.id === builtin.id)
      const merged = override ? { ...builtin, ...override, builtIn: true } : { ...builtin }
      const migrated = migrateLegacyProviderBaseUrl(merged)
      changed ||= migrated.baseUrl !== merged.baseUrl
      return migrated
    })
    for (const savedProvider of saved) {
      if (!friendsMode && savedProvider.id === 'sparkring') {
        changed = true
        continue
      }
      if (!result.find((item) => item.id === savedProvider.id)) {
        const migrated = migrateLegacyProviderBaseUrl({ ...savedProvider, builtIn: false })
        changed ||= migrated.baseUrl !== savedProvider.baseUrl
        result.push(migrated)
      }
    }
    if (changed) persistProviders(result)
    return result
  } catch {
    return BUILTIN_PROVIDERS.map((provider) => ({ ...provider }))
  }
}

function persistProviders(providers: ProviderConfig[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(providers))
}

function normalizeAccount(raw: Partial<ProviderAccount>): ProviderAccount | null {
  if (!raw.id || !raw.providerId) return null
  return {
    id: raw.id,
    providerId: raw.providerId,
    name: raw.name || DEFAULT_ACCOUNT_NAME,
    enabled: raw.enabled !== false,
    isDefault: !!raw.isDefault,
    createdAt: raw.createdAt || Date.now(),
    lastUsedAt: raw.lastUsedAt ?? null,
    lastErrorAt: raw.lastErrorAt ?? null,
    lastErrorType: raw.lastErrorType ?? null,
    suppressedUntil: raw.suppressedUntil ?? null,
  }
}

function loadAccounts(): ProviderAccount[] {
  try {
    const raw = localStorage.getItem(ACCOUNTS_STORAGE_KEY)
    if (!raw) return []
    const saved = JSON.parse(raw) as Partial<ProviderAccount>[]
    return saved.map((item) => normalizeAccount(item)).filter((item): item is ProviderAccount => !!item)
  } catch {
    return []
  }
}

function persistAccounts(accounts: ProviderAccount[]) {
  localStorage.setItem(ACCOUNTS_STORAGE_KEY, JSON.stringify(accounts))
}

function generateAccountId(providerId: string) {
  return `acct-${providerId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function endOfDay() {
  return new Date().setHours(23, 59, 59, 999)
}

export const useProviderStore = defineStore('provider', () => {
  const providers = ref<ProviderConfig[]>(loadProviders())
  const accounts = ref<ProviderAccount[]>(loadAccounts())
  const keyStatus = ref<Record<string, boolean>>({})
  const accountKeyStatus = ref<Record<string, boolean>>({})

  const enabledProviders = computed(() => providers.value.filter((provider) => provider.enabled))

  const configuredProviders = computed(() =>
    enabledProviders.value.filter((provider) => provider.type === 'mock' || getRuntimeAccounts(provider.id).length > 0),
  )

  function saveProviders() {
    persistProviders(providers.value)
  }

  function saveAccountsOnly() {
    persistAccounts(accounts.value)
  }

  function isAccountSuppressed(account: ProviderAccount) {
    return !!account.suppressedUntil && account.suppressedUntil > Date.now()
  }

  function clearExpiredSuppressions() {
    let changed = false
    const now = Date.now()
    for (const account of accounts.value) {
      if (account.suppressedUntil && account.suppressedUntil <= now) {
        account.suppressedUntil = null
        if (account.lastErrorType === 'rate_limited') {
          account.lastErrorType = null
          account.lastErrorAt = null
        }
        changed = true
      }
    }
    if (changed) saveAccountsOnly()
  }

  function sortAccounts(items: ProviderAccount[]) {
    return [...items].sort((left, right) => {
      if (left.isDefault !== right.isDefault) return left.isDefault ? -1 : 1
      return left.createdAt - right.createdAt
    })
  }

  function recomputeProviderKeyStatus() {
    const next: Record<string, boolean> = {}
    for (const provider of providers.value) {
      next[provider.id] =
        provider.type === 'mock' ||
        accounts.value.some((account) => account.providerId === provider.id && accountKeyStatus.value[account.id])
    }
    keyStatus.value = next
  }

  /**
   * 禁用所有没有配置 API Key 的 built-in provider
   * 用于清除所有密钥后的清理操作
   */
  function disableBuiltInProvidersWithoutKey() {
    let changed = false

    for (const provider of providers.value) {
      if (!provider.builtIn || provider.type === 'mock') continue

      if (!keyStatus.value[provider.id] && provider.enabled) {
        provider.enabled = false
        changed = true
      }
    }

    if (changed) saveProviders()
  }

  function normalizeProviderDefaults(providerId: string) {
    const providerAccounts = sortAccounts(accounts.value.filter((account) => account.providerId === providerId))
    if (!providerAccounts.length) return

    const currentDefault = providerAccounts.find((account) => account.isDefault)
    const fallback = currentDefault || providerAccounts.find((account) => account.enabled) || providerAccounts[0]

    for (const account of providerAccounts) {
      account.isDefault = account.id === fallback.id
    }
  }

  function ensureDefaultAccount(providerId: string) {
    let account = accounts.value.find((item) => item.providerId === providerId && item.isDefault)
    if (account) return account

    account = accounts.value.find((item) => item.providerId === providerId)
    if (account) {
      account.isDefault = true
      saveAccountsOnly()
      return account
    }

    const created: ProviderAccount = {
      id: generateAccountId(providerId),
      providerId,
      name: DEFAULT_ACCOUNT_NAME,
      enabled: true,
      isDefault: true,
      createdAt: Date.now(),
      lastUsedAt: null,
      lastErrorAt: null,
      lastErrorType: null,
      suppressedUntil: null,
    }
    accounts.value.push(created)
    saveAccountsOnly()
    return created
  }

  function getProvider(id: string) {
    return providers.value.find((provider) => provider.id === id)
  }

  function getAccountsByProvider(providerId: string) {
    return sortAccounts(accounts.value.filter((account) => account.providerId === providerId))
  }

  function getDefaultAccount(providerId: string) {
    return getAccountsByProvider(providerId).find((account) => account.isDefault)
  }

  function getRuntimeAccounts(providerId: string, options: { includeSuppressed?: boolean } = {}) {
    clearExpiredSuppressions()
    return getAccountsByProvider(providerId).filter(
      (account) =>
        account.enabled &&
        accountKeyStatus.value[account.id] &&
        (options.includeSuppressed || !isAccountSuppressed(account)),
    )
  }

  function getFallbackAccounts(providerId: string) {
    return getRuntimeAccounts(providerId)
  }

  async function migrateLegacyProviderKeys() {
    let changed = false
    const credentialIds = new Set(await listCredentialIds())

    for (const provider of providers.value) {
      if (provider.type === 'mock' || !credentialIds.has(provider.id)) continue

      const hasAccountCredential = accounts.value.some(
        (account) => account.providerId === provider.id && credentialIds.has(account.id),
      )
      if (hasAccountCredential) continue

      const legacyKey = await getApiKey(provider.id)
      if (!legacyKey) continue

      const account = ensureDefaultAccount(provider.id)
      await saveApiKey(account.id, legacyKey)
      await deleteApiKey(provider.id)
      changed = true
    }

    if (changed) saveAccountsOnly()
  }

  async function refreshKeyStatus() {
    await migrateLegacyProviderKeys()
    const ids = await listCredentialIds()
    const next: Record<string, boolean> = {}
    for (const id of ids) next[id] = true
    accountKeyStatus.value = next
    recomputeProviderKeyStatus()
    // 不再自动禁用 provider，允许用户先启用再配置 Key
  }

  function addProvider(config: Omit<ProviderConfig, 'builtIn'>) {
    if (providers.value.find((provider) => provider.id === config.id)) return
    providers.value.push({ ...config, builtIn: false })
    saveProviders()
  }

  function syncFriendsModeProvider(enabled: boolean) {
    const index = providers.value.findIndex((provider) => provider.id === 'sparkring')

    if (enabled) {
      const next = index >= 0
        ? {
            ...providers.value[index],
            ...SPARKRING_PROVIDER,
            baseUrl: normalizeSparkringBaseUrl(providers.value[index].baseUrl || SPARKRING_PROVIDER.baseUrl),
            enabled: true,
            builtIn: true,
          }
        : { ...SPARKRING_PROVIDER, enabled: true }

      if (index >= 0) {
        providers.value[index] = next
      } else {
        providers.value.push(next)
      }

      saveProviders()
      recomputeProviderKeyStatus()
      return
    }

    if (index < 0) return
    providers.value.splice(index, 1)
    saveProviders()
    recomputeProviderKeyStatus()
  }

  async function removeProvider(id: string) {
    const provider = providers.value.find((item) => item.id === id)
    if (!provider || provider.builtIn) return

    const toRemove = accounts.value.filter((account) => account.providerId === id)
    for (const account of toRemove) {
      await deleteApiKey(account.id)
      delete accountKeyStatus.value[account.id]
    }

    accounts.value = accounts.value.filter((account) => account.providerId !== id)
    providers.value = providers.value.filter((item) => item.id !== id)
    saveProviders()
    saveAccountsOnly()
    recomputeProviderKeyStatus()
  }

  function updateProvider(id: string, patch: Partial<ProviderConfig>) {
    const index = providers.value.findIndex((provider) => provider.id === id)
    if (index < 0) return
    providers.value[index] = { ...providers.value[index], ...patch, id }
    saveProviders()
  }

  function addAccount(providerId: string, name?: string) {
    const provider = getProvider(providerId)
    if (!provider || provider.type === 'mock') return null

    const providerAccounts = getAccountsByProvider(providerId)
    const account: ProviderAccount = {
      id: generateAccountId(providerId),
      providerId,
      name: name?.trim() || `账户 ${providerAccounts.length + 1}`,
      enabled: true,
      isDefault: providerAccounts.length === 0,
      createdAt: Date.now(),
      lastUsedAt: null,
      lastErrorAt: null,
      lastErrorType: null,
      suppressedUntil: null,
    }
    accounts.value.push(account)
    normalizeProviderDefaults(providerId)
    saveAccountsOnly()
    return account
  }

  function updateAccount(accountId: string, patch: Partial<ProviderAccount>) {
    const index = accounts.value.findIndex((account) => account.id === accountId)
    if (index < 0) return

    const current = accounts.value[index]
    const next = normalizeAccount({ ...current, ...patch, id: accountId, providerId: current.providerId })
    if (!next) return
    accounts.value[index] = next
    normalizeProviderDefaults(current.providerId)
    saveAccountsOnly()
  }

  async function removeAccount(accountId: string) {
    const account = accounts.value.find((item) => item.id === accountId)
    if (!account) return

    await deleteApiKey(account.id)
    delete accountKeyStatus.value[account.id]
    accounts.value = accounts.value.filter((item) => item.id !== accountId)
    normalizeProviderDefaults(account.providerId)
    saveAccountsOnly()
    recomputeProviderKeyStatus()
  }

  function setDefaultAccount(accountId: string) {
    const target = accounts.value.find((account) => account.id === accountId)
    if (!target) return
    for (const account of accounts.value) {
      if (account.providerId === target.providerId) {
        account.isDefault = account.id === accountId
      }
    }
    saveAccountsOnly()
  }

  async function setAccountApiKey(accountId: string, key: string) {
    const account = accounts.value.find((item) => item.id === accountId)
    if (!account) return
    await saveApiKey(accountId, key)
    const provider = getProvider(account.providerId)
    account.enabled = true
    account.lastErrorAt = null
    account.lastErrorType = null
    account.suppressedUntil = null
    accountKeyStatus.value[accountId] = true
    recomputeProviderKeyStatus()
    if (provider?.builtIn && provider.type !== 'mock' && !provider.enabled) {
      provider.enabled = true
      saveProviders()
    }
    saveAccountsOnly()
  }

  async function removeAccountApiKey(accountId: string) {
    const account = accounts.value.find((item) => item.id === accountId)
    if (!account) return
    await deleteApiKey(accountId)
    delete accountKeyStatus.value[accountId]
    account.lastErrorAt = null
    account.lastErrorType = null
    account.suppressedUntil = null
    recomputeProviderKeyStatus()
    saveAccountsOnly()
  }

  async function setApiKey(providerId: string, key: string) {
    const account = ensureDefaultAccount(providerId)
    await setAccountApiKey(account.id, key)
  }

  async function removeApiKey(providerId: string) {
    const account = getDefaultAccount(providerId)
    if (!account) return
    await removeAccountApiKey(account.id)
  }

  function markAccountUsed(accountId: string) {
    const account = accounts.value.find((item) => item.id === accountId)
    if (!account) return
    account.lastUsedAt = Date.now()
    account.lastErrorAt = null
    account.lastErrorType = null
    account.suppressedUntil = null
    saveAccountsOnly()
  }

  function markAccountFailure(accountId: string, errorCode?: string) {
    const account = accounts.value.find((item) => item.id === accountId)
    if (!account) return

    account.lastErrorAt = Date.now()
    account.lastErrorType = errorCode ?? 'request_failed'

    if (errorCode === 'invalid_key') {
      account.enabled = false
      account.suppressedUntil = null
    } else if (errorCode === 'rate_limited') {
      account.suppressedUntil = endOfDay()
    }

    saveAccountsOnly()
  }

  async function clearAllCredentials() {
    await clearAllKeys()
    accountKeyStatus.value = {}
    recomputeProviderKeyStatus()
    disableBuiltInProvidersWithoutKey()
  }

  async function importConfig(json: string) {
    const toast = useToastStore()
    try {
      const data = JSON.parse(json) as ImportPayload
      if (data.version !== 1 || !Array.isArray(data.providers)) {
        toast.error('配置文件格式不对')
        return false
      }

      const importedCount = await importConfigData(data, { source: 'plain' })
      toast.success(`导入了 ${importedCount} 个配置`)
      return true
    } catch (error: any) {
      toast.error('导入出错了: ' + error.message)
      return false
    }
  }

  async function importConfigData(data: ImportPayload, options: { source: 'plain' | 'share' }) {
    let importedCount = 0

    for (const item of data.providers) {
      if (!item.id || !item.baseUrl) continue
      const normalizedBaseUrl = item.id === 'sparkring'
        ? normalizeSparkringBaseUrl(item.baseUrl)
        : item.baseUrl

      const existing = providers.value.find((provider) => provider.id === item.id)
      if (existing) {
        Object.assign(existing, {
          name: item.name ?? existing.name,
          type: item.type ?? existing.type,
          baseUrl: normalizedBaseUrl ?? existing.baseUrl,
          enabled: item.enabled ?? true,
          models: item.models ?? existing.models,
          customModels: item.customModels ?? existing.customModels,
        })
      } else {
        providers.value.push({
          id: item.id,
          name: item.name ?? item.id,
          type: item.type ?? 'openai-compatible',
          baseUrl: normalizedBaseUrl,
          enabled: item.enabled ?? true,
          builtIn: false,
          models: item.models,
          customModels: item.customModels,
        })
      }

      if (Array.isArray(item.accounts)) {
        for (const rawAccount of item.accounts) {
          const normalized = normalizeAccount({
            ...rawAccount,
            providerId: item.id,
            id: rawAccount.id || generateAccountId(item.id),
          })
          if (!normalized) continue

          const existingAccount = accounts.value.find((account) => account.id === normalized.id)
          const targetAccount = existingAccount ?? normalized
          if (existingAccount) Object.assign(existingAccount, normalized)
          else accounts.value.push(normalized)

          if (rawAccount.apiKey) {
            await setAccountApiKey(targetAccount.id, rawAccount.apiKey)
          }
        }
        normalizeProviderDefaults(item.id)
      }

      if (options.source === 'plain' && item.apiKey) {
        await setApiKey(item.id, item.apiKey)
      }

      importedCount += 1
    }

    saveProviders()
    saveAccountsOnly()
    recomputeProviderKeyStatus()
    return importedCount
  }

  async function exportShareBundle(
    accountIds: string[],
    password: string,
    options: { expiresAt?: string | null } = {},
  ) {
    const selected = accountIds
      .map((accountId) => accounts.value.find((account) => account.id === accountId))
      .filter((account): account is ProviderAccount => !!account)

    if (!selected.length) {
      throw new Error('至少选择一个已配置账户')
    }

    const providerMap = new Map<string, ImportProviderInput>()

    for (const account of selected) {
      const provider = getProvider(account.providerId)
      if (!provider || provider.type === 'mock') continue

      const apiKey = await getApiKey(account.id)
      if (!apiKey) {
        throw new Error(`${provider.name} / ${account.name} 没有可分享的 API Key`)
      }

      if (!providerMap.has(provider.id)) {
        providerMap.set(provider.id, {
          id: provider.id,
          name: provider.name,
          type: provider.type,
          baseUrl: provider.baseUrl,
          enabled: provider.enabled,
          models: provider.models,
          customModels: provider.customModels,
          accounts: [],
        })
      }

      providerMap.get(provider.id)!.accounts!.push({
        id: account.id,
        providerId: account.providerId,
        name: account.name,
        enabled: account.enabled,
        isDefault: account.isDefault,
        apiKey,
      })
    }

    if (!providerMap.size) {
      throw new Error('没有可导出的真实账户')
    }

    const payload: ShareImportPayload = {
      version: 1,
      exportedAt: new Date().toISOString(),
      expiresAt: options.expiresAt ?? null,
      providers: Array.from(providerMap.values()),
    }

    const bundle = await createShareBundle(payload, password)
    return JSON.stringify(bundle, null, 2)
  }

  async function importShareBundle(bundleJson: string, password: string) {
    const toast = useToastStore()
    try {
      const payload = await readShareBundle<ShareImportPayload>(bundleJson, password)
      if (payload.version !== 1 || !Array.isArray(payload.providers)) {
        toast.error('分享链接内容不对')
        return false
      }

      if (payload.expiresAt && new Date(payload.expiresAt).getTime() <= Date.now()) {
        toast.error('分享链接已过期，让分享的人重新生成一个')
        return false
      }

      const hasCustomProvider = payload.providers.some((item) => {
        const builtIn = BUILTIN_PROVIDERS.some((provider) => provider.id === item.id)
        return !builtIn
      })
      if (hasCustomProvider) {
        toast.info('分享链接里有自定义通道，确认来源可信再导入')
      }

      const importedCount = await importConfigData(payload, { source: 'share' })
      toast.success(`导入了 ${importedCount} 个分享配置`)
      return true
    } catch (error: any) {
      toast.error(error.message || '导入分享链接失败')
      return false
    }
  }

  function exportConfig() {
    return JSON.stringify(
      {
        version: 1,
        providers: providers.value.map((provider) => ({
          id: provider.id,
          name: provider.name,
          type: provider.type,
          baseUrl: provider.baseUrl,
          enabled: provider.enabled,
          models: provider.models,
          accounts: getAccountsByProvider(provider.id).map((account) => ({
            id: account.id,
            name: account.name,
            enabled: account.enabled,
            isDefault: account.isDefault,
          })),
        })),
      },
      null,
      2,
    )
  }

  return {
    providers,
    accounts,
    keyStatus,
    accountKeyStatus,
    enabledProviders,
    configuredProviders,
    addProvider,
    syncFriendsModeProvider,
    removeProvider,
    updateProvider,
    getProvider,
    getAccountsByProvider,
    getDefaultAccount,
    getRuntimeAccounts,
    getFallbackAccounts,
    refreshKeyStatus,
    setApiKey,
    removeApiKey,
    addAccount,
    updateAccount,
    removeAccount,
    setDefaultAccount,
    setAccountApiKey,
    removeAccountApiKey,
    markAccountUsed,
    markAccountFailure,
    clearAllCredentials,
    importConfig,
    importShareBundle,
    exportConfig,
    exportShareBundle,
  }
})
