# MMS 改动交接文档（Handoff to Claude）

> **文档用途**：用于将 2026-09-15（5.0.0 发布）至 2026-09-16（当前最新 `dev-pre`）期间的所有改动完整同步给 Claude / 协作者。包含改动背景、根因分析、涉及文件、核心逻辑实现、新增测试及验证结果。

---

## 📌 1. 改动总览与版本上下文

- **目标仓库**：`multi-model-switch (MMS)`
- **当前开发分支**：`dev-pre`（Tracking `origin/dev-pre`）
- **基准起点**：`74295c8b`（5.0.0 正式发版 Merge PR #267）
- **发版节点**：`8fc1adf8` / `0aab7215`（5.0.1 Preview 紧急修复发版 Merge PR #269）
- **最新提交**：`6d9001d6`
- **累计文件变动**：17 个文件（+861 / -120 行），全量 121 项前端单测 + 68 项 Python pytest 全部 100% 通过。

---

## 📦 2. 改动模块详解

### 第一部分：v5.0.1 紧急修复项（Commit: `8fc1adf8`）

#### 1. 设置页滚动条遮挡底部保存按钮
* **问题**：在某些分辨率和系统滚动条常驻模式下，设置页面的右侧滚动条通栏覆盖了底部 sticky 的保存操作栏，导致保存按钮右侧被截断或不易点击。
* **修改文件**：`apps/mms-web/src/styles.css`
* **处理方案**：为滚动容器增加底部内边距与横向避让内边距，确保 sticky 保存栏拥有独立的 z-index 与完整可视宽度。

#### 2. Bot 对话界面中停止/重试位置及弹窗样式
* **问题**：在 Bot 处于 waiting 或 error 阶段时，停止/重试操作条脱离底部视口基准线，弹窗层叠上下文在某些缩放比下被截断。
* **修改文件**：`apps/mms-web/src/Bot.tsx`, `apps/mms-web/src/bot.css`, `apps/mms-web/src/quick-model.css`
* **处理方案**：重构操作栏的固定与弹性定位，修正 z-index 隔离，保证多状态下操作条稳定停靠在输入框上方。

---

### 第二部分：v5.0.1 之后的体验与功能增强（Commit: `5be8649a` -> `6d9001d6`）

#### 模块 A：Bot 侧边抽屉面板 Click Outside / Escape 关闭与脏表单安全守卫
* **Commit**：`5be8649afb09b14ade5785a5de97fa698a300c8c`
* **涉及文件**：
  - `apps/mms-web/src/BotPresetPanel.tsx`（工作预设面板）
  - `apps/mms-web/src/BotMemoryPanel.tsx`（记忆面板）
  - `apps/mms-web/src/BotCommunications.tsx`（协作面板）
  - `apps/mms-web/src/Bot.tsx`
  - `apps/mms-web/tests/bot-preset-outside-close.test.mjs`（新增单测）
* **核心逻辑**：
  1. **点击外部与 Escape 监听**：抽屉面板监听全局 `mousedown` 与 `keydown`，点击面板外部空白区域或按 `Escape` 键自动收起。
  2. **触发按钮互斥排除**：排除触发按钮所在的 DOM（如 `.bot-meta-card`、头部预设入口），防止点击触发按钮时因外部点击与按钮点击冲突导致状态“闪关又开”。
  3. **脏表单（`isDirty`）防误触守卫**：
     - 若表单内容未改动，直接秒关；
     - 若用户在预设面板中有正在编辑且尚未点击“保存”的未保存修改，弹出确认提示框（`confirm`）防止用户因误触背景导致输入丢失。

---

#### 模块 B：Bot 回复纯文本选项自动转可点击胶囊按钮 & 配置直达
* **Commit**：`f8c21cb2528e9459096e15e660b1bad0665acc8c`
* **涉及文件**：
  - `apps/mms-web/src/bot-presets.ts`
  - `apps/mms-web/src/Bot.tsx`
  - `apps/mms-web/src/bot.css`
  - `apps/mms-web/tests/bot-message-options.test.mjs`（新增单测）
