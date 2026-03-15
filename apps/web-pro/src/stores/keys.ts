import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface ProviderInfo {
  id: string
  name: string
  color: string
  freeInfo: string
  freeBadge: string // short label like "永久免费" or "2000万 tokens"
  steps: string[]
  registerUrl: string
  keyUrl: string
  keyPlaceholder: string
  keyPrefix?: string
  models: string[]
  region: 'cn' | 'intl' // for grouping
}

// Ordered by: easiest free → most free → more setup
export const PROVIDERS: ProviderInfo[] = [
  // ── 国产推荐（国内直连，无需代理）──
  {
    id: 'siliconflow',
    name: '硅基流动 SiliconFlow',
    color: '#6366F1',
    freeInfo: '注册送 2000 万 tokens，含 16 个永久免费模型（Qwen、DeepSeek、GLM 等）',
    freeBadge: '2000万 tokens',
    steps: [
      '访问硅基流动官网，手机号注册',
      '进入控制台 →「API 密钥」，创建新密钥',
      '复制 Key 粘贴到下方输入框',
    ],
    registerUrl: 'https://cloud.siliconflow.cn/',
    keyUrl: 'https://cloud.siliconflow.cn/account/ak',
    keyPlaceholder: 'sk-...',
    keyPrefix: 'sk-',
    models: ['deepseek-r1', 'deepseek-v3'],
    region: 'cn',
  },
  {
    id: 'zhipu',
    name: '智谱 AI (GLM)',
    color: '#2563EB',
    freeInfo: '注册送 2000 万 tokens，GLM-4-Flash 永久免费不限量',
    freeBadge: '永久免费模型',
    steps: [
      '访问智谱开放平台，注册账号',
      '进入用户中心 →「API Keys」，创建密钥',
      '复制 Key 粘贴到下方输入框',
    ],
    registerUrl: 'https://open.bigmodel.cn/',
    keyUrl: 'https://bigmodel.cn/usercenter/proj-mgmt/apikeys',
    keyPlaceholder: '...',
    models: ['glm-4-flash'],
    region: 'cn',
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    color: '#EF4444',
    freeInfo: '注册送 500 万 tokens（约 $8 价值），30 天有效',
    freeBadge: '500万 tokens',
    steps: [
      '访问 DeepSeek 开放平台，用手机号注册',
      '进入「API Keys」页面，点击「创建 API Key」',
      '复制 Key 粘贴到下方输入框',
    ],
    registerUrl: 'https://platform.deepseek.com/',
    keyUrl: 'https://platform.deepseek.com/api_keys',
    keyPlaceholder: 'sk-...',
    keyPrefix: 'sk-',
    models: ['deepseek-r1', 'deepseek-v3'],
    region: 'cn',
  },
  // ── 国际推荐（需网络条件）──
  {
    id: 'google',
    name: 'Google AI Studio',
    color: '#3B82F6',
    freeInfo: '永久免费使用 Gemini 全系列，15 RPM / 100 万 TPM',
    freeBadge: '永久免费',
    steps: [
      '用 Google 账号登录 AI Studio',
      '点击左侧「Get API key」→「Create API key」',
      '复制 Key 粘贴到下方输入框',
    ],
    registerUrl: 'https://aistudio.google.com/',
    keyUrl: 'https://aistudio.google.com/apikey',
    keyPlaceholder: 'AIzaSy...',
    keyPrefix: 'AIza',
    models: ['gemini-2.5-pro'],
    region: 'intl',
  },
  {
    id: 'groq',
    name: 'Groq',
    color: '#F97316',
    freeInfo: '永久免费，无需信用卡，超快推理（Llama / Qwen / DeepSeek）',
    freeBadge: '永久免费',
    steps: [
      '访问 Groq Console，用 Google 或 GitHub 账号注册',
      '进入「API Keys」页面，创建密钥',
      '复制 Key 粘贴到下方输入框',
    ],
    registerUrl: 'https://console.groq.com/',
    keyUrl: 'https://console.groq.com/keys',
    keyPlaceholder: 'gsk_...',
    keyPrefix: 'gsk_',
    models: ['llama-3.3-70b', 'deepseek-r1-distill-70b'],
    region: 'intl',
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    color: '#8B5CF6',
    freeInfo: '聚合 100+ 模型，带 :free 后缀的模型永久免费',
    freeBadge: '免费模型',
    steps: [
      '用 Google 或 GitHub 账号登录 OpenRouter',
      '进入「Keys」页面，创建 API Key',
      '复制 Key 粘贴到下方输入框',
    ],
    registerUrl: 'https://openrouter.ai/',
    keyUrl: 'https://openrouter.ai/keys',
    keyPlaceholder: 'sk-or-v1-...',
    keyPrefix: 'sk-or-',
    models: ['gemini-2.5-flash-free', 'llama-3-8b-free'],
    region: 'intl',
  },
]

const STORAGE_KEY = 'mms-api-keys'

function loadKeys(): Record<string, string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export const useKeyStore = defineStore('keys', () => {
  const keys = ref<Record<string, string>>(loadKeys())

  function setKey(providerId: string, key: string) {
    keys.value = { ...keys.value, [providerId]: key }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(keys.value))
  }

  function removeKey(providerId: string) {
    const { [providerId]: _, ...rest } = keys.value
    keys.value = rest
    localStorage.setItem(STORAGE_KEY, JSON.stringify(keys.value))
  }

  function getKey(providerId: string): string {
    return keys.value[providerId] || ''
  }

  function hasKey(providerId: string): boolean {
    return !!keys.value[providerId]?.trim()
  }

  const configuredCount = computed(() =>
    PROVIDERS.filter(p => hasKey(p.id)).length
  )

  const configuredProviders = computed(() =>
    PROVIDERS.filter(p => hasKey(p.id)).map(p => p.id)
  )

  const isFirstTime = computed(() => configuredCount.value === 0)

  return {
    keys, setKey, removeKey, getKey, hasKey,
    configuredCount, configuredProviders, isFirstTime,
  }
})
