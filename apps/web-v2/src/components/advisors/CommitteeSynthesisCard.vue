<script setup lang="ts">
import type { CommitteeSynthesis } from '@/features/committee'
import MarkdownIt from 'markdown-it'
import { computed, reactive } from 'vue'
import { sanitizeModelOutput } from '@/utils/modelOutput'
import { Share2 } from 'lucide-vue-next'
import { shareText } from '@/composables/useShare'

const props = defineProps<{
  synthesis: CommitteeSynthesis | null
  content: string
  streaming?: boolean
}>()

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const expanded = reactive<Record<string, boolean>>({})
const sanitized = computed(() => sanitizeModelOutput(props.content || props.synthesis?.content || ''))
const rendered = computed(() => md.render(sanitized.value.content || ''))

function getSanitizedText(text: string) {
  return sanitizeModelOutput(text || '')
}

function toggle(id: string) {
  expanded[id] = !expanded[id]
}

function renderMarkdown(text: string) {
  return md.render(getSanitizedText(text).content || '')
}

function hiddenThink(text: string) {
  return getSanitizedText(text).hiddenThink
}

function isLong(text: string) {
  const content = getSanitizedText(text).content
  return content.length > 180 || content.includes('\n') || content.includes('|') || content.includes('```')
}
</script>

