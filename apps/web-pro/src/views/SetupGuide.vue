<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-2xl mx-auto px-6 py-10">
      <!-- Header -->
      <div class="text-center mb-10 animate-fade-in">
        <div class="w-12 h-12 rounded-2xl bg-gradient-to-br from-emerald-400 to-cyan-500 flex items-center justify-center mx-auto mb-4 shadow-lg">
          <Key class="w-6 h-6 text-white" />
        </div>
        <h1 class="text-xl font-bold text-gray-900 mb-2">3 分钟获取免费 API</h1>
        <p class="text-sm text-gray-500 max-w-md mx-auto">
          以下服务商均提供免费额度，选一个注册即可开始。配置越多，可用模型越多。
        </p>
        <!-- Progress -->
        <div class="flex items-center justify-center gap-2 mt-5">
          <div class="flex gap-1">
            <div
              v-for="p in allProviders"
              :key="p.id"
              class="w-2 h-2 rounded-full transition-colors duration-300"
              :class="keyStore.hasKey(p.id) ? 'bg-emerald-500' : 'bg-gray-200'"
            />
          </div>
          <span class="text-xs text-gray-400">{{ keyStore.configuredCount }} / {{ allProviders.length }} 已配置</span>
        </div>
      </div>

      <!-- CN Providers -->
      <div class="mb-8">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-xs font-semibold text-gray-400 uppercase tracking-wider">国产服务商</span>
          <span class="text-[10px] text-gray-300">国内直连，无需代理</span>
        </div>
        <div class="space-y-3">
          <ProviderCard
            v-for="p in cnProviders"
            :key="p.id"
            :provider="p"
            :expanded="expanded === p.id"
            :show-key="showKey === p.id"
            @toggle-expand="toggleExpand(p.id)"
            @toggle-show-key="showKey = showKey === p.id ? '' : p.id"
            @key-input="(val: string) => keyStore.setKey(p.id, val.trim())"
            @remove-key="keyStore.removeKey(p.id)"
          />
        </div>
      </div>

      <!-- International Providers -->
      <div class="mb-10">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-xs font-semibold text-gray-400 uppercase tracking-wider">国际服务商</span>
          <span class="text-[10px] text-gray-300">需科学上网</span>
        </div>
        <div class="space-y-3">
          <ProviderCard
            v-for="p in intlProviders"
            :key="p.id"
            :provider="p"
            :expanded="expanded === p.id"
            :show-key="showKey === p.id"
            @toggle-expand="toggleExpand(p.id)"
            @toggle-show-key="showKey = showKey === p.id ? '' : p.id"
            @key-input="(val: string) => keyStore.setKey(p.id, val.trim())"
            @remove-key="keyStore.removeKey(p.id)"
          />
        </div>
      </div>

      <!-- Bottom Actions -->
      <div class="flex items-center justify-between">
        <button
          @click="$router.push('/')"
          class="text-sm text-gray-400 hover:text-gray-600 transition-colors"
        >
          {{ keyStore.configuredCount > 0 ? '返回首页' : '跳过，先体验 Demo' }}
        </button>
        <button
          v-if="keyStore.configuredCount > 0"
          @click="$router.push('/chat')"
          class="px-4 py-2 text-sm font-medium text-white bg-accent-600 rounded-xl hover:bg-accent-700 transition-colors shadow-sm"
        >
          开始使用 →
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Key } from 'lucide-vue-next'
import { useKeyStore, PROVIDERS } from '@/stores/keys'
import ProviderCard from '@/components/ProviderCard.vue'

const keyStore = useKeyStore()
const allProviders = PROVIDERS
const cnProviders = computed(() => PROVIDERS.filter(p => p.region === 'cn'))
const intlProviders = computed(() => PROVIDERS.filter(p => p.region === 'intl'))

const expanded = ref(PROVIDERS[0].id)
const showKey = ref('')

function toggleExpand(id: string) {
  expanded.value = expanded.value === id ? '' : id
}
</script>
