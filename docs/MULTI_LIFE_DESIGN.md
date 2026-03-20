# 多重人生 (Multi-Life) — 产品设计文档

> 版本: v0.1 Draft
> 日期: 2026-03-20
> 定位: SparkRing Play Mode — AI 多角色推理交互体验
> 核心卖点: **多模型即角色，模型差异即游戏性**

---

## 1. 一句话

> 同一个案件，3 个 AI 角色（不同模型）各执一词，你通过质疑和信任推进叙事，最终还原属于你的真相。

---

## 2. 为什么做这个

| 已有模式 | 缺失的体验 |
|---------|-----------|
| Story Live（剧情共演） | 线性叙事，没有分支选择 |
| Turtle Soup（海龟汤） | 只能 yes/no，没有多角色对抗 |
| Story Lite（冒险模式） | 单线冒险，没有推理博弈 |
| Case Reconstruction（案件重构） | 太重太复杂，7 阶段状态机 + 打分系统 |

多重人生填补的是：**多模型角色驱动 + 分支叙事 + 推理博弈 + 交互极简**。

---

## 3. 核心设计原则

### 3.1 多 AI 参与是灵魂（非可选）

**每个角色必须绑定不同的 AI 模型**。这不是装饰——模型本身的差异（逻辑严谨度、创造力、信息密度）就是游戏性的来源：

- **逻辑型模型**（如 Claude）：证词严谨、细节准确，但可能隐瞒关键信息
- **创意型模型**（如 GPT）：描述生动、提供新视角，但可能添油加醋
- **轻量模型**（如 小模型）：回答简短直白，可能遗漏关键细节但不会编造

同一案件换一组模型 = 完全不同的游戏体验。这就是 SparkRing 区别于任何独立 AI 产品的核心差异。

### 3.2 交互必须极简

每轮玩家只需要做一个决策：**质疑** 或 **接受**。

- 不需要拖拽、连线、打分、填写推理
- 不需要管理背包/证据板
- 所有证据自动收集，玩家只需"听"和"判断"
- 适合移动端单手操作

### 3.3 没有失败，只有"你的版本"

不设分数、不设对错。最终生成"你版本的真相"并排展示"标准真相"。偏了 5 步也是一次完整体验，甚至比"完美通关"更有分享欲。

---

## 4. 游戏机制

### 4.1 角色系统

每个案件有 3 个固定角色，**每个角色绑定一个不同的 AI 模型**：

```
角色 A（如"目击者"）→ 模型 1 → 有视觉信息但可能看错
角色 B（如"嫌疑人"）→ 模型 2 → 知道真相但可能隐瞒/编造
角色 C（如"调查员"）→ 模型 3 → 有专业分析但可能推断错误
```

角色设定由案件决定（不同案件 = 不同角色身份），但以下属性是通用的：
- **可靠性**：每个角色有隐藏的真实可靠度（玩家不知道）
- **隐藏信息**：每个角色知道的真相比例不同
- **说谎倾向**：某些角色在特定轮次会被 prompt 指令"隐瞒"或"误导"

### 4.2 核心循环：一轮（Round）

```
┌─────────────────────────────────────────┐
│  1. 场景描述                              │
│     （AI 叙事者描述当前发生什么）            │
│                                          │
│  2. 三角色证词（并行生成，同时展示）         │
│     ┌──────┐ ┌──────┐ ┌──────┐          │
│     │ 目击者│ │ 嫌疑人│ │ 调查员│          │
│     │ 模型1 │ │ 模型2 │ │ 模型3 │          │
│     └──────┘ └──────┘ └──────┘          │
│                                          │
│  3. 矛盾检测                              │
│     → 有矛盾：高亮显示，进入裁决模式       │
│     → 无矛盾：自动推进，无需操作           │
│                                          │
│  4. 玩家决策（仅在有矛盾时）               │
│     → [接受] 继续当前叙事                  │
│     → [质疑 X] 挑战某个角色的说法          │
│                                          │
│  5. 结果                                  │
│     → 接受：按所选路径推进，获得证据卡      │
│     → 质疑：被质疑角色补充更多信息          │
│       （可能是真话，也可能编更多）          │
└─────────────────────────────────────────┘
```

**关键：玩家不是每轮都要操作。** 只有三角色出现矛盾时才需要裁决。没有矛盾的轮次自动推进，保持节奏感。

### 4.3 矛盾触发机制

**不是随机矛盾。** 案件预设"矛盾点"（Contradiction Point），按轮次释放：

