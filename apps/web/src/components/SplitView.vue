<template>
  <div class="flex flex-col lg:flex-row gap-4 items-start">
    <!-- Main Card (Left) -->
    <div class="flex-1 w-full lg:w-auto relative">
      <Transition name="main-card" mode="out-in">
        <div v-if="mainResponse" :key="mainResponse.model">
          <ChatResponseCard
            :response="mainResponse"
            :selected="true"
            :archived="false"
            @select="null"
          />
        </div>
      </Transition>
    </div>

    <!-- Thumbnail Stack (Right) - Compact -->
    <div class="w-full lg:w-72 xl:w-80 flex-shrink-0 flex flex-col gap-2">
      <div class="text-xs font-medium text-gray-500 px-1">
        其他模型 ({{ otherResponses.length }})
      </div>

      <!-- Thumbnail Cards with Transition -->
      <TransitionGroup name="thumb-list" tag="div" class="flex flex-col gap-2">
        <div
          v-for="response in otherResponses"
          :key="response.model"
          class="group relative cursor-pointer"
          :class="{ 'is-selected': selectedThumb === response.model }"
          @click="handleSelect(response.model)"
        >
          <!-- Unread Dot -->
          <div
            v-if="!isViewed(response.model)"
            class="absolute -left-1.5 top-1/2 -translate-y-1/2 w-2 h-2 bg-red-500 rounded-full border border-white shadow-sm z-10"
          />

          <!-- Compact Card -->
          <div
            class="relative rounded-lg border p-2 transition-all duration-200 hover:shadow-md"
            :class="[
              !isViewed(response.model)
                ? 'bg-indigo-50/50 border-indigo-200'
                : 'bg-white border-gray-200 hover:border-indigo-300'
            ]"
          >
            <!-- Viewed indicator line -->
            <div
              v-if="isViewed(response.model)"
              class="absolute left-0 top-2 bottom-2 w-0.5 bg-gray-300 rounded-full"
            />
            <!-- Header -->
            <div class="flex items-center gap-2">
              <div
                class="w-5 h-5 rounded flex items-center justify-center flex-shrink-0"
                :class="getModelColor(response.model)"
              >
                <span class="text-[9px] font-bold text-white">{{ getInitial(response.model) }}</span>
              </div>
              <span class="text-xs font-medium text-gray-700 truncate flex-1">{{ getModelName(response.model) }}</span>
              <!-- Status dot removed - user asked what it's for -->
            </div>

            <!-- Preview -->
            <p class="text-[11px] text-gray-500 line-clamp-2 mt-1.5 leading-relaxed">
              {{ getPreview(response) }}
            </p>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ChatRound, ChatResponse, ModelMeta } from '@mms/contracts'
import ChatResponseCard from './ChatResponseCard.vue'

const props = defineProps<{
  round: ChatRound
  models: ModelMeta[]
  viewedResponses?: Set<string>
}>()

const emit = defineEmits<{
  select: [modelId: string]
}>()

const selectedThumb = ref<string | null>(null)

const mainResponse = computed(() => {
  const responses = props.round.responses
  if (responses.length === 0) return null
  if (props.round.selectedModel) {
    return responses.find(r => r.model === props.round.selectedModel) || responses[0]
  }
  return responses[0]
})

const otherResponses = computed(() => {
  const main = mainResponse.value
  if (!main) return props.round.responses
  // Put the previously selected model at the end, followed by others
  const others = props.round.responses.filter(r => r.model !== main.model)
  // Sort: unviewed first, then by original order
  return others
})

function isViewed(modelId: string): boolean {
  return props.viewedResponses?.has(modelId) ?? false
}

function handleSelect(modelId: string) {
  selectedThumb.value = modelId
  emit('select', modelId)
  setTimeout(() => {
    selectedThumb.value = null
  }, 500)
}

function getModelColor(modelId: string): string {
  const colors = ['bg-indigo-500', 'bg-emerald-500', 'bg-blue-500', 'bg-purple-500', 'bg-amber-500', 'bg-pink-500']
  const index = modelId.split('').reduce((a, b) => a + b.charCodeAt(0), 0) % colors.length
  return colors[index]
}

function getInitial(modelId: string): string {
  const model = props.models.find(m => m.id === modelId)
  return (model?.name || modelId).charAt(0).toUpperCase()
}

function getModelName(modelId: string): string {
  const model = props.models.find(m => m.id === modelId)
  return model?.name || modelId
}

function getPreview(response: ChatResponse): string {
  const text = response.displayText || response.content
  const clean = text.replace(/<BRIEF>[\s\S]*?<\/BRIEF>/gi, '').trim()
  return clean.slice(0, 60) + (clean.length > 60 ? '...' : '')
}
</script>

<style scoped>
/* Main card: slide down to exit, slide up to enter */
.main-card-enter-active {
  transition: all 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.main-card-leave-active {
  transition: all 0.3s ease-in;
}

/* New main card enters from below (was the clicked thumbnail) */
.main-card-enter-from {
  opacity: 0;
  transform: translateY(30px) scale(0.95);
}

/* Old main card exits downward to become a thumbnail */
.main-card-leave-to {
  opacity: 0;
  transform: translateY(40px) scale(0.9);
}

/* Thumbnail list animations */
.thumb-list-move {
  transition: transform 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.thumb-list-enter-active {
  transition: all 0.35s ease-out;
}

.thumb-list-leave-active {
  transition: all 0.25s ease-in;
  position: absolute;
  width: 100%;
}

/* Cards enter thumbnails from below (old main card comes in from bottom) */
.thumb-list-enter-from {
  opacity: 0;
  transform: translateY(30px) scale(0.95);
}

/* Selected thumbnail leaves downward to become main card */
.thumb-list-leave-to {
  opacity: 0;
  transform: translateY(-30px) scale(1.05);
}

/* Highlight selected thumbnail during transition */
.is-selected .bg-white {
  border-color: rgb(99 102 241) !important;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.2);
}
</style>