* **核心逻辑**：
  1. **选项提取与正文剥离（`parseMessageOptions`）**：
     - 智能识别 Bot 回复末尾的选项模式（如 `选项：[A] [B]`、`可选项：1. xxx | 2. yyy`、`[要] [不要]` 等）；
     - 从正文中自动剥离生硬的选项文字，避免重复展现。
  2. **交互胶囊按钮（`.bot-option-capsule`）**：
     - 在消息气泡正文下方渲染高亮可点击的快捷选项胶囊按钮；
     - 用户点击后自动组装并作为用户回复指令发送给 Bot，免去用户手动打字。
  3. **Web UI 配置直达**：
     - 识别 Bot 回复中引导用户前往 Web UI 配置预设/记忆的语义文本；
     - 在气泡下方渲染「打开工作预设与配置」快捷入口按钮，点击直接唤起对应的侧边抽屉面板。

---

#### 模块 C：Pilot 主会话折叠思考过程增加工作状态指示器
* **Commit**：`8811476595562c5b7414df8343eb259d048408f6`
* **涉及文件**：
  - `apps/mms-web/src/SessionStatus.tsx`
  - `apps/mms-web/src/Transcript.tsx`
  - `apps/mms-web/src/transcript.css`
  - `apps/mms-web/tests/turn-working-status.test.mjs`（新增单测）
* **核心逻辑**：
  1. **背景痛点**：用户在 Pilot 提问后点击“收起过程”，此时后端还在执行工具调用或思考，导致折叠条下方出现大片完全空白的留白区。
  2. **新增 `TurnWorkingStatus` 组件**：
     - 当会话活跃且尚未产生最终答案时，若过程被折叠或尚未产出过程，在回答位置渲染优雅的工作状态占位卡片；
     - 保持与最终回答一致的左侧头像与模型作者信息（如 `Pilot · claude-3-7-sonnet`）。
  3. **状态文案动态化（`turnWorkingHint`）**：
     - 思考中：`正在思考…`
     - 工具调用中：`正在执行工具 · <toolName>`（如 `正在执行工具 · read_file`）
     - 输出中：`正在输出回复…`
     - 等待审批：`等待确认工具操作`

---

#### 模块 D：折叠条后台运行脉冲点与流式正文提前呈现
* **Commit**：`6d9001d67067fc4d9e525a74659bf5a452ef3225`
* **涉及文件**：
  - `apps/mms-web/src/Transcript.tsx`
  - `apps/mms-web/src/transcript.css`
  - `apps/mms-web/tests/turn-working-status.test.mjs`
* **核心逻辑**：
  1. **流式正文提前捕获（`findActiveAnswer`）**：
     - 原逻辑中，只要会话未标记 `completed`，即使 17 次工具已跑完并开始打字输出正文，这段正文也会被错误算入 `process` 并在折叠状态下被吞没。
     - 现通过 `findActiveAnswer(events)` 检查最后一个 tool 之后是否有正在流式输出的 assistant 文本，若有则提前提升为 `answer` 渲染，使文字能实时流式打字展现。
  2. **折叠条运行态微点（`.turn-process-live-dot`）**：
     - 会话执行期间，折叠条按钮（`> 展开过程 17 次工具调用`）右侧显示 `var(--accent)` 微型呼吸脉冲点，提示过程正在后台活跃产出。
  3. **像素级对齐与移动端适配**：
     - 严格对齐会话流 `39px` 基准线（头像 27px + 12px gap），回答生成切换时零抖动；
     - 胶囊采用圆润 `20px` border-radius 与半透明 soft/surface 背景，在窄屏（<= 600px）下施加 `max-width: 220px` 截断保护。

---

## 🔍 3. 关键代码变更对照

