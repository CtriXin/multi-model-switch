# StoryLite V2 - 假如模拟器（多 AI 共演版）

## 设计理念

**差异化定位：**

| 模式 | AI 数量 | AI 角色关系 | 用户角色 | 核心体验 |
|------|--------|------------|---------|---------|
| **Story Live** | 3 个固定 | 同一剧情的不同副轨（主镜头/情绪/异动） | 主角 | 分层叙事 |
| **Multi-Life** | 3 个角色 | 证人/嫌疑人（互相对立） | 调查员 | 找矛盾 |
| **StoryLite V2** | 3 个角色 | 引路人/伙伴/变量（互补） | 参与者 | 选择站在哪种判断上继续前进 |
| **Daily Challenge** | 1 个 | 对手 | 辩手 | 对抗辩论 |

---

## 核心特性

### 1. 三 AI 共演架构

```
用户输入："假如我是特工，拿到了一份机密文件"

┌─────────────────────────────────────────────┐
│  3 个 AI 同时扮演不同角色                      │
├─────────────────────────────────────────────┤
│  AI 1 (Claude) → 引路人 (Guide)            │
│  "先稳住主控塔，这是阻止全城崩盘的主线。"      │
│  职责：主线推进、任务窗口、止损判断           │
│                                             │
│  AI 2 (GPT-4) → 伙伴 (Partner)             │
│  "可电话那头是你母亲，你真的要先放下她？"      │
│  职责：关系代价、情感压力、人性视角          │
│                                             │
│  AI 3 (Gemini) → 变量 (Variable)           │
│  "第三信号比求救电话更早出现，有人故意布题。"   │
│  职责：异常细节、隐藏规则、第三种可能        │
└─────────────────────────────────────────────┘
           ↓
    用户决定继续相信哪一种判断框架
           ↓
    剧情根据选择分支推进
```

### 2. 角色定义

```typescript
// 引路人 - 主线推进
guide: {
  label: '引路人',
  title: '主线推进',
  accent: 'text-cyan-400',
  systemPrompt: `只关注主线目标、局势止损、任务窗口...`
}

// 伙伴 - 关系代价
partner: {
  label: '伙伴',
  title: '关系代价',
  accent: 'text-rose-400',
  systemPrompt: `提醒用户这次选择会伤害谁、失去谁、辜负谁...`
}

// 变量 - 异常变量
variable: {
  label: '变量',
  title: '异常变量',
  accent: 'text-amber-400',
  systemPrompt: `指出题面之外的不合理细节、隐藏规则或第三路径...`
}
```

### 3. 选择驱动

每个选项标注：
- **风险等级**: 安全 / 有风险 / 危险
- **回应对象**: 引路人 / 伙伴 / 变量（可选）
- **提示**: 可能的后果

```typescript
interface StoryLiteV2Choice {
  id: string
  label: string
  targetRole?: StoryLiteV2Role  // 回应哪个 AI
  risk: StoryLiteV2RiskLevel
  hint?: string
}
```

---

## Mock vs 真实 AI

### 检测逻辑

```typescript
// 检测是否在使用 demo 模型
function isUsingDemoModels(selectedModelIds: string[]): boolean {
  return selectedModelIds.every(id => id.startsWith('demo/'))
}

// demo 模型列表
const DEMO_MODELS = [
  'demo/claude-sonnet-4',
  'demo/gpt-4.1',
  'demo/gemini-2.5-pro',
  'demo/deepseek-r1',
  ...
]
```

### 行为差异

| 状态 | 模型分配 | 场景生成 | 选择分支 |
|------|---------|---------|---------|
| **Demo 模式** | 预设 demo 角色 | 根据 seed 生成 skeleton，角色回复走 mock | 查表 `STORY_LITE_V2_BRANCHES` |
| **Selected Live** | 当前选中的真实模型 | 场景骨架查表，角色回复实时生成 | 用户决定 |
| **Auto Live** | 自动从可用 provider 中补 3 个真实模型 | 场景骨架查表，角色回复实时生成 | 用户决定 |

### UI 提示

**Demo 模式：**
```
┌────────────────────────────────────┐
│ Demo Mode · 当前显示 seed-aware 骨架 │
│ 接入真实模型后，三位角色回复会实时生成 │
└────────────────────────────────────┘
```

**Selected Live：**
```
┌────────────────────────────────────────────┐
│ Live Multi-Model                            │
│ 引路人：Claude Sonnet 4                      │
│ 伙伴：GPT-4.1 · 变量：Gemini                │
└────────────────────────────────────────────┘
```

**Auto Live：**
```
┌────────────────────────────────────────────┐
│ Live Auto-Assign                            │
│ 未手动选模型时，优先从可用 provider 自动分配  │
└────────────────────────────────────────────┘
```

### 选择后的反馈策略

