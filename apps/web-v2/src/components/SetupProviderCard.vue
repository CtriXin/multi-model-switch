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
    class="rounded-[28px] border overflow-hidden transition-all duration-500 shadow-xl"
    :class="hasKey
      ? 'border-emerald-500/20 bg-emerald-500/5'
      : 'glass-v3 border-white/10 bg-surface-2'"
  >
    <!-- Card Header -->
    <button
      @click="$emit('toggleExpand')"
      class="w-full flex items-center gap-4 p-5 text-left hover:bg-white/5 transition-colors group"
    >
      <!-- Provider Icon -->
      <div
        class="w-12 h-12 rounded-2xl flex items-center justify-center text-lg font-black text-white shrink-0 shadow-lg transition-transform duration-500 group-hover:scale-110"
        :style="{ background: provider.color }"
      >{{ provider.name.charAt(0) }}</div>

      <!-- Info -->
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-base font-black text-text-primary uppercase tracking-tight">{{ provider.name }}</span>
          <span
            v-if="hasKey"
            class="text-[9px] px-2 py-0.5 bg-emerald-500/20 text-emerald-400 rounded-full font-black uppercase tracking-widest border border-emerald-500/20"
          >已接入</span>
          <span
            v-else
            class="text-[9px] px-2 py-0.5 bg-accent/20 text-accent rounded-full font-black uppercase tracking-widest border border-accent/20"
          >{{ provider.freeBadge }}</span>
        </div>
        <p class="text-[11px] text-text-tertiary mt-1 font-medium opacity-60 truncate">{{ provider.freeInfo }}</p>
      </div>

      <!-- Expand Arrow -->
      <div class="p-2 rounded-full bg-white/5 group-hover:bg-white/10 transition-colors">
        <ChevronDown
          :size="18"
          stroke-width="3"
          class="text-text-tertiary shrink-0 transition-transform duration-500"
          :class="expanded ? 'rotate-180' : ''"
        />
      </div>
    </button>

    <!-- Expanded Content -->
    <Transition name="expand">
      <div v-if="expanded" class="px-5 pb-6 border-t border-white/5 bg-black/[0.02]">
        <!-- Steps -->
        <div class="py-6 space-y-4">
          <div
            v-for="(step, i) in provider.steps"
            :key="i"
            class="flex gap-4 items-start"
          >
            <div class="w-7 h-7 rounded-full bg-white/5 flex items-center justify-center shrink-0 mt-0.5 border border-white/5">
              <span class="text-[11px] font-black text-accent">{{ i + 1 }}</span>
            </div>
            <p class="text-sm text-text-secondary leading-relaxed font-medium">{{ step }}</p>
          </div>
        </div>

        <!-- Action Links -->
        <div class="flex gap-2.5 mb-6 overflow-x-auto pb-1 no-scrollbar">
          <button
            type="button"
            @click="openLink(provider.registerUrl)"
            class="inline-flex items-center gap-2 px-4 py-2 text-[11px] font-black text-white rounded-2xl transition-all hover:scale-105 active:scale-95 shadow-lg uppercase tracking-widest whitespace-nowrap"
            :style="{ background: provider.color }"
          >
            <ExternalLink :size="14" stroke-width="3" />
            去注册
          </button>
          <button
            type="button"
            @click="openLink(provider.keyUrl)"
            class="inline-flex items-center gap-2 px-4 py-2 text-[11px] font-black text-text-secondary bg-white/5 rounded-2xl hover:bg-white/10 transition-all hover:scale-105 active:scale-95 border border-white/10 uppercase tracking-widest whitespace-nowrap"
          >
            <KeyRound :size="14" stroke-width="3" />
            获取密钥
          </button>
          <button
            v-if="provider.modelsUrl"
            type="button"
            @click="openLink(provider.modelsUrl)"
            class="inline-flex items-center gap-2 px-4 py-2 text-[11px] font-black text-text-secondary bg-white/5 rounded-2xl hover:bg-white/10 transition-all hover:scale-105 active:scale-95 border border-white/10 uppercase tracking-widest whitespace-nowrap"
          >
            <BookOpen :size="14" stroke-width="3" />
            支持列表
          </button>
        </div>

        <!-- Key Input -->
        <div class="relative group/input">
          <input
            :type="showKey ? 'text' : 'password'"
            :value="keyInput"
            @input="onKeyInput"
            @keydown="handleKeydown"
            :placeholder="hasKey ? '输入新 Key 覆盖...' : '粘贴你的 API Key：' + provider.keyPlaceholder"
            class="w-full pl-5 pr-24 py-3.5 text-sm font-mono bg-white/5 rounded-2xl border
                   focus:outline-none focus:border-accent/50 transition-all text-text-primary
                   placeholder:text-text-tertiary/40 shadow-inner"
            :class="hasKey ? 'border-emerald-500/30' : 'border-white/10'"
          />
          <div class="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
            <button
              v-if="keyInput || hasKey"
              @click="showKey = !showKey"
              class="p-2 text-text-tertiary hover:text-text-secondary rounded-xl transition-colors"
            >
              <component :is="showKey ? EyeOff : Eye" :size="16" stroke-width="3" />
            </button>
            <button
              v-if="keyInput.trim()"
              @click="saveKey"
              :disabled="saving"
              class="px-4 py-1.5 text-[10px] font-black text-white bg-accent rounded-xl
                     hover:scale-105 active:scale-95 disabled:opacity-50 transition-all uppercase tracking-widest shadow-lg"
            >
              {{ saving ? '...' : '保存' }}
            </button>
            <button
              v-if="hasKey && !keyInput.trim()"
              @click="removeKey"
              class="p-2 text-text-tertiary hover:text-red-400 rounded-xl transition-colors"
            >
              <Trash2 :size="16" stroke-width="3" />
            </button>
          </div>
        </div>

        <!-- Validation hint -->
        <div v-if="hasKey" class="flex items-center gap-2 mt-4 px-1">
          <CheckCircle :size="14" stroke-width="3" class="text-emerald-400" />
          <span class="text-[11px] font-black text-emerald-400 uppercase tracking-widest">已保存（{{ maskedKeyValue }}）</span>
        </div>

        <!-- Available models -->
        <div class="mt-4 flex items-center gap-2 flex-wrap px-1">
          <span class="text-[10px] font-black text-text-tertiary uppercase tracking-widest opacity-40">代表模型：</span>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="mId in provider.models"
              :key="mId"
              class="text-[9px] px-2 py-0.5 bg-white/5 text-text-tertiary rounded-lg font-black uppercase tracking-tight border border-white/5"
            >{{ mId }}</span>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.expand-enter-active {
  transition: all 0.5s cubic-bezier(0.32, 0.72, 0, 1);
  overflow: hidden;
}
.expand-leave-active {
  transition: all 0.4s cubic-bezier(0.32, 0.72, 0, 1);
  overflow: hidden;
}
.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