<template>
  <div class="space-y-4">
    <div class="overflow-hidden rounded-4xl border border-border-default bg-surface-1 shadow-sm">
      <div class="border-b border-border-subtle bg-surface-2/60 px-5 py-4">
        <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-text-tertiary">锦囊团结论</div>
        <div class="mt-2 text-base font-semibold text-text-primary">{{ synthesis?.oneLiner || '系统正在组织最终结论…' }}</div>
        <div class="mt-3 flex flex-wrap gap-2">
          <span
            v-for="item in synthesis?.contributions || []"
            :key="item.roleId"
            class="rounded-full bg-surface-1 px-2.5 py-1 text-[11px] font-medium text-text-secondary border border-border-subtle"
          >
            {{ item.label }}
          </span>
          <button
            v-if="!streaming && synthesis"
            @click="shareText('锦囊团结论', content || synthesis?.content || '')"
            class="rounded-full bg-surface-1 px-2.5 py-1 text-[11px] font-medium text-text-secondary border border-border-subtle hover:bg-surface-3 transition-colors flex items-center gap-1"
          >
            <Share2 :size="11" />
            分享
          </button>
        </div>
      </div>
      <div class="px-5 py-4 text-sm">
        <div class="md-body max-w-none" v-html="rendered" />
        <div v-if="sanitized.hiddenThink" class="pt-3 text-[10px] italic text-text-tertiary">
          已隐藏系统思考过程，只展示最终结论
        </div>
        <div v-if="streaming" class="pt-3">
          <span class="inline-flex gap-1">
            <span class="h-1.5 w-1.5 rounded-full bg-amber-400 animate-typing" style="animation-delay:0s" />
            <span class="h-1.5 w-1.5 rounded-full bg-amber-400 animate-typing" style="animation-delay:0.2s" />
            <span class="h-1.5 w-1.5 rounded-full bg-amber-400 animate-typing" style="animation-delay:0.4s" />
          </span>
        </div>
      </div>
    </div>

    <div v-if="synthesis" class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <section class="rounded-4xl border border-border-default bg-surface-1 shadow-sm">
        <div class="border-b border-border-subtle px-5 py-4">
          <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-emerald-400">Consensus</div>
          <h4 class="mt-1 text-base font-semibold text-text-primary">共识</h4>
        </div>
        <div class="space-y-3 px-5 py-4">
          <div v-for="item in synthesis.consensus" :key="item.id" class="rounded-2xl bg-surface-2 p-4">
            <button class="w-full text-left" type="button" @click="toggle(item.id)">
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-semibold text-text-primary">{{ item.title }}</div>
                <span v-if="isLong(item.summary)" class="text-[11px] text-text-tertiary">{{ expanded[item.id] ? '收起' : '展开' }}</span>
              </div>
            </button>
            <div class="relative mt-2 text-xs text-text-secondary">
              <div
                class="md-body max-w-none overflow-hidden transition-[max-height] duration-200"
                :class="expanded[item.id] || !isLong(item.summary) ? '' : 'max-h-24'"
                v-html="renderMarkdown(item.summary)"
              />
              <div
                v-if="!expanded[item.id] && isLong(item.summary)"
                class="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-surface-2 to-transparent"
              />
              <div v-if="hiddenThink(item.summary)" class="mt-2 text-[10px] italic text-text-tertiary">
                已隐藏系统思考过程
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="rounded-4xl border border-border-default bg-surface-1 shadow-sm">
        <div class="border-b border-border-subtle px-5 py-4">
          <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-rose-400">Tensions</div>
          <h4 class="mt-1 text-base font-semibold text-text-primary">主要分歧</h4>
        </div>
        <div class="space-y-3 px-5 py-4">
          <div v-for="item in synthesis.tensions" :key="item.id" class="rounded-2xl bg-surface-2 p-4">
            <button class="w-full text-left" type="button" @click="toggle(item.id)">
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-semibold text-text-primary">{{ item.title }}</div>
                <span v-if="isLong(item.summary)" class="text-[11px] text-text-tertiary">{{ expanded[item.id] ? '收起' : '展开' }}</span>
              </div>
            </button>
            <div class="relative mt-2 text-xs text-text-secondary">
              <div
                class="md-body max-w-none overflow-hidden transition-[max-height] duration-200"
                :class="expanded[item.id] || !isLong(item.summary) ? '' : 'max-h-24'"
                v-html="renderMarkdown(item.summary)"
              />
              <div
                v-if="!expanded[item.id] && isLong(item.summary)"
                class="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-surface-2 to-transparent"
              />
              <div v-if="hiddenThink(item.summary)" class="mt-2 text-[10px] italic text-text-tertiary">
                已隐藏系统思考过程
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="rounded-4xl border border-border-default bg-surface-1 shadow-sm xl:col-span-2">
        <div class="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
          <div>
            <div class="border-b border-border-subtle px-5 py-4">
              <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-sky-400">Actions</div>
              <h4 class="mt-1 text-base font-semibold text-text-primary">建议动作</h4>
            </div>
            <div class="space-y-3 px-5 py-4">
              <div v-for="item in synthesis.actions" :key="item.id" class="rounded-2xl bg-surface-2 p-4">
                <button class="w-full text-left" type="button" @click="toggle(item.id)">
                  <div class="flex items-center justify-between gap-3">
                    <div class="text-sm font-semibold text-text-primary">{{ item.title }}</div>
                    <span v-if="isLong(item.summary)" class="text-[11px] text-text-tertiary">{{ expanded[item.id] ? '收起' : '展开' }}</span>
                  </div>
                </button>
                <div class="relative mt-2 text-xs text-text-secondary">
                  <div
                    class="md-body max-w-none overflow-hidden transition-[max-height] duration-200"
                    :class="expanded[item.id] || !isLong(item.summary) ? '' : 'max-h-24'"
                    v-html="renderMarkdown(item.summary)"
                  />
                  <div
                    v-if="!expanded[item.id] && isLong(item.summary)"
                    class="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-surface-2 to-transparent"
                  />
                  <div v-if="hiddenThink(item.summary)" class="mt-2 text-[10px] italic text-text-tertiary">
                    已隐藏系统思考过程
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="border-t border-border-subtle xl:border-l xl:border-t-0">
            <div class="px-5 py-4">
              <div class="text-[11px] font-semibold uppercase tracking-[0.22em] text-amber-400">Minority</div>
              <h4 class="mt-1 text-base font-semibold text-text-primary">少数派意见</h4>
            </div>
            <div class="space-y-3 px-5 pb-5">
              <div v-for="item in synthesis.minority" :key="item.id" class="rounded-2xl bg-amber-500/10 p-4">
                <button class="w-full text-left" type="button" @click="toggle(item.id)">
                  <div class="flex items-center justify-between gap-3">
                    <div class="text-sm font-semibold text-text-primary">{{ item.title }}</div>
                    <span v-if="isLong(item.summary)" class="text-[11px] text-text-tertiary">{{ expanded[item.id] ? '收起' : '展开' }}</span>
                  </div>
                </button>
                <div class="relative mt-2 text-xs text-text-secondary">
                  <div
                    class="md-body max-w-none overflow-hidden transition-[max-height] duration-200"
                    :class="expanded[item.id] || !isLong(item.summary) ? '' : 'max-h-24'"
                    v-html="renderMarkdown(item.summary)"
                  />
                  <div
                    v-if="!expanded[item.id] && isLong(item.summary)"
                    class="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-amber-500/10 to-transparent"
                  />
                  <div v-if="hiddenThink(item.summary)" class="mt-2 text-[10px] italic text-text-tertiary">
                    已隐藏系统思考过程
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
@keyframes typing {
  0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); }
  30% { opacity: 1; transform: scale(1.2); }
}
.animate-typing {
  animation: typing 1.2s ease-in-out infinite;
}
</style>
