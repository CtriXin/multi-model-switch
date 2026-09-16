# T5b · 定时的选择器与管理列表（前端）

Date: 2026-09-16
Task: Stride 370e87ec37e741df
分支：`bot/T5b-schedule-ui`，**必须从 T5a 完成后的 HEAD 开**（不是 `dev` / `dev-pre` 的 HEAD）。T5a 的 base 是 `dev`（重组后 `dev` 即 5.x 线）；重组尚未完成时用 `origin/dev-pre`（本次刷新基准 `77f2fd8a` = 5.0.1）
建议模型：gemini3.6（纯前端）
来源：owner 2026-09-16 反馈——定时只能选一个时间点，建了撤不掉

先读：`docs/mms-web/bot-work/README.md`（并行规则、通用验收）、`docs/mms-web/bot-work/T5a-schedule-backend.md`（API 形状、限额、错误码）、`apps/mms-web/DESIGN.md`、然后按下面"要读的代码"逐处确认。

## 前置依赖（不可绕过）

**必须从 T5a 完成后的 HEAD 开分支。** UI 要按 T5a 定下的 API 形状写：schedule 实体的字段名、四种 rule kind 的 JSON 形状、错误码、`POST` 路由后缀（这个仓库没有 PUT/DELETE，删除走 `.../delete`）。T5a 没落地就动手，写出来的形状一定对不上。

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch
git worktree add .worktrees/wt-T5b -b bot/T5b-schedule-ui bot/T5a-schedule-backend
cd .worktrees/wt-T5b && npm install
```

**两个包一起才算完成，后端不单独落地。** owner 的硬约束是"功能要么做完，要么不做"：T5a 单独进主线是被禁止的，T5a 和 T5b 都验收完才一起合进 base 分支（`dev`，重组未完成时 `dev-pre`）。

同批还有 **T5c**（`T5c-model-switch-by-dialogue.md`，在对话里换 Bot 的模型），同样从 T5a 的 HEAD 开分支。T5c 后端为主，只在 `Bot.tsx` / `BotStudio.tsx` 做最小接线（模型显示、`parseBotSettingCommand`），**不碰本包的 `BotSchedulePanel.tsx` / `bot-schedules.ts` / `bot-visual-system.ts`**；本包也不要碰 T5c 的那几处。两包可以并行，但 `Bot.tsx` 和 `BotStudio.tsx` 是共享文件，合并时按各自"只许改"清单核对。落地顺序：**T5a → T5b / T5c**，三个包都验收完才一起合进任务分支。

## 共同背景（T5a / T5b 共享，必读）

Bot 现在的"定时执行"只是 task 上的一个 `runAt` 字段：到点把 task 从 `scheduled` 转成 `queued`，`runAt` 立刻清空。所以它**只能触发一次**，本质是"定时发送"，用户仍然要每次手动发起。owner 明确否掉了这种做法，也否掉了"Bot 跑完自己再约下一次"的取巧方案（漏一轮就断，且依赖 Bot 每次记得重约）。

T5a 把它换成独立的 schedule 实体 + 真正的周期调度；T5b 让用户能建、能看、能改、能撤。

已知并已被 owner 接受的能力边界：**Pilot 是本机进程，它不运行定时就不触发。** UI 上要说明这一点（见"空状态和错误文案"），**不要引入 launchd / systemd / 开机自启方案**。

## 目标一句话

用户能在聊天里选"一次 / 每天 / 每周 / 每 N 小时"，能在一个列表里看到这个 Bot 的所有定时并暂停、修改、删除。

## 要读的代码（只读，先看完再动手）

| 位置 | 看什么 |
| --- | --- |
| `apps/mms-web/src/Bot.tsx` **1540 / 1766-1783 / 1914** 行 | composer 的 `runAt` state（1540）、`scheduleDateOptions` IIFE（1766-1783）、提交时 `...(runAt ? { runAt: new Date(runAt).toISOString() } : {})`（**1914**）。**注意**：`f8c21cb2` 把 `submit(event)` 拆成了 `sendMessage(textToSend)`（1885-1933）+ 一层薄 `submit(event)`（1934-1937），1914 行在 **`sendMessage` 里面**，改提交逻辑要改 `sendMessage` |
| `apps/mms-web/src/Bot.tsx` **2669-2706** 行 | `bot-chat-composer-footer`（2669）&gt; `bot-chat-composer-meta`（2670）&gt; 已选定时的 chip（**2672-2685**，`bot-schedule-chip` 2673、时间 2675、`bot-schedule-chip-clear` 2678-2683）；`bot-chat-send-group`（2689）里 **`8fc1adf8` 新加的停止按钮三元**（`isTaskRunning && onCancel` → `button.bot-chat-send.stop`，2691-2701）与发送按钮的 aria/title 分支（**2705-2706**，文案 `busy ? "发送中" : hasPendingQuestion ? "回复" : runAt ? "定时执行" : "发送"`） |
| `apps/mms-web/src/Bot.tsx` **2714-2856** 行 | `bot-chat-schedule-trigger` 按钮（2714-2739，`disabled` 条件在 **2716**：`disabled \|\| busy \|\| !bot \|\| isTaskRunning`）+ `id="bot-schedule-popover"` 的 `popover="auto"` 弹层（2740-2745）：`bot-schedule-presets`（2753-2789：1 小时后 / 今晚 20:00 / 明天 09:00 / 自定义…）与 `bot-schedule-custom-panel`（2793-2831）+ `bot-schedule-custom-actions`（2833-2856）。**弹层定位是命令式 JS**（2722-2733：`position:fixed`、`bottom = innerHeight - rect.top + 6`、`right = max(16, innerWidth - rect.right)`，然后 `togglePopover()`），不是 CSS 定位——改弹层高度不会自动重新锚定，要一起看 |
| `apps/mms-web/src/Bot.tsx` 726-834 行 | 另一处定时入口 `BotDispatchForm`：`runAt` state（**736**）、提交（**763**）、"执行时间"`datetime-local`（**812-820**，旁边 813 行 `留空立即执行`）、自动唤醒 checkbox（**825-834**）。**文案已变**：825-834 那个 checkbox 现在写的是 **`需要时自动唤醒`**（**832** 行），state 变量叫 `wake`（737 行，默认 `true`），不是 `wakeEnabled` |
| `apps/mms-web/src/Bot.tsx` **901-903** 行 | 任务列表里 `task.runAt && task.status === "scheduled"` 的渲染。**注意它用的是 `formatLocalDateTime`，不是 `formatScheduledTaskTime`**；903 行接的是 `task.queueReason && task.status === "queued"` 分支 |
| `apps/mms-web/src/Bot.tsx` **1106-1132** 行 | `AutoWakeControl({ enabled, onChange, disabled })`：`wakeEnabled` 开关，文案 **1125** 行 `自动唤醒`、**1126-1128** 行 `{enabled ? "定时任务到点后自动开始" : "仅在手动唤醒后继续"}`（三句都逐字仍在） |
| `apps/mms-web/src/Bot.tsx` **59-149** 行 | `TaskStatus` 联合类型（**59-68**）、`BotDefinition`（**69-87**，`presetId` 74、`wakeEnabled` 77、`modelName?` 79）、`BotTask`（**88-102**，`runAt?` 96）、`BotDispatchPayload`（**143-149**，`runAt?` 146）。Bot 的类型都在 `Bot.tsx` 里（`apps/mms-web/src/types.ts` 存在，但不含 Bot 类型）。`Bot.tsx` 全文 **2984** 行 |
| `apps/mms-web/src/bot-visual-system.ts` **150-157** 行 | `getBotSecondLine`（函数体 **121-175**，签名 `(bot, task?, allTasks?, referenceNow?) => string \| null`）里 schedule 的第 3 优先级位置：活跃任务（129-134）→ pendingQuestion/waiting（136-148）→ **定时（150-157，现在取 `botTasks.find(t => t.status === "scheduled" \|\| Boolean(t.runAt))`，输出 `${formatScheduledTaskTime(runAt, referenceNow)} · ${prompt.slice(0,12)}`）** → 预设摘要（159-165）→ description（167-171，把 `"随时可以接活"` 当空）→ null（173-174）。同文件 **177-201** 是 `getIndicatorStatus` |
| `apps/mms-web/src/bot-visual-system.ts` **72-96** 行 | `formatScheduledTaskTime(value?, referenceNow?)`：今天（86-88）/明天（89-91）/后天（92-94）/`M月D日`（95）+ HH:MM，空值返回 `""`、解析不了就原样返回，`referenceNow` 可注入便于测试。直接复用 |
| `apps/mms-web/src/BotStudio.tsx` **138 / 154 / 286-294** 行 | 138 行 `const [wakeEnabled, setWakeEnabled] = useState(bot?.wakeEnabled \|\| false);`、154 行保存 payload 里的 `wakeEnabled,`、286-294 行的 checkbox（290 `checked`，**293** 行文案 `允许定时任务自动唤醒`） |
| `apps/mms-web/src/BotStudio.tsx` **953-980** 行 | `AutoWakeControl` 的挂载点（953-955，从 `./Bot` 于第 6 行 import）与保存逻辑：958-964 行 `run<BotDefinition>("/bots/:id", { name, description, systemPrompt, presetId, wakeEnabled })` —— **整对象覆盖式 POST，且不带 avatar 字段**（和 1078-1086 那条 patch 式路径不同，别混用）；965-971 成功合并进 `setBots` + `refreshInBackground()`，972-979 失败写 `自动唤醒设置保存失败。` |
| `apps/mms-web/src/BotStudio.tsx` **845 / 859** 行 | 新建 Bot 时显式传 `wakeEnabled: true`（845 是本地草稿对象 838-847，859 是真正的 `run<BotDefinition>("/bots", ...)` 854-860），与 138 行 `\|\| false` 的既存不一致。**订正**：旧包写的 1083 行**不是新建点**，那是 1078-1086 行 `onUpdateBot` 透传里的 `wakeEnabled: patch.wakeEnabled ?? current.wakeEnabled` |
| `apps/mms-web/src/api.ts` + `BotStudio.tsx` 679-685 | **`api.ts` 里没有 `run`**。真正的封装是 `request<T>(path, body?, signal?)`（**21-61**：`/api/v1${path}`，`body === undefined` 走 GET 否则 POST，POST 带 `X-MMS-CSRF`）和 `mutate<T>(path, payload)`（**164** 起，用 `requestId` 做幂等）。错误提取在 38 / 44 / 55-59 行（`ApiError(payload.error?.message, payload.error?.code)`，`ApiError` **未导出**）；`INVALID_CSRF` 会 `bootstrap()` 后自动重试一次。Bot 侧用的 `run` 是 `BotStudio.tsx` **679-685** 行的本地 `useCallback`，内部转调 `mutate` |
| `apps/mms-web/DESIGN.md` | token、间距、禁止的通用 AI 设计模式 |
| `apps/mms-web/tests/bot-visual-system.test.mjs` | 只有一条测试 `"getBotSecondLine follows strict priority order and returns null when empty"`（**58** 行起），逐档断言六级优先级，其中 **86** 行断言 schedule 档输出 `"明天 09:00 · 超长定时任务名称用来测试"`（12 字截断 + 固定 `refNow`）。改函数要同步改这条 |

## 落地顺序与 base 分支（2026-09-16 刷新）

**base 分支**：`dev`。重组后 `dev` 就是 5.x 线；**重组尚未完成时用 `origin/dev-pre`**。本次刷新的实测基准是 `origin/dev-pre` = `77f2fd8a` = **5.0.1**。

当前分支现状（2026-09-16 实测，别凭记忆）：

| 分支 | 版本 | HEAD |
| --- | --- | --- |
| `origin/dev-pre` | **5.0.1** | `77f2fd8a` |
| `origin/dev` | **4.22.1** | `1f466eea` |
| `origin/main` | 4.10.0（**陈旧，重组前不要用**） | `ca6c09eb` |

**顺序不变：T5a → 然后 T5b 和 T5c。** T5b 和 T5c 都依赖 T5a 定下的 API 形状与提示词改动，且 T5c 与 T5a 动同一批文件（`bot_executor.py` / `bot_client.py`），**所以 T5c 不能和 T5a 并行**；T5b（纯前端）与 T5c（后端为主）彼此不重叠，可以并行。

**硬约束原样保留：后端不单独进主线。T5a 和 T5b 验收完才一起合。** owner 的原话是"功能要么做完，要么不做"。

## 与近期改动的冲突面（2026-09-16 刷新，必读）

这三个包原本是对着 `66b7fc16` 写的。`origin/dev-pre` 此后走到 5.0.1，并且多了 gemini 的四个交互改动，动的正是这批包要改的文件。下面逐条列出真实冲突面——**这一节是本次刷新最重要的产出，动手前必须读完。**

近期改动清单（全部已在 `origin/dev-pre` 上）：

| commit | 做了什么 | 动到的文件 |
| --- | --- | --- |
| `8fc1adf8` | 5.0.1 热修：设置页滚动条遮挡保存栏、Bot 停止/重试位置与弹窗层叠 | `styles.css`、`Bot.tsx`、`bot.css`、`quick-model.css`、`studio.css` |
| `5be8649a` | 侧边抽屉面板支持点击外部空白与 Esc 收起，带脏表单守卫 | `BotPresetPanel.tsx`、`BotMemoryPanel.tsx`、`BotCommunications.tsx`、新增 `tests/bot-preset-outside-close.test.mjs` |
| `f8c21cb2` | Bot 回复里的文本选项自动解析成可点击胶囊按钮，并加配置直达入口 | `bot-presets.ts`、`Bot.tsx`、`bot.css`、新增 `tests/bot-message-options.test.mjs` |
| `88114765` + `6d9001d6` | Pilot 主会话折叠态指示器、流式正文提前呈现 | `SessionStatus.tsx`、`Transcript.tsx`、`transcript.css`、新增 `tests/turn-working-status.test.mjs` |

**订正一条**：`5be8649a` 的提交说明里提到 `Bot.tsx`，但 `git show --stat 5be8649a` 显示它**没有改 `Bot.tsx`**。它只改了那三个面板组件加一个新测试。

**`88114765` / `6d9001d6` 与 Bot 工作台零重叠**（逐文件核对过：只有 `SessionStatus.tsx` / `Transcript.tsx` / `transcript.css` / `turn-working-status.test.mjs`，没有任何 `Bot*.tsx`、`bot*.css`、`bot-*.ts`）。它们对本批包唯一的影响见下面第 5 条的 `mms_web_static/`。

**PR #270（`fix/bot-compact-pilot-restart` → `dev-pre`）尚未合并**，它改 `mms_web/bot_executor.py`（+39/−12）、`mms_web/bots.py`（+2/−3）、`mms_web/service.py`（+9/−2），并新增 `tests/test_mms_bot_compaction.py`。**它是纯 Python，零 `apps/mms-web/**`。**

### 1. 【最高风险】T5b 的定时选择器和 `f8c21cb2` 的选项胶囊都在 `Bot.tsx` 与 `bot.css`

这是本批包里冲突风险最高的一处。**先把两者的真实位置搞清楚，再决定怎么共存——不要各做一套。**

**两者在 DOM 里其实不在同一层，这是好消息：**

| | 选项胶囊（`f8c21cb2`） | 定时选择器（本包要改的） |
| --- | --- | --- |
| 组件 | `BotMessageBody`（`Bot.tsx` **1426-1475**） | composer footer（`Bot.tsx` **2669-2856**） |
| 位置 | **消息流里**，每条 Bot 气泡正文下方 | **输入框下面那一行**，不在消息流里 |
| 挂载点 | 2409-2414（流式消息）、2484-2489（最终结果） | 2672-2685（chip）、2714-2856（trigger + popover） |
| DOM | `.bot-chat-event-body` &gt; `RichText` + `.bot-chat-quick-options[role=group]` &gt; N × `button.bot-chat-quick-option` | `.bot-chat-composer-footer` &gt; `.bot-chat-composer-meta`（chip）+ `.bot-chat-send-group`；trigger 与 `popover="auto"` 弹层 |
| CSS | `bot.css` **3213-3270** | `bot.css` **1711-1772** 一带 |

**所以不要在消息流里再造一套定时选择器**，也不要把定时选择器做成第二种"胶囊"。两者视觉上都是 pill，但职责不同：胶囊是"替用户打一句话发出去"，定时选择器是"给这次发送附加一个周期"。**T5b 的四种 kind 切换用分段控件 / tab，不要复用 `.bot-chat-quick-option` 的 class**，否则以后改胶囊样式会连带改坏定时选择器。

**真正的冲突点有四个，逐条处理：**

**(a) `submit` 已经被拆了。** `f8c21cb2` 把 `submit(event)` 拆成 `sendMessage(textToSend: string)`（**1885-1933**）+ 一层薄 `submit(event)`（**1934-1937**，内部 `await sendMessage(value)`）。本包要改的 `...(runAt ? { runAt: ... } : {})` 现在在 **1914** 行，**在 `sendMessage` 里面**。改提交逻辑要改 `sendMessage`，改错地方会让胶囊点击走不到定时分支（胶囊的 `onSelectOption` 直接调 `sendMessage`）。

**(b) `popover="auto"` 的轻量关闭会吞掉胶囊的第一次点击。** `.bot-schedule-popover` 是原生 `popover="auto"`（`Bot.tsx` 2740-2745），处于浏览器 **top layer**。定时弹层开着的时候，用户点消息流里的胶囊，浏览器会先做 light-dismiss 关掉弹层并吞掉这一次点击，用户要点两下。**本包必须处理**：要么在弹层打开时让胶囊 `disabled`（和它现有的 `disabled={busy || disabled || isTaskRunning}` 合并），要么接受"第一次点击关弹层"但在验收里明确记录这个行为。**不允许放着不管。**

**(c) z-index 不是问题，`popover` 互斥才是。** `bot.css` 当前只有 5 条 `z-index`：`.bot-card-menu` 40（376）、`.bot-avatar-popover` **1000**（617）、`.bot-schedule-popover` **1000**（1772）、`.bot-dialog-scrim` 50（2057）、`.bot-artifact-lightbox` 60（2341）。`f8c21cb2` **一条 z-index 都没加**，胶囊在正常文档流里。但 `.bot-avatar-popover` 和 `.bot-schedule-popover` 都是 `popover="auto"`，**两者互相 light-dismiss**：打开头像弹层会关掉定时弹层，反之亦然。本包新增的 kind 切换如果还在同一个 `popover="auto"` 里就没有新问题；**如果新做一个普通绝对定位的浮层，它必须 `z-index > 60`**（越过 `.bot-artifact-lightbox`），而且仍然会被任何打开的 `popover` / `dialog` 压在下面。

**(d) 弹层定位是命令式 JS，改高度会顶出视口。** `Bot.tsx` **2722-2733** 行：`position:fixed`、`margin:0`、`bottom = window.innerHeight - rect.top + 6`、`right = Math.max(16, window.innerWidth - rect.right)`，然后 `popover.togglePopover()`。它把弹层**下沿钉在触发按钮上沿**，高度往上长。四种 kind 的字段高度不同，切 tab 之后要么重跑这段定位，要么给弹层加 `max-height` + 内部滚动。`onToggle`（2746-2750）在关闭时会 `setCustomSchedule(false)`，新增的 kind state 也要在这里一起复位。

**窄屏布局：`f8c21cb2` 一条 `@media` 都没加**，胶囊纯靠 `flex-wrap: wrap` 换行（`.bot-chat-quick-options` 在 `bot.css` 3213-3219）。`bot.css` 现有断点是 900（2648，侧栏宽度）、640（2655，工作区改块级）、480（3074，`.bot-peer-thread*` / `.bot-communications-panel` 内距），**三个都没提 composer 和 `bot-schedule-*`**。所以：**本包的四种 kind 切换也用 `flex-wrap`，不要新开断点**；弹层用上面 (d) 的 `max-height` + 滚动来适配矮屏，不要靠媒体查询换一套布局。

**`8fc1adf8` 还在同一片区域埋了东西**：它把发送按钮改成了 `isTaskRunning && onCancel` 三元——运行中显示 `button.bot-chat-send.stop`（2691-2701，红色，`aria-label="停止执行"`），并新加了 `.bot-chat-composer-footer` / `.bot-chat-composer-meta` / `.bot-chat-send-group` 三层包裹。CSS 上 `.bot-chat-send.stop` 在 `bot.css` **1711-1720**，离 `.bot-chat-schedule-trigger`（~1740-1762）和 `.bot-schedule-popover`（1764-1772）只有几十行，**是同一个 CSS 邻域，文本冲突概率高**。另外 `isTaskRunning` 现在同时是定时按钮 `disabled`（2716）和胶囊 `disabled` 的条件，改其中一个要想清楚另一个。

### 2. 【硬要求】T5b 的 schedule 管理列表必须复用 `5be8649a` 那套抽屉机制，不许新写一份

**先说一个必须知道的事实：`5be8649a` 没有抽出可复用的 hook 或 util，它是把同一段 `useEffect` 在三个组件里各抄了一份。** 三份逐字相同，只有"触发按钮排除选择器"不同：

| 文件 | 排除选择器 | `<aside>` class |
| --- | --- | --- |
| `BotPresetPanel.tsx` | `'[aria-label="调整工作预设"], [title="工作预设"]'` | `bot-memory-panel bot-preset-panel` |
| `BotMemoryPanel.tsx` | `'[aria-label="打开记忆面板"], [title="记忆"]'` | `bot-memory-panel` |
| `BotCommunications.tsx` | `'[aria-label="打开协作面板"], [title="协作"]'` | `bot-communications-panel` |

机制本身（以 `BotPresetPanel.tsx` 为准，当前行号）：

- `const panelRef = useRef<HTMLElement>(null)` —— **94**，`ref` 挂在顶层 `<aside>` 上（**260**）
- 点击外部 / Escape 的 `useEffect` —— **228-258**（`document.addEventListener("pointerdown", ...)` 在 251，`window.addEventListener("keydown", ...)` 在 252，清理在 254-255）
- 判定：`panel.contains(target)` 就返回；`target.closest?.(<排除选择器>)` 就返回（**防止点触发按钮时"闪关又开"**）；否则 `handleClose()`
- Escape：`e.key === "Escape"` → `e.stopPropagation()` → `handleClose()`
- 脏表单守卫 —— `isDirty`（**204-210**）、`isDirtyRef`（**211-212**）、`handleClose()`（**214-226**）。脏了就 `window.confirm("当前工作预设已修改，确定要放弃未保存的修改并关闭吗？")`；取消就不关。`typeof window.confirm === "function"` 的兜底在非浏览器环境默认放行。
- 基线快照：`initialPromptRef`（**95**，在 97-105 的 effect 里按 `[bot.id, bot.systemPrompt]` 重置，保存成功后在 **119** 行更新）
- **点击外部、Escape、头部 × 三条退出路径全部走同一个 `handleClose`**（头部关闭按钮在 **274**）

**本包的要求：**

1. **照 `BotPresetPanel.tsx` 的做法做，一个字不要自创。** 排除选择器换成 schedule 面板自己的触发按钮的 `aria-label` / `title` 对——**不加这一条，面板会在点自己的触发按钮时自关**。
2. **schedule 的编辑表单是脏表单**（改 prompt / rule / timezone / overlapPolicy），**必须有脏表单守卫**。`BotMemoryPanel` 和 `BotCommunications` 目前**没有**守卫，别照那两个抄。
3. **首选做法：把这段抽成一个共享 hook**（例如 `useDismissiblePanel({ panelRef, excludeSelector, onClose })`），然后把三个现有面板一起改过去，新面板直接用。这条是"不要各做一套"的正解。
   **但有一个代价必须先知道**：`apps/mms-web/tests/bot-preset-outside-close.test.mjs` 是一个**源码文本正则测试**（`readFileSync` 读 `.tsx` 然后 `assert.match`），它断言的是 `ref={panelRef}`、`document.addEventListener("pointerdown", handlePointerDown)`、`panel.contains(target)`、`e.key === "Escape"`、`window.addEventListener("keydown", handleKeyDown)`、`isDirty`、`initialPromptRef`、`window.confirm` 这些**标识符本身**。抽 hook 会让这条测试红。**抽的话必须同时改这条测试**，把断言改成对新 hook 文件的断言 + 对各面板"确实调用了该 hook"的断言。
4. 如果判断抽 hook 超出 T5b 的风险预算，**退而求其次是第 4 份逐字复制 + 在交付里明确写出"这是第 4 份复制，建议后续单开一个包抽 hook"**。**不允许自己发明第二套关闭语义**（例如只有 Escape 没有点击外部、或者没有脏表单确认）。
5. 关闭确认的文案要和现有那句同一风格，不要写成"确定吗？"。

### 3. `getBotSecondLine` 要和 gemini 的改动共存 —— 复核结果：签名和调用点都没变

- 函数体 **121-175**，schedule 分支 **150-157**（旧包写的 148-158 已偏移）。
- 签名仍是 `(bot, task?, allTasks?, referenceNow?) => string | null` —— **gemini 的四个提交没动这个文件**，本包按原计划加第 5 个可选参数 `schedules?` 是安全的。
- 实际实现的六级优先级（源码里有注释）：活跃任务（129-134）→ `pendingQuestion` / `waitReason`（136-148）→ 定时（150-157）→ 预设摘要（159-165）→ description（167-171，把 `"随时可以接活"` 当空）→ null（173-174）。同文件 **177-201** 是 `getIndicatorStatus`。
- 调用点：`grep -n "getBotSecondLine" apps/mms-web/src/*.tsx` 应当只看到 import 与调用，**不能有内联复制**（T1f 回修第 7 条踩过这个坑，验收清单里有这条）。
- 测试 `apps/mms-web/tests/bot-visual-system.test.mjs` 只有一条测试（**58** 行起）逐档断言六级优先级，schedule 那档在 **86** 行断言 `"明天 09:00 · 超长定时任务名称用来测试"`（12 字截断 + 固定 `refNow`）。改函数必须同步改它。

### 4. `8fc1adf8` 顺带动了 `ModelPicker` 的几何

`styles.css` 里 `.model-picker-trigger` 被重写成 `width:100%; display:flex; justify-content:space-between`，子元素从 `strong`/`small` 两行变成单个带省略号的 `span` + 不收缩的 `svg`。**`BotStudio.tsx` 263 行用的就是这个 `ModelPicker`**。本包不改它，但如果你在 Bot 编辑器里加"待生效模型"之类的显示（那是 T5c 的范围），要知道这个 trigger 的布局刚变过。

### 5. `mms_web_static/` 是提交进仓库的构建产物

上面五个 commit **每一个**都重写了 `mms_web_static/build.json`、`index.html` 和带 hash 的 asset 文件名。任何跑了 `npm run build` 又把产物一起提交的分支，在 rebase 时**必然**和它们文本冲突。**本包在 worktree 里 build 用于验证，但不要 stage `mms_web_static/`**，交给发版步骤统一重建。

## 范围

### 1. composer 的定时控件

现在只能选**一个时间点**（`Bot.tsx` **1540 / 1766-1783 / 1914** 的 `runAt`，**2714-2856** 的 trigger + popover）。改成能选：

- **一次** —— 保留现在的日期 + 时间选择（今天/明天/后天/7 天内 + 常用时段 + HH:mm 精确输入），对应 `{kind:"once", at}`。
- **每天** —— 选一个 HH:MM，对应 `{kind:"daily", atLocalTime}`。
- **每周** —— 选星期 + HH:MM，对应 `{kind:"weekly", weekday, atLocalTime}`。weekday 的 0=周一…6=周日（T5a 的约定），UI 上显示"周一…周日"，不要让用户碰数字。
- **每 N 小时** —— 对应 `{kind:"interval", everySeconds: N*3600}`。给几个常用值（1 / 3 / 6 / 12 小时）加一个自定义数字输入。

`timezone` 一律用 `Intl.DateTimeFormat().resolvedOptions().timeZone` 一起提交，不要让用户填。

**最小间隔 300 秒要在 UI 上拦住并给出人能看懂的提示**，不要只靠后端报错：小于 5 分钟的 interval 让确认按钮 disabled 并就地显示提示（文案见下）。后端的 `SCHEDULE_INTERVAL_TOO_SHORT` 仍要能被正确展示，作为兜底。

复用现有 popover 结构和 `bot-schedule-*` class，不要新起一套弹层机制。**注意弹层是原生 `popover="auto"` + 命令式定位（2722-2733）**：四种 kind 切换会改变弹层高度，而定位是按触发按钮的 `getBoundingClientRect()` 把 `bottom` 钉在按钮上沿的，高度变化时不会自动重算——切 tab 之后要重新跑一遍那段定位，或改成 `bottom` 锚定后用 `max-height` + 内部滚动，别让弹层顶出视口。四种 kind 用一排 tab / 分段控件切换，切换后下方只显示该 kind 需要的字段——**不要把四种的字段全摆出来**（那正是 T1f 里 owner 已经否过的"一张表单"观感）。

提交：一次性的走现有"建 task"路径；周期性的走 T5a 的 `POST /api/v1/bots/:id/schedules`。按 T5a 响应里的 `kind` 字段区分建了 task 还是 schedule，UI 反馈要说清楚（建了定时应该说"已设定，下次 X"，不该显示成"任务已派发"）。

已选定时的 chip（**2672-2685**）要能显示周期形状，例如"每天 09:00"、"每 3 小时"，不是只显示一个绝对时刻。

### 2. Bot 卡片第二行展示 schedule

`bot-visual-system.ts` 的 `getBotSecondLine` 里已经有 schedule 的第 3 优先级位置（**150-157** 行，现在读的是 `task.runAt`）。改成读 schedule：

- 形如 **"每天 09:00 · 下次 明天 09:00"**（周期描述 + `formatScheduledTaskTime(nextRunAt)`）。
- 一次性的仍然显示 `formatScheduledTaskTime(at)`。
- 多条 schedule 时取 `nextRunAt` 最近的那条，并在后面补条数，例如"每天 09:00 · 下次 明天 09:00 · 共 3 条"。
- **要处理 `enabled === false` 的显示**：已暂停的 schedule 不能当作"下次会跑"。全部暂停时显示"定时已暂停"；部分暂停时只按未暂停的算，不显示暂停的。
- Bot 级 `wakeEnabled === false` 时显示"自动唤醒已关闭"，优先于单条 schedule 的描述（因为那是总闸）。
- 优先级顺序不动：活跃任务 → pendingQuestion/waiting → 定时 → 预设摘要 → description → null。

**不要在 `Bot.tsx` 或 `BotStudio.tsx` 里内联复制 `getBotSecondLine`**（T1f 回修第 7 条踩过这个坑），直接扩展 `bot-visual-system.ts` 里那个函数并同步更新 `apps/mms-web/tests/bot-visual-system.test.mjs`。

### 3. 管理列表

某个 Bot 的所有 schedule，**能看、能暂停/恢复、能删、能改**。

- **建了撤不掉是不可接受的，这是硬验收项。** 删除和暂停必须在 UI 上直接可达，不需要去改 systemPrompt、不需要重建 Bot。
- 每条显示：周期描述、prompt（截断，可 title 全文）、下次触发时间、上次触发时间 + 上次那个 task 的入口（点进去看结果）、`enabled` 状态、`overlapPolicy`（skip 显示"上一轮在跑就跳过"，queue 显示"排队执行"）。
- 操作：暂停 / 恢复、编辑（改 prompt、rule、timezone、overlapPolicy）、删除。删除要二次确认，并说明"已经跑出来的任务会保留"。
- `kind:"once"` 且已触发（`nextRunAt === null`）的显示"已执行完"，删除入口照旧可用。
- 挂在哪里：跟"记忆""协作""预设"面板并列，作为一个"定时"面板（`Bot.tsx` 头部按钮那一排，T1f 已经在那里加过"预设"页签，照它的做法）。**不要为此新开一个顶层页面。**

### 4. 空状态和错误文案

逐条写准，不要占位符：

- **没有任何定时时**：说明这个 Bot 现在没有定时安排，一句话告诉用户怎么建（在聊天框右边的定时按钮里选周期，或者直接跟 Bot 说"每天早上九点…"）。同时说明 **Pilot 关着的时候定时不会触发**，这是本机应用的边界——一句话，不要写成告警块。
- **超过 20 条上限时**：明确说"一个 Bot 最多 20 条定时，先删掉不用的再加"，并把当前条数显示出来。达到 19 条起就在建的入口上提示剩余额度。
- **间隔太短时**：明确说"定时间隔最短 5 分钟"，并说明原因一句话（太频繁会持续消耗模型额度）。这条要在 UI 侧先拦住。
- 后端其它错误码（`SCHEDULE_NOT_FOUND` / `INVALID_SCHEDULE_RULE` / `INVALID_TIMEZONE`）走现有 `bot-inline-error` 展示，不要吞掉。

### 5. `wakeEnabled` 的文案

如果 T5a 让 `wakeEnabled` 变成 schedule 总开关（按 T5a 的设计，它就是），那么：

- `Bot.tsx` 1105-1132 的 `AutoWakeControl`：文案要跟着改准。"定时任务到点后自动开始"在新语义下应该是"这个 Bot 的定时到点后自动开始"，关闭时是"定时不会触发，只在你手动唤醒时执行"。
- `BotStudio.tsx` 288-293 那个 checkbox 的"允许定时任务自动唤醒"同样要改准，两处说法要一致。
- 关闭时，管理列表里所有 schedule 要显示成被总闸拦住的状态（不是"已暂停"，那是单条的 `enabled`），两层要在 UI 上分得清。
- **顺带看一眼既存不一致**：`BotStudio.tsx:138` 是 `useState(bot?.wakeEnabled || false)`，而后端 `create_bot` 默认 `True`、`BotStudio.tsx` 845/859 又显式传 `true`。修正成与后端一致（默认 true），改动限制在这一行加相邻的初始化，不要顺手重构那个表单。

## 只许改 / 不许改

**只许改**：

- `apps/mms-web/src/Bot.tsx`：composer 定时控件（1540 / 1766-1783 / 1914 / 2669-2706 / 2714-2856）、头部按钮、`AutoWakeControl` 文案（1106-1132）、任务列表里的 runAt 渲染（**901-903**）、`BotDispatchForm` 的定时入口（**736 / 763 / 812-820 / 825-834**）
- 新增 `apps/mms-web/src/BotSchedulePanel.tsx`（管理列表，从 Bot.tsx 拆出来更清楚，照 `BotPresetPanel.tsx` 的形状）
- 新增 `apps/mms-web/src/bot-schedules.ts`（rule ↔ 人类文案的纯函数：`describeRule(rule)`、`ruleFromForm(...)`、`validateRuleForm(...)`），**可测**
- `apps/mms-web/src/bot-visual-system.ts`：`getBotSecondLine` 的 schedule 分支
- `apps/mms-web/src/BotStudio.tsx`：只改 `wakeEnabled` 文案/默认值那几行 + 面板挂载所需的最小接线
- `apps/mms-web/src/bot.css`：**hex 去重计数必须仍是 12**（2026-09-16 在 `77f2fd8a` 实测仍是 12，gemini 的胶囊按钮没有新增颜色字面量）
- 新增 `apps/mms-web/tests/bot-schedules.test.mjs`；更新 `apps/mms-web/tests/bot-visual-system.test.mjs`
- `apps/mms-web/DESIGN.md`：把本次的视觉决定补写进去（照 T1f 的做法）

**不许改**：

- 任何 `mms_web/**` Python（T5a 已经定了后端；发现后端缺口写进"需要 Fable 确认"，不要自己补后端）
- `BotCommunications.tsx`、`BotPlan.tsx`、`BotMemoryPanel.tsx`、`BotPresetPanel.tsx`、`Composer.tsx`、`App.tsx`
- **不要碰 `BotStudio.tsx` 以外的无关面板，不要顺手重构**
- 受保护文件：`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`
- 真实 `~/.config/mms*`
- 不加依赖，图标只用已引入的 lucide-react（`Timer`、`Clock3`、`Calendar`、`AlarmClockCheck`、`X`、`ChevronDown` 都已在用）

## 设计约束

- **不要引入新的颜色字面量。** `apps/mms-web/src/bot*.css`（= `bot.css` / `bot-communications.css` / `bot-memory.css` / `bot-plan.css`）的 hex 去重计数**必须仍是 12**——2026-09-16 在 `origin/dev-pre` = `77f2fd8a` 实测就是 12，`f8c21cb2` 的胶囊按钮用的是 `color-mix(in srgb, var(--accent) 8%, var(--surface))`，没有引入新 hex，所以这条约束没有放松：
  ```bash
  grep -ohE '#[0-9a-fA-F]{3,8}\b' apps/mms-web/src/bot*.css | sort -u | wc -l   # 必须是 12
  ```
  当前这 12 个值：`#059669 #0d9488 #2dd4bf #34d399 #4f46e5 #7c3aed #818cf8 #a78bfa #d97706 #db2777 #f472b6 #fbbf24`。
- 遵守 `apps/mms-web/DESIGN.md`（注意：T1e / T1f / T2c / T3c 几个旧包里写的 `docs/mms-web/DESIGN.md` **不存在**，2026-09-16 在 `77f2fd8a` 复核过，实际是 `apps/mms-web/DESIGN.md`）。
- 不要引入通用 AI 设计模式：渐变文字、装饰性玻璃拟态、卡片套卡片、过度圆角、重复的图标卡片网格。
- 四种 kind 的切换用分段控件或 tab，切换后只显示该 kind 的字段；不要一次摆出全部输入框。
- 时间一律显示本地时区的人话（复用 `formatScheduledTaskTime`），不要在界面上出现 ISO8601 或 UTC 偏移。

## 门禁

```bash
# 1. 类型
npx tsc --noEmit -p apps/mms-web

# 2. 前端单测（**必须带 glob**；`node --test apps/mms-web/tests/` 不带 glob 会直接 fail 1）
node --test apps/mms-web/tests/*.test.mjs

# 3. hex 计数
grep -ohE '#[0-9a-fA-F]{3,8}\b' apps/mms-web/src/bot*.css | sort -u | wc -l

# 4. 构建
npm run build --workspace @mms/web
```

**基线（2026-09-16 在 `origin/dev-pre` = `77f2fd8a` = 5.0.1 实测）**：

| 门禁 | 实测值 |
| --- | --- |
| `node --test apps/mms-web/tests/*.test.mjs` | **121 pass / 0 fail**（19 个测试文件；gemini 新增了 `bot-preset-outside-close` / `bot-message-options` / `turn-working-status` 三个，旧包写的 114 已过期） |
| `npx tsc --noEmit -p apps/mms-web` | **0 错**（跑之前先在 worktree 里 `npm install`） |
| `grep -ohE '#[0-9a-fA-F]{3,8}\b' apps/mms-web/src/bot*.css \| sort -u \| wc -l` | **12**（没变） |

通过数只增不减。你的 base 是 T5a 的 HEAD，以 T5a 交付里的实测数字为准，若 T5a 没动前端就仍是 121。

## 真实验证（不是可选项）

用 ego-browser 在**隔离实例**上验证，**不要重启 60824，也不要动 8767**（owner 在用的实例），自己另起端口：

```bash
cd .worktrees/wt-T5b
npm install
npm run build --workspace @mms/web
PYTHONPATH=$PWD python3 -P -m mms_web --port 61752 \
  --state-root /tmp/bot-verify-t5b \
  --config-root ~/.config/mms-next \
  --static-root $PWD/apps/mms-web/dist
```

截图全部存到 `docs/mms-web/design/t5b/`。验证 UI 用空草稿或一句话任务，不要在真实模型上发长任务。

## 验收清单（逐条可勾）

composer：

- [ ] 定时按钮弹层里有"一次 / 每天 / 每周 / 每 N 小时"四个选项，切换后只显示对应字段。截图。
- [ ] 选"每天 09:00"提交，`GET /api/v1/bots/:id/schedules` 读回 `{kind:"daily", atLocalTime:"09:00"}` 且 `timezone` 是本机时区。截图 + 接口返回。
- [ ] 选"每周 周一 09:00"提交，读回 `weekday` 正确（0=周一）。
- [ ] 选"每 3 小时"提交，读回 `everySeconds: 10800`。
- [ ] 选"一次"仍然走原来的路径并正常执行，没有回归。
- [ ] 间隔填 2 分钟：确认按钮 disabled，就地提示"定时间隔最短 5 分钟"，**没有发出请求**。截图。
- [ ] 已选定时的 chip 显示周期形状（"每天 09:00"），不是一个绝对时刻。截图。
- [ ] 建成定时后的反馈说的是"已设定，下次 X"，不是"任务已派发"。

侧栏卡片第二行：

- [ ] 有一条启用的 daily schedule 时显示"每天 09:00 · 下次 明天 09:00"。截图。
- [ ] 多条时取最近的一条并显示总条数。
- [ ] 全部暂停时显示"定时已暂停"。截图。
- [ ] Bot 级 `wakeEnabled=false` 时显示"自动唤醒已关闭"，优先于 schedule 描述。截图。
- [ ] 有活跃任务 / pendingQuestion 时优先级不变（定时不抢前面两档）。
- [ ] `getBotSecondLine` 没有被内联复制到 `Bot.tsx` / `BotStudio.tsx`（`grep -n "getBotSecondLine" apps/mms-web/src/*.tsx` 只应看到 import 与调用）。

管理列表：

- [ ] 面板跟"记忆""协作""预设"并列可达。截图。
- [ ] 列表里每条显示周期、prompt、下次、上次 + 上次任务入口、enabled、overlapPolicy。截图。
- [ ] 暂停后侧栏与列表都变化，`GET` 读回 `enabled:false`；恢复后回到启用。截图各一张。
- [ ] 编辑一条的 prompt 和 rule，`GET` 读回一致。截图。
- [ ] **删除一条**：二次确认文案说明已产生的任务会保留；删除后列表里消失、`GET` 读不到，**之前跑出来的 task 仍在任务列表里**。截图。**这是硬验收项。**
- [ ] `kind:"once"` 已触发的那条显示"已执行完"且能删。

文案：

- [ ] 空状态：说明没有定时、怎么建、以及"Pilot 关着不会触发"。截图。
- [ ] 造到 20 条，第 21 条被拦住并显示"最多 20 条定时，先删掉不用的再加"+ 当前条数。截图。
- [ ] 19 条起在建的入口上显示剩余额度。
- [ ] 后端 `SCHEDULE_NOT_FOUND` / `INVALID_SCHEDULE_RULE` / `INVALID_TIMEZONE` 能显示出来（可手工构造一次非法请求验证），不被吞。

`wakeEnabled`：

- [ ] `AutoWakeControl` 与 `BotStudio.tsx` 的 checkbox 文案改准且两处一致。截图两处。
- [ ] 总闸关闭 ≠ 单条暂停，UI 上能分清。截图。
- [ ] 新建 Bot 时 `wakeEnabled` 默认与后端一致（true）。

门禁：

- [ ] `npx tsc --noEmit -p apps/mms-web` → 0。
- [ ] `node --test apps/mms-web/tests/*.test.mjs` → 全过，且数量 ≥ **121** + 你新增（必须带 `*.test.mjs` glob）。
- [ ] hex 计数 = 12。
- [ ] `npm run build --workspace @mms/web` 通过。
- [ ] `apps/mms-web/DESIGN.md` 已补写本次视觉决定。
- [ ] 截图全部在 `docs/mms-web/design/t5b/`。
- [ ] 没有重启 60824。

## 交付格式

照 README 的通用验收，写进 worktree 的 `walls.md`（追加，不改旧条目）：

```
包：T5b
分支 / worktree：（从 bot/T5a-schedule-backend 开）
改动文件：git diff --stat 输出
测试：tsc 结果、node --test 通过数（对比基线 **121**）、hex 计数（对比 12）、build 结果
真实验证：端口、验收清单逐条勾选结果、截图路径
未完成 / 未验证：逐条
需要 Fable 确认：逐条
```

**不提交、不 push、不 merge。** T5a 和 T5b 都验收完，才一起合进 base 分支；**后端不单独落地。**

## 需要 Fable 确认

下面是写包时对照现有代码发现的、设计里没覆盖或与现状有张力的点。**不要自己改设计**；按包里给出的默认做法实现，同时把你的实际处置写回交付里。

1. **前端有两处定时入口，不是一处。** 任务描述把 composer 的定时控件写成"约 735、762、816、2603-2625"，但实际是两个不同组件，且行号在 5.0.1 上已经整体下移：**736 / 763 / 812-820 / 825-834** 属于 `BotDispatchForm`（一个"执行时间"`datetime-local` 输入 + 一个文案为 `需要时自动唤醒` 的 checkbox，用在任务派发表单里），**2714-2856** 才是聊天 composer 的定时按钮 + popover。本包默认**两处都改**（`BotDispatchForm` 也换成四种 kind 的选择器，否则它会继续产出只能触发一次的东西）。如果 Fable 只想改 composer，`BotDispatchForm` 那条路径需要一个明确处置（例如去掉它的定时入口），请确认。
2. **`getBotSecondLine` 的 schedule 分支现在读的是 `task.runAt`**（`bot-visual-system.ts` **150-157** 行，函数体 121-175），签名是 `(bot, task?, allTasks?, referenceNow?)`（2026-09-16 复核未变）。改成读 schedule 需要把 schedule 数据传进这个函数——本包默认给它加第 5 个可选参数 `schedules?: BotScheduleSummary[]`，保持前 4 个参数与现有调用点和测试兼容。若 Fable 希望改成 options 对象，会动到所有调用点和现有测试，本包没有采用。
3. **`Bot.tsx` **901-903** 行任务列表里的 `task.runAt && task.status === "scheduled"` 渲染分支在 T5a 之后会失效**（T5a 不再产生 `scheduled` task）。本包默认改成显示"由定时 X 触发"（用 T5a 在 task 上加的 `scheduleId`）。同时 `TaskStatus` 联合类型里的 `"scheduled"` 与 `taskStatusLabels.scheduled`（"已安排"）、`getStatusBadgeText` 里 `scheduled → "已排队"` 是否要一起清掉，需要确认——本包默认**保留类型和标签不删**（旧记录里可能还有 `scheduled` 的历史 task，删了会渲染成裸字符串），只是新流程不再产生它。
4. **`BotStudio.tsx:138` 的 `useState(bot?.wakeEnabled || false)` 与后端默认 `True` 不一致**（845/859 行又显式传 `true`）。这是既存问题。本包默认在 T5b 修正成与后端一致，但这会改到 `BotStudio.tsx` 的表单初始化——如果 Fable 认为这超出 T5b 范围，就只改文案不改默认值，请确认。
5. **`node --test apps/mms-web/tests/` 不带 glob 会直接失败**（2026-09-16 在 `77f2fd8a` 上重测仍然 `fail 1`，报 `test at apps/mms-web/tests:1:1`），必须写成 `apps/mms-web/tests/*.test.mjs`。README 第"通用验收"节已按此订正。
6. **`docs/mms-web/DESIGN.md` 不存在**（2026-09-16 在 `77f2fd8a` 复核），实际文件是 `apps/mms-web/DESIGN.md`（T1e / T1f / T2c / T3c 里的路径已过期）。本包用后者。
8. **`parseBotSettingCommand` 的调用点不在它自己里。** 它只 `return { patch, message }`，真正的 `onUpdateBot(bot.id, setting.patch)` 在 `Bot.tsx` **1902** 行、`sendMessage` 内。这条是 T5c 的范围，本包不动，但改 `sendMessage` 的提交逻辑时会撞到同一个函数体，见"与近期改动的冲突面"。
7. **"共 3 条""定时已暂停""自动唤醒已关闭"这些第二行文案是本包自拟的**，设计里只给了"每天 09:00 · 下次 明天 09:00"一种形状和"要处理 enabled=false"的要求。如果 owner 对措辞有偏好，在验收时一并给回。

---

# 追加（2026-09-16，T5a 独立验收之后）

T5a（#278）已经过独立验收：**周期调度是真周期**（实测两次真实触发，`nextRunAt` 推进 300.000000 秒零漂移，连续 14 次正常）、**旧的一次性 `runAt` 取巧路径真删干净了**（`grep '"scheduled"' mms_web/*.py` 没有任何代码路径再把 task 置成 `scheduled`）、**Bot 的提示词里真的列出了 schedule 子命令**（`command_catalog_text()` 生成 20 条，并且有一条门禁测试盯着"新增子命令必须进清单"，变异实测为红）。所以 T5b 可以按 T5a 已定的 API 形状写，不用担心地基会变。

但验收查出四条 T5a 侧的问题，deepseek 正在修。其中两条**直接改变 T5b 的做法**。

## A. 从修好之后的 T5a HEAD 开分支

`bot/T5a-schedule-backend` 会再推一次。**等它推完再开分支**，否则你会基于一份已知有数据丢失缺陷的后端写 UI。四条分别是：

- **P1（必须改）**：`once` 定时在 Bot「自动唤醒关闭」或 schedule「暂停中」到点时，**被永久吃掉且不留任何痕迹**（`nextRunAt=None, lastRunAt=None, lastSkip=None`，tasks 0）。修法已定：未 armed 时不消耗 `once`，保留 `nextRunAt` 并写 `lastSkip{reason:"paused"}`，重新 armed 之后的下一个 tick 补触发一次。
- **P2**：迁移在 Bot 已有 20 条 schedule 时静默丢定时，并写了一条假消息（"原来的定时已迁移成独立的定时"）。按实际结果分支写消息。
- **P3**：`POST /bots/:id/schedules/:sid` **静默忽略 body 里的 `enabled`**（实测返回 200 但值没变）。已定：改成**显式报错**，启停只走 `/enable` `/disable`。
- **P4**：提示词门禁测试加 `assert len(names) >= 20`，防止 argparse 私有属性失效后变成空断言。

**P3 直接是你的事**：管理列表里的暂停/恢复**只能**调 `/enable` `/disable`，不许在编辑 schedule 的 POST body 里塞 `enabled`。那条路现在会报错，以前是静默吞掉——两种都不会生效。

## B. `wakeEnabled` 默认值那条从"顺带修正"升级为"必须修"

包正文第 220-228 行把 `BotStudio.tsx:138` 的 `useState(bot?.wakeEnabled || false)` 写成了"顺带看一眼既存不一致"。**降级判断错了，它是承重的。**

后端 `create_bot` 默认 `wakeEnabled=True`，`BotStudio.tsx` 845/859 新建时也显式传 `true`。但 138 行的 `|| false` 意味着：**用户打开 Bot 编辑器改任何一项设置（改名、改描述、改系统提示词、换预设），保存时都会把 `wakeEnabled` 一起写成 `false`** —— 因为 958-964 行那个 POST 是**整对象覆盖式**的。

叠上 T5a 的 P1，净效果是：**用户改一次 Bot 名字，这个 Bot 名下所有待触发的一次性定时全部无声报废。** 而 `create_task(runAt=...)` 和旧记录迁移产出的都是 `once`，所以旧用户升级后那批定时正好落在这条路径上。

所以：

- 138 行改成与后端一致（`bot?.wakeEnabled ?? true`）。
- **补一条测试锁住它**：构造一个 `wakeEnabled: true` 的 bot，走一次"只改名字"的保存，断言提交的 payload 里 `wakeEnabled` 仍然是 `true`。没有这条测试，这个缺陷随时会被下一次重构放回来。
- 顺带确认 953-980 的 `AutoWakeControl` 保存路径和 1078-1086 的 patch 式路径**不要混用**（包正文第 51 行已经点出这两条路径不同）。

## C. UI 必须能区分「执行过了」和「被跳过了」

T5a 的 schedule 记录里有 `lastRunAt`、`lastSkip{reason, skipped}` 两组字段。已知的 reason 至少有 `missed`（进程没开着，错过 N 次，不补发）、`paused`（P1 修好之后的新值）、`invalid`（`sanitize_schedules` 对坏行保留并停用）。

**这三种在列表里必须看得出区别，而且不能和"已执行完"混在一起。** 这是 P1 之所以严重的原因——在 UI 上 `lastRunAt=null / lastSkip=null` 和"从来没到过点"长得一模一样。

另外这几条是 T5a 已实测确认的实际行为，UI 要如实反映，不要自己另编一套说法：

- 暂停期间 `interval/daily/weekly` 的 `nextRunAt` **继续推进**，恢复后**不补跑**（这是对的，别显示成"欠了 N 次"）。
- 编辑 `rule` 或 `timezone` 会从**现在**重算 `nextRunAt`；只改 `overlapPolicy` 不动 `nextRunAt`。
- `--once` 传一个已经过去的时间：允许创建，**下一 tick 立即补触发一次**。创建成功的提示要说明这一点。
- 跳过/错过的说明消息挂在**上一轮 task** 上；没有上一轮时只有 `lastSkip` 字段、没有消息——这种情况列表是唯一的出口。
- 同一个 Bot 的两条 schedule 在同一 tick 同时到点，即使都是 `overlapPolicy:"skip"` 也会各建一个 task（它们会自然排队，无害）。不要在 UI 上说成"重叠会被跳过"。

## D. 变异测试（硬要求，本轮新增）

交付之前，自己把核心改动**逐处撤销**，确认对应的测试**变红**。撤销之后还全绿的，说明那条测试没测到东西，要重写。

至少要覆盖：

- 把 `BotStudio.tsx:138` 改回 `|| false` → **必须红**（B 里要求的那条测试）。
- 把 composer 定时控件的 rule 构造改坏（比如 `every` 的单位换算）→ **必须红**。
- 把管理列表的暂停/恢复改成走编辑 POST 而不是 `/enable` `/disable` → **必须红**。
- 把 `lastSkip` 的三种 reason 在列表里的区分删掉 → **必须红**。

把每一条变异和它的实际输出贴进交付。**这一段没有的交付直接退回。**

理由：这一批已经反复出现"把核心修复整个撤销，测试仍然全绿"——测试只测了纯函数，没锁住真正决定行为的那一层。`node --test` 全绿不等于测到了。

## E. 交付里额外要回答的

在包正文「交付格式」的基础上补这几条：

- B 那条测试的实际断言和变异结果。
- C 里三种 `lastSkip.reason` 在列表里分别长什么样（截图）。
- 你基于的 T5a HEAD 是哪个 commit，P1–P4 是否都已经在里面。
