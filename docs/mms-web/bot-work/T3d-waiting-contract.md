# T3d · "等你补充"必须带问题；记忆不存无产出任务

Date: 2026-09-15
Task: Stride 370e87ec37e741df
起点：任务分支 `codex/stride-370e87ec37e741df` 当前 HEAD
建议模型：后端 deepseek；前端部分另派 gemini，等后端字段定下来再做
来源：owner 2026-09-15 截图反馈（大总管侧栏一直"等待你补充信息"，进去找不到要补充什么）

## 问题

1. 大总管有一条 9 月的旧任务"自动路由测试：只等待，不要修改文件"，模型说了"等待"但没有提出任何问题，任务状态卡在 `waiting / waitReason=user`。侧栏卡片一直显示"等待你补充信息"，点进去聊天底部只有一个"等待你补充信息"的小标签，没有问题、没有输入入口，头部却显示"待命"。
2. 记忆面板把"跟大总管打招呼"这种没有产出的任务也自动存成"任务摘要"（`bots.py` 737 行附近，`state == "completed"` 就存 digest），两条问候就占了两条记忆，是噪音。

## 后端（deepseek）

### A. 等待契约

任务进入 `waiting / waitReason=user` 的唯一入口在 `bots.py` 1239 到 1244 行（`waitRequested` 分支，现在从最后一条 progress 消息取 reason）。改成：

- 新字段：`task.waitQuestion: str`（必填，非空）、`task.waitOptions: list[str]`（可选，最多 4 条快捷回复）、`task.waitSince: iso`。
- 问题来源按优先级：执行器 `wait` 内部工具的显式参数（先看 `bot_executor.py` 里 `wait` 工具怎么定义、`waitRequested` 怎么设，给它加 `question` 与 `options` 两个可选参数并透传）；没有显式参数时取最后一条 progress / assistant 文本，但必须像一个问题：含 `?` 或 `？`，或以"请…""吗""哪""什么""是否""要不要"等疑问形式结尾（写成一个纯函数 `looks_like_question(text)`，带单测）。
- 两者都拿不到问题时，不进入等待：按 `completed` 结束，结果就是那段文本，并在 task 上记 `waitDeclined=true` 便于排查。
- `GET /api/v1/bots` 每个 bot 增加派生字段 `pendingQuestion: {taskId, question, options, since} | null`，取该 bot 最新一条 `waiting/user` 任务。头部和侧栏都只读这个字段，不再各自推断。
- 回复：确认现有 `inbox` 路径（1232 行）能让用户在聊天里发一句话就恢复任务；补一个 `POST /api/v1/tasks/:id/wait {action: "answer", text} | {action: "dismiss"}`，`dismiss` 把任务按 `completed` 收尾并记 `waitDismissed=true`。
- 过期：`tick` 里 `waiting/user` 超过 7 天自动 `dismiss`，结果文本"等待超时，已结束"。
- 迁移：启动加载时，已有的 `waiting/user` 任务若没有 `waitQuestion`，从其 progress 文本套 `looks_like_question`；套不出来的直接标 `waitQuestion=""` 并让 `pendingQuestion` 忽略它们（`question` 为空的不算 pending），这样旧脏数据不再点亮侧栏。

### B. 记忆噪音

`_finish` 完成分支只在满足任一条件时存 digest：`task.outcome` 有非空 `conclusion` 或 `changes`；任务有 artifacts；结果文本 ≥ 120 字且不是纯粹的问候/确认（复用 `looks_like_question` 旁边再写一个 `is_trivial_result(text)`：短于 120 字或匹配"收到|明白|已发送|沟通完毕|无待办|先候着"即为琐碎）。纯 peer 消息任务（有 communications、无 artifacts、无 outcome）一律不存。带单测。

### 只许改

`mms_web/bots.py`（新方法承载，不重排已有函数）、`mms_web/bot_executor.py`（只加 `wait` 工具的两个参数透传）、`mms_web/server.py`（一个路由 `/tasks/:id/wait`）、`mms_web/bot_memory.py` 不动、`tests/test_mms_web_bots.py` / `tests/test_mms_bot_runtime.py` 新增用例、`docs/mms-web/BOTS.md` 追加"等待契约"一节。

### 不许改

前端文件；`bot_coordinator.py`、`bot_notify.py`、`sessions.py`；受保护文件；真实 `~/.config/mms*`。

### 验收

- 单测：`looks_like_question` 正反各 6 条；`is_trivial_result` 正反各 4 条；无问题不进等待、显式 question 进等待并带 options、`dismiss`、7 天过期、启动迁移把旧脏任务的 `pendingQuestion` 置空；记忆四种条件各一条。focused 集合只增不减。
- 用 60824 的 state 复制到 `/tmp/bot-verify-T3d`，起独立实例 61703：启动后 `GET /api/v1/bots` 里大总管的 `pendingQuestion` 为 null（旧任务无问题）；用假执行器或真实小任务让 Bot 提一个问题，看到 `pendingQuestion` 有内容，`answer` 后任务恢复。贴 JSON。
- `python3 -m compileall -q mms_web`；focused pytest；`python3 scripts/regression_fresh_user_gate.py --quick`。

## 前端（gemini，后端合入后做）

- 聊天底部固定一张提问卡：问题文本、`waitOptions` 作为按钮、输入框自动聚焦；两个动作"回复"（发到 `/tasks/:id/wait answer`）和"结束等待"（`dismiss`）。有 `pendingQuestion` 时输入框 placeholder 改成"回答它的问题…"。
- 头部状态：有 `pendingQuestion` 时显示"等你回复"，与侧栏卡片一致；侧栏卡片点进来自动滚到提问卡。
- 现在那个只有小标签的"等待你补充信息"状态（1110 行、2242 行）：`pendingQuestion` 为空的等待任务显示"这条旧任务在等待，但没有留下问题"加一个"结束等待"按钮。
- 只许改 `Bot.tsx`、`BotStudio.tsx` 卡片行、`bot.css`、`types.ts`、测试；hex 保持 12。验收：三种状态各一张截图（有问题、旧任务无问题、回复后恢复），tsc / node / build 通过。

## 并行规则

沿用 README：后端 `git worktree add ../wt-T3d -b bot/T3d-waiting codex/stride-370e87ec37e741df`，端口 61703；前端另开 `../wt-T3d-ui`、分支 `bot/T3d-waiting-ui`，从后端合入后的任务分支 HEAD 开，端口 61704。不碰 60824，不提交、不 push、不 merge。