```
第 1-2 轮：角色各说各的，无矛盾（建立信任阶段）
第 3 轮：第一次矛盾（轻度，某个细节对不上）
第 5 轮：第二次矛盾（中度，关键事实冲突）
第 7 轮：第三次矛盾（重度，直接指向真相）
```

矛盾检测由 prompt 控制，不需要 LLM 独立判断——在 prompt 中告诉角色"你知道 X 事实，但基于你的角色设定你应该说 Y"。

### 4.4 质疑机制

**质疑次数有限**（每个案件 3-5 次），用完只能"接受"。

质疑的后果由 AI 角色的**隐藏可靠度**决定：
- 质疑了说真话的角色 → 角色委屈但给出更多信息（正面）
- 质疑了说谎的角色 → 角色可能圆谎（更深的假线索）或崩溃说出真话（高风险高回报）
- 质疑了不可靠的角色 → 什么有用的都得不到（浪费次数）

**玩家不知道可靠度，所以每次质疑都是在赌。**

### 4.5 证据卡

每轮结束后自动生成一张证据卡：
- 卡面：关键信息的一句话摘要
- 来源：哪个角色 / 哪个选择
- 标签：关键证据 / 可疑信息 / 已证伪

证据卡自动归入时间线，玩家不需要手动管理。时间线只在最后揭晓时展示。

### 4.6 结局：你的版本 vs 真相

游戏在 N 轮后（通常 7-10 轮）进入结局阶段：

1. **玩家提交推理**：用自然语言写"你认为发生了什么"（1-3 句话即可）
2. **AI 生成"你的版本"**：基于玩家所有选择生成的完整叙事
3. **AI 生成"真相版本"**：案件的标准真相
4. **并排展示**：你的版本 | 真相版本 | 偏差分析
5. **未探索分支**：展示你没走的 1-2 条关键分支"如果当时你质疑了 X，会发现..."

没有分数，没有胜负。只有"你的版本"——可以保存、分享。

### 4.7 可复玩性

同一案件 × 不同模型组合 = 不同体验：
- 换掉"嫌疑人"的模型 → 说谎风格变了 → 矛盾点不同
- 换掉"目击者"的模型 → 记忆细节不同 → 线索方向不同
- 3 个模型全换 → 几乎是全新的游戏

---

## 5. 数据模型

```typescript
interface MultiLifeCase {
  id: string
  title: string                          // 案件标题
  premise: string                        // 开场白（"暴雨夜，仓库门口..."）
  truth: string                          // 标准真相（AI 生成结局时用，玩家永远看不到）
  roles: MultiLifeRole[]                 // 3 个角色定义
  rounds: MultiLifeRoundConfig[]          // 每轮预设
  totalRounds: number                    // 总轮次（7-10）
  challengeBudget: number                // 质疑次数（3-5）
}

interface MultiLifeRole {
  id: string
  name: string                           // 角色名（如"目击者 张三"）
  archetype: 'witness' | 'suspect' | 'analyst' | 'insider' | 'innocent'
  reliability: number                    // 隐藏可靠度 0-1（玩家不可见）
  hiddenKnowledge: number                 // 知道真相的比例 0-1
  lyingPattern: 'never' | 'selective' | 'consistent' | 'increasing'
  personality: string                    // 角色性格描述（注入 prompt）
  systemPrompt: string                   // 完整 system prompt
}

interface MultiLifeRoundConfig {
  roundNumber: number
  scene: string                          // 场景描述
  contradictions?: ContradictionPoint[]  // 本轮预设矛盾（可选）
  roles: {
    [roleId: string]: {
      directive: string                  // 本轮给角色的指令（"你应该说 X 但假装 Y"）
      lying: boolean                     // 本轮是否在说谎
    }
  }
}

interface ContradictionPoint {
  betweenRoles: [string, string]         // 哪两个角色矛盾
  topic: string                          // 矛盾点（"关于案发时间"）
  description: string                    // 矛盾描述
}

// 运行时状态
interface MultiLifeSession {
  caseId: string
  currentRound: number
  challengeRemaining: number             // 剩余质疑次数
  trustMap: Record<string, number>        // roleId → 信任度（-1 到 +5）
  choices: PlayerChoice[]                // 所有历史选择
  evidenceCards: EvidenceCard[]          // 收集的证据
  phase: 'prologue' | 'investigation' | 'resolution' | 'ended'
  ending?: SessionEnding                 // 结局数据
}

interface PlayerChoice {
  round: number
  type: 'accept' | 'challenge'
  challengedRoleId?: string              // 质疑了谁
  narrativePath: string                   // 导致的叙事分支标识
}

interface EvidenceCard {
  id: string
  round: number
  source: string                         // 来源角色名
  summary: string                        // 一句话摘要
  tag: 'key' | 'suspicious' | 'debunked' | 'ambiguous'
}

interface SessionEnding {
  playerNarrative: string                 // AI 生成的"你的版本"
  truthNarrative: string                  // 标准真相
  deviationAnalysis: string               // 偏差分析
  unexploredBranches: string[]            // 未探索的关键分支
}
```

