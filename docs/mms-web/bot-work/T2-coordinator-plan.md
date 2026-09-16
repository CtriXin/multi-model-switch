# T2 · Coordinator 计划层落地

Task: 370e87ec37e741df · 分支 `bot/T2-coordinator` · 建议模型 k3
先读：`docs/mms-web/bot-work/README.md`、`docs/mms-web/BOT-ROADMAP.md` P0-1、`docs/mms-web/CLAUDE-CONTINUATION.md` 的"不能退回的架构边界"、`mms_web/bot_coordinator.py`、`mms_web/bots.py` 第 378 到 410 行（`create_task`）、第 635 到 760 行（`_finish`、`tick`、`_launch`）、`mms_web/bot_executor.py` 的 prompt 拼装。

## 目标一句话

把"要不要分工、派给谁、等谁、用什么模型"从 Pi 提示词里拿出来，变成一个落库、可见、可执行、可测试的计划对象。这是 MMS 相对 Grok 的护城河：每个子任务都能换模型。

## 现状

`bot_coordinator.py` 的 `make_plan` 只做两件事：中文关键字正则判断"是否协作"，再按 Bot 名字 / 描述词频挑候选。它产出的 `coordinatorPlan` 只是记录，`steps` 从不被执行；实际是否 `dispatch` 仍由 Pi 里的模型自己决定。`orchestrationPolicy` 是写死的 `"direct-first"` 字符串。

## 要做成什么

### 1. 计划由一次带 schema 的模型调用产出
- 新增 `BotRuntime.plan_task(task, bot)`：在任务进入 `starting` 前，用 **任务所属 Bot 的 preset** 发一次短请求，输入 = 用户目标 + 可用 Bot 列表（名字、描述、模型）+ 该 Bot 的相关记忆摘要，要求输出严格 JSON：
  ```json
  {"mode": "direct" | "delegate",
   "reason": "一句话",
   "steps": [{"id": "s1", "botId": "...", "goal": "...", "dependsOn": [], "presetId": null}],
   "merge": "owner"}
  ```
- JSON 解析失败或模型不可用时退回现有 `make_plan` 的关键字逻辑，并在 plan 上标 `"source": "fallback"`。任何情况下不得阻塞任务启动超过 20 秒。
- 调用走现有 `PiBotExecutor` / sessions 通道，不新开常驻 planner session。用完即弃。
- 用户在 Bot 设置里能关掉：`bot["planner"] = "model" | "keywords" | "off"`，默认 `"model"`。`off` 时 plan 为 direct 单步。

### 2. 计划由 runtime 执行，不靠提示词自觉
- `mode == "delegate"` 时，runtime 按 `dependsOn` 顺序为每个 step 创建子任务（沿用现有 `dispatch` 路径和深度 5 / 同链不重复的守卫），父任务进入 `waiting`，`waitReason = "children"`；子任务全部终态后父任务恢复，恢复提示里带各子任务的 `outcome.summary`。
- step 可指定 `presetId`，为空则用目标 Bot 自己的 preset。
- 用户可以在计划执行前拒绝或改：新增 `POST /api/v1/tasks/:id/plan` 接受 `{ "action": "approve" | "reject" | "replace", "plan": {...} }`。`planner` 为 `model` 时默认 **不等确认直接执行**，但计划块在聊天里可见且 30 秒内可撤回；用户在设置里可以改成"先确认"。
- `orchestrationPolicy` 字段保留兼容，值改为实际策略：`direct-first` / `plan-approve` / `off`。

### 3. 计划在聊天里可见
- 新建 `apps/mms-web/src/BotPlan.tsx` + `bot-plan.css`。在 `Bot.tsx` 的 `BotChat` 里，紧接任务的第一条用户消息之后插入 `<BotPlan task={task} bots={bots} onAction={...} />`。**只允许这一处插入，一行 JSX。** 样式跟随 T1 的 token 和 gutter 规范（读 `T1-ui-visual-system.md` 的"一条左边缘"），T1 未合并前先用 `var(--accent)` 等已有 token 写。
- 显示：一句 reason；delegate 时列出每个 step（目标 Bot 头像 + 名字 + 一句目标 + 状态点）；可展开看 dependsOn 和模型。
- 不显示模型思维过程，不显示 JSON。

### 4. 状态与恢复
- plan 持久化到 task 记录；重启后父任务处于 `waiting/children` 的，按已有子任务终态判断是否恢复，不重复创建子任务。
- 子任务失败：父任务恢复时把失败摘要交给 owner，由 owner 决定重试或报告；runtime 不自动重试子任务（重试策略归 T3）。

## 只许改 / 不许改
只许改：`mms_web/bot_coordinator.py`、`mms_web/bots.py`、`mms_web/bot_executor.py`（只加 planner 调用和 prompt 里的"计划已由系统决定"一句）、`mms_web/server.py`（只加 `/tasks/:id/plan` 一个路由）、`tests/test_mms_bot_coordinator.py`、`tests/test_mms_bot_runtime.py`、新增 `BotPlan.tsx` / `bot-plan.css`、`Bot.tsx` 一行插入、`types.ts` 加 plan 类型、`docs/mms-web/BOTS.md` 追加一节。
不许改：`bot.css` 及其它样式文件、`BotStudio.tsx`、受保护文件。`bots.py` 里不要重排已有函数，新逻辑放新方法。

## 验收
1. 单元：plan JSON 解析（合法、缺字段、非 JSON、超时）四条；delegate 执行创建子任务且 `dependsOn` 顺序正确；父任务恢复只发生一次；重启后不重复创建；`planner=off` 走 direct。focused tests 总数只增不减。
2. 真实链路（这是 roadmap P0-1 的验收，必须做）：自建实例，创建 A / B / C 三个 Bot（可用 glm5.3 之类便宜模型），给 A 一句包含两个独立子目标的话，例如"让 B 在工作目录写 b.txt 内容 hello，让 C 写 c.txt 内容 world，都完成后告诉我两个文件的字节数"。期望：聊天里出现计划块，B / C 各一个子任务，A 进入等待，两者完成后 A 恢复并只给用户一条结论。截图放 `docs/mms-web/design/t2/`，把三个任务的 JSON（脱敏）附在汇报。
3. 反向：一句普通任务"把工作目录里的 txt 文件列出来"不得触发 delegate。
4. 不重启 60824。
5. walls.md 汇报。
