<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { RotateCcw, AlertTriangle, Loader2, Shield, ChevronRight, Scale } from 'lucide-vue-next'
import { useMultiLifeStore } from '@/stores/multiLife'
import { listCases } from '@/features/play-modes/multi-life'
import type { MultiLifeRoleResponse } from '@/features/play-modes/multi-life'

const store = useMultiLifeStore()

const {
  caseData,
  processing,
  endingGenerating,
  error,
  hydrated,
  phase,
  currentRound,
  challengeRemaining,
  lastRound,
  hasContradiction,
  started,
  evidenceCards,
  ending,
  rounds,
} = storeToRefs(store)

const cases = listCases()

const ROLE_COLORS = [
  { border: 'border-cyan-400/30', bg: 'bg-cyan-500/[0.06]', text: 'text-cyan-400', dot: 'bg-cyan-400' },
  { border: 'border-rose-400/30', bg: 'bg-rose-500/[0.06]', text: 'text-rose-400', dot: 'bg-rose-400' },
  { border: 'border-amber-400/30', bg: 'bg-amber-500/[0.06]', text: 'text-amber-400', dot: 'bg-amber-400' },
]

const TAG_COLORS: Record<string, { dot: string; label: string }> = {
  key: { dot: 'bg-emerald-400', label: '关键' },
  suspicious: { dot: 'bg-yellow-400', label: '可疑' },
  debunked: { dot: 'bg-red-400', label: '证伪' },
  ambiguous: { dot: 'bg-gray-400', label: '模糊' },
}

function trustColor(value: number): string {
  if (value >= 2) return 'bg-emerald-400'
  if (value >= 0) return 'bg-yellow-400'
  return 'bg-red-400'
}

const canChallenge = computed(() =>
  lastRound.value
  && !lastRound.value.playerChoice
  && challengeRemaining.value > 0
  && !processing.value,
)

const canAccept = computed(() =>
  lastRound.value
  && !lastRound.value.playerChoice
  && !processing.value,
)

const isResolutionPhase = computed(() =>
  phase.value === 'resolution' || phase.value === 'ended',
)

onMounted(() => {
  store.init()
})

function handleStart() {
  if (cases.length > 0) store.selectCase(cases[0].id)
}

function handleBegin() {
  store.startRound()
}

function handleNextRound() {
  store.startRound()
}

function handleAccept() {
  store.acceptRound()
}

function handleChallenge(roleId: string) {
  store.challengeRole(roleId)
}

function handleGenerateEnding() {
  store.generateEnding()
}
</script>

