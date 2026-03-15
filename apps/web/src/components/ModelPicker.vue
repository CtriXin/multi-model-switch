<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="$emit('update:show', false)">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" />

        <!-- Modal Content -->
        <div class="relative w-full max-w-4xl max-h-[85vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <div>
              <h2 class="text-lg font-semibold text-gray-900">选择模型</h2>
              <p class="text-sm text-gray-500 mt-0.5">
                已选择 {{ selected.length }} 个模型 (最多 {{ maxSelect }})
              </p>
            </div>
            <button
              @click="$emit('update:show', false)"
              class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X class="w-5 h-5" />
            </button>
          </div>

          <div class="flex flex-1 overflow-hidden">
            <!-- Left: Model Selection -->
            <div class="flex-1 flex flex-col min-w-0">
              <!-- Presets -->
              <div class="px-6 py-3 border-b border-gray-200 bg-gray-50">
                <div class="flex items-center gap-2 overflow-x-auto pb-1">
                  <span class="text-xs font-medium text-gray-500 uppercase whitespace-nowrap">预设:</span>
                  <button
                    v-for="preset in presets"
                    :key="preset.id"
                    @click="$emit('apply-preset', preset.id)"
                    class="px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-sm text-gray-700 hover:border-indigo-500 hover:text-indigo-600 transition-colors whitespace-nowrap"
                  >
                    {{ preset.name }}
                  </button>
                </div>
              </div>

              <!-- Search -->
              <div class="px-6 py-3 border-b border-gray-200">
                <div class="relative">
                  <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    v-model="searchQuery"
                    type="text"
                    placeholder="搜索模型..."
                    class="w-full pl-10 pr-4 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  >
                </div>
              </div>

              <!-- Model List -->
              <div class="flex-1 overflow-y-auto p-6">
                <div v-for="(models, category) in filteredCategories" :key="category" class="mb-6">
                  <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                    {{ categoryNames[category as string] || category }}
                  </h3>
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <ModelCard
                      v-for="model in models"
                      :key="model.id"
                      :model="model"
                      :selected="selected.includes(model.id)"
                      :disabled="!selected.includes(model.id) && selected.length >= maxSelect"
                      @toggle="$emit('toggle', model.id)"
                    />
                  </div>
                </div>
              </div>
            </div>

            <!-- Right: Selected Models -->
            <div class="w-64 bg-gray-50 border-l border-gray-200 flex flex-col">
              <div class="px-4 py-3 border-b border-gray-200">
                <h3 class="text-sm font-medium text-gray-900">已选择</h3>
              </div>
              <div class="flex-1 overflow-y-auto p-4 space-y-2">
                <div
                  v-for="modelId in selected"
                  :key="modelId"
                  class="flex items-center justify-between p-2 bg-white rounded-lg border border-gray-200"
                >
                  <span class="text-sm text-gray-700 truncate">{{ getModelName(modelId) }}</span>
                  <button
                    @click="$emit('toggle', modelId)"
                    class="p-1 text-gray-400 hover:text-red-500 transition-colors"
                  >
                    <X class="w-4 h-4" />
                  </button>
                </div>
                <div v-if="selected.length === 0" class="text-sm text-gray-500 text-center py-4">
                  未选择模型
                </div>
              </div>
              <div class="p-4 border-t border-gray-200 space-y-2">
                <button
                  v-if="selected.length > 0"
                  @click="$emit('clear')"
                  class="w-full px-4 py-2 text-sm text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  清空选择
                </button>
                <button
                  @click="$emit('update:show', false)"
                  class="w-full px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                >
                  完成
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { X, Search } from 'lucide-vue-next'
import type { ModelMeta, Preset } from '@mms/contracts'
import { CATEGORY_NAMES, MAX_SELECT } from '@mms/contracts'
import ModelCard from './ModelCard.vue'

const props = defineProps<{
  show: boolean
  models: ModelMeta[]
  selected: string[]
  presets: Preset[]
}>()

defineEmits<{
  'update:show': [value: boolean]
  toggle: [modelId: string]
  'apply-preset': [presetId: string]
  clear: []
}>()

const searchQuery = ref('')
const maxSelect = MAX_SELECT
const categoryNames = CATEGORY_NAMES

const filteredCategories = computed(() => {
  const query = searchQuery.value.toLowerCase()
  const result: Record<string, ModelMeta[]> = {}

  for (const model of props.models) {
    if (query && !model.id.toLowerCase().includes(query) && !model.name.toLowerCase().includes(query)) {
      continue
    }

    if (!result[model.category]) {
      result[model.category] = []
    }
    result[model.category].push(model)
  }

  return result
})

function getModelName(modelId: string): string {
  const model = props.models.find(m => m.id === modelId)
  return model?.name || modelId
}
</script>

<style scoped>
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
