<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { getModelColor, useAppStore } from '@/stores/app'
import { useProviderStore } from '@/stores/provider'
import { streamChat } from '@/services/api'
import { getApiKey } from '@/services/keychain'
import { ChevronDown, ChevronUp, Sparkles, MessageSquare, Check, Maximize2, AlertTriangle } from 'lucide-vue-next'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const props = defineProps<{
  prompt: string
  responses: Map<string, { content: string; model?: string }>
  showDiscuss?: boolean
  selectedModelId?: string | null
}>()

const emit = defineEmits<{
  discuss: []
  activate: []
  select: [modelId: string]
}>()

const appStore = useAppStore()
const providerStore = useProviderStore()
const showRaw = ref(false)
const summaryText = ref('')
const streaming = ref(false)
const done = ref(false)
const judgeModel = ref('')
const showDetails = ref(false)
const error = ref('')

// Track which raw response cards are expanded
const expandedCards = reactive<Record<string, boolean>>({})

const summaryHtml = computed(() => md.render(summaryText.value || ''))

function getModelName(id: string): string {
  return appStore.models.find(m => m.id === id)?.name ?? id
}

function getProvider(id: string): string {
  return appStore.models.find(m => m.id === id)?.provider ?? 'unknown'
}

function toggleExpand(modelId: string) {
  expandedCards[modelId] = !expandedCards[modelId]
}

/** Pick evaluator: prefer a model NOT in the response set, highest tier first */
function pickEvaluator(): { modelId: string; isSelfEval: boolean } {
  const respondingIds = new Set(props.responses.keys())
  // Non-participating models, sorted by tier desc
  const candidates = appStore.models
    .filter(m => !respondingIds.has(m.id))
    .sort((a, b) => b.tier - a.tier)

  if (candidates.length) {
    return { modelId: candidates[0].id, isSelfEval: false }
  }
  // Fallback: use responding model with highest tier
  const responding = Array.from(respondingIds)
    .map(id => appStore.models.find(m => m.id === id))
    .filter(Boolean)
    .sort((a, b) => b!.tier - a!.tier)

  return {
    modelId: responding[0]?.id ?? Array.from(respondingIds)[0],
    isSelfEval: true,
  }
}

function buildJudgePrompt(isSelfEval: boolean): string {
  const responseEntries = Array.from(props.responses.entries())
    .map(([id, msg], i) => `[回答 ${String.fromCharCode(65 + i)}]\n${msg.content}`)
    .join('\n\n---\n\n')

  const singleModelClause = isSelfEval
    ? '\n\n注意：你只有一个信息来源（单模型自评）。在 uncertainty 中默认从「中等」起评，除非有充分证据支持更高确信度。'
    : ''

  return `你是一个 Risk-Aware Decision Judge。你的职责不是中立总结，而是从多个回答中提取可行动的决策建议。

用户的原始问题：
${props.prompt}

以下是匿名的多个模型回答（不要猜测来源）：

${responseEntries}

请按以下 Markdown 格式输出你的评估：

## 决策评估

### 各回答评分
对每个回答给出 1-5 分评分和一句话评语（评分仅供参考，不是唯一标准）：
- 回答 A: X/5 — 评语
- 回答 B: X/5 — 评语
...

### 共识
各回答达成一致的部分。

### 分歧
有争议的部分及各方立场。

### 风险与盲点
回答中被忽略或低估的风险。

### 建议行动
- **现在可以安全做的**：...
- **需要进一步验证的**：...
- **条件失效时**：说明什么情况下以上建议不再适用

### 不确定性
对本次评估的整体信心：高 / 中 / 低，并说明原因。${singleModelClause}`
}

async function generateSummary() {
  if (streaming.value || done.value) return
  emit('activate')
  streaming.value = true
  summaryText.value = ''
  error.value = ''

  const { modelId, isSelfEval } = pickEvaluator()
  const model = appStore.models.find(m => m.id === modelId)
  judgeModel.value = (model?.name ?? modelId) + (isSelfEval ? ' (自评)' : '')

  // Find provider for this model
  let providerConfig = providerStore.providers.find(p => p.id === model?.provider)
  if (!providerConfig) {
    if (modelId.startsWith('demo/')) {
      providerConfig = providerStore.providers.find(p => p.type === 'mock')
    }
    if (!providerConfig) {
      providerConfig = providerStore.providers.find(p => p.type === 'openrouter')
    }
  }

  if (!providerConfig) {
    error.value = '未找到可用的评估模型通道'
    streaming.value = false
    return
  }

  const apiKey = providerConfig.type === 'mock' ? 'demo' : await getApiKey(providerConfig.id)
  if (!apiKey) {
    error.value = '评估模型的 API Key 未配置'
    streaming.value = false
    return
  }

  try {
    const prompt = buildJudgePrompt(isSelfEval)
    const stream = streamChat({
      provider: providerConfig,
      apiKey,
      model: modelId,
      messages: [{ role: 'user', content: prompt }],
    })

    for await (const chunk of stream) {
      summaryText.value += chunk
    }
  } catch (e: any) {
    error.value = e.message
    if (!summaryText.value) {
      summaryText.value = `> 评估失败: ${e.message}`
    }
  }

  streaming.value = false
  done.value = true
}
</script>