<template>
  <div class="min-h-screen bg-[#0B0B1A] text-gray-100">
    <!-- Header -->
    <header class="sticky top-0 z-10 border-b border-white/[0.06] bg-[#0B0B1A]/80 backdrop-blur-md">
      <div class="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <div class="flex items-center gap-3">
          <Shield class="h-5 w-5 text-indigo-400" />
          <h1 class="text-base font-semibold">
            {{ caseData?.title ?? '多重人生' }}
          </h1>
        </div>
        <div class="flex items-center gap-3 text-xs text-gray-500">
          <span v-if="started">
            第 {{ currentRound }}/{{ caseData?.totalRounds ?? '?' }} 轮
          </span>
          <span
            v-if="started"
            class="inline-flex items-center gap-1 rounded-full border border-amber-400/20 bg-amber-500/[0.08] px-2 py-0.5 text-amber-400"
          >
            <Scale class="h-3 w-3" />
            {{ challengeRemaining }}
          </span>
          <button
            v-if="started || caseData"
            class="rounded-lg p-1.5 text-gray-500 transition hover:bg-white/[0.06] hover:text-gray-300"
            title="重新开始"
            @click="store.restart()"
          >
            <RotateCcw class="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-5xl px-4 py-6">
      <!-- Error banner -->
      <div
        v-if="error"
        class="mb-4 rounded-lg border border-red-400/20 bg-red-500/[0.08] px-4 py-3 text-sm text-red-300"
      >
        {{ error }}
      </div>

      <!-- Phase: Setup -->
      <div v-if="phase === 'setup' && !caseData" class="flex flex-col items-center justify-center gap-6 py-20">
        <div class="text-center">
          <h2 class="mb-2 text-xl font-semibold">多重人生</h2>
          <p class="mx-auto max-w-md text-sm text-gray-400">
            同一个案件，3 个 AI 角色各执一词。你通过质疑和信任推进叙事，最终还原属于你的真相。
          </p>
        </div>
        <button
          class="rounded-xl bg-indigo-600 px-6 py-3 text-sm font-medium text-white transition hover:bg-indigo-500"
          @click="handleStart"
        >
          选择案件开始
        </button>
      </div>

      <!-- Phase: Setup (case selected, not started) -->
      <div v-if="phase === 'setup' && caseData" class="flex flex-col gap-6 py-8">
        <!-- Case premise -->
        <div class="rounded-xl border border-white/[0.06] bg-white/[0.03] p-5">
          <h2 class="mb-2 text-lg font-semibold">{{ caseData.title }}</h2>
          <p class="text-sm leading-relaxed text-gray-300">{{ caseData.premise }}</p>
          <div class="mt-4 flex flex-wrap gap-3">
            <span class="text-xs text-gray-500">
              {{ caseData.totalRounds }} 轮
            </span>
            <span class="text-xs text-gray-500">
              {{ caseData.challengeBudget }} 次质疑机会
            </span>
          </div>
        </div>

        <!-- Roles preview -->
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div
            v-for="(role, idx) in caseData.roles"
            :key="role.id"
            class="rounded-xl border p-4 transition"
            :class="ROLE_COLORS[idx].border + ' ' + ROLE_COLORS[idx].bg"
          >
            <p class="text-sm font-medium" :class="ROLE_COLORS[idx].text">{{ role.name }}</p>
            <p class="mt-1 text-xs text-gray-500">等待模型分配…</p>
          </div>
        </div>

        <button
          class="mx-auto rounded-xl bg-indigo-600 px-8 py-3 text-sm font-medium text-white transition hover:bg-indigo-500"
          @click="handleBegin"
        >
          开始调查
        </button>
      </div>

      <!-- Phase: Investigation -->
      <div v-if="phase === 'investigation' && started">
        <!-- Rounds history (collapsed) -->
        <div v-if="rounds.length > 1" class="mb-4 space-y-2">
          <button
            v-for="r in rounds.slice(0, -1)"
            :key="r.id"
            class="flex w-full items-center gap-2 rounded-lg border border-white/[0.04] bg-white/[0.02] px-4 py-2 text-left text-xs text-gray-500 transition hover:bg-white/[0.04]"
          >
            <span class="font-medium text-gray-400">第 {{ r.roundNumber }} 轮</span>
            <span>{{ r.scene.slice(0, 40) }}…</span>
            <span v-if="r.playerChoice?.type === 'challenge'" class="text-amber-400">
              （质疑）
            </span>
            <ChevronRight class="ml-auto h-3 w-3" />
          </button>
        </div>

        <!-- Current round -->
        <div v-if="lastRound" class="space-y-4">
          <!-- Scene -->
          <div class="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
            <p class="mb-1 text-xs font-medium uppercase tracking-wider text-indigo-400">
              第 {{ lastRound.roundNumber }} 轮
            </p>
            <p class="text-sm leading-relaxed text-gray-200">{{ lastRound.scene }}</p>
          </div>

          <!-- Role testimonies -->
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div
              v-for="(resp, idx) in lastRound.responses"
              :key="resp.roleId"
              class="rounded-xl border p-4"
              :class="ROLE_COLORS[idx].border + ' ' + ROLE_COLORS[idx].bg"
            >
              <div class="mb-2 flex items-center justify-between">
                <p class="text-sm font-medium" :class="ROLE_COLORS[idx].text">
                  {{ caseData?.roles.find(r => r.id === resp.roleId)?.name }}
                </p>
                <span
                  v-if="resp.modelName"
                  class="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-gray-500"
                >
                  {{ resp.modelName }}
                </span>
              </div>

              <!-- Trust dot -->
              <div class="mb-2 flex items-center gap-1">
                <span
                  class="inline-block h-2 w-2 rounded-full"
                  :class="trustColor(store.trustMap[resp.roleId] ?? 0)"
                />
                <span class="text-[10px] text-gray-600">信任度</span>
              </div>

              <!-- Testimony text -->
              <div v-if="resp.status === 'generating'" class="flex items-center gap-2 py-4 text-xs text-gray-500">
                <Loader2 class="h-3 w-3 animate-spin" />
                正在生成证词…
              </div>
              <div v-else-if="resp.status === 'error'" class="py-4 text-xs text-red-400">
                {{ resp.error || '生成失败' }}
              </div>
              <p v-else class="text-sm leading-relaxed text-gray-300">{{ resp.text }}</p>

              <!-- Challenge response -->
              <div
                v-if="resp.isChallenged && resp.challengeResponse"
                class="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/[0.06] p-3"
              >
                <p class="mb-1 text-[10px] font-medium text-amber-400">被质疑后补充</p>
                <p class="text-xs leading-relaxed text-gray-300">{{ resp.challengeResponse }}</p>
              </div>
            </div>
          </div>

          <!-- Contradiction alert -->
          <div
            v-if="hasContradiction && !lastRound.playerChoice"
            class="flex items-start gap-3 rounded-xl border border-amber-400/20 bg-amber-500/[0.06] p-4"
          >
            <AlertTriangle class="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
            <div>
              <p class="text-sm font-medium text-amber-300">发现矛盾</p>
              <div class="mt-1 space-y-1">
                <p
                  v-for="(c, ci) in lastRound.contradictions"
                  :key="ci"
                  class="text-xs text-amber-200/70"
                >
                  {{ c.description }}
                </p>
              </div>
            </div>
          </div>

          <!-- Action buttons -->
          <div v-if="!lastRound.playerChoice" class="flex flex-wrap gap-2 pt-2">
            <button
              :disabled="!canAccept"
              class="flex-1 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
              @click="handleAccept"
            >
              {{ hasContradiction ? '接受当前说法' : '继续' }}
            </button>
            <template v-if="canChallenge">
              <button
                v-for="resp in lastRound.responses.filter(r => r.status === 'done')"
                :key="'ch-' + resp.roleId"
                class="rounded-xl border border-amber-400/30 bg-amber-500/[0.08] px-4 py-3 text-sm font-medium text-amber-300 transition hover:bg-amber-500/[0.15]"
                @click="handleChallenge(resp.roleId)"
              >
                质疑 {{ caseData?.roles.find(r => r.id === resp.roleId)?.name }}
              </button>
            </template>
          </div>

          <!-- After choice, show next round button -->
          <div v-if="lastRound.playerChoice && !isResolutionPhase" class="pt-2">
            <button
              :disabled="processing"
              class="w-full rounded-xl bg-indigo-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
              @click="handleNextRound"
            >
              <span v-if="processing" class="flex items-center justify-center gap-2">
                <Loader2 class="h-4 w-4 animate-spin" />
                生成下一轮…
              </span>
              <span v-else>
                下一轮
                <ChevronRight class="ml-1 inline h-4 w-4" />
              </span>
            </button>
          </div>
        </div>

        <!-- Evidence rail -->
        <div v-if="evidenceCards.length > 0" class="mt-6">
          <p class="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">证据卡</p>
          <div class="flex gap-2 overflow-x-auto pb-2">
            <div
              v-for="card in evidenceCards"
              :key="card.id"
              class="flex shrink-0 items-start gap-2 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-2"
              style="min-width: 200px; max-width: 260px"
            >
              <span
                class="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
                :class="TAG_COLORS[card.tag]?.dot ?? 'bg-gray-400'"
              />
              <div>
                <p class="text-[10px] text-gray-600">第 {{ card.round }} 轮</p>
                <p class="mt-0.5 text-xs text-gray-300">{{ card.summary }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Phase: Resolution -->
      <div v-if="isResolutionPhase && phase === 'resolution'" class="flex flex-col items-center gap-6 py-12">
        <div v-if="!ending && !endingGenerating" class="text-center">
          <h2 class="mb-2 text-lg font-semibold">调查结束</h2>
          <p class="text-sm text-gray-400">所有轮次已完成，查看你的版本与真相对比。</p>
          <button
            class="mt-4 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-medium text-white transition hover:bg-indigo-500"
            @click="handleGenerateEnding"
          >
            生成结局对比
          </button>
        </div>
        <div v-if="endingGenerating" class="flex items-center gap-2 text-sm text-gray-400">
          <Loader2 class="h-4 w-4 animate-spin" />
          正在生成结局…
        </div>
      </div>

      <!-- Phase: Ended -->
      <div v-if="ending" class="space-y-4 py-6">
        <h2 class="text-center text-lg font-semibold">结局对比</h2>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <!-- Player's version -->
          <div class="rounded-xl border border-cyan-400/20 bg-cyan-500/[0.04] p-5">
            <p class="mb-3 text-sm font-medium text-cyan-400">你的版本</p>
            <p class="text-sm leading-relaxed text-gray-300">{{ ending.playerNarrative }}</p>
          </div>
          <!-- Truth -->
          <div class="rounded-xl border border-emerald-400/20 bg-emerald-500/[0.04] p-5">
            <p class="mb-3 text-sm font-medium text-emerald-400">真相</p>
            <p class="text-sm leading-relaxed text-gray-300">{{ ending.truthNarrative }}</p>
          </div>
        </div>

        <!-- Deviation analysis -->
        <div v-if="ending.deviationAnalysis" class="rounded-xl border border-white/[0.06] bg-white/[0.03] p-5">
          <p class="mb-2 text-sm font-medium text-amber-400">偏差分析</p>
          <p class="text-sm leading-relaxed text-gray-300">{{ ending.deviationAnalysis }}</p>
        </div>

        <!-- Unexplored branches -->
        <div v-if="ending.unexploredBranches?.length" class="rounded-xl border border-white/[0.06] bg-white/[0.03] p-5">
          <p class="mb-2 text-sm font-medium text-purple-400">未探索的分支</p>
          <ul class="space-y-1">
            <li
              v-for="(branch, bi) in ending.unexploredBranches"
              :key="bi"
              class="text-sm text-gray-400"
            >
              {{ branch }}
            </li>
          </ul>
        </div>

        <button
          class="mx-auto mt-6 rounded-xl bg-indigo-600 px-6 py-3 text-sm font-medium text-white transition hover:bg-indigo-500"
          @click="store.restart()"
        >
          再来一局
        </button>
      </div>
    </main>
  </div>
</template>
