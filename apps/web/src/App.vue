<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Navigation Header -->
    <nav class="fixed top-0 left-0 right-0 z-50 bg-white border-b border-gray-200">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
          <!-- Logo & Brand -->
          <div class="flex items-center">
            <router-link to="/" class="flex items-center gap-2">
              <div class="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
                <span class="text-white font-bold text-sm">M</span>
              </div>
              <span class="font-semibold text-gray-900">MMS</span>
            </router-link>

            <!-- Nav Links -->
            <div class="hidden md:flex ml-8 space-x-1">
              <router-link
                v-for="item in navItems"
                :key="item.path"
                :to="item.path"
                :class="[
                  'px-3 py-2 rounded-md text-sm font-medium transition-colors',
                  $route.path === item.path
                    ? 'bg-indigo-50 text-indigo-700'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                ]"
              >
                <component :is="item.icon" class="inline-block w-4 h-4 mr-1.5" />
                {{ item.name }}
              </router-link>
            </div>
          </div>

          <!-- Right Section -->
          <div class="flex items-center gap-3">
            <!-- Model Picker Button -->
            <button
              @click="showModelPicker = true"
              class="flex items-center gap-2 px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm text-gray-700 transition-colors"
            >
              <Bot class="w-4 h-4" />
              <span class="hidden sm:inline">
                {{ selectedModels.length > 0 ? `${selectedModels.length} 个模型` : '选择模型' }}
              </span>
              <span v-if="selectedModels.length > 0" class="bg-indigo-600 text-white text-xs px-1.5 py-0.5 rounded-full">
                {{ selectedModels.length }}
              </span>
            </button>

            <!-- Settings -->
            <router-link
              to="/settings"
              class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <Settings class="w-5 h-5" />
            </router-link>
          </div>
        </div>
      </div>
    </nav>

    <!-- Main Content -->
    <main class="pt-16">
      <router-view />
    </main>

    <!-- Model Picker Modal -->
    <ModelPicker
      v-model:show="showModelPicker"
      :models="models"
      :selected="selectedModels"
      :presets="presets"
      @toggle="toggleModel"
      @apply-preset="applyPreset"
      @clear="clearSelection"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Bot, Settings, MessageSquare, Users, History, Home } from 'lucide-vue-next'
import { useAppStore } from '@/stores'
import ModelPicker from '@/components/ModelPicker.vue'

const appStore = useAppStore()
const showModelPicker = ref(false)

const navItems = [
  { name: '首页', path: '/', icon: Home },
  { name: '对话', path: '/chat', icon: MessageSquare },
  { name: '讨论', path: '/discuss', icon: Users },
  { name: '会话', path: '/sessions', icon: History },
]

const models = computed(() => appStore.models)
const selectedModels = computed(() => appStore.selectedModels)
const presets = computed(() => appStore.presets)

const { toggleModel, applyPreset, clearSelection } = appStore

onMounted(() => {
  appStore.initialize()
})
</script>