### A. 流式回答捕获与指示器渲染（`Transcript.tsx`）
```tsx
function findActiveAnswer(events: SessionEvent[]): SessionEvent | undefined {
  const lastAssistant = [...events].reverse().find(e => e.kind === "assistant" && !!e.text.trim());
  if (!lastAssistant) return undefined;
  const assistantIndex = events.indexOf(lastAssistant);
  const subsequentTools = events.slice(assistantIndex + 1).some(e => e.kind === "tool");
  if (subsequentTools) return undefined;
  return lastAssistant;
}

// 在 Turn 组件内：
const completedAnswer = completed ? [...events].reverse().find(e => e.kind === "assistant" && !!e.text.trim()) : undefined;
const streamingAnswer = !completed ? findActiveAnswer(events) : undefined;
const answer = completedAnswer || streamingAnswer;

const isWorking = !completed && !answer && (collapsed || !hasProcess);
const isRunning = !completed;

// 折叠控制条：
const controls = <button type="button" className="turn-process-toggle" aria-expanded={!collapsed} onClick={toggle}>
  {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
  {collapsed ? "展开过程" : "收起过程"}
  <span>{count ? `${count} 次工具调用` : "思考与执行记录"}</span>
  {isRunning && collapsed && <span className="turn-process-live-dot" title="正在执行中" aria-label="正在执行中" />}
  {!!failures && <span className="process-failure">{failures} 项失败</span>}
</button>;
```

### B. 状态提示推导（`SessionStatus.tsx`）
```ts
export function turnWorkingHint(session: Session, disconnected = false): string {
  if (disconnected) return "状态未同步，等待重新连接…";
  const { phase } = sessionStatus(session, disconnected);
  if (phase === "tool" && session.activity?.toolName) {
    return `正在执行工具 · ${session.activity.toolName}`;
  }
  if (phase === "waiting") {
    return session.activity?.method === "confirm" ? "等待确认工具操作" : "等待你的回答";
  }
  return activityHints[phase] || "正在处理中…";
}
```

### C. 选项文本解析提取（`bot-presets.ts`）
```ts
export function parseMessageOptions(text: string): { cleanText: string; options: string[] } {
  if (!text) return { cleanText: text, options: [] };
  // 识别选项：[A] [B] 或 选项：1. A | 2. B 等常见格式
  const optionRegex = /(?:(?:\r?\n)+|\b)(?:选项|可选|选择|options?)[：:]\s*([^\n\r]+)$/i;
  const match = text.match(optionRegex);
  if (!match) return { cleanText: text, options: [] };
  
  const rawOptions = match[1];
  const items = rawOptions.split(/[|/、,，\t]+|(?<=\])\s*(?=\[)/)
    .map(s => s.replace(/^[\[\(\d+\.、\s]+|[\]\)\s]+$/g, "").trim())
    .filter(Boolean);

  if (items.length >= 2) {
    const cleanText = text.slice(0, match.index).trimEnd();
    return { cleanText, options: items };
  }
  return { cleanText: text, options: [] };
}
```

---

## 🧪 4. 验证与测试命令

1. **前端类型检查**：
   ```bash
   cd apps/mms-web && npx tsc --noEmit
   # 结果：0 errors
   ```
2. **前端单元测试**：
   ```bash
   node --test apps/mms-web/tests/*.test.mjs
   # 结果：121 passed, 0 failed
   ```
3. **Python 门禁测试**：
   ```bash
   PYTHONPATH=. pytest tests/test_mms_release_version.py tests/test_mms_web_bots.py tests/test_mms_web_updates.py
   # 结果：68 passed in 0.45s
   ```
4. **静态资源发布包重新构建**：
   ```bash
   python3 scripts/build_mms_web_release.py --skip-install
   # 结果：打包构建完成，mms_web_static/ 静态资源已全量更新
   ```

---

## 🚀 5. Git Commit 树记录

```text
* 6d9001d6 - fix(transcript): 优化折叠状态对齐、运行指示点与流式正文提前呈现
* 88114765 - fix(transcript): 收起思考过程后增加正在工作与思考状态指示器
* f8c21cb2 - feat(bot): 自动将文本选项解析为可点击胶囊按钮并增加配置直达入口
* 5be8649a - feat(bot): 支持点击外部空白及按 Esc 键收起侧边抽屉面板
* 0aab7215 - Merge pull request #269 from CtriXin/release/5.0.1
* 8fc1adf8 - release: 5.0.1 Preview · 修复设置滚动条遮挡与 Bot 交互/弹窗样式
* 74295c8b - Merge pull request #267 from CtriXin/codex/release-5.0.0 (昨日发版基准)
```
