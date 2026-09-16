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

## 验收回修（2026-09-15，Claude 验收后退回）

主体链路实测可用（逐题对话、键盘选项、自由输入、起名、记忆入库、预设页签），tsc 0、Node 98、hex 12。下面这些要改完再交，按严重度排。改动仍在 `../wt-T1f`（分支 `bot/T1f-wizard`）上继续，开工前先 `git merge codex/stride-370e87ec37e741df`（任务分支已合入 T3d-ui 与 T2c；`Bot.tsx` 侧栏卡片第二行会冲突，规则是：有 `pendingQuestion` 显示"等你回复"，其次预设摘要，再描述；`BotStudio.tsx` 同理），解完先跑 tsc。

必修：

1. **删"了解到的偏好"后保存是假的。** `runWizard` / `parsePreset` 给 `extra` 同时写 `q_<id>` 和 shortLabel 两个键，面板只删 shortLabel，`buildPreset` 又从 `q_<id>` 复活。只保留一个键（用 `q_<id>` 做键、shortLabel 做显示），面板删除后 `GET` 读回必须没有。补单测。
2. **跳过向导的 Bot 每次重开都再走一遍向导。** "先聊聊再说"或点 × 后要持久化"已跳过"：最省事是往 systemPrompt 写一行空的 `了解到的偏好：` 段标记，或者用现有 `PUT /bots/:id` 里任一已有字段（看 `bots.py` 的 bot 字段清单，不要新增后端字段）。`onboardingDone` 以此判断。
3. **预设面板的 focus / style / autonomy 只有 4 个写死芯片。** 向导分支和自由输入产生的值（温和提醒、专业严谨等）在面板看不到也改不了，点芯片会静默覆盖。改成：芯片来自题库里该字段所有可能选项，加一个"自定义"输入，当前值若不在选项里就以自定义形式显示并选中。

与工单不符，一并改：

4. 首题顺序按工单：日常事务与提醒 / 工作与项目 / 查询与研究 / 写作与沟通 / 先聊聊再说，键 A 到 E 对应；D 的 value 与 label 一致（"写作与沟通"）。
5. 自由回答只写进 `extra`，不要同时写 focus/style/autonomy 造成 systemPrompt 同一句出现两次。
6. 题库补到 10 到 12 题。
7. 侧栏卡片第二行：不要在 `Bot.tsx` 内联复制 `getBotSecondLine`，直接扩展 `bot-visual-system.ts` 里那个函数并更新它的测试；`BotStudio.tsx:939` 改回去（那是未读通知卡，不是侧栏卡片）。
8. 头部把 `description === "随时可以接活"` 当空，侧栏卡片却照显，两处统一。
9. 清死代码：`Bot.tsx` 1340 / 1350 / 1729 / 1980 附近未用变量，`BotPresetPanel.tsx` 未用的 `WIZARD_POOL` 导入；把顺手删掉的 T1c / T1e 说明注释放回 `bot-presets.ts`。

回修后的验收补两条：删偏好后 `GET` 一致的截图；跳过向导的 Bot 重开后直接进聊天的截图。其余验收项照旧。
