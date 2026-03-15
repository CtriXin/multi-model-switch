<script setup lang="ts">
import { ref, computed, inject } from 'vue'
import { usePersonaStore, CATEGORY_META, buildPersonaSystemPrompt, type PersonaCategory } from '@/stores/persona'
import { useAppStore, getModelColor } from '@/stores/app'
import { useProviderStore } from '@/stores/provider'
import { streamChat } from '@/services/api'
import { getApiKey } from '@/services/keychain'
import PixelAvatar from '@/components/PixelAvatar.vue'
import MarkdownIt from 'markdown-it'
import {
  Users, Play, RotateCcw, ChevronDown, ChevronUp,
  Loader2, Square,
} from 'lucide-vue-next'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const personaStore = usePersonaStore()
const appStore = useAppStore()
const providerStore = useProviderStore()

const prompt = ref('')
const streaming = ref(false)
const abortController = ref<AbortController | null>(null)
const responses = ref<Map<string, { text: string; done: boolean }>>(new Map())
const showPersonaPanel = ref(true)
const expandedCategories = ref<Set<string>>(new Set(Object.keys(CATEGORY_META)))

const hasActivePersonas = computed(() => personaStore.activePersonaIds.length > 0)
const hasResults = computed(() => responses.value.size > 0)

const categories = computed(() => {
  return Object.entries(CATEGORY_META).map(([key, meta]) => ({
    key: key as PersonaCategory,
    ...meta,
    personas: personaStore.personasByCategory[key] || [],
  }))
})

function toggleCategory(key: string) {
  if (expandedCategories.value.has(key)) {
    expandedCategories.value.delete(key)
  } else {
    expandedCategories.value.add(key)
  }
}

function stanceTag(val: number, neg: string, pos: string): { label: string; color: string } {
  if (val > 0.3) return { label: pos, color: 'text-emerald-400 bg-emerald-500/10' }
  if (val < -0.3) return { label: neg, color: 'text-rose-400 bg-rose-500/10' }
  return { label: '中性', color: 'text-slate-400 bg-slate-500/10' }
}

/** 为每个 persona 分配模型 */
function assignModels(personaIds: string[]): Map<string, string> {
  const assignment = new Map<string, string>()
  const availableModels = appStore.selectedModelIds.length
    ? [...appStore.selectedModelIds]
    : appStore.models.map((m) => m.id)
  if (!availableModels.length) return assignment

  let modelIdx = 0
  for (const pid of personaIds) {
    const persona = personaStore.personas.find((p) => p.id === pid)
    if (!persona) continue
    if (persona.boundModelId && availableModels.includes(persona.boundModelId)) {
      assignment.set(pid, persona.boundModelId)
    } else {
      assignment.set(pid, availableModels[modelIdx % availableModels.length])
      modelIdx++
    }
  }
  return assignment
}

function getModelName(modelId: string): string {
  return appStore.models.find((m) => m.id === modelId)?.name ?? modelId
}

function getProvider(modelId: string): string {
  return appStore.models.find((m) => m.id === modelId)?.provider ?? 'unknown'
}

