# StoryLite V2 - 假如模拟器（多 AI 共演版）

## 设计理念

**差异化定位：**

| 模式 | AI 数量 | AI 角色关系 | 用户角色 | 核心体验 |
|------|--------|------------|---------|---------|
| **Story Live** | 3 个固定 | 同一剧情的不同副轨（主镜头/情绪/异动） | 主角 | 分层叙事 |
| **Multi-Life** | 3 个角色 | 证人/嫌疑人（互相对立） | 调查员 | 找矛盾 |
| **StoryLite V2** | 3 个角色 | 引路人/伙伴/变量（互补） | 参与者 | 选择回应谁 |
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
│  "地址在老城区，距离 2.3 公里。建议尽快前往。"  │
│  职责：任务指引、背景信息、目标设定           │
│                                             │
│  AI 2 (GPT-4) → 伙伴 (Partner)             │
│  "等等...你有没有觉得有人在盯着我们？"        │
│  职责：情感支持、担忧、人性视角              │
│                                             │
│  AI 3 (Gemini) → 变量 (Variable)           │
│  "那张纸条的背面，你翻过来看过了吗？"         │
│  职责：悬念、转折、不确定因素                │
└─────────────────────────────────────────────┘
           ↓
    用户选择回应其中一个 AI
           ↓
    剧情根据选择分支推进
```

### 2. 角色定义

```typescript
// 引路人 - 冷静专业的指引者
guide: {
  label: '引路人',
  title: '任务指引',
  accent: 'text-cyan-400',
  systemPrompt: `给用户提供任务目标、方向指引、背景信息...`
}

// 伙伴 - 有情感支持的同行者
partner: {
  label: '伙伴',
  title: '同行伙伴',
  accent: 'text-rose-400',
  systemPrompt: `作为用户的搭档、队友、朋友，提供情感支持...`
}

// 变量 - 神秘的不确定因素
variable: {
  label: '变量',
  title: '未知变量',
  accent: 'text-amber-400',
  systemPrompt: `扮演神秘人、意外因素、剧情转折触发器...`
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
| **Demo 模式** | 预设 `mock-1/2/3` | 查表 `STORY_LITE_V2_MOCK_SCENES` | 查表 `STORY_LITE_V2_BRANCHES` |
| **真实 AI** | 用户选择的 3 个模型 | AI 实时生成 | AI 生成选择 + 用户决定 |

### UI 提示

**Demo 模式：**
```
┌────────────────────────────────────┐
│ Demo Mode · 当前显示预设剧情数据    │
│ 配置真实 API Key 后体验完整 AI 生成  │
└────────────────────────────────────┘
```

**真实 AI 模式：**
```
┌────────────────────────────────────────────┐
│ AI 已就绪                                   │
│ 引路人：Claude Sonnet 4 · 伙伴：GPT-4.1 · 变量：Gemini │
└────────────────────────────────────────────┘
```

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
start (十字路口)
├── check-paper (回应变量) → check-paper 场景
│   ├── find-bank (回应引路人) → ending-good
│   ├── ask-variable (回应变量) → ending-mystery
│   └── calm-partner (回应伙伴) → ending-normal
│
├── follow-address (回应引路人) → follow-address 场景
│   ├── knock-door (回应引路人) → ending-good
│   ├── sneak-in (回应变量) → ending-bad
│   └── reassure-partner (回应伙伴) → ending-normal
│
└── look-around (回应伙伴) → look-around 场景
    ├── follow-him (回应变量) → ending-mystery
    ├── ignore-continue (回应引路人) → ending-normal
    └── protect-partner (回应伙伴) → ending-good
```

---

## UI 布局

### 左侧：AI 回复区
- 情境描述
- 3 个 AI 回复卡片（不同颜色区分）
  - 引路人（青色）- 冷静分析
  - 伙伴（粉红色）- 情感表达
  - 变量（琥珀色）- 神秘暗示
- 历史记录（最近 3 个选择）

### 右侧：选择区
- 行动选项（3 个）
- 风险等级标识
- 回应对象提示
- 结局展示（完成后）

---

## 与 Story Live 的区别

| 维度 | Story Live | StoryLite V2 |
|------|-----------|-------------|
| AI 输出 | 分层（主剧情 + 情绪 + 异动） | 分角色（3 个独立人格） |
| 用户输入 | 自由输入动作 | 选择回应哪个 AI + 动作 |
| 复杂度 | 高（有 state 管理） | 低（纯分支叙事） |
| 定位 | 深度共演体验 | 轻量快节奏体验 |
| 回合数 | 不限 | 3-5 回合 |

---

## 下一步开发

### Phase 1: Mock 验证（已完成）
- [x] 多 AI 角色类型定义
- [x] 角色 system prompt
- [x] Mock 场景数据（4 个场景 × 3 个选择）
- [x] 分支映射表
- [x] UI 组件

### Phase 2: AI 集成（待开发）
- [ ] 集成真实 AI 调用
- [ ] 模型分配逻辑（沿袭 Story Live）
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
