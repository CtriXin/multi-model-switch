# T1f · 向导改成对话，预设看得见

Date: 2026-09-15
Task: Stride 370e87ec37e741df
起点：任务分支 `codex/stride-370e87ec37e741df` 当前 HEAD（T1e 已于 2026-09-15 合入）
建议模型：gemini3.6
来源：owner 2026-09-15 反馈，对照 Grok 的新建 Bot 流程截图

## 问题

1. 现在的向导（`Bot.tsx` 1311 到 1313 行 `WIZARD` 三道题，1377 行"告诉我几个你的偏好，之后我会作为默认工作方式："）是一张表单：三个问题一次全摆出来，选项是一排芯片，每次都是同样三道题，不能自由输入。用户觉得生硬。
2. 选完之后，性格和约定只能在"预设"编辑器里看到；侧栏卡片第二行显示的是描述或最后一条模型回复。

参照 Grok：头像自动选好（我们已经在创建时随机分配几何头像，保持）；一次只问一个问题，问题是聊天气泡；选项是 A 到 E 带一行说明，最后一项是"先聊聊再说"；下面有"输入你自己的回答"；问题按上一题的答案挑下一题，不是固定三道；答案会被记住。

## 要做成什么

### A. 题库与分支（`bot-presets.ts`，纯函数，可测）

- `WIZARD_POOL`：每题 `{ id, ask: string, options: [{ key: "A"…, label, hint }], next?: (answerKey|"free") => id | null, writes: "focus" | "style" | "autonomy" | "extra" }`。`ask` 用第一人称聊天语气，例如"你最希望我主要帮你做什么？""这类事你一般希望我怎么汇报？""要是我拿不准，是先做还是先问你？"。每题固定末项 `{ key: "E", label: "先聊聊再说" }`，选它就结束向导。
- 起始题固定问"主要帮你做什么"（选项：日常事务与提醒 / 工作与项目 / 查询与研究 / 写作与沟通 / 先聊聊再说，各带一行 hint，和 Grok 截图一致）。第二、三题按第一题分支：日常事务 → 问提醒方式与时间习惯；工作与项目 → 问汇报方式，再问推进方式；查询与研究 → 问结论要不要带依据；写作与沟通 → 问语气偏好。题库先放 10 到 12 道，最多问 3 道。
- `runWizard(answers) -> { nextQuestion | null, preset }`：给定已答列表算下一题和当前预设，纯函数，带单测覆盖每条分支和自由输入。
- 自由输入：任何一题都能打字回答；文本进 `answers.extra[questionId]`，`buildPreset` 输出到新段落"了解到的偏好："下，每条"- <问题短标签>：<回答>"；`parsePreset` 能读回。`focus/style/autonomy` 三个已有字段的映射保持，老 Bot 的 systemPrompt 不受影响。
- 结束时除了 `systemPrompt`，把三句话以内的偏好摘要通过现有记忆接口存一条 `fact`（找 `BotMemoryPanel.tsx` 里"保存记忆"调用的路由复用），来源 user。

### B. 对话式呈现（`Bot.tsx` 向导部分）

- 第一条 Bot 气泡："你好，我是刚建好的助手。" 紧接第一个问题；每题一张卡：问题标题、A 到 E 选项行（键 + 标签 + hint）、底部"输入你自己的回答"输入框，卡右上有 × 表示"跳过向导"。
- 用户选或输入后，答案作为用户气泡出现在右侧，Bot 再发下一题；结束时 Bot 发一句"好，记住了。"再进入起名（沿用 T1c 的起名步）。
- 键盘：按 A 到 E 字母键直接选，回车提交输入框。
- 已有 Bot 重新打开"预设"时，不再走向导，直接进预设面板（见 C）。

### C. 预设看得见

- 侧栏卡片第二行：Bot 有向导预设时显示摘要"工作与项目 · 只说结论 · 直接做"（从 `parsePreset` 取，`extra` 不进摘要）；没有预设时显示描述；不再显示模型最后一条回复。
- 右侧面板加"预设"页签，与"记忆""协作"并列（头部按钮 1948 / 1970 行旁边加一个）：展示工作重点、汇报方式、推进方式、了解到的偏好、补充约定，每项可改；T1e 做的编辑器搬到这个面板里，面板的关闭就是编辑器的关闭入口。
- 头部描述为空时，用预设摘要顶上，不再显示"随时可以接活"。

## 只许改

`apps/mms-web/src/Bot.tsx`（向导、头部按钮、面板挂载）、`apps/mms-web/src/bot-presets.ts`、新增 `apps/mms-web/src/BotPresetPanel.tsx`（可选，从 Bot.tsx 拆出来更清楚）、`apps/mms-web/src/BotStudio.tsx` 只改卡片第二行的取值、`apps/mms-web/src/bot.css`（hex 保持 12）、`apps/mms-web/tests/bot-presets.test.mjs`、`docs/mms-web/DESIGN.md`。

## 不许改

`mms_web/` 任何 Python（存记忆用现有接口）；`BotCommunications.tsx`、`BotPlan.tsx`；受保护文件；真实 `~/.config/mms*`。

## 验收

- 全新 state 建 Bot：看到逐题对话，选"工作与项目"后第二题是汇报方式；用键盘 A 选；第三题自由输入一句；结束后 `GET /api/v1/bots` 的 systemPrompt 含三段（工作预设、了解到的偏好、补充约定为空则无），记忆里多一条 fact。截图每一步。
- 选"先聊聊再说"直接进起名，systemPrompt 没有偏好段。
- 侧栏卡片第二行是预设摘要；面板"预设"页签能看能改，改完 `GET` 读回一致；截图。
- `node --test apps/mms-web/tests/*.test.mjs` 全过且数量 ≥ T1e 之后的数量加你新增；`npx tsc --noEmit -p apps/mms-web` 0；`npm run build --workspace @mms/web` 通过；hex 12。

## 并行规则

沿用 README：`git worktree add ../wt-T1f -b bot/T1f-wizard codex/stride-370e87ec37e741df`，端口 61705，不碰 60824，不提交、不 push、不 merge。
