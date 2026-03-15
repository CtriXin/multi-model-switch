<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useAppStore, getModelColor, type ModelMeta } from '@/stores/app'
import { Search, Check, X } from 'lucide-vue-next'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const appStore = useAppStore()
const search = ref('')
const sheetRef = ref<HTMLElement>()
const detent = ref<'half' | 'full'>('half')

// Drag state
const dragging = ref(false)
const dragStartY = ref(0)
const dragCurrentY = ref(0)
const sheetTranslateY = ref(0)
const handleAnimating = ref(false)

const HALF_HEIGHT = 55 // vh
const FULL_HEIGHT = 92 // vh

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return appStore.models
  return appStore.models.filter(m =>
    m.name.toLowerCase().includes(q) ||
    m.category.toLowerCase().includes(q) ||
    m.provider.toLowerCase().includes(q)
  )
})

const selectedCount = computed(() => appStore.selectedModelIds.length)

const presetIcons: Record<string, string> = {
  'preset-coding': '🏆',
  'preset-reasoning': '🧠',
  'preset-fast': '⚡',
  'preset-balanced': '🎯',
  'preset-economy': '💰',
}

function tierLabel(tier: number): string {
  return tier === 2 ? 'premium' : tier === 1 ? 'standard' : 'free'
}

function tierColor(tier: number): string {
  return tier === 2 ? 'text-amber-500 bg-amber-500/10' : tier === 1 ? 'text-accent bg-accent/10' : 'text-emerald-500 bg-emerald-500/10'
}

function modelInitial(model: ModelMeta): string {
  return model.provider.charAt(0).toUpperCase()
}

function isSelected(id: string) {
  return appStore.selectedModelIds.includes(id)
}

function clearAll() {
  appStore.clearSelection()
}

function done() {
  emit('close')
}

// --- Touch drag for two-detent ---
function onTouchStart(e: TouchEvent) {
  dragging.value = true
  dragStartY.value = e.touches[0].clientY
  dragCurrentY.value = e.touches[0].clientY
}

function onTouchMove(e: TouchEvent) {
  if (!dragging.value) return
  dragCurrentY.value = e.touches[0].clientY
  const delta = dragCurrentY.value - dragStartY.value
  // Only allow downward drag from half, or any drag from full
  if (detent.value === 'half' && delta < 0) {
    // dragging up → expand
    sheetTranslateY.value = delta * 0.4 // dampened
  } else if (delta > 0) {
    // dragging down
    sheetTranslateY.value = delta
  }
}

function onTouchEnd() {
  if (!dragging.value) return
  dragging.value = false
  const delta = dragCurrentY.value - dragStartY.value

  if (detent.value === 'half') {
    if (delta < -60) {
      detent.value = 'full'
    } else if (delta > 80) {
      emit('close')
    }
  } else {
    if (delta > 100) {
      detent.value = 'half'
    }
  }
  sheetTranslateY.value = 0
}

// Mouse fallback for desktop testing
function onMouseDown(e: MouseEvent) {
  dragging.value = true
  dragStartY.value = e.clientY
  dragCurrentY.value = e.clientY
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e: MouseEvent) {
  if (!dragging.value) return
  dragCurrentY.value = e.clientY
  const delta = dragCurrentY.value - dragStartY.value
  if (detent.value === 'half' && delta < 0) {
    sheetTranslateY.value = delta * 0.4
  } else if (delta > 0) {
    sheetTranslateY.value = delta
  }
}

function onMouseUp() {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  onTouchEnd()
}

// Reset detent on open
watch(() => props.open, (val) => {
  if (val) {
    detent.value = 'half'
    search.value = ''
    sheetTranslateY.value = 0
    // Start handle morph animation after sheet slides in
    handleAnimating.value = false
    setTimeout(() => { handleAnimating.value = true }, 450)
  }
})

const sheetHeight = computed(() => detent.value === 'full' ? FULL_HEIGHT : HALF_HEIGHT)

const sheetStyle = computed(() => {
  const baseTranslate = sheetTranslateY.value
  return {
    height: `${sheetHeight.value}vh`,
    transform: baseTranslate ? `translateY(${baseTranslate}px)` : undefined,
    transition: dragging.value ? 'none' : 'height 0.4s cubic-bezier(0.32, 0.72, 0, 1), transform 0.4s cubic-bezier(0.32, 0.72, 0, 1)',
  }
})

