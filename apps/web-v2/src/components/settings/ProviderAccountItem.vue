<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, KeyRound, Power, ShieldOff, ShieldCheck, Star, X } from 'lucide-vue-next'
import { getApiKey, maskKey } from '@/services/keychain'
import { useAppStore } from '@/stores/app'
import { useProviderStore, type ProviderAccount, type ProviderConfig } from '@/stores/provider'

const props = defineProps<{
  provider: ProviderConfig
  account: ProviderAccount
  canDelete: boolean
}>()

const providerStore = useProviderStore()
const appStore = useAppStore()

const editing = ref(false)
const nameInput = ref(props.account.name)
const keyInput = ref('')
const saving = ref(false)
const maskedKeyValue = ref('')

const hasKey = computed(() => !!providerStore.accountKeyStatus[props.account.id])
const isSuppressed = computed(() => (
  !!props.account.suppressedUntil && props.account.suppressedUntil > Date.now()
))

const statusText = computed(() => {
  if (props.account.lastErrorType === 'invalid_key') {
    return '上次请求返回 invalid key，已自动停用'
  }
  if (isSuppressed.value) {
    return '今日额度或频率受限，已临时跳过'
  }
  if (!props.account.enabled) {
    return '当前账户已手动停用'
  }
  if (!hasKey.value) {
    return '还没有保存 API Key'
  }
  if (props.account.lastUsedAt) {
    return `最近使用 ${new Date(props.account.lastUsedAt).toLocaleString()}`
  }
  return '可参与模型拉取与请求 fallback'
})

async function loadMaskedKey() {
  if (!hasKey.value) {
    maskedKeyValue.value = ''
    return
  }

  const key = await getApiKey(props.account.id)
  maskedKeyValue.value = key ? maskKey(key) : ''
}

watch(
  () => [props.account.id, providerStore.accountKeyStatus[props.account.id]],
  () => {
    void loadMaskedKey()
  },
  { immediate: true },
)

function startEdit() {
  nameInput.value = props.account.name
  keyInput.value = ''
  editing.value = true
}

function cancelEdit() {
  nameInput.value = props.account.name
  keyInput.value = ''
  editing.value = false
}

async function saveAccount() {
  const nextName = nameInput.value.trim()
  if (!nextName) return

  saving.value = true
  try {
    if (nextName !== props.account.name) {
      providerStore.updateAccount(props.account.id, { name: nextName })
    }

    const nextKey = keyInput.value.trim()
    if (nextKey) {
      await providerStore.setAccountApiKey(props.account.id, nextKey)
    }

    await loadMaskedKey()
    await appStore.refreshModels()
    cancelEdit()
  } finally {
    saving.value = false
  }
}

function setDefault() {
  providerStore.setDefaultAccount(props.account.id)
}

async function removeKey() {
  await providerStore.removeAccountApiKey(props.account.id)
  maskedKeyValue.value = ''
  await appStore.refreshModels()
}

async function toggleEnabled() {
  providerStore.updateAccount(props.account.id, { enabled: !props.account.enabled })
  await appStore.refreshModels()
}

async function removeAccount() {
  await providerStore.removeAccount(props.account.id)
  await appStore.refreshModels()
}
</script>

