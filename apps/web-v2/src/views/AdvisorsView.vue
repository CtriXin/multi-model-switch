<script setup lang="ts">
import { ref, computed, inject } from 'vue'
import { usePersonaStore, CATEGORY_META, buildPersonaSystemPrompt, type PersonaCategory, type PersonaDefinition } from '@/stores/persona'
import { useAppStore, getModelColor } from '@/stores/app'
import { useProviderStore } from '@/stores/provider'
import { streamChat } from '@/services/api'
import { getApiKey } from '@/services/keychain'
import MarkdownIt from 'markdown-it'
import {
  Users, Play, RotateCcw, ChevronDown, ChevronUp,
  Loader2, Zap, Swords, Crown,
} from 'lucide-vue-next'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const personaStore = usePersonaStore()
const appStore = useAppStore()
const providerStore = useProviderStore()
const platform = inject<import('vue').Ref<string>>('platform')

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

function stanceLabel(val: number, negative: string, positive: string): string {
  if (val > 0.3) return positive
  if (val < -0.3) return negative
  return '中性'
}

/** 为每个 persona 分配模型：绑定的优先，否则轮转可用模型 */
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
      if (modelId.startsWith('demo/')) {
        providerConfig = providerStore.providers.find((p) => p.type === 'mock')
      }
      if (!providerConfig) {
        providerConfig = providerStore.providers.find((p) => p.type === 'openrouter')
      }
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
        provider: providerConfig,
        apiKey,
        model: modelId,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: prompt.value },
        ],
        signal,
      })

      for await (const chunk of stream) {
        if (signal.aborted) return
        const current = responses.value.get(persona.id)
        if (current) {
          responses.value.set(persona.id, { text: current.text + chunk, done: false })
        }
      }
    } catch (e: any) {
      if (e.name === 'AbortError' || signal.aborted) return
      const current = responses.value.get(persona.id)
      responses.value.set(persona.id, {
        text: (current?.text || '') + `\n\n> 错误: ${e.message}`,
        done: true,
      })
    }

    const current = responses.value.get(persona.id)
    if (current) {
      responses.value.set(persona.id, { ...current, done: true })
    }
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
      <!-- Empty state -->
      <div
        v-if="!hasResults && !streaming"
        class="max-w-4xl mx-auto px-4 py-6"
      >
        <!-- Hero -->
        <div class="text-center mb-6 animate-fade-in">
          <div class="w-16 h-16 rounded-2xl bg-amber-500/10 flex items-center justify-center mx-auto mb-4">
            <Users :size="28" class="text-amber-400" />
          </div>
          <h2 class="text-lg font-semibold text-text-primary mb-1">锦囊团</h2>
          <p class="text-sm text-text-secondary max-w-md mx-auto">
            立场不同的 AI 角色，从多维度真实地思考你的问题
          </p>
        </div>

        <!-- Quick presets -->
        <div class="flex items-center justify-center gap-2 mb-6 animate-slide-up" style="animation-delay: 50ms">
          <button
            @click="personaStore.activatePreset('tech')"
            class="px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors"
            :class="personaStore.activePersonaIds.length === 6 && personaStore.activePersonas.every(p => ['feasibility','risk','execution'].includes(p.category))
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-400'
              : 'border-border-subtle text-text-secondary hover:border-border-strong'"
          >
            🛠️ 技术决策组合
          </button>
          <button
            @click="personaStore.activatePreset('business')"
            class="px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors"
            :class="personaStore.activePersonaIds.length === 6 && personaStore.activePersonas.every(p => ['strategy','business','user'].includes(p.category))
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-400'
              : 'border-border-subtle text-text-secondary hover:border-border-strong'"
          >
            📈 商业决策组合
          </button>
          <button
            @click="personaStore.activatePreset('all')"
            class="px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors"
            :class="personaStore.activePersonaIds.length === 12
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-400'
              : 'border-border-subtle text-text-secondary hover:border-border-strong'"
          >
            👥 全体出动
          </button>
          <button
            v-if="hasActivePersonas"
            @click="personaStore.clearActive()"
            class="px-3 py-1.5 rounded-lg text-xs text-text-tertiary hover:text-text-secondary transition-colors"
          >
            清除
          </button>
        </div>

        <!-- Persona grid -->
        <div v-if="showPersonaPanel" class="space-y-3 animate-slide-up" style="animation-delay: 100ms">
          <div v-for="cat in categories" :key="cat.key">
            <!-- Category header -->
            <button
              @click="toggleCategory(cat.key)"
              class="flex items-center gap-2 w-full px-2 py-1.5 text-left group"
            >
              <span class="text-sm">{{ cat.icon }}</span>
              <span class="text-xs font-medium text-text-primary">{{ cat.label }}</span>
              <span class="text-[10px] text-text-tertiary">{{ cat.desc }}</span>
              <component
                :is="expandedCategories.has(cat.key) ? ChevronUp : ChevronDown"
                :size="12"
                class="ml-auto text-text-tertiary group-hover:text-text-secondary transition-colors"
              />
            </button>

            <!-- Persona cards -->
            <div v-if="expandedCategories.has(cat.key)" class="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1 ml-6">
              <button
                v-for="persona in cat.personas"
                :key="persona.id"
                @click="personaStore.togglePersona(persona.id)"
                class="text-left p-3 rounded-lg border transition-all duration-150"
                :class="personaStore.activePersonaIds.includes(persona.id)
                  ? 'border-amber-500/40 bg-amber-500/5 ring-1 ring-amber-500/20'
                  : 'border-border-subtle hover:border-border-strong'"
              >
                <div class="flex items-center gap-2 mb-1.5">
                  <span class="text-sm font-semibold text-text-primary">{{ persona.name }}</span>
                  <span class="text-[10px] text-text-tertiary">· {{ persona.title }}</span>
                </div>
                <p class="text-[11px] text-text-secondary leading-relaxed mb-2">{{ persona.coreBelief }}</p>
                <div class="flex items-center gap-1.5 flex-wrap">
                  <span class="text-[9px] px-1.5 py-0.5 rounded bg-surface-3 text-text-tertiary">
                    {{ stanceLabel(persona.stance.cognition, '悲观', '乐观') }}
                  </span>
                  <span class="text-[9px] px-1.5 py-0.5 rounded bg-surface-3 text-text-tertiary">
                    {{ stanceLabel(persona.stance.horizon, '短期', '长期') }}
                  </span>
                  <span class="text-[9px] px-1.5 py-0.5 rounded bg-surface-3 text-text-tertiary">
                    {{ stanceLabel(persona.stance.interest, '内部', '外部') }}
                  </span>
                </div>
              </button>
            </div>
          </div>
        </div>

        <!-- Active count + model assignment preview -->
        <div v-if="hasActivePersonas" class="mt-4 px-2 animate-fade-in">
          <div class="flex items-center gap-2 text-xs text-text-tertiary">
            <span>已选 {{ personaStore.activePersonaIds.length }} 位角色</span>
            <span>·</span>
            <span>{{ appStore.selectedModelIds.length || appStore.models.length }} 个模型可用</span>
          </div>
        </div>
      </div>

      <!-- Results: broadcast output -->
      <div v-if="hasResults || streaming" class="max-w-5xl mx-auto px-4 py-4">
        <!-- Topic -->
        <div class="mb-4 animate-slide-up">
          <div class="flex items-center gap-2 mb-1">
            <Users :size="14" class="text-amber-400" />
            <span class="text-xs text-text-tertiary uppercase tracking-wider">锦囊团 · 广播模式</span>
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400">
              {{ personaStore.activePersonas.length }} 位角色
            </span>
          </div>
          <p class="text-sm text-text-primary">{{ prompt }}</p>
        </div>

        <!-- Response grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div
            v-for="persona in personaStore.activePersonas"
            :key="persona.id"
            class="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden animate-scale-in"
          >
            <!-- Card header -->
            <div class="flex items-center gap-2 px-3 py-2.5 bg-surface-2 border-b border-border-subtle">
              <span class="text-sm">{{ CATEGORY_META[persona.category].icon }}</span>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="text-xs font-semibold text-text-primary">{{ persona.name }}</span>
                  <span class="text-[10px] text-text-tertiary">· {{ persona.title }}</span>
                </div>
                <div class="flex items-center gap-1 mt-0.5">
                  <span
                    v-if="modelAssignments.get(persona.id)"
                    class="text-[9px] text-text-tertiary flex items-center gap-1"
                  >
                    <span
                      class="w-1.5 h-1.5 rounded-full"
                      :style="{ backgroundColor: getModelColor(getProvider(modelAssignments.get(persona.id)!)) }"
                    />
                    {{ getModelName(modelAssignments.get(persona.id)!) }}
                  </span>
                </div>
              </div>
              <Loader2
                v-if="responses.get(persona.id) && !responses.get(persona.id)!.done"
                :size="12"
                class="text-amber-400 animate-spin"
              />
            </div>

            <!-- Content -->
            <div class="p-3">
              <div
                v-if="responses.get(persona.id)?.text"
                class="md-body text-xs"
                v-html="md.render(responses.get(persona.id)!.text)"
              />
              <div v-else class="space-y-2">
                <div class="h-3 bg-surface-3 rounded animate-pulse w-full" />
                <div class="h-3 bg-surface-3 rounded animate-pulse w-3/4" />
                <div class="h-3 bg-surface-3 rounded animate-pulse w-1/2" />
              </div>
              <span
                v-if="responses.get(persona.id) && !responses.get(persona.id)!.done && responses.get(persona.id)!.text"
                class="inline-block w-1.5 h-4 bg-amber-400 ml-0.5 animate-cursor_blink align-text-bottom"
              />
            </div>
          </div>
        </div>

        <!-- Post-broadcast actions -->
        <div
          v-if="hasResults && !streaming"
          class="flex items-center gap-2 mt-4 animate-fade-in"
        >
          <button
            @click="resetAll"
            class="btn-ghost flex items-center gap-1.5 text-xs"
          >
            <RotateCcw :size="13" />
            新问题
          </button>
        </div>
      </div>
    </div>

    <!-- Input bar -->
    <div class="shrink-0 border-t border-border-subtle bg-surface-1 px-4 py-3">
      <div class="max-w-4xl mx-auto flex items-center gap-2">
        <input
          v-model="prompt"
          @keydown.enter.prevent="streaming ? stopStreaming() : startBroadcast()"
          :disabled="!hasActivePersonas"
          :placeholder="hasActivePersonas ? '向锦囊团提问...' : '请先选择角色...'"
          class="flex-1 bg-surface-2 border border-border-subtle rounded-lg px-3 py-2 text-sm
                 text-text-primary placeholder:text-text-tertiary focus:outline-none
                 focus:border-accent/50 transition-colors"
        />
        <button
          v-if="streaming"
          @click="stopStreaming"
          class="px-4 py-2 rounded-lg bg-red-500/20 text-red-400 text-sm font-medium
                 hover:bg-red-500/30 transition-colors"
        >
          停止
        </button>
        <button
          v-else
          @click="startBroadcast"
          :disabled="!hasActivePersonas || !prompt.trim()"
          class="px-4 py-2 rounded-lg bg-amber-500 text-white text-sm font-medium
                 hover:bg-amber-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Play :size="14" />
        </button>
      </div>
    </div>
  </div>
</template>
