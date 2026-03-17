<script setup lang="ts">
import { ref, computed } from 'vue'
import { ChevronDown, ExternalLink, Eye, EyeOff, Trash2, CheckCircle, KeyRound, BookOpen } from 'lucide-vue-next'
import { useProviderStore } from '@/stores/provider'
import { useAppStore } from '@/stores/app'
import { getApiKey, maskKey } from '@/services/keychain'
import type { FreeProviderInfo } from '@/data/freeProviders'
import { openExternalUrl } from '@/utils/openExternalUrl'

const props = defineProps<{
  provider: FreeProviderInfo
  expanded: boolean
}>()

const emit = defineEmits<{
  toggleExpand: []
  configured: []
}>()

const providerStore = useProviderStore()
const appStore = useAppStore()

const keyInput = ref('')
const showKey = ref(false)
const saving = ref(false)
const maskedKeyValue = ref('')

const hasKey = computed(() => providerStore.keyStatus[props.provider.id])

// Load masked key on mount if configured
async function loadMaskedKey() {
  if (providerStore.keyStatus[props.provider.id]) {
    const account = providerStore.getDefaultAccount(props.provider.id)
    if (!account) return
    const key = await getApiKey(account.id)
    if (key) maskedKeyValue.value = maskKey(key)
  }
}
loadMaskedKey()

async function saveKey() {
  const key = keyInput.value.trim()
  if (!key) return
  saving.value = true
  try {
    await providerStore.setApiKey(props.provider.id, key)
    maskedKeyValue.value = maskKey(key)
    keyInput.value = ''
    showKey.value = false
    await appStore.refreshModels()
    emit('configured')
  } finally {
    saving.value = false
  }
}

async function removeKey() {
  await providerStore.removeApiKey(props.provider.id)
  maskedKeyValue.value = ''
  await appStore.refreshModels()
}

function onKeyInput(e: Event) {
  keyInput.value = (e.target as HTMLInputElement).value
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') saveKey()
}

function openLink(url?: string) {
  openExternalUrl(url)
}
</script>

<template>
  <div
    class="rounded-xl border overflow-hidden transition-all duration-200"
    :class="hasKey
      ? 'border-emerald-500/30 bg-emerald-500/5'
      : 'border-border-default bg-surface-2'"
  >
    <!-- Card Header -->
    <button
      @click="$emit('toggleExpand')"
      class="w-full flex items-center gap-3.5 p-4 text-left hover:bg-white/3 transition-colors"
    >
      <!-- Provider Icon -->
      <div
        class="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold text-white shrink-0 shadow-sm"
        :style="{ background: provider.color }"
      >{{ provider.name.charAt(0) }}</div>

      <!-- Info -->
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm font-semibold text-text-primary">{{ provider.name }}</span>
          <span
            v-if="hasKey"
            class="text-[10px] px-1.5 py-0.5 bg-emerald-500/15 text-emerald-400 rounded-full font-medium"
          >已配置</span>
          <span
            v-else
            class="text-[10px] px-1.5 py-0.5 bg-amber-500/15 text-amber-400 rounded-full font-medium"
          >{{ provider.freeBadge }}</span>
        </div>
        <p class="text-xs text-text-tertiary mt-0.5 truncate">{{ provider.freeInfo }}</p>
      </div>

      <!-- Expand Arrow -->
      <ChevronDown
        :size="16"
        class="text-text-tertiary shrink-0 transition-transform duration-200"
        :class="expanded ? 'rotate-180' : ''"
      />
    </button>

    <!-- Expanded Content -->
    <Transition name="expand">
      <div v-if="expanded" class="px-4 pb-4 border-t border-border-subtle">
        <!-- Steps -->
        <div class="py-4 space-y-3">
          <div
            v-for="(step, i) in provider.steps"
            :key="i"
            class="flex gap-3"
          >
            <div class="w-6 h-6 rounded-full bg-surface-3 flex items-center justify-center shrink-0 mt-0.5">
              <span class="text-xs font-semibold text-text-tertiary">{{ i + 1 }}</span>
            </div>
            <p class="text-sm text-text-secondary leading-relaxed">{{ step }}</p>
          </div>
        </div>

        <!-- Action Links -->
        <div class="flex gap-2 mb-4">
          <button
            type="button"
            @click="openLink(provider.registerUrl)"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white rounded-lg transition-opacity hover:opacity-90 shadow-sm"
            :style="{ background: provider.color }"
          >
            <ExternalLink :size="12" />
            去注册
          </button>
          <button
            type="button"
            @click="openLink(provider.keyUrl)"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-text-secondary bg-surface-3 rounded-lg hover:bg-surface-4 transition-colors"
          >
            <KeyRound :size="12" />
            获取 API Key
          </button>
          <button
            v-if="provider.modelsUrl"
            type="button"
            @click="openLink(provider.modelsUrl)"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-text-secondary bg-surface-3 rounded-lg hover:bg-surface-4 transition-colors"
          >
            <BookOpen :size="12" />
            查看模型
          </button>
        </div>

        <!-- Key Input -->
        <div class="relative">
          <input
            :type="showKey ? 'text' : 'password'"
            :value="keyInput"
            @input="onKeyInput"
            @keydown="handleKeydown"
            :placeholder="hasKey ? '输入新 Key 覆盖...' : '粘贴你的 API Key：' + provider.keyPlaceholder"
            class="w-full pl-3 pr-20 py-2.5 text-sm font-mono bg-surface-1 rounded-xl border
                   focus:outline-none focus:border-accent transition-all text-text-primary
                   placeholder:text-text-tertiary/40"
            :class="hasKey ? 'border-emerald-500/30' : 'border-border-default'"
          />
          <div class="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
            <button
              v-if="keyInput || hasKey"
              @click="showKey = !showKey"
              class="p-1 text-text-tertiary hover:text-text-secondary rounded transition-colors"
            >
              <component :is="showKey ? EyeOff : Eye" :size="14" />
            </button>
            <button
              v-if="keyInput.trim()"
              @click="saveKey"
              :disabled="saving"
              class="px-2 py-0.5 text-xs font-medium text-white bg-accent rounded-md
                     hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              {{ saving ? '...' : '保存' }}
            </button>
            <button
              v-if="hasKey && !keyInput.trim()"
              @click="removeKey"
              class="p-1 text-text-tertiary hover:text-red-400 rounded transition-colors"
            >
              <Trash2 :size="14" />
            </button>
          </div>
        </div>

        <!-- Validation hint -->
        <div v-if="hasKey" class="flex items-center gap-1.5 mt-2">
          <CheckCircle :size="14" class="text-emerald-400" />
          <span class="text-xs text-emerald-400">Key 已保存（{{ maskedKeyValue }}）</span>
        </div>

        <!-- Available models -->
        <div class="mt-3 flex items-center gap-1.5 flex-wrap">
          <span class="text-[10px] text-text-tertiary">代表模型：</span>
          <span
            v-for="mId in provider.models"
            :key="mId"
            class="text-[10px] px-1.5 py-0.5 bg-surface-3 text-text-tertiary rounded"
          >{{ mId }}</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.expand-enter-active {
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  overflow: hidden;
}
.expand-leave-active {
  transition: all 0.2s ease-in;
  overflow: hidden;
}
.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}
</style>