<template>
  <div class="rounded-xl border border-border-subtle bg-surface-2/70 p-3 space-y-3">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-sm font-medium text-text-primary">{{ account.name }}</span>
          <span
            v-if="account.isDefault"
            class="inline-flex items-center gap-1 rounded-full bg-accent/12 px-2 py-0.5 text-[10px] font-medium text-accent"
          >
            <Star :size="10" />
            默认账户
          </span>
          <span
            v-if="hasKey && account.enabled && !isSuppressed"
            class="inline-flex items-center gap-1 rounded-full bg-emerald-500/12 px-2 py-0.5 text-[10px] font-medium text-emerald-400"
          >
            <ShieldCheck :size="10" />
            可用
          </span>
          <span
            v-else-if="isSuppressed"
            class="inline-flex items-center gap-1 rounded-full bg-amber-500/12 px-2 py-0.5 text-[10px] font-medium text-amber-400"
          >
            <ShieldOff :size="10" />
            今日停用
          </span>
          <span
            v-else-if="!account.enabled"
            class="inline-flex items-center gap-1 rounded-full bg-surface-3 px-2 py-0.5 text-[10px] font-medium text-text-tertiary"
          >
            <Power :size="10" />
            已停用
          </span>
          <span
            v-else
            class="inline-flex items-center gap-1 rounded-full bg-surface-3 px-2 py-0.5 text-[10px] font-medium text-text-tertiary"
          >
            <KeyRound :size="10" />
            未配置
          </span>
        </div>

        <div class="mt-1 text-xs font-mono text-text-tertiary">
          {{ maskedKeyValue || '未保存 API Key' }}
        </div>
        <div class="mt-1 text-[11px] leading-5 text-text-tertiary">
          {{ statusText }}
        </div>
      </div>

      <div class="flex flex-wrap gap-1.5 sm:max-w-[18rem] sm:justify-end">
        <button
          v-if="!account.isDefault"
          @click="setDefault"
          class="rounded-lg border border-border-default px-2.5 py-1 text-[11px] text-text-secondary transition-colors hover:bg-surface-3"
        >
          设为默认
        </button>
        <button
          @click="toggleEnabled"
          class="rounded-lg border border-border-default px-2.5 py-1 text-[11px] transition-colors hover:bg-surface-3"
          :class="account.enabled ? 'text-text-secondary' : 'text-amber-400'"
        >
          {{ account.enabled ? '停用' : '启用' }}
        </button>
        <button
          @click="startEdit"
          class="rounded-lg border border-border-default px-2.5 py-1 text-[11px] text-text-secondary transition-colors hover:bg-surface-3"
        >
          {{ hasKey ? '修改' : '配置' }}
        </button>
        <button
          v-if="hasKey"
          @click="removeKey"
          class="rounded-lg border border-red-500/20 px-2.5 py-1 text-[11px] text-red-400 transition-colors hover:bg-red-500/10"
        >
          清除 Key
        </button>
        <button
          v-if="canDelete"
          @click="removeAccount"
          class="rounded-lg border border-red-500/20 px-2.5 py-1 text-[11px] text-red-400 transition-colors hover:bg-red-500/10"
        >
          删除账户
        </button>
      </div>
    </div>

    <div v-if="editing" class="space-y-3 border-t border-border-subtle pt-3">
      <div class="grid gap-3 sm:grid-cols-[minmax(0,180px)_minmax(0,1fr)]">
        <div>
          <label class="mb-1 block text-[11px] text-text-tertiary">账户名称</label>
          <input
            v-model="nameInput"
            type="text"
            placeholder="比如：免费号 A / 内部测试"
            class="w-full rounded-lg border border-border-default bg-surface-1 px-3 py-2 text-sm text-text-primary transition-colors focus:border-accent focus:outline-none"
          />
        </div>
        <div>
          <label class="mb-1 block text-[11px] text-text-tertiary">API Key</label>
          <input
            v-model="keyInput"
            type="password"
            :placeholder="hasKey ? '留空则只修改名称；输入则覆盖当前 Key' : `粘贴 ${provider.name} 的 API Key`"
            class="w-full rounded-lg border border-border-default bg-surface-1 px-3 py-2 text-sm font-mono text-text-primary transition-colors focus:border-accent focus:outline-none"
          />
        </div>
      </div>

      <div class="flex flex-wrap gap-2">
        <button
          @click="saveAccount"
          :disabled="saving || !nameInput.trim()"
          class="inline-flex items-center gap-1 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent/90 disabled:opacity-50"
        >
          <Check :size="12" />
          保存
        </button>
        <button
          @click="cancelEdit"
          class="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs text-text-tertiary transition-colors hover:bg-surface-3"
        >
          <X :size="12" />
          取消
        </button>
      </div>
    </div>
  </div>
</template>
