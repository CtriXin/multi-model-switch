# 多重人生 (Multi-Life) — 实现计划

> 版本：v0.1
> 日期：2026-03-20
> 状态：待实现

---

## 一、核心架构决策

### 1.1 复用策略

**多重人生 = Story Live 的结构化变体**，不是从零构建。

| Story Live 机制 | 多重人生对应 | 复用方式 |
|----------------|-------------|---------|
| 3 角色并行生成 | 3 角色证词并行 | 直接复用 `generateRole()` |
| Logic/Emotion/Twist | 案件角色 A/B/C | 改 prompt 模板 |
| Twist 条件触发 | 矛盾预设触发 | 移除 twist-trigger |
| Tension 弧线结局 | 轮次耗尽结局 | 简化结局逻辑 |
| Director Memory | Branch Memory | 改追踪字段 |

### 1.2 不实现的内容（设计文档明确说明）

- ❌ 7 阶段状态机（那是 Case Reconstruction 的）
- ❌ 打分系统（"没有失败，只有你的版本"）
- ❌ LLM 独立矛盾检测（prompt 层控制）
- ❌ 背包/证据板手动管理（证据卡自动收集）
- ❌ 拖拽/连线交互（只需"质疑"或"接受"）

---

## 二、文件结构

```
apps/web-v2/src/
├── features/
│   ├── multi-life/
│   │   ├── types.ts              # 类型定义（Case/Role/Round/Session）
│   │   ├── prompts.ts            # Prompt 模板
│   │   └── cases/
│   │       ├── index.ts          # 案件列表
│   │       ├── warehouse.ts      # 案件 1：暴雨仓库
│   │       ├── last-message.ts   # 案件 2：最后一条消息
│   │       └── alibi.ts          # 案件 3：不在场证明
│   │
│   └── play-modes/shared/        # 直接复用
│
├── stores/
│   ├── multiLife.ts              # 新建：状态管理 + 游戏逻辑
│   ├── storyLive.ts              # 复用：并行生成机制
│   └── story-live-helpers.ts     # 复用：chooseModelIds 等
│
├── views/
│   ├── MultiLifeView.vue         # 新建：主界面
│   └── StoryLiveView.vue         # 复用：三栏布局
│
└── components/
    └── multi-life/
        ├── RoleCard.vue          # 角色证词卡片
        ├── ConflictBanner.vue    # 矛盾高亮条
        ├── ActionButtons.vue     # 接受/质疑按钮
        ├── EvidenceCards.vue     # 证据卡流
        └── EndingCompare.vue     # 结局对比界面
```

---

## 三、Phase 1：类型与数据（1-2h）

### 3.1 `features/multi-life/types.ts`

```typescript
// 案件定义（设计文档 §5）
export interface MultiLifeCase {
  id: string
  title: string
  premise: string
  truth: string
  roles: MultiLifeRole[]
  rounds: MultiLifeRoundConfig[]
  totalRounds: number
  challengeBudget: number
}

export interface MultiLifeRole {
  id: string
  name: string
  archetype: 'witness' | 'suspect' | 'analyst' | 'insider' | 'innocent'
  reliability: number           // 0-1
  hiddenKnowledge: number        // 0-1
  lyingPattern: 'never' | 'selective' | 'consistent' | 'increasing'
  personality: string
}

export interface MultiLifeRoundConfig {
  roundNumber: number
  scene: string
  contradictions?: ContradictionPoint[]
  roles: Record<string, { directive: string; lying: boolean }>
}

export interface ContradictionPoint {
  betweenRoles: [string, string]
  topic: string
  description: string
}

// 运行时状态
export interface MultiLifeSession {
  caseId: string
  currentRound: number
  challengeRemaining: number
  trustMap: Record<string, number>
  choices: PlayerChoice[]
  evidenceCards: EvidenceCard[]
  phase: 'prologue' | 'investigation' | 'resolution' | 'ended'
  ending?: SessionEnding
  roleModelMap: Record<string, string>  // roleId → modelId
}

export interface PlayerChoice {
  round: number
  type: 'accept' | 'challenge'
  challengedRoleId?: string
  narrativePath: string
}

export interface EvidenceCard {
  id: string
  round: number
  source: string
  summary: string
  tag: 'key' | 'suspicious' | 'debunked' | 'ambiguous'
}

export interface SessionEnding {
  playerNarrative: string
  truthNarrative: string
  deviationAnalysis: string
  unexploredBranches: string[]
}
```

### 3.2 `features/multi-life/cases/warehouse.ts`（示例案件）

