# Daily Challenge + Thinking Pattern Snapshot — 技术 Spec

> Created: 2026-03-18
> Status: Ready for implementation
> Source: 2 轮 Codex discuss + 用户确认

## 产品定义

**一句话**：每天一个辩题，3 分钟参与，多 AI 对辩，保存观点卡 + 思维快照，周度回顾。

**核心叙事**：不是问 AI，是和多个 AI 一起辩论并追踪自己的思维轮廓。

## 设计决策（已确认）

| 决策项 | 结论 |
|--------|------|
| Tracker 形态 | 轻量 4 轴 tags 挂在 opinion card 上，不独立 store |
| 文案 | "思维快照 (AI 观察，仅供参考)"，不用"认知进化/测评" |
| 辩论形式 | AI Debate Show 是 Daily Challenge 的交互皮肤，不是独立功能 |
| 时间目标 | 30-45s 完成，长叙事最多 60s |
| 模型选择 | 默认固定一对（自动从已配置 provider 中选便宜快的），高级用户可换 |
| 用户输入 | 选立场后必须输入一句话原因 |
| 换题 | 支持，topic 一次生成 3 个 candidate |
| 报告 | Weekly reflection card，不做月报 |
| 曲线命名 | "clarity curve"（清晰度），不叫"成长曲线" |
| 题库 | 96 个 seed tension（每 category 16 个）+ AI 改写 |
| 数据存储 | IndexedDB，无后端 |

## 数据模型

```typescript
// ===== Types =====

export type DailyCategory = 'tech' | 'society' | 'career' | 'philosophy' | 'life' | 'economy'

export type DebateStance = 'support' | 'oppose' | 'mixed'

export type TopicSource = 'curated' | 'ai_seeded' | 'hybrid'

export type AxisId = 'evidence_intuition' | 'decisive_exploratory' | 'risk_seeking_risk_aware' | 'self_systems'

export type ArgumentStyle = 'evidence_first' | 'principle_first' | 'pragmatic' | 'possibility_first' | 'balanced'

// ===== Thinking Pattern Snapshot =====

export interface ThinkingAxisScore {
  /** 0-100, 50 is neutral. Left label at 0, right label at 100 */
  score: number
  /** 0-1, how confident the tagger is */
  confidence: number
  /** short note explaining the score */
  note: string
}

export interface ThinkingPatternSnapshot {
  version: 'v1'
  label: '思维快照 (AI 观察，仅供参考)'
  modelId: string
  generatedAt: number
  axes: Record<AxisId, ThinkingAxisScore>
  /** top 1-2 axes that deviate most from 50 */
  dominantAxes: AxisId[]
  /** one-sentence summary in user's language */
  summary: string
}

// ===== Topic =====

export interface TopicCandidate {
  id: string
  title: string
  prompt: string
  angle: string
  sideA: string
  sideB: string
  category: DailyCategory
}

export interface TopicMeta {
  title: string
  prompt: string
  angle: string
  source: TopicSource
  seed: string
  sourceTopicId?: string
  /** IDs of past cards used for personalization */
  historyCardIds: string[]
  personalizationVersion: 'v1'
  /** other candidates user could have picked */
  alternatives: string[]
}

// ===== Debate =====

export interface DebateRound {
  speaker: 'pro' | 'con' | 'moderator'
  phase: 'opening' | 'crossfire' | 'wrap'
  modelId: string
  text: string
  latencyMs?: number
}

export interface DebateTakeaway {
  strongestPointFor: string
  strongestPointAgainst: string
  decisiveQuestion: string
  oneLineVerdict: string
}

export interface DebateRecord {
  format: 'daily_challenge_v1'
  durationMs: number
  models: {
    generator: string
    pro: string
    con: string
    moderator: string
  }
  rounds: DebateRound[]
  takeaway: DebateTakeaway
}

// ===== Opinion Card (核心实体) =====

export interface OpinionCard {
  id: string
  challengeDate: string // YYYY-MM-DD
  createdAt: number
  updatedAt: number
  category: DailyCategory

  topic: TopicMeta

  stance: {
    initial: DebateStance
    final: DebateStance
    changed: boolean
    confidenceBefore?: number
    confidenceAfter?: number
    /** required: user must provide a one-line reason */
    userReason: string
  }

  debate: DebateRecord
  thinkingSnapshot: ThinkingPatternSnapshot

  personalizationSignals: {
    extractedKeywords: string[]
    argumentStyles: ArgumentStyle[]
  }

  shareCard?: {
    title: string
    subtitle: string
    quote: string
  }
}

// ===== Weekly Reflection =====

export interface WeeklyReflection {
  weekStart: string // YYYY-MM-DD (Monday)
  weekEnd: string
  completedDays: number
  streak: number
  mostDiscussedCategory: DailyCategory
  dominantAxis: AxisId
  mostVolatileAxis: AxisId
  stanceChangeRate: number // 0-1
  clarityScore: number // 0-100
  clarityCurve: number[] // 7 values, one per day
  summary: string // AI-generated one-line
  representativeCardIds: string[] // up to 3
}
```

## API 调用流程（30-45s 目标）

