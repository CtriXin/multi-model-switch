<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="open" class="fixed inset-0 z-50">
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-black/30 backdrop-blur-sm transition-opacity"
          :style="{ opacity: backdropOpacity }"
          @click="dismiss"
        />

        <!-- Bottom Sheet -->
        <div
          ref="sheetRef"
          class="absolute left-0 right-0 bottom-0 bg-white rounded-t-2xl shadow-float flex flex-col overflow-hidden will-change-transform"
          :style="sheetStyle"
          @touchstart.passive="onDragStart"
          @touchmove.passive="onDragMove"
          @touchend="onDragEnd"
          @mousedown="onMouseDragStart"
        >
          <!-- Drag Handle -->
          <div class="flex justify-center pt-2.5 pb-1 cursor-grab active:cursor-grabbing" data-handle>
            <div class="w-9 h-1 rounded-full bg-gray-300" />
          </div>

          <!-- Header -->
          <div class="flex items-center justify-between px-5 pb-2">
            <div>
              <h2 class="text-base font-semibold text-gray-900">选择模型</h2>
              <p class="text-[11px] text-gray-400 mt-0.5">{{ selectedCount }} / 5 已选</p>
            </div>
            <div class="flex items-center gap-2">
              <button
                v-if="selectedCount > 0"
                @click="appStore.clearSelection(mode)"
                class="px-2.5 py-1 text-[11px] text-gray-500 hover:bg-gray-100 rounded-lg transition-colors"
              >清空</button>
              <button
                @click="dismiss"
                class="px-3 py-1 text-[11px] font-semibold text-accent-600 hover:bg-accent-50 rounded-lg transition-colors"
              >完成</button>
            </div>
          </div>

          <!-- Presets (horizontal scroll) -->
          <div class="px-5 py-2 border-t border-gray-100">
            <div class="flex items-center gap-2 overflow-x-auto no-scrollbar">
              <button
                v-for="preset in appStore.presets"
                :key="preset.id"
                @click="appStore.applyPreset(mode, preset.id)"
                class="px-3 py-1.5 text-xs font-medium whitespace-nowrap rounded-full border transition-colors"
                :class="isPresetActive(preset.id)
                  ? 'border-accent-400 bg-accent-50 text-accent-700'
                  : 'border-gray-200 text-gray-600 hover:border-gray-300'"
              >
                {{ preset.icon }} {{ preset.name }}
              </button>
            </div>
          </div>

          <!-- Search -->
          <div class="px-5 py-2">
            <div class="relative">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input
                v-model="search"
                type="text"
                placeholder="搜索模型..."
                class="w-full pl-9 pr-3 py-2 text-sm bg-gray-50 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-accent-100 focus:border-accent-400 transition-all"
              />
            </div>
          </div>

          <!-- Model Grid (scrollable) -->
          <div ref="scrollRef" class="flex-1 overflow-y-auto overscroll-contain px-5 pb-safe">
            <div class="grid grid-cols-2 gap-2 pb-4">
              <button
                v-for="model in flatModels"
                :key="model.id"
                @click="toggle(model.id)"
                class="relative flex items-start gap-2.5 p-3 rounded-xl text-left transition-all duration-150"
                :class="isSelected(model.id)
                  ? 'bg-accent-50 ring-2 ring-accent-400/40'
                  : 'bg-gray-50 hover:bg-gray-100 active:scale-[0.97]'"
              >
                <!-- Model Icon -->
                <div
                  class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 shadow-sm"
                  :style="{ background: getProviderColor(model.provider) }"
                >{{ model.name.charAt(0) }}</div>

                <!-- Info -->
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium text-gray-900 truncate leading-tight">{{ model.name }}</div>
                  <div class="text-[11px] text-gray-400 mt-0.5">{{ model.provider }}</div>
                  <div class="flex items-center gap-1 mt-1.5 flex-wrap">
                    <span
                      class="text-[10px] px-1.5 py-0.5 rounded font-medium"
                      :class="tierBadgeClass(model.tier)"
                    >{{ tierName(model.tier) }}</span>
                    <span
                      v-for="tag in model.tags.slice(0, 1)"
                      :key="tag"
                      class="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded"
                    >{{ tag }}</span>
                  </div>
                </div>

                <!-- Selected Check -->
                <div
                  v-if="isSelected(model.id)"
                  class="absolute top-2 right-2 w-5 h-5 rounded-full bg-accent-500 flex items-center justify-center"
                >
                  <Check class="w-3 h-3 text-white" />
                </div>
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Search, Check } from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'
import type { ModelMeta, ModelTier } from '@mms/contracts'

const props = defineProps<{
  open: boolean
  mode: 'chat' | 'discuss'
}>()

const emit = defineEmits<{ 'update:open': [val: boolean] }>()

const appStore = useAppStore()
const search = ref('')
const sheetRef = ref<HTMLElement>()
const scrollRef = ref<HTMLElement>()

