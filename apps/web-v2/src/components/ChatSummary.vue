<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { getModelColor, useAppStore } from '@/stores/app'
import { ChevronDown, ChevronUp, Sparkles, MessageSquare, Check, Maximize2 } from 'lucide-vue-next'
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
const showRaw = ref(false)
const summaryText = ref('')
const streaming = ref(false)
const done = ref(false)

// Track which raw response cards are expanded (default: collapsed/summary)
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

// Mock summary generation
async function generateSummary() {
  if (streaming.value || done.value) return
  emit('activate')
  streaming.value = true
  summaryText.value = ''

  const modelNames = Array.from(props.responses.keys()).map(id => getModelName(id))

  const text = `### 中立总结

**共识：** ${modelNames.join('、')} 都认同应该采用渐进式的架构演进策略，避免一步到位的过度设计。各方均强调明确的模块/服务边界是成功的关键。

**分歧：**
- **服务粒度** — 部分模型倾向更细的拆分（函数级），部分建议保持适中粒度（服务级）
- **通信方式** — 事件驱动 vs 同步调用，各有侧重

**推荐：** 如果团队规模较小且业务初期，建议从模块化单体入手；如果已有微服务经验且流量波动大，可直接采用混合架构方案。`

  for (let i = 0; i < text.length; i++) {
    summaryText.value += text[i]
    const delay = '，。！？\n'.includes(text[i]) ? 35 : (4 + Math.random() * 8)
    await new Promise(r => setTimeout(r, delay))
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
        一键总结 — 中立 Agent 帮你看
      </span>
    </div>

    <!-- Summary content -->
    <div v-else class="p-4">
      <div class="flex items-center gap-2 mb-3">
        <Sparkles :size="14" class="text-amber-400" />
        <span class="text-sm font-medium text-text-primary">中立总结</span>
        <span
          v-if="streaming"
          class="inline-block w-1.5 h-4 bg-amber-400 ml-1 animate-cursor_blink"
        />
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

                <!-- Show "展开" hint when clamped -->
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

        <!-- Discuss CTA (only when showDiscuss is true = a model is selected) -->
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