async function startBroadcast() {
  if (streaming.value || !prompt.value.trim() || !hasActivePersonas.value) return
  streaming.value = true
  responses.value = new Map()
  showPersonaPanel.value = false
  abortController.value = new AbortController()
  const signal = abortController.value.signal
  const assignments = assignModels(personaStore.activePersonaIds)

  const tasks = personaStore.activePersonas.map(async (persona) => {
    const modelId = assignments.get(persona.id)
    if (!modelId) return
    responses.value.set(persona.id, { text: '', done: false })

    const model = appStore.models.find((m) => m.id === modelId)
    let providerConfig = providerStore.providers.find((p) => p.id === model?.provider)
    if (!providerConfig) {
      if (modelId.startsWith('demo/')) providerConfig = providerStore.providers.find((p) => p.type === 'mock')
      if (!providerConfig) providerConfig = providerStore.providers.find((p) => p.type === 'openrouter')
    }
    if (!providerConfig) {
      responses.value.set(persona.id, { text: '> 未找到可用的 API 通道', done: true })
      return
    }
    const apiKey = providerConfig.type === 'mock' ? 'demo' : await getApiKey(providerConfig.id)
    if (!apiKey) {
      responses.value.set(persona.id, { text: '> API Key 未配置', done: true })
      return
    }
    try {
      const systemPrompt = buildPersonaSystemPrompt(persona)
      const stream = streamChat({
        provider: providerConfig, apiKey, model: modelId,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: prompt.value },
        ],
        signal,
      })
      for await (const chunk of stream) {
        if (signal.aborted) return
        const cur = responses.value.get(persona.id)
        if (cur) responses.value.set(persona.id, { text: cur.text + chunk, done: false })
      }
    } catch (e: any) {
      if (e.name === 'AbortError' || signal.aborted) return
      const cur = responses.value.get(persona.id)
      responses.value.set(persona.id, { text: (cur?.text || '') + `\n\n> ${e.message}`, done: true })
    }
    const cur = responses.value.get(persona.id)
    if (cur) responses.value.set(persona.id, { ...cur, done: true })
  })

  await Promise.allSettled(tasks)
  streaming.value = false
  abortController.value = null
}

function stopStreaming() {
  abortController.value?.abort()
  streaming.value = false
}

function resetAll() {
  stopStreaming()
  responses.value = new Map()
  prompt.value = ''
  showPersonaPanel.value = true
}