```typescript
import type { MultiLifeCase } from '../types'

export const warehouseCase: MultiLifeCase = {
  id: 'warehouse-rain',
  title: '暴雨仓库',
  premise: '暴雨夜，仓库里发现一具尸体。三个相关人被带到警局分别问话。',
  truth: '死者是仓库管理员，嫌疑人在雨夜进入仓库盗窃被发现，失手杀人...',
  totalRounds: 7,
  challengeBudget: 3,
  roles: [
    {
      id: 'witness',
      name: '目击者 张三',
      archetype: 'witness',
      reliability: 0.7,
      hiddenKnowledge: 0.6,
      lyingPattern: 'selective',
      personality: '谨慎，说话留有余地',
    },
    {
      id: 'suspect',
      name: '嫌疑人 李四',
      archetype: 'suspect',
      reliability: 0.4,
      hiddenKnowledge: 1.0,
      lyingPattern: 'consistent',
      personality: '冷静，善于伪装',
    },
    {
      id: 'analyst',
      name: '王警官',
      archetype: 'analyst',
      reliability: 0.9,
      hiddenKnowledge: 0.8,
      lyingPattern: 'never',
      personality: '理性，注重证据',
    },
  ],
  rounds: [
    // 第 1-2 轮：无矛盾，建立信任
    {
      roundNumber: 1,
      scene: '三个人被带到不同的审讯室，窗外下着暴雨。',
      roles: {
        witness: { directive: '描述你看到的黑影', lying: false },
        suspect: { directive: '否认你在现场', lying: true },
        analyst: { directive: '陈述物证情况', lying: false },
      },
    },
    // 第 3 轮：第一次矛盾（轻度）
    {
      roundNumber: 3,
      scene: '审讯进入白热化，细节开始对不上。',
      contradictions: [
        {
          betweenRoles: ['witness', 'suspect'],
          topic: '案发时间',
          description: '目击者说 9 点，嫌疑人说 11 点',
        },
      ],
      roles: {
        witness: { directive: '坚持说案发时间是 9 点', lying: false },
        suspect: { directive: '声称案发时你在家', lying: true },
        analyst: { directive: '分析时间线疑点', lying: false },
      },
    },
    // ... 第 5、7 轮矛盾
  ],
}
```

---

## 四、Phase 2：Store 核心逻辑（3-4h）

### 4.1 `stores/multiLife.ts` 核心函数