```
┌─────────────────────────────────────────────────┐
│ Step 0: 用户打开 Daily Challenge                   │
│   本地: 从 IndexedDB 取最近 8-12 张卡摘要           │
│   本地: 取用户 category 偏好权重                    │
│   本地: 取最近 7 天 topic IDs（排重用）              │
├─────────────────────────────────────────────────┤
│ Step 1: Topic Generation（小模型，1 次调用）        │
│   输入: dateSeed + categories + history digest    │
│         + exclusion list                         │
│   输出: 3 个 TopicCandidate JSON                  │
│   耗时: ~3-5s                                    │
├─────────────────────────────────────────────────┤
│ Step 2: 用户交互（不计入 API 时间）                 │
│   - 看 3 个题目，选 1 个（或换一批）                │
│   - 选立场 (support / oppose / mixed)             │
│   - 输入一句话原因                                │
├─────────────────────────────────────────────────┤
│ Step 3: Debate（2 次并行调用）                     │
│   Pro model: opening + anticipated rebuttal      │
│   Con model: opening + anticipated rebuttal      │
│   限制: 90-120 字 + 3 bullet + 1 最强反击          │
│   耗时: ~8-15s (并行)                             │
├─────────────────────────────────────────────────┤
│ Step 4: Moderator + Tagger（1 次调用，合并）        │
│   输入: pro/con output + user stance + reason     │
│   输出: takeaway JSON + thinkingSnapshot JSON     │
│   耗时: ~5-10s                                   │
├─────────────────────────────────────────────────┤
│ Step 5: 本地保存                                  │
│   - 构建 OpinionCard                             │
│   - 写入 IndexedDB                               │
│   - 提取 personalizationSignals 回写              │
│   耗时: <100ms                                   │
└─────────────────────────────────────────────────┘
总 API 调用: 3 次（1 generator + 2 parallel debaters + 1 moderator/tagger）
总耗时目标: 16-30s API + 用户交互时间
```

## 话题系统

### Seed Tension 库（96 个）

每个 category 16 个母题张力，格式：

```json
{
  "id": "tech-001",
  "category": "tech",
  "tensionA": "效率",
  "tensionB": "深度",
  "template": "{tensionA} vs {tensionB}：在 {context} 场景下，哪个更值得追求？",
  "tags": ["productivity", "quality"]
}
```

AI 改写规则：小模型拿到 seed tension + 用户历史关键词 → 生成具体话题。

### 个性化链路

```
Layer 1: Category 偏好（首次 onboarding 选 1-3 个）
Layer 2: 本地 digest（最近 8-12 张卡的 keywords + stances + argumentStyles）
Layer 3: Topic generation prompt 注入:
  - "优先命中用户偏好 category"
  - "避开最近 7 天已用角度"
  - "参考用户论证风格"
  - "每 3 天强制跨 category 探索一次"（防过拟合）
```

## Weekly Reflection 计算

```
日向量: v_d = [axis1_score, axis2_score, axis3_score, axis4_score]  (0-100 each)
周均值: meanAxis[i] = avg(v_d[i] for d in week)
摆动:   swingAxis[i] = stddev(v_d[i] for d in week)
清晰度: clarity_d = round(100 * avg(abs(v_d[i] - 50)) / 50)
平滑:   clarity_ema = 3-day EMA of clarity_d
主导轴: argmax(abs(meanAxis[i] - 50))
最大摆动轴: argmax(swingAxis[i])
```

## 文件清单（预估）

### 新增文件

| 文件 | 用途 |
|------|------|
| `src/stores/dailyChallenge.ts` | 辩论流程状态 + IndexedDB 持久化 |
| `src/views/DailyChallengeView.vue` | 主视图 |
| `src/components/challenge/TopicPicker.vue` | 3 题选 1 + 换题 |
| `src/components/challenge/StanceInput.vue` | 选立场 + 一句话原因 |
| `src/components/challenge/DebateStage.vue` | 正反方辩论展示 |
| `src/components/challenge/ResultCard.vue` | moderator 总结 + 思维快照 |
| `src/components/challenge/OpinionCardView.vue` | 保存后的卡片视图 |
| `src/components/challenge/WeeklyReflection.vue` | 周度回顾卡 |
| `src/components/challenge/ClarityChart.vue` | 清晰度曲线图 |
| `src/features/challenge/topicSeeds.json` | 96 个 seed tension |
| `src/features/challenge/prompts.ts` | 4 个 prompt template |
| `src/features/challenge/types.ts` | 上述 TypeScript 类型 |
| `src/features/challenge/reflection.ts` | 周度计算逻辑 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/router.ts` | 添加 /challenge 路由 |
| `src/components/layout/IOSTabBar.vue` | 添加 Challenge tab |
| `src/components/layout/Sidebar.vue` | 添加 Challenge 入口 |
| `src/App.vue` | 注册新 store |

## Prompts 契约（4 个）

### 1. topic-generator

输入: dateSeed, categories, historyDigest, exclusions
输出: `{ candidates: TopicCandidate[3] }`
限制: 只返 JSON，不要解释

### 2. debater (pro/con 共用，stance 参数化)

输入: topic, stance, userReason
输出: 90-120 字正文 + 3 个 bullet point + 1 个最强反击
限制: 不超过 150 字总长

### 3. moderator-tagger (合并)

输入: proOutput, conOutput, userStance, userReason, topicContext
输出: `{ takeaway: DebateTakeaway, thinkingSnapshot: ThinkingPatternSnapshot }`
限制: 只返 JSON，snapshot 必须含 disclaimer label

### 4. weekly-reflector

输入: 7 张 OpinionCard 摘要
输出: 一句话周度回顾
限制: ≤ 50 字