// Snap points as % of viewport height
const SNAP_COLLAPSED = 0.45
const SNAP_EXPANDED = 0.88
const SNAP_DISMISS = 0.2

// Drag state
const currentHeight = ref(SNAP_COLLAPSED)
const isDragging = ref(false)
const dragStartY = ref(0)
const dragStartHeight = ref(0)
const isAnimating = ref(false)

const selected = computed(() =>
  props.mode === 'chat' ? appStore.chatSelectedModels : appStore.discussSelectedModels
)
const selectedCount = computed(() => selected.value.length)

const sheetStyle = computed(() => {
  const h = Math.max(0.15, Math.min(0.95, currentHeight.value))
  return {
    height: `${h * 100}vh`,
    transition: isDragging.value ? 'none' : 'height 0.35s cubic-bezier(0.32, 0.72, 0, 1)',
  }
})

const backdropOpacity = computed(() => {
  const ratio = (currentHeight.value - SNAP_DISMISS) / (SNAP_EXPANDED - SNAP_DISMISS)
  return Math.max(0, Math.min(1, ratio))
})

// Reset height when opened
watch(() => props.open, (val) => {
  if (val) {
    currentHeight.value = SNAP_COLLAPSED
    search.value = ''
  }
})

// Touch drag
function onDragStart(e: TouchEvent) {
  const target = e.target as HTMLElement
  // Only drag from handle or header area, not from scroll content
  if (scrollRef.value?.contains(target) && scrollRef.value.scrollTop > 0) return
  isDragging.value = true
  dragStartY.value = e.touches[0].clientY
  dragStartHeight.value = currentHeight.value
}

function onDragMove(e: TouchEvent) {
  if (!isDragging.value) return
  const deltaY = dragStartY.value - e.touches[0].clientY
  const deltaRatio = deltaY / window.innerHeight
  currentHeight.value = Math.max(0.15, Math.min(0.95, dragStartHeight.value + deltaRatio))
}

function onDragEnd() {
  if (!isDragging.value) return
  isDragging.value = false
  snapToNearest()
}

// Mouse drag (for desktop)
function onMouseDragStart(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('[data-handle]')) return
  isDragging.value = true
  dragStartY.value = e.clientY
  dragStartHeight.value = currentHeight.value

  const onMove = (ev: MouseEvent) => {
    const deltaY = dragStartY.value - ev.clientY
    const deltaRatio = deltaY / window.innerHeight
    currentHeight.value = Math.max(0.15, Math.min(0.95, dragStartHeight.value + deltaRatio))
  }
  const onUp = () => {
    isDragging.value = false
    snapToNearest()
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function snapToNearest() {
  const h = currentHeight.value
  if (h < SNAP_DISMISS + 0.05) {
    dismiss()
  } else if (h < (SNAP_COLLAPSED + SNAP_EXPANDED) / 2) {
    currentHeight.value = SNAP_COLLAPSED
  } else {
    currentHeight.value = SNAP_EXPANDED
  }
}

function dismiss() {
  currentHeight.value = 0.15
  setTimeout(() => emit('update:open', false), 300)
}

function isSelected(id: string): boolean {
  return selected.value.includes(id)
}

function toggle(id: string) {
  appStore.toggleModel(props.mode, id)
}

function isPresetActive(presetId: string): boolean {
  const preset = appStore.presets.find(p => p.id === presetId)
  if (!preset) return false
  return preset.models.length === selected.value.length &&
    preset.models.every(m => selected.value.includes(m))
}

const flatModels = computed(() => {
  const q = search.value.toLowerCase()
  return appStore.models.filter(m => {
    if (!q) return true
    return m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)
  })
})

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: '#D97706',
  openai: '#10B981',
  google: '#3B82F6',
  deepseek: '#EF4444',
  moonshot: '#8B5CF6',
  gateway: '#6B7280',
}

function getProviderColor(provider: string): string {
  return PROVIDER_COLORS[provider] || '#6B7280'
}

function tierBadgeClass(tier: ModelTier): string {
  return tier === 2 ? 'bg-amber-100 text-amber-700'
    : tier === 1 ? 'bg-blue-100 text-blue-700'
    : 'bg-emerald-100 text-emerald-700'
}

function tierName(tier: ModelTier): string {
  return tier === 2 ? 'premium' : tier === 1 ? 'standard' : 'free'
}
</script>

<style scoped>
.sheet-enter-active { transition: all 0.35s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-leave-active { transition: all 0.25s ease-in; }
.sheet-enter-from .absolute.left-0 { transform: translateY(100%); }
.sheet-leave-to .absolute.left-0 { transform: translateY(100%); }
.sheet-enter-from .absolute.inset-0 { opacity: 0; }
.sheet-leave-to .absolute.inset-0 { opacity: 0; }

.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

.pb-safe { padding-bottom: calc(1rem + env(safe-area-inset-bottom, 0px)); }
</style>