```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { streamModelChat } from '@/services/runtime'
import { buildContextMessages } from '@/utils/contextBuilder'
import type { MultiLifeCase, MultiLifeSession, EvidenceCard } from '@/features/multi-life/types'
import { ALL_CASES } from '@/features/multi-life/cases'

export const useMultiLifeStore = defineStore('multiLife', () => {
  // 状态
  const currentCase = ref<MultiLifeCase | null>(null)
  const session = ref<MultiLifeSession | null>(null)
  const streaming = ref(false)
  const roundResponses = ref<Map<string, string>>(new Map())

  // 计算属性
  const currentRoundConfig = computed(() => {
    if (!currentCase.value || !session.value) return null
    return currentCase.value.rounds.find(r => r.roundNumber === session.value.currentRound)
  })

  const hasContradiction = computed(() => {
    return !!currentRoundConfig.value?.contradictions?.length
  })

  // 初始化游戏
  function startGame(caseId: string, roleModelMap: Record<string, string>) {
    const caseData = ALL_CASES.find(c => c.id === caseId)
    if (!caseData) throw new Error('Case not found')

    currentCase.value = caseData
    session.value = {
      caseId,
      currentRound: 1,
      challengeRemaining: caseData.challengeBudget,
      trustMap: {},
      choices: [],
      evidenceCards: [],
      phase: 'prologue',
      roleModelMap,
    }
  }

  // 并行生成三个角色证词（复用 Story Live 机制）
  async function generateRoundResponses() {
    if (!currentCase.value || !session.value) return

    streaming.value = true
    roundResponses.value.clear()

    const roundConfig = currentRoundConfig.value
    if (!roundConfig) return

    // 并行请求三个角色
    const promises = currentCase.value.roles.map(async (role) => {
      const modelId = session.value!.roleModelMap[role.id]
      const roleDirective = roundConfig.roles[role.id].directive
      const prompt = buildRolePrompt(role, roundConfig, currentCase.value!.premise)

      const response = await streamModelChat({
        modelId,
        messages: [{ role: 'user', content: prompt }],
      })

      roundResponses.value.set(role.id, response)

      // 生成本轮证据卡
      generateEvidenceCard(role, response)
    })

    await Promise.all(promises)
    streaming.value = false
  }

  // 玩家决策：接受
  function acceptNarrative() {
    if (!session.value) return

    session.value.choices.push({
      round: session.value.currentRound,
      type: 'accept',
      narrativePath: 'default',
    })

    advanceRound()
  }

  // 玩家决策：质疑
  function challengeRole(roleId: string) {
    if (!session.value || session.value.challengeRemaining <= 0) return

    session.value.choices.push({
      round: session.value.currentRound,
      type: 'challenge',
      challengedRoleId: roleId,
      narrativePath: `challenge-${roleId}`,
    })

    session.value.challengeRemaining--
    updateTrust(roleId, -1)  // 质疑降低信任度

    // 被质疑角色补充信息（此处可触发额外生成）
    advanceRound()
  }

  // 推进轮次
  function advanceRound() {
    if (!session.value || !currentCase.value) return

    if (session.value.currentRound >= currentCase.value.totalRounds) {
      session.value.phase = 'resolution'
      generateEnding()
    } else {
      session.value.currentRound++
      generateRoundResponses()
    }
  }

  // 生成证据卡
  function generateEvidenceCard(role: any, response: string) {
    if (!session.value) return

    const card: EvidenceCard = {
      id: `evidence-${session.value.currentRound}-${role.id}`,
      round: session.value.currentRound,
      source: role.name,
      summary: response.slice(0, 50) + '...',
      tag: 'ambiguous',
    }

    session.value.evidenceCards.push(card)
  }

  // 更新信任度
  function updateTrust(roleId: string, delta: number) {
    if (!session.value) return
    session.value.trustMap[roleId] = (session.value.trustMap[roleId] || 0) + delta
  }

  // 生成结局
  async function generateEnding() {
    if (!session.value || !currentCase.value) return

    // 调用 LLM 生成"你的版本"和"真相版本"对比
    const prompt = buildEndingPrompt(currentCase.value, session.value)
    const ending = await streamModelChat({
      modelId: Object.values(session.value.roleModelMap)[0],
      messages: [{ role: 'user', content: prompt }],
    })

    session.value.ending = parseEnding(ending)
    session.value.phase = 'ended'
  }

  // 重置
  function reset() {
    currentCase.value = null
    session.value = null
    roundResponses.value.clear()
  }

  return {
    currentCase,
    session,
    streaming,
    roundResponses,
    hasContradiction,
    startGame,
    generateRoundResponses,
    acceptNarrative,
    challengeRole,
    reset,
  }
})
```

---

## 五、Phase 3：Prompt 模板（1h）

### 5.1 `features/multi-life/prompts.ts`

```typescript
import type { MultiLifeCase, MultiLifeRole, MultiLifeRoundConfig } from './types'

// 叙事者 Prompt（场景描述）
export function buildNarratorPrompt(case_: MultiLifeCase, round: number): string {
  const roundConfig = case_.rounds.find(r => r.roundNumber === round)
  return `你是叙事者。根据以下案件设定，用 2-3 句话描述当前场景。
不要暗示任何线索或真相，只描述氛围和事件进展。
保持客观、冷静的语气。

案件背景：${case_.premise}
当前轮次：第${round}轮
场景设定：${roundConfig?.scene || '继续推进'}

请描述场景：`
}

// 角色 Prompt（每个角色不同）
export function buildRolePrompt(
  role: MultiLifeRole,
  roundConfig: MultiLifeRoundConfig,
  casePremise: string
): string {
  const roleDirective = roundConfig.roles[role.id]

  return `你是${role.name}，${role.personality}。

关于"${casePremise}"，你知道一些内情。
但在本轮中，你的指令是：${roleDirective.directive}。

规则：
- 用第一人称说话，保持角色性格
- 不要直接说出真相，除非被质疑且角色可靠度要求
- 如果被质疑且在说谎，可以选择圆谎或崩溃说出部分真话
- 每次回复不超过 80 字

你的证词：`
}

// 结局生成 Prompt
export function buildEndingPrompt(case_: MultiLifeCase, session: any): string {
  return `基于以下游戏记录：
- 玩家做了 ${session.choices.length} 次选择，其中质疑 ${session.choices.filter((c: any) => c.type === 'challenge').length} 次
- 信任度最高的角色是 ${Object.entries(session.trustMap).sort((a, b) => b[1] - a[1])[0]?.[0]}
- 收集的证据：${session.evidenceCards.map((e: any) => e.summary).join('; ')}

生成以下三部分（用 JSON 格式返回）：
1. "playerNarrative": 玩家的真相版本（3-5 句）
2. "truthNarrative": 标准真相（3-5 句）
3. "deviationAnalysis": 偏差分析（1-2 句）
4. "unexploredBranches": 未探索的关键分支（1-2 条）