---

## 6. 技术架构

### 6.1 与现有代码的关系

多重人生是 **Story Live 的结构化变体**，不是从零构建：

| Story Live | 多重人生 |
|-----------|---------|
| 3 角色（logic/emotion/twist） | 3 角色（案件角色 A/B/C） |
| 每轮 3 个并行生成 | 每轮 3 个并行生成（相同机制） |
| 用户自由输入动作 | 用户选择"质疑"或"接受"（更简单） |
| twist 条件触发 | 矛盾点预设触发（更可控） |
| tension 弧线检测结局 | 轮次耗尽 → 结局 |
| director memory | 分支状态追踪（类似） |
| useStoryFlow composable | 复用，改结局确认逻辑 |

**可以直接复用的模块：**
- `features/play-modes/shared/` — envelope 类型、phase guard
- `stores/storyLive.ts` 的并行生成机制（`generateRole` + `streamModelChat`）
- `stores/story-live-helpers.ts` 的 envelope/memory 构建
- `views/StoryLiveView.vue` 的三栏角色卡片布局

**需要新建/改动的：**
- `features/multi-life/` — 案件数据结构 + prompt 模板
- `stores/multiLife.ts` — 分支状态管理 + 信任度 + 矛盾判定
- `views/MultiLifeView.vue` — UI（比 StoryLive 更简单，因为交互更少）
- `components/multi-life/` — 证据卡、矛盾高亮、结局对比

### 6.2 模型分配策略

复用 `story-live-helpers.ts` 的 `chooseModelIds()`，但加一个约束：**三个角色必须用不同的 provider**。

```typescript
function chooseCaseModels(appStore): MultiLifeModelAssignment {
  // 1. 优先用户已选的 3 个不同 provider 的模型
  // 2. 其次自动分配：选 3 个不同 provider 的 top model
  // 3. 保证角色 A/B/C 绑定的是不同模型
}
```

### 6.3 Prompt 设计

**叙事者 System Prompt（场景描述）：**
```
你是一个叙事者。根据案件设定和当前进度，用 2-3 句话描述当前场景。
不要暗示任何线索或真相，只描述氛围和事件进展。
保持客观、冷静的语气。
```

**角色 System Prompt（每个角色不同，但共享模板）：**
```
你是{role.name}，{role.personality}。

关于{case.premise}，你知道以下事实：{role.knownFacts}。
但在本轮中，你的指令是：{round.roles[role.id].directive}。

规则：
- 用第一人称说话，保持角色性格
- 不要直接说出真相，除非被质疑且角色可靠度要求
- 如果被质疑且在说谎，可以选择圆谎或崩溃说出部分真话
- 每次回复不超过 80 字
```

**矛盾检测（不需要 LLM，在 prompt 层控制）：**
- 案件预设矛盾点，注入到对应角色的 prompt 中
- 例如角色 A 的 prompt："你说案发时间是 9 点"，角色 B 的 prompt："你说案发时间是 11 点"
- UI 层做关键词匹配高亮矛盾

**结局生成 Prompt：**
```
基于以下游戏记录：
- 玩家做了 {n} 次选择，其中 {m} 次质疑
- 信任度最高的角色是 {topRole}
- 收集的证据卡：{evidenceCards}

生成"玩家的真相版本"：一个 3-5 句的完整叙事，
反映玩家选择所导致的"他们认为发生了什么"。
这个版本应该合理但不一定完全正确——取决于玩家是否识破了说谎者。
```

---

## 7. 案件内容设计

### 7.1 首批案件（3 个）

| # | 标题 | 类型 | 难度 | 轮次 |
|---|------|------|------|------|
| 1 | 暴雨仓库 | 经典推理 | 入门 | 7 |
| 2 | 最后一条消息 | 社交推理 | 中等 | 8 |
| 3 | 不在场证明 | 法律推理 | 困难 | 10 |

### 7.2 案件数据结构

每个案件是一个 JSON/TS 文件，包含：
- `premise`：开场白
- `truth`：标准真相
- `roles[3]`：角色定义（名字、性格、可靠度、隐藏信息、说谎模式）
- `rounds[N]`：每轮预设（场景、矛盾点、角色指令）

