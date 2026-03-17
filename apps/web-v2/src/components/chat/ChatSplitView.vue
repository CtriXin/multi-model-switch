<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAppStore, getModelColor } from '@/stores/app'
import { useChatStore, type ChatMessage, type ChatRound } from '@/stores/chat'
import { CheckCircle2, MessageSquare } from 'lucide-vue-next'
import ModelResponseCard from './ModelResponseCard.vue'

const props = defineProps<{
  round: ChatRound
}>()

const appStore = useAppStore()
const chatStore = useChatStore()
type ResponseEntry = [string, ChatMessage]

const entries = computed<ResponseEntry[]>(() => Array.from(props.round.responses.entries()))

const activeModelId = computed(() => props.round.activeModelId || entries.value[0]?.[0])

const mainResponse = computed(() => {
  if (!entries.value.length) return null
  const found = entries.value.find(([id]) => id === activeModelId.value)
  return found || entries.value[0]
})

const otherResponses = computed(() => {
  return entries.value.filter(([id]) => id !== activeModelId.value)
})

function handleSelect(modelId: string) {
  chatStore.setActiveModel(props.round.id, modelId)
}

function getModelInitial(modelId: string): string {
  const name = appStore.getModel(modelId)?.name || modelId
  return name.charAt(0).toUpperCase()
}

function getPreviewText(content: string): string {
  if (!content) return '正在生成中...'
  const clean = content.replace(/<[^>]*>?/gm, '').trim()
  return clean.slice(0, 80) + (clean.length > 80 ? '...' : '')
}
</script>

<template>
  <div class="flex flex-col lg:flex-row gap-6 items-start animate-v3-fade-in">
    <!-- Main Display (Left/Top) -->
    <div class="flex-1 w-full min-w-0">
      <Transition name="v3-main-card" mode="out-in">
        <div v-if="mainResponse" :key="mainResponse[0]" class="h-full">
          <ModelResponseCard
            :model-id="mainResponse[0]"
            :model-name="appStore.getModel(mainResponse[0])?.name || mainResponse[0]"
            :provider="appStore.getModel(mainResponse[0])?.provider || ''"
            :content="mainResponse[1].content"
            :elapsed="mainResponse[1].elapsed"
            :tier="appStore.getModel(mainResponse[0])?.tier"
            :error="mainResponse[1].error"
            :streaming="mainResponse[1].streaming"
            :active="true"
            :selected="round.selectedModelId === mainResponse[0]"
            @select="chatStore.selectModel(round.id, mainResponse[0])"
          />
        </div>
      </Transition>
    </div>

    <!-- Sidebar Thumbnails (Right/Bottom) -->
    <div class="w-full lg:w-72 xl:w-80 shrink-0 flex flex-col gap-3">
      <div class="flex items-center justify-between px-2">
        <span class="text-[10px] font-black text-text-tertiary uppercase tracking-[0.2em]">
          其他候选 ({{ otherResponses.length }})
        </span>
      </div>

      <div class="flex flex-col gap-2">
        <div
          v-for="[modelId, msg] in otherResponses"
          :key="modelId"
          class="group relative cursor-pointer transition-all duration-300 active:scale-95"
          @click="handleSelect(modelId)"
        >
          <!-- Selection Overlay/Icon -->
          <button 
            v-if="!msg.streaming && !msg.error"
            @click.stop="chatStore.selectModel(round.id, modelId)"
            class="absolute top-2 right-2 z-20 w-8 h-8 rounded-full flex items-center justify-center transition-all duration-500"
            :class="[
              round.selectedModelId === modelId 
                ? 'bg-green-500 text-white shadow-lg' 
                : 'bg-white/5 text-text-tertiary/20 hover:text-green-400 hover:bg-green-500/10 opacity-0 group-hover:opacity-100'
            ]"
            :title="round.selectedModelId === modelId ? '当前上下文' : '设为上下文'"
          >
            <CheckCircle2 :size="18" :stroke-width="3" />
          </button>

          <div 
            class="p-3 rounded-2xl border transition-all duration-300 overflow-hidden"
            :class="[
              round.selectedModelId === modelId
                ? 'border-green-500/50 bg-green-500/5 shadow-[0_8px_24px_rgba(34,197,94,0.1)]'
                : msg.streaming ? 'border-accent/30 bg-accent/5' : 'border-white/5 bg-white/5 hover:border-white/20 hover:bg-white/10'
            ]"
          >
            <!-- Header -->
            <div class="flex items-center gap-2 mb-2">
              <div 
                class="w-5 h-5 rounded-lg flex items-center justify-center text-[10px] font-black text-white shadow-lg shrink-0"
                :style="{ backgroundColor: getModelColor(appStore.getModel(modelId)?.provider || '') }"
              >
                {{ getModelInitial(modelId) }}
              </div>
              <span class="text-[11px] font-bold text-text-primary truncate uppercase tracking-tight">{{ appStore.getModel(modelId)?.name || modelId }}</span>
              <div v-if="msg.streaming" class="ml-auto flex gap-0.5">
                <div class="w-1 h-1 rounded-full bg-accent animate-bounce"></div>
                <div class="w-1 h-1 rounded-full bg-accent animate-bounce [animation-delay:0.2s]"></div>
              </div>
            </div>

            <!-- Preview -->
            <p class="text-[10px] text-text-tertiary/80 leading-relaxed line-clamp-2 font-medium">
              {{ getPreviewText(msg.content) }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.v3-main-card-enter-active {
  transition: all 0.4s cubic-bezier(0.23, 1, 0.32, 1);
}
.v3-main-card-leave-active {
  transition: all 0.3s cubic-bezier(0.32, 0.72, 0, 1);
}
.v3-main-card-enter-from {
  opacity: 0;
  transform: translateY(10px) scale(0.98);
}
.v3-main-card-leave-to {
  opacity: 0;
  transform: translateY(-5px) scale(0.99);
}
</style>