玩家的版本应该合理但不一定完全正确——取决于玩家是否识破了说谎者。`
}
```

---

## 六、Phase 4：UI 组件（3-4h）

### 6.1 `views/MultiLifeView.vue` 结构

```vue
<script setup lang="ts">
import { useMultiLifeStore } from '@/stores/multiLife'
import RoleCard from '@/components/multi-life/RoleCard.vue'
import ConflictBanner from '@/components/multi-life/ConflictBanner.vue'
import ActionButtons from '@/components/multi-life/ActionButtons.vue'
import EvidenceCards from '@/components/multi-life/EvidenceCards.vue'
import EndingCompare from '@/components/multi-life/EndingCompare.vue'

const store = useMultiLifeStore()

function handleAccept() {
  store.acceptNarrative()
}

function handleChallenge(roleId: string) {
  store.challengeRole(roleId)
}
</script>

<template>
  <div class="min-h-screen bg-gradient-to-b from-slate-900 to-slate-800">
    <!-- 顶栏 -->
    <header class="sticky top-0 z-50 backdrop-blur-md bg-slate-900/80 border-b border-white/10">
      <div class="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <h1 class="text-lg font-bold text-white">{{ store.currentCase?.title }}</h1>
        <div class="flex items-center gap-4 text-sm">
          <span class="text-slate-400">第 {{ store.session?.currentRound }}/{{ store.currentCase?.totalRounds }} 轮</span>
          <span class="text-orange-400 font-bold">⊕ {{ store.session?.challengeRemaining }} 质疑</span>
        </div>
      </div>
    </header>

    <!-- 主内容 -->
    <main class="max-w-6xl mx-auto px-4 py-8">
      <!-- 结局界面 -->
      <EndingCompare v-if="store.session?.phase === 'ended'" :ending="store.session.ending" />

      <!-- 游戏进行中 -->
      <template v-else>
        <!-- 场景描述 -->
        <div class="mb-8 p-6 rounded-2xl bg-white/5 border border-white/10">
          <p class="text-lg text-slate-200 leading-relaxed">
            {{ store.currentRoundConfig?.scene }}
          </p>
        </div>

        <!-- 矛盾高亮 -->
        <ConflictBanner v-if="store.hasContradiction" :contradictions="store.currentRoundConfig?.contradictions" />

        <!-- 三角色证词 -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <RoleCard
            v-for="role in store.currentCase?.roles"
            :key="role.id"
            :role="role"
            :model-id="store.session?.roleModelMap[role.id]"
            :response="store.roundResponses.get(role.id)"
            :streaming="store.streaming"
            @challenge="handleChallenge"
          />
        </div>

        <!-- 操作按钮 -->
        <ActionButtons
          v-if="store.hasContradiction"
          @accept="handleAccept"
          :challenge-options="store.currentCase?.roles.map(r => ({ id: r.id, name: r.name }))"
          :disabled="store.streaming"
        />
      </template>
    </main>

    <!-- 证据卡流 -->
    <EvidenceCards :cards="store.session?.evidenceCards || []" />
  </div>
</template>
```

### 6.2 `components/multi-life/RoleCard.vue`

```vue
<script setup lang="ts">
import type { MultiLifeRole } from '@/features/multi-life/types'

defineProps<{
  role: MultiLifeRole
  modelId?: string
  response?: string
  streaming?: boolean
}>()

defineEmits<{
  challenge: [roleId: string]
}>()
</script>

<template>
  <div class="relative p-5 rounded-2xl bg-white/5 border border-white/10 hover:border-accent/50 transition-colors">
    <!-- 角色头 -->
    <div class="flex items-center justify-between mb-3">
      <div>
        <h3 class="text-white font-bold">{{ role.name }}</h3>
        <p class="text-xs text-slate-400">{{ role.archetype }}</p>
      </div>
      <span class="text-xs px-2 py-1 rounded-full bg-accent/10 text-accent">
        {{ modelId?.split('/')[1] }}
      </span>
    </div>

    <!-- 证词内容 -->
    <div class="min-h-[100px]">
      <p v-if="streaming" class="text-slate-400 animate-pulse">思考中...</p>
      <p v-else-if="response" class="text-slate-200 text-sm leading-relaxed">{{ response }}</p>
      <p v-else class="text-slate-500 text-sm">等待生成...</p>
    </div>

    <!-- 质疑按钮（仅当有矛盾时显示） -->
    <button
      @click="$emit('challenge', role.id)"
      class="absolute bottom-3 right-3 text-xs px-3 py-1.5 rounded-full bg-orange-500/20 text-orange-400 border border-orange-500/30 hover:bg-orange-500/30 transition-colors"
    >
      质疑
    </button>
  </div>
</template>
```