- 点击某个分叉后，页面会立刻进入下一幕场景骨架
- 三位角色的回复并行生成，而不是串行等待全部完成
- 左侧先展示新场景与角色卡占位，再逐个补全角色判断
- 右侧在分叉生成期间显示进度态，避免用户误以为点击无效或页面卡死

### 开场输入策略

- 输入框为空时，会显示一个“直接试试当前示例”的快捷入口
- 点击该入口会直接采用当前轮播 placeholder 作为 seed 并开局
- 用户仍然可以手动输入自己的高压两难，不会被示例覆盖
- 即使在 demo 模式下，首幕场景和分叉骨架也会跟随 seed 变化，不再固定为同一套文案

---

## 技术实现

### 文件结构

```
src/features/play-modes/story-lite-v2/
├── types.ts       # 类型定义 + 角色元数据
├── prompts.ts     # Prompt 构建 + Mock 数据 + 分支映射
└── index.ts       # 导出
```

### 数据结构

```typescript
interface StoryLiteV2Scene {
  id: string
  chapter: string
  title: string
  premise: string                    // 当前情境
  responses: StoryLiteV2Response[]   // 3 个 AI 的回复
  choices: StoryLiteV2Choice[]       // 玩家选项
  ending?: { ... }
}

interface StoryLiteV2Response {
  role: StoryLiteV2Role              // guide / partner / variable
  modelId: string
  modelName: string
  text: string
  tone?: string                      // 语气提示
}
```

### Mock 分支示例

```
start (双重求救)
├── secure-shield (主线推进) → secure-shield 场景
│   ├── reroute-shield → ending-normal
│   ├── call-mother → ending-good
│   └── open-maintenance-path → ending-mystery
│
├── save-mother (关系代价) → save-mother 场景
│   ├── borrow-substation → ending-good
│   ├── extract-now → ending-normal
│   └── follow-red-led → ending-bad
│
└── trace-signal (异常变量) → trace-signal 场景
    ├── decode-route → ending-good
    ├── return-mainline → ending-bad
    └── keep-mother-awake → ending-mystery
```

---

## UI 布局

### 左侧：AI 回复区
- 情境描述
- 3 个 AI 回复卡片（不同颜色区分）
  - 引路人（青色）- 主线推进
  - 伙伴（粉红色）- 关系代价
  - 变量（琥珀色）- 异常变量
- 每张卡片显示当前扮演该角色的模型名称

### 右侧：选择区
- 行动选项（3 个，分别代表你站向哪种判断）
- 风险等级标识
- 对应角色提示
- 结局展示（完成后）

---

## 与 Story Live 的区别

| 维度 | Story Live | StoryLite V2 |
|------|-----------|-------------|
| AI 输出 | 分层（主剧情 + 情绪 + 异动） | 分框架（主线 / 关系 / 变量） |
| 用户输入 | 自由输入动作 | 站队某一种判断并继续推进 |
| 复杂度 | 高（有 state 管理） | 低（快节奏命运分叉） |
| 定位 | 深度共演体验 | 高概念两难模拟 |
| 回合数 | 不限 | 3-5 回合 |

---

## 下一步开发

### Phase 1: Mock 验证（已完成）
- [x] 多 AI 角色类型定义
- [x] 角色 system prompt
- [x] Mock 场景数据（4 个场景 × 3 个选择）
- [x] 分支映射表
- [x] UI 组件

### Phase 2: AI 集成（进行中）
- [x] 集成真实 AI 调用（角色回复）
- [x] 模型分配逻辑（支持 selected live / auto live / demo）
- [ ] 动态生成场景和选择
- [ ] Session 持久化

### Phase 3: 增强体验（待开发）
- [ ] 更多角色类型（可切换）
- [ ] 角色好感度系统
- [ ] 成就系统
- [ ] 分享功能

---

## 代码示例

### 构建 Prompt

```typescript
// 每个 AI 角色独立的 prompt
buildStoryLiteV2SystemPrompt('guide')
// → "你是"假如模拟器"中的引路人角色..."

buildStoryLiteV2UserPrompt(
  '假如我是特工',
  1,
  '你站在十字路口...',
  { role: 'variable', label: '翻到纸条背面看看' }
)
```

### 分支逻辑

```typescript
const nextSceneId = STORY_LITE_V2_BRANCHES[currentSceneId]?.[choiceId]
// 简单的查表式分支，无复杂状态机
```

---

## 总结

**StoryLite V2 的核心价值：**
1. **多 AI 但不复杂** - 3 个 AI 同时输出，但 UI 清晰
2. **选择有指向性** - 回应不同 AI = 不同剧情走向
3. **轻量但完整** - 3-5 回合一局，有完整起承转合
4. **差异化定位** - 介于 Story Live（深度）和 Chat（单 AI）之间