案件数据不需要硬编码在代码里——可以从本地 JSON 加载，后续可以扩展为在线案件库。

---

## 8. UI 设计要点

### 8.1 主界面

```
┌────────────────────────────────────┐
│  [案件标题]     第 3/8 轮   质疑 ⊕3 │  ← 顶栏
├────────────────────────────────────┤
│                                    │
│  🌧️ 暴雨夜的仓库里，三个人被        │  ← 场景描述
│  带到警局分别问话...               │
│                                    │
├────────┬────────┬────────────────┤
│ 目击者 │ 嫌疑人 │ 调查员           │
│ 张三   │ 李四   │ 王警官           │  ← 三个角色
│ 🟢 Claude│ 🟢 GPT │ 🟢 Gemini       │     (模型标签)
│        │        │                  │
│ "我当时看到│ "我一直在│ "根据物证，    │
│  一个黑影在│ 家里看电视│ 凶器上只有    │  ← 证词
│  仓库门口│ 根本没有出│ 死者的指纹，  │
│  一闪而过"│ 门"        │ 这很可疑"    │
│        │        │                  │
│        │ ⚡ 矛盾！│                  │  ← 矛盾高亮
├────────┴────────┴────────────────┤
│                                    │
│   [ 接受 ]    [ 质疑嫌疑人 ]        │  ← 唯一操作
│                                    │
├────────────────────────────────────┤
│ 📌 案发时间不确定 (第2轮收集)       │  ← 证据卡流
│ 📌 仓库门没有破坏痕迹 (第1轮)       │
└────────────────────────────────────┘
```

### 8.2 结局对比界面

```
┌─────────────────┬─────────────────┐
│   你的版本       │   真相          │
├─────────────────┼─────────────────┤
│                 │                 │
│  李四在家中看    │  李四在仓库实    │
│  电视，案发时    │  施了犯罪，张三   │
│  不在现场。张三   │  看到的是李四     │
│  的证词和物证    │  而不是"黑影"。   │
│  都指向李四...   │  王警官的分析     │
│                 │  是正确的...       │
│                 │                 │
├─────────────────┴─────────────────┤
│ 💡 你在第 3 轮质疑了张三（目击者）│
│    但张三其实说了真话。你全程信任  │
│    李四（凶手），最终推理偏移 3 步  │
│                                 │
│ 🔀 如果你当时质疑了李四...         │
└────────────────────────────────────┘
```

### 8.3 移动端适配

- 三个角色卡片在移动端纵向堆叠
- "接受/质疑"按钮固定在底部
- 证据卡流在底部可展开
- 全程单手可操作

---

## 9. 与 Story Live 的代码复用清单

| 模块 | 复用方式 |
|------|---------|
| `features/play-modes/shared/` | 直接复用（envelope 类型、phase guard） |
| `stores/story-live-helpers.ts` | 复用 `chooseModelIds`, `createEnvelope`, `getMeta`, `cloneForStorage`, `persist` |
| Story Live 的 `generateRole()` | 复用并行生成机制，改 prompt |
| Story Live 的三栏布局 | 复用 CSS/Tailwind，改内容 |
| `useStoryFlow.ts` | 复用结局确认流程，改 ending 类型 |
| `buildDirectorMemory()` | 改为 `buildBranchMemory()`，追踪分支状态 |
| `validateByRole()` | 移除（多重人生不需要角色输出校验） |

不需要复用的：
- `twist-trigger.ts`（矛盾机制是预设的，不是启发式的）
- `state-utils.ts`（没有 tension/entity 追踪）
- `validation.ts`（无角色输出校验需求）

---

## 10. 参考文件路径

### 现有代码（可复用）
- `apps/web-v2/src/features/play-modes/shared/` — 共享类型框架
- `apps/web-v2/src/features/play-modes/story-live/` — Story Live（核心参考）
- `apps/web-v2/src/stores/storyLive.ts` — Store（并行生成机制）
- `apps/web-v2/src/stores/story-live-helpers.ts` — 辅助函数
- `apps/web-v2/src/views/StoryLiveView.vue` — View（三栏布局参考）

### 需要新建
- `apps/web-v2/src/features/multi-life/types.ts` — 类型定义
- `apps/web-v2/src/features/multi-life/prompts.ts` — Prompt 模板
- `apps/web-v2/src/features/multi-life/cases/` — 案件数据
- `apps/web-v2/src/stores/multiLife.ts` — Store
- `apps/web-v2/src/views/MultiLifeView.vue` — View
- `apps/web-v2/src/components/multi-life/` — 组件
