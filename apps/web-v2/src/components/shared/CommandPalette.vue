<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore, getModelColor } from '@/stores/app'
import { Search, MessageSquare, GitMerge, Zap, Palette, Sparkles, Cpu, Check, Bot } from 'lucide-vue-next'

const router = useRouter()
const appStore = useAppStore()
const open = ref(false)
const query = ref('')
const selectedIndex = ref(0)

interface Command {
  id: string
  label: string
  desc: string
  icon: any
  action: () => void
}

const commands: Command[] = [
  { id: 'chat', label: '前往对话', desc: '多模型并行对话', icon: MessageSquare, action: () => router.push('/chat') },
  { id: 'discuss', label: '前往辩论', desc: '三阶段深度辩论', icon: GitMerge, action: () => router.push('/discuss') },
]

const filteredModels = computed(() => {
  if (!query.value.trim()) return []
  const q = query.value.toLowerCase()
  return appStore.models.filter(m => 
    m.name.toLowerCase().includes(q) || 
    m.provider.toLowerCase().includes(q) || 
    m.id.toLowerCase().includes(q)
  ).slice(0, 8)
})

const filteredCommands = computed(() => {
  const q = query.value.toLowerCase()
  return q
    ? commands.filter(c => c.label.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q))
    : commands
})

const totalResultsCount = computed(() => filteredCommands.value.length + filteredModels.value.length)

function handleKeydown(e: KeyboardEvent) {
  const count = totalResultsCount.value
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectedIndex.value = (selectedIndex.value + 1) % count
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectedIndex.value = (selectedIndex.value - 1 + count) % count
  } else if (e.key === 'Enter') {
    e.preventDefault()
    executeCurrent()
  } else if (e.key === 'Escape') {
    close()
  }
}

function executeCurrent() {
  if (selectedIndex.value < filteredCommands.value.length) {
    const cmd = filteredCommands.value[selectedIndex.value]
    if (cmd) { cmd.action(); close() }
  } else {
    const modelIdx = selectedIndex.value - filteredCommands.value.length
    const model = filteredModels.value[modelIdx]
    if (model) {
      appStore.toggleModel(model.id)
      close()
    }
  }
}

function close() {
  open.value = false
  query.value = ''
  selectedIndex.value = 0
}

function onGlobalKey(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    open.value = !open.value
    if (!open.value) close()
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKey))
onUnmounted(() => window.removeEventListener('keydown', onGlobalKey))
</script>

<template>
  <Teleport to="body">
    <Transition name="page">
      <div v-if="open" class="fixed inset-0 z-[9998] flex items-start justify-center pt-[15vh] px-4" @click.self="close">
        <div class="absolute inset-0 bg-black/60 backdrop-blur-md" @click="close" />

        <div class="relative w-full max-w-xl glass-v3 rounded-[32px] border border-white/10 shadow-[0_40px_100px_rgba(0,0,0,0.5)] overflow-hidden animate-scale-in flex flex-col">
          <!-- Search Header -->
          <div class="flex items-center gap-4 px-6 py-5 border-b border-white/5 bg-white/2">
            <Search :size="20" class="text-text-tertiary shrink-0" stroke-width="3" />
            <input
              v-model="query"
              @keydown="handleKeydown"
              placeholder="搜索模型基因、功能命令..."
              class="flex-1 bg-transparent text-lg font-bold text-text-primary placeholder:text-text-tertiary/30 outline-none"
              autofocus
            />
            <div class="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-black/20 border border-white/5">
              <span class="text-[9px] font-black uppercase text-text-tertiary">esc</span>
            </div>
          </div>

          <!-- Content Area -->
          <div class="max-h-[60vh] overflow-y-auto p-4 space-y-6 custom-scrollbar">
            <!-- Commands Section -->
            <div v-if="filteredCommands.length" class="space-y-2">
              <div class="px-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-tertiary opacity-40">System Actions</div>
              <div class="space-y-1">
                <button
                  v-for="(cmd, i) in filteredCommands"
                  :key="cmd.id"
                  @click="cmd.action(); close()"
                  @mouseenter="selectedIndex = i"
                  class="w-full flex items-center gap-4 px-4 py-3.5 rounded-2xl transition-all duration-300 group"
                  :class="i === selectedIndex ? 'bg-text-primary text-surface-1 shadow-lg' : 'text-text-secondary hover:bg-white/5'"
                >
                  <component :is="cmd.icon" :size="18" stroke-width="3" :class="i === selectedIndex ? 'text-surface-1' : 'text-accent'" />
                  <div class="text-left flex-1 min-w-0">
                    <div class="text-sm font-black uppercase tracking-tight">{{ cmd.label }}</div>
                    <div class="text-[10px] opacity-60 font-medium truncate mt-0.5">{{ cmd.desc }}</div>
                  </div>
                  <Check v-if="i === selectedIndex" :size="14" stroke-width="4" />
                </button>
              </div>
            </div>

            <!-- Models Section (V3 Grid Refactor) -->
            <div v-if="filteredModels.length" class="space-y-3">
              <div class="px-3 text-[10px] font-black uppercase tracking-[0.2em] text-text-tertiary opacity-40">Model Registry Matching</div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                <button
                  v-for="(model, i) in filteredModels"
                  :key="model.id"
                  @click="appStore.toggleModel(model.id); close()"
                  @mouseenter="selectedIndex = i + filteredCommands.length"
                  class="flex flex-col items-start p-4 rounded-[24px] border transition-all duration-300 relative group"
                  :class="selectedIndex === (i + filteredCommands.length)
                    ? 'border-accent/50 bg-accent/5 shadow-inner'
                    : 'border-white/5 bg-white/5 hover:border-white/20'"
                >
                  <div class="flex items-center justify-between w-full mb-3">
                    <div class="w-8 h-8 rounded-xl flex items-center justify-center text-xs font-black text-white shadow-lg" :style="{ backgroundColor: getModelColor(model.provider) }">
                      {{ model.provider.slice(0, 1).toUpperCase() }}
                    </div>
                    <div class="w-5 h-5 rounded-full flex items-center justify-center border border-white/10"
                         :class="appStore.selectedModelIds.includes(model.id) ? 'bg-accent border-accent text-white' : ''">
                      <Check v-if="appStore.selectedModelIds.includes(model.id)" :size="12" stroke-width="4" />
                    </div>
                  </div>
                  <div class="text-[11px] font-black text-text-primary uppercase tracking-tight truncate w-full">{{ model.name }}</div>
                  <div class="text-[9px] font-bold text-text-tertiary uppercase tracking-widest mt-1 opacity-60">{{ model.provider }}</div>
                </button>
              </div>
            </div>

            <!-- Empty State -->
            <div v-if="!totalResultsCount" class="py-12 flex flex-col items-center justify-center text-center">
              <div class="p-4 bg-white/5 rounded-full mb-4 opacity-20"><Bot :size="40" stroke-width="1" /></div>
              <p class="text-sm font-black text-text-tertiary uppercase tracking-[0.2em]">没有发现匹配的指令或基因</p>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