const modelAssignments = computed(() => assignModels(personaStore.activePersonaIds))
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="flex-1 overflow-y-auto">
      <!-- ============ 选角色 ============ -->
      <div v-if="!hasResults && !streaming" class="max-w-4xl mx-auto px-4 py-6">
        <!-- Hero -->
        <div class="text-center mb-8 animate-fade-in">
          <h2 class="text-xl font-bold text-text-primary mb-1">锦囊团</h2>
          <p class="text-sm text-text-secondary">
            选几位顾问，听听不同立场的真话
          </p>
        </div>

        <!-- 快捷预设 -->
        <div class="flex items-center justify-center gap-2 mb-6 animate-slide-up" style="animation-delay: 50ms">
          <button
            @click="personaStore.activatePreset('tech')"
            class="px-3 py-1.5 rounded-full text-xs font-medium border transition-all"
            :class="personaStore.activePersonaIds.length === 6 && personaStore.activePersonas.every(p => ['feasibility','risk','execution'].includes(p.category))
              ? 'border-amber-400/50 bg-amber-500/10 text-amber-300 shadow-sm shadow-amber-500/10'
              : 'border-border-subtle text-text-secondary hover:border-amber-400/30 hover:text-text-primary'"
          >
            技术决策
          </button>
          <button
            @click="personaStore.activatePreset('business')"
            class="px-3 py-1.5 rounded-full text-xs font-medium border transition-all"
            :class="personaStore.activePersonaIds.length === 6 && personaStore.activePersonas.every(p => ['strategy','business','user'].includes(p.category))
              ? 'border-amber-400/50 bg-amber-500/10 text-amber-300 shadow-sm shadow-amber-500/10'
              : 'border-border-subtle text-text-secondary hover:border-amber-400/30 hover:text-text-primary'"
          >
            商业决策
          </button>
          <button
            @click="personaStore.activatePreset('all')"
            class="px-3 py-1.5 rounded-full text-xs font-medium border transition-all"
            :class="personaStore.activePersonaIds.length === 12
              ? 'border-amber-400/50 bg-amber-500/10 text-amber-300 shadow-sm shadow-amber-500/10'
              : 'border-border-subtle text-text-secondary hover:border-amber-400/30 hover:text-text-primary'"
          >
            全体出动
          </button>
          <button
            v-if="hasActivePersonas"
            @click="personaStore.clearActive()"
            class="px-2 py-1 text-[10px] text-text-tertiary hover:text-text-secondary transition-colors"
          >
            清除
          </button>
        </div>

        <!-- 角色卡片 -->
        <div class="space-y-4 animate-slide-up" style="animation-delay: 100ms">
          <div v-for="cat in categories" :key="cat.key">
            <button
              @click="toggleCategory(cat.key)"
              class="flex items-center gap-2 w-full px-1 py-1 text-left group mb-2"
            >
              <span class="text-base">{{ cat.icon }}</span>
              <span class="text-xs font-semibold text-text-primary">{{ cat.label }}</span>
              <span class="text-[10px] text-text-tertiary hidden sm:inline">{{ cat.desc }}</span>
              <component
                :is="expandedCategories.has(cat.key) ? ChevronUp : ChevronDown"
                :size="12"
                class="ml-auto text-text-tertiary"
              />
            </button>

            <div v-if="expandedCategories.has(cat.key)" class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                v-for="persona in cat.personas"
                :key="persona.id"
                @click="personaStore.togglePersona(persona.id)"
                class="flex items-start gap-3 p-3 rounded-xl border transition-all duration-150 text-left group"
                :class="personaStore.activePersonaIds.includes(persona.id)
                  ? 'border-amber-400/40 bg-amber-500/5 ring-1 ring-amber-400/15'
                  : 'border-border-subtle hover:border-border-strong hover:bg-surface-2'"
              >
                <!-- 像素头像 -->
                <PixelAvatar
                  :grid="persona.avatar.grid"
                  :palette="persona.avatar.palette"
                  :size="40"
                />

                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-0.5">
                    <span class="text-sm font-bold text-text-primary">{{ persona.name }}</span>
                    <span class="text-[10px] text-text-tertiary">{{ persona.title }}</span>
                  </div>
                  <p class="text-[11px] text-text-secondary leading-relaxed line-clamp-2">
                    「{{ persona.coreBelief }}」
                  </p>
                  <div class="flex items-center gap-1 mt-1.5">
                    <span
                      class="text-[9px] px-1.5 py-0.5 rounded-full"
                      :class="stanceTag(persona.stance.cognition, '悲观', '乐观').color"
                    >{{ stanceTag(persona.stance.cognition, '悲观', '乐观').label }}</span>
                    <span
                      class="text-[9px] px-1.5 py-0.5 rounded-full"
                      :class="stanceTag(persona.stance.horizon, '短期', '长期').color"
                    >{{ stanceTag(persona.stance.horizon, '短期', '长期').label }}</span>
                    <span
                      class="text-[9px] px-1.5 py-0.5 rounded-full"
                      :class="stanceTag(persona.stance.interest, '内部', '外部').color"
                    >{{ stanceTag(persona.stance.interest, '内部', '外部').label }}</span>
                  </div>
                </div>
              </button>
            </div>
          </div>
        </div>

        <!-- 已选数量 -->
        <div v-if="hasActivePersonas" class="mt-5 text-center animate-fade-in">
          <p class="text-xs text-text-tertiary">
            已请 <span class="text-amber-400 font-bold">{{ personaStore.activePersonaIds.length }}</span> 位顾问就位
          </p>
        </div>
      </div>

      <!-- ============ 输出结果 ============ -->
      <div v-if="hasResults || streaming" class="max-w-5xl mx-auto px-4 py-4">
        <!-- 话题 -->
        <div class="mb-5 animate-slide-up">
          <div class="flex items-center gap-2 mb-1.5">
            <Users :size="14" class="text-amber-400" />
            <span class="text-xs text-text-tertiary">锦囊团 · 广播</span>
            <span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 font-medium">
              {{ personaStore.activePersonas.length }} 位顾问
            </span>
          </div>
          <p class="text-sm text-text-primary font-medium">{{ prompt }}</p>
        </div>

        <!-- 回答卡片 -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div
            v-for="(persona, idx) in personaStore.activePersonas"
            :key="persona.id"
            class="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden animate-scale-in"
            :style="{ animationDelay: idx * 60 + 'ms' }"
          >
            <!-- 卡片头部 -->
            <div class="flex items-center gap-2.5 px-3 py-2.5 border-b border-border-subtle bg-surface-2/50">
              <PixelAvatar
                :grid="persona.avatar.grid"
                :palette="persona.avatar.palette"
                :size="32"
              />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="text-xs font-bold text-text-primary">{{ persona.name }}</span>
                  <span class="text-[10px] text-text-tertiary">{{ persona.title }}</span>
                </div>
                <span
                  v-if="modelAssignments.get(persona.id)"
                  class="text-[9px] text-text-tertiary flex items-center gap-1 mt-0.5"
                >
                  <span
                    class="w-1.5 h-1.5 rounded-full inline-block"
                    :style="{ backgroundColor: getModelColor(getProvider(modelAssignments.get(persona.id)!)) }"
                  />
                  {{ getModelName(modelAssignments.get(persona.id)!) }}
                </span>
              </div>
              <Loader2
                v-if="responses.get(persona.id) && !responses.get(persona.id)!.done"
                :size="14"
                class="text-amber-400 animate-spin"
              />
            </div>

            <!-- 内容 -->
            <div class="p-3">
              <div
                v-if="responses.get(persona.id)?.text"
                class="md-body text-xs leading-relaxed"
                v-html="md.render(responses.get(persona.id)!.text)"
              />
              <div v-else class="space-y-2 py-2">
                <div class="h-2.5 bg-surface-3 rounded-full animate-pulse w-full" />
                <div class="h-2.5 bg-surface-3 rounded-full animate-pulse w-3/4" />
                <div class="h-2.5 bg-surface-3 rounded-full animate-pulse w-1/2" />
              </div>
              <span
                v-if="responses.get(persona.id) && !responses.get(persona.id)!.done && responses.get(persona.id)!.text"
                class="inline-block w-1.5 h-4 bg-amber-400 ml-0.5 animate-cursor_blink align-text-bottom"
              />
            </div>
          </div>
        </div>

        <!-- 后续操作 -->
        <div v-if="hasResults && !streaming" class="flex items-center justify-center gap-3 mt-6 animate-fade-in">
          <button
            @click="resetAll"
            class="flex items-center gap-1.5 px-4 py-2 rounded-full border border-border-subtle
                   text-xs text-text-secondary hover:text-text-primary hover:border-border-strong transition-all"
          >
            <RotateCcw :size="12" />
            换个问题
          </button>
        </div>
      </div>
    </div>

    <!-- ============ 输入栏 ============ -->
    <div class="shrink-0 border-t border-border-subtle bg-surface-1 px-4 py-3">
      <div class="max-w-4xl mx-auto flex items-center gap-2">
        <input
          v-model="prompt"
          @keydown.enter.prevent="streaming ? stopStreaming() : startBroadcast()"
          :disabled="!hasActivePersonas"
          :placeholder="hasActivePersonas ? '向锦囊团提问...' : '请先选择顾问'"
          class="flex-1 bg-surface-2 border border-border-subtle rounded-full px-4 py-2.5 text-sm
                 text-text-primary placeholder:text-text-tertiary focus:outline-none
                 focus:border-amber-400/40 focus:ring-1 focus:ring-amber-400/20 transition-all"
        />
        <button
          v-if="streaming"
          @click="stopStreaming"
          class="w-10 h-10 rounded-full bg-red-500/20 text-red-400
                 flex items-center justify-center hover:bg-red-500/30 transition-colors"
        >
          <Square :size="14" fill="currentColor" />
        </button>
        <button
          v-else
          @click="startBroadcast"
          :disabled="!hasActivePersonas || !prompt.trim()"
          class="w-10 h-10 rounded-full bg-amber-500 text-white
                 flex items-center justify-center hover:bg-amber-600 transition-colors
                 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <Play :size="14" fill="currentColor" />
        </button>
      </div>
    </div>
  </div>
</template>