### 6.3 `components/multi-life/ActionButtons.vue`

```vue
<script setup lang="ts">
defineProps<{
  challengeOptions?: Array<{ id: string; name: string }>
  disabled?: boolean
}>()

defineEmits<{
  accept: []
  challenge: [roleId: string]
}>()
</script>

<template>
  <div class="fixed bottom-0 left-0 right-0 p-4 backdrop-blur-md bg-slate-900/90 border-t border-white/10">
    <div class="max-w-4xl mx-auto flex items-center gap-4">
      <!-- 接受 -->
      <button
        @click="$emit('accept')"
        :disabled="disabled"
        class="flex-1 py-4 rounded-xl bg-emerald-500 text-white font-bold hover:bg-emerald-600 transition-colors disabled:opacity-50"
      >
        ✓ 接受当前说法
      </button>

      <!-- 质疑下拉 -->
      <div class="relative group">
        <button
          :disabled="disabled"
          class="px-6 py-4 rounded-xl bg-orange-500 text-white font-bold hover:bg-orange-600 transition-colors disabled:opacity-50"
        >
          ⚡ 质疑
        </button>

        <!-- 下拉菜单 -->
        <div class="absolute bottom-full right-0 mb-2 hidden group-hover:block w-48 rounded-xl bg-slate-800 border border-white/10 shadow-xl overflow-hidden">
          <button
            v-for="opt in challengeOptions"
            :key="opt.id"
            @click="$emit('challenge', opt.id)"
            class="w-full px-4 py-3 text-left text-slate-200 hover:bg-white/10 transition-colors"
          >
            {{ opt.name }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
```

---

## 七、Phase 5：模型分配（0.5h）

复用 `story-live-helpers.ts` 的 `chooseModelIds()`，确保三个角色绑定不同模型：

```typescript
// stores/multiLife.ts
import { chooseModelIds } from './story-live-helpers'

function assignRoleModels(): Record<string, string> {
  const modelIds = chooseModelIds(appStore, 3, { requireDifferentProviders: true })
  return {
    witness: modelIds[0],
    suspect: modelIds[1],
    analyst: modelIds[2],
  }
}
```

---

## 八、Phase 6：入口与路由（0.5h）

### 8.1 添加到模式选择

在 `PlayModeSelect.vue` 中添加"多重人生"入口：

```vue
<router-link to="/multi-life" class="...">
  <div class="p-6 rounded-2xl bg-gradient-to-br from-purple-500/20 to-blue-500/20">
    <h3>多重人生</h3>
    <p>同一案件，3 个 AI 各执一词</p>
  </div>
</router-link>
```

### 8.2 路由配置

```typescript
// router/index.ts
{
  path: '/multi-life',
  component: () => import('@/views/MultiLifeView.vue'),
}
```

---

## 九、验收清单

- [ ] 三个角色卡片并行生成（同时显示）
- [ ] 每个角色绑定不同模型（模型标签可见）
- [ ] 矛盾轮次高亮显示矛盾条
- [ ] "接受"按钮推进剧情
- [ ] "质疑"按钮消耗次数并记录选择
- [ ] 证据卡自动收集
- [ ] 轮次耗尽后生成结局对比
- [ ] 移动端三栏变单栏
- [ ] 至少实现 1 个完整案件（暴雨仓库）

---

## 十、预计工时

| Phase | 内容 | 预计时间 |
|-------|------|---------|
| 1 | 类型与数据 | 1-2h |
| 2 | Store 核心逻辑 | 3-4h |
| 3 | Prompt 模板 | 1h |
| 4 | UI 组件 | 3-4h |
| 5 | 模型分配 | 0.5h |
| 6 | 入口与路由 | 0.5h |
| **总计** | | **9-13h** |

---

## 十一、技术风险与对策

| 风险 | 对策 |
|------|------|
| 并行生成时序不一致 | 用 `Promise.all` 等待全部完成 |
| 矛盾检测逻辑复杂 | Prompt 层预设矛盾，UI 只做高亮 |
| 结局生成质量不稳定 | 用 JSON schema 约束输出格式 |
| 移动端布局错乱 | 用 Tailwind `md:grid-cols-3` 响应式 |

---

## 十二、下一步行动

1. 创建 `features/multi-life/types.ts`
2. 创建 `features/multi-life/cases/warehouse.ts`
3. 创建 `stores/multiLife.ts`（核心逻辑）
4. 创建 `views/MultiLifeView.vue`
5. 创建组件目录和子组件
6. 添加路由和入口
7. 本地测试并行生成和交互流程