// Category tag text for models
function modelTags(model: ModelMeta): string[] {
  return model.tags.filter(t => ['reasoning', 'fast', 'coding', 'vision'].includes(t))
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[9997]">
      <!-- Backdrop — fade only -->
      <Transition name="sheet-backdrop">
        <div v-if="open" class="absolute inset-0 bg-black/40" @click="emit('close')" />
      </Transition>

      <!-- Sheet — slide from bottom -->
      <Transition name="sheet-content">
        <div
          v-if="open"
          ref="sheetRef"
          class="absolute bottom-0 left-0 right-0 flex flex-col
                 bg-surface-1 rounded-t-[14px] overflow-hidden"
          :style="sheetStyle"
        >
          <!-- Drag Handle -->
          <div
            class="flex flex-col items-center py-2.5 shrink-0 cursor-grab active:cursor-grabbing"
            @touchstart.passive="onTouchStart"
            @touchmove.passive="onTouchMove"
            @touchend="onTouchEnd"
            @mousedown="onMouseDown"
          >
            <div
              class="w-9 h-[5px] rounded-full bg-text-tertiary/30"
              :class="{ 'handle-breathe': handleAnimating }"
            />
          </div>

          <!-- Header -->
          <div class="flex items-center justify-between px-5 pb-3 shrink-0">
            <div>
              <h2 class="text-lg font-bold text-text-primary">选择模型</h2>
              <p class="text-xs text-text-tertiary mt-0.5">{{ selectedCount }} / 5 已选</p>
            </div>
            <div class="flex items-center gap-3">
              <button
                v-if="selectedCount > 0"
                @click="clearAll"
                class="text-sm text-text-secondary hover:text-text-primary transition-colors"
              >清空</button>
              <button
                @click="done"
                class="text-sm font-semibold text-accent hover:text-accent-hover transition-colors"
              >完成</button>
            </div>
          </div>

          <!-- Presets -->
          <div class="flex gap-2 px-5 pb-3 overflow-x-auto shrink-0 no-scrollbar">
            <button
              v-for="p in appStore.presets"
              :key="p.id"
              @click="appStore.applyPreset(p)"
              class="shrink-0 inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs
                     border border-border-default text-text-primary
                     hover:border-accent/30 active:scale-95 transition-all"
            >
              <span>{{ presetIcons[p.id] || '⚡' }}</span>
              <span>{{ p.name }}</span>
            </button>
          </div>

          <!-- Search -->
          <div class="px-5 pb-3 shrink-0">
            <div class="flex items-center gap-2 px-3 py-2 rounded-xl bg-surface-2 border border-border-default">
              <Search :size="15" class="text-text-tertiary shrink-0" />
              <input
                v-model="search"
                placeholder="搜索模型..."
                class="flex-1 bg-transparent text-sm text-text-primary placeholder-text-tertiary outline-none"
              />
            </div>
          </div>

          <!-- Model Grid -->
          <div class="flex-1 overflow-y-auto px-5 pb-6">
            <div class="grid grid-cols-2 gap-2.5">
              <button
                v-for="model in filtered"
                :key="model.id"
                @click="appStore.toggleModel(model.id)"
                class="relative flex flex-col items-start p-3 rounded-xl border text-left
                       active:scale-[0.97] transition-all duration-150"
                :class="isSelected(model.id)
                  ? 'border-accent/40 bg-accent/5'
                  : 'border-border-default bg-surface-2 hover:border-border-strong'"
              >
                <!-- Checkmark -->
                <div
                  class="absolute top-2.5 right-2.5 w-5 h-5 rounded-full flex items-center justify-center transition-all"
                  :class="isSelected(model.id)
                    ? 'bg-accent text-white'
                    : 'border border-border-strong'"
                >
                  <Check v-if="isSelected(model.id)" :size="12" :stroke-width="3" />
                </div>

                <!-- Avatar -->
                <div
                  class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold text-white mb-2"
                  :style="{ backgroundColor: getModelColor(model.provider) }"
                >
                  {{ modelInitial(model) }}
                </div>

                <!-- Name -->
                <span class="text-sm font-medium text-text-primary leading-tight pr-6">{{ model.name }}</span>
                <span class="text-[11px] text-text-tertiary mt-0.5">{{ model.provider }}</span>

                <!-- Tags -->
                <div class="flex flex-wrap gap-1 mt-2">
                  <span
                    class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                    :class="tierColor(model.tier)"
                  >{{ tierLabel(model.tier) }}</span>
                  <span
                    v-for="tag in modelTags(model)"
                    :key="tag"
                    class="px-1.5 py-0.5 rounded text-[10px] text-text-tertiary bg-surface-3"
                  >{{ tag }}</span>
                </div>
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </Teleport>
</template>

<style scoped>
/* Backdrop: simple opacity fade */
.sheet-backdrop-enter-active,
.sheet-backdrop-leave-active { transition: opacity 0.3s ease; }
.sheet-backdrop-enter-from,
.sheet-backdrop-leave-to { opacity: 0; }

/* Content: slide from bottom */
.sheet-content-enter-active { animation: sheetIn 0.4s cubic-bezier(0.32, 0.72, 0, 1); }
.sheet-content-leave-active { animation: sheetOut 0.3s cubic-bezier(0.32, 0.72, 0, 1) forwards; }

@keyframes sheetIn {
  from { transform: translateY(100%); }
  to   { transform: translateY(0); }
}
@keyframes sheetOut {
  from { transform: translateY(0); opacity: 1; }
  to   { transform: translateY(100%); opacity: 0; }
}

/*
  Apple-style handle hint: gentle float upward 3 times then settle.
  - Small vertical translation (3px) — barely noticeable but enough to draw attention
  - Slight width squeeze at peak — like the bar is being "pinched" upward
  - Slow, ease-in-out timing — feels organic, not mechanical
*/
.handle-breathe {
  animation: handleFloat 1.2s ease-in-out 3;
}

@keyframes handleFloat {
  0%   { transform: translateY(0) scaleX(1);    opacity: 0.3; }
  40%  { transform: translateY(-3px) scaleX(0.85); opacity: 0.6; }
  70%  { transform: translateY(-3px) scaleX(0.85); opacity: 0.6; }
  100% { transform: translateY(0) scaleX(1);    opacity: 0.3; }
}

.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