<template>
  <div class="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden animate-slide-up">
    <!-- Header / Trigger -->
    <div
      v-if="!done && !streaming"
      @click="generateSummary"
      class="flex items-center justify-center gap-2 px-4 py-3 cursor-pointer
             hover:bg-surface-2 transition-colors group"
    >
      <Sparkles :size="14" class="text-amber-400 group-hover:scale-110 transition-transform" />
      <span class="text-sm text-text-secondary group-hover:text-text-primary transition-colors">
        决策评估 — Judge Agent 帮你看
      </span>
    </div>

    <!-- Summary content -->
    <div v-else class="p-4">
      <div class="flex items-center gap-2 mb-3">
        <Sparkles :size="14" class="text-amber-400" />
        <span class="text-sm font-medium text-text-primary">决策评估</span>
        <span v-if="judgeModel" class="text-[10px] text-text-tertiary bg-surface-3 px-1.5 py-0.5 rounded">
          由 {{ judgeModel }} 评估
        </span>
        <span
          v-if="streaming"
          class="inline-block w-1.5 h-4 bg-amber-400 ml-1 animate-cursor_blink"
        />
      </div>

      <!-- Error -->
      <div v-if="error && !summaryText" class="flex items-center gap-2 text-xs text-red-400">
        <AlertTriangle :size="14" />
        {{ error }}
      </div>

      <div class="md-body text-sm" v-html="summaryHtml" />

      <!-- Collapsible raw responses -->
      <div v-if="done" class="mt-4 pt-3 border-t border-border-subtle">
        <button
          @click="showRaw = !showRaw"
          class="flex items-center gap-1.5 text-xs text-text-tertiary hover:text-text-secondary transition-colors"
        >
          <component :is="showRaw ? ChevronUp : ChevronDown" :size="12" />
          {{ showRaw ? '收起' : '查看' }}各模型原始回答
        </button>

        <Transition name="collapse">
          <div v-if="showRaw" class="mt-3 space-y-3">
            <div
              v-for="[modelId, msg] of responses"
              :key="modelId"
              class="rounded-lg border overflow-hidden transition-all duration-200"
              :class="selectedModelId === modelId
                ? 'ring-1'
                : 'border-border-subtle'"
              :style="selectedModelId === modelId
                ? { borderColor: getModelColor(getProvider(modelId)) + '60', '--tw-ring-color': getModelColor(getProvider(modelId)) + '30' }
                : {}"
            >
              <!-- Card header -->
              <div class="flex items-center gap-2 px-3 py-2 bg-surface-2">
                <span
                  class="w-2.5 h-2.5 rounded-full shrink-0"
                  :style="{ backgroundColor: getModelColor(getProvider(modelId)) }"
                />
                <span class="text-xs font-medium text-text-primary flex-1">{{ getModelName(modelId) }}</span>

                <!-- Select button -->
                <button
                  v-if="selectedModelId !== modelId"
                  @click.stop="emit('select', modelId)"
                  class="text-[10px] px-2 py-0.5 rounded font-medium transition-colors"
                  :style="{ color: getModelColor(getProvider(modelId)) }"
                  :class="`hover:bg-[${getModelColor(getProvider(modelId))}15]`"
                >
                  选择
                </button>
                <span
                  v-else
                  class="text-[10px] font-medium flex items-center gap-0.5"
                  :style="{ color: getModelColor(getProvider(modelId)) }"
                >
                  <Check :size="10" /> 已选
                </span>

                <!-- Expand/collapse toggle -->
                <button
                  @click.stop="toggleExpand(modelId)"
                  class="p-0.5 rounded text-text-tertiary hover:text-text-secondary transition-colors"
                  :title="expandedCards[modelId] ? '收起' : '展开全文'"
                >
                  <component :is="expandedCards[modelId] ? ChevronUp : Maximize2" :size="12" />
                </button>
              </div>

              <!-- Content: summary (clamped) or full -->
              <div class="px-3 py-2">
                <div
                  class="text-xs text-text-secondary whitespace-pre-wrap transition-all duration-200"
                  :class="expandedCards[modelId] ? '' : 'line-clamp-4'"
                >{{ msg.content }}</div>

                <button
                  v-if="!expandedCards[modelId]"
                  @click.stop="toggleExpand(modelId)"
                  class="text-[10px] text-text-tertiary hover:text-accent mt-1 transition-colors"
                >
                  展开全文 ↓
                </button>
              </div>
            </div>
          </div>
        </Transition>

        <!-- Discuss CTA -->
        <button
          v-if="showDiscuss"
          @click="emit('discuss')"
          class="mt-3 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                 text-purple-400 hover:bg-purple-500/10 transition-colors"
        >
          <MessageSquare :size="12" />
          深入讨论 →
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.collapse-enter-active,
.collapse-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.collapse-enter-from,
.collapse-leave-to {
  opacity: 0;
  max-height: 0;
}
.collapse-enter-to,
.collapse-leave-from {
  opacity: 1;
  max-height: 2000px;
}
</style>
