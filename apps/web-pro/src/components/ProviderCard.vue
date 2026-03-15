<template>
  <div
    class="bg-white rounded-2xl border border-gray-200 overflow-hidden transition-all duration-200"
    :class="hasKey ? 'ring-2 ring-emerald-200 border-emerald-300' : ''"
  >
    <!-- Card Header -->
    <button
      @click="$emit('toggleExpand')"
      class="w-full flex items-center gap-3.5 p-4 text-left hover:bg-gray-50/50 transition-colors"
    >
      <!-- Provider Icon -->
      <div
        class="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold text-white flex-shrink-0 shadow-sm"
        :style="{ background: provider.color }"
      >{{ provider.name.charAt(0) }}</div>

      <!-- Info -->
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm font-semibold text-gray-900">{{ provider.name }}</span>
          <span
            v-if="hasKey"
            class="text-[10px] px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded-full font-medium"
          >已配置</span>
          <span
            v-else
            class="text-[10px] px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded-full font-medium"
          >{{ provider.freeBadge }}</span>
        </div>
        <p class="text-xs text-gray-400 mt-0.5 truncate">{{ provider.freeInfo }}</p>
      </div>

      <!-- Expand Arrow -->
      <ChevronDown
        class="w-4 h-4 text-gray-300 flex-shrink-0 transition-transform duration-200"
        :class="expanded ? 'rotate-180' : ''"
      />
    </button>

    <!-- Expanded Content -->
    <Transition name="expand">
      <div v-if="expanded" class="px-4 pb-4 border-t border-gray-100">
        <!-- Steps -->
        <div class="py-4 space-y-3">
          <div
            v-for="(step, i) in provider.steps"
            :key="i"
            class="flex gap-3"
          >
            <div class="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0 mt-0.5">
              <span class="text-xs font-semibold text-gray-500">{{ i + 1 }}</span>
            </div>
            <p class="text-sm text-gray-600 leading-relaxed">{{ step }}</p>
          </div>
        </div>

        <!-- Action Links -->
        <div class="flex gap-2 mb-4">
          <a
            :href="provider.registerUrl"
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white rounded-lg transition-colors shadow-sm hover:opacity-90"
            :style="{ background: provider.color }"
          >
            <ExternalLink class="w-3 h-3" />
            去注册
          </a>
          <a
            :href="provider.keyUrl"
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
          >
            <KeyRound class="w-3 h-3" />
            获取 API Key
          </a>
        </div>

        <!-- Key Input -->
        <div class="relative">
          <input
            :type="showKey ? 'text' : 'password'"
            :value="keyStore.getKey(provider.id)"
            @input="$emit('keyInput', ($event.target as HTMLInputElement).value)"
            :placeholder="'粘贴你的 API Key：' + provider.keyPlaceholder"
            class="w-full pl-3 pr-20 py-2.5 text-sm font-mono bg-gray-50 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-emerald-100 focus:border-emerald-400 transition-all"
            :class="hasKey ? 'border-emerald-300 bg-emerald-50/30' : ''"
          />
          <div class="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
            <button
              v-if="keyStore.getKey(provider.id)"
              @click="$emit('toggleShowKey')"
              class="p-1 text-gray-400 hover:text-gray-600 rounded transition-colors"
            >
              <component :is="showKey ? EyeOff : Eye" class="w-3.5 h-3.5" />
            </button>
            <button
              v-if="hasKey"
              @click="$emit('removeKey')"
              class="p-1 text-gray-400 hover:text-red-500 rounded transition-colors"
            >
              <Trash2 class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <!-- Validation hint -->
        <div v-if="hasKey" class="flex items-center gap-1.5 mt-2">
          <CheckCircle class="w-3.5 h-3.5 text-emerald-500" />
          <span class="text-xs text-emerald-600">Key 已保存（{{ maskKey(keyStore.getKey(provider.id)) }}）</span>
        </div>

        <!-- Available models -->
        <div class="mt-3 flex items-center gap-1.5 flex-wrap">
          <span class="text-[10px] text-gray-400">可用模型：</span>
          <span
            v-for="mId in provider.models"
            :key="mId"
            class="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded"
          >{{ mId }}</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  ChevronDown, ExternalLink, Eye, EyeOff,
  Trash2, CheckCircle, KeyRound,
} from 'lucide-vue-next'
import { useKeyStore, type ProviderInfo } from '@/stores/keys'

const props = defineProps<{
  provider: ProviderInfo
  expanded: boolean
  showKey: boolean
}>()

defineEmits<{
  toggleExpand: []
  toggleShowKey: []
  keyInput: [val: string]
  removeKey: []
}>()

const keyStore = useKeyStore()
const hasKey = computed(() => keyStore.hasKey(props.provider.id))

function maskKey(key: string): string {
  if (key.length <= 8) return '****'
  return key.slice(0, 6) + '...' + key.slice(-4)
}
</script>

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
