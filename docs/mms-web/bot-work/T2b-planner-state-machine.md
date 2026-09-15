# T2b · Coordinator 成为真正的自动计划层

Date: 2026-09-15
Task: Stride 370e87ec37e741df
起点：任务分支 `codex/stride-370e87ec37e741df` 当前 HEAD（90287459 或之后），不是 6a223c7c
建议模型：k3 主做，Claude 评审；UI 跟进另开 T2c 给 gemini

## 现状（已核对代码，不必重查）

T2 已经落了第一版：`mms_web/bot_coordinator.py` 是纯函数模块（`direct_plan`、`make_plan`、`plan_for`、`build_planner_prompt`、`sanitize_plan`、`parse_model_plan`），plan 对象有 `mode/steps/candidates/source/status`，step 有 `id/kind/botId/goal/dependsOn/presetId/status/taskId`。`bots.py` 里 `plan_task`(784-831) 在 starting 前决策一次，`_advance_plan`(833-882) 按 `dependsOn` 创建子任务，`_resume_children`(765-782) 在子任务全部终态后把摘要拼成 `resumeText` 让父任务 queued 恢复；`waitReason` 用 `children` / `plan-approval` 表达等待；`presetIdOverride` 实现每步换模型；`POST /api/v1/tasks/:id/plan` 只有 approve/reject，30 秒撤回。`BotPlan.tsx` 只展示步骤和状态点。

它离"自动计划层"差四件事，这个包只做这四件：

1. **什么时候该计划**只靠中文协作关键词和 Bot 名字打分。一句"分别给我 A 和 B"不会触发，明明能并行的任务被一个 Bot 串行做完。
2. **没有计划状态机**。`status` 只有 auto/proposed/approved/rejected，运行中、合并中、失败、取消都没有；步骤失败后父任务要么永远 waiting，要么恢复时不知道哪步坏了。
3. **没有结果图**。子任务结果只是文本拼接进 `resumeText`，父任务看不到每步的结论、证据、产物引用，也没法在界面上按步骤回看。
4. **重启与失败没有明确规则**。tick 里 `_advance_plan` 反复跑，子任务去重靠隐式条件；步骤失败没有 retry/skip/abort 语义。

## 要做成什么

### A. 计划触发：direct-first 不变，加"形状检查"

- 保留 direct-first：普通任务不调 planner，不额外启动会话。
- 新增纯函数 `looks_multi_goal(text) -> bool`：命中任一即为真：编号列表 ≥2 项（`1）`、`1.`、`①`、`- ` 开头的行）、"分别 / 同时 / 各自 / 一边…一边"、`@Bot名` 或提到 ≥2 个 roster 里的 Bot 名。不命中一律 False。
- 触发顺序：`orchestrationPolicy=off` → direct；`planner=off` → direct；显式协作信号或 `looks_multi_goal` 为真 → 走模型 planner（20 秒预算不变），失败退关键词，再失败 direct；其它 → direct。
- planner prompt 给 roster 时带每个 Bot 的 `description`、最近 3 次成功任务的标题（从 task 历史取，没有就空），让模型有依据选人。
- 反向保证：`"列出当前目录的 txt 文件"`、`"用三句话解释 git rebase"` 这类单目标任务必须 direct，写进单测。

### B. 计划状态机

plan 级 `status` 改为：`proposed → approved | rejected`，`approved | auto → running → merging → done | failed | cancelled`。每次迁移追加到 `plan.history[]`（`{at, from, to, by}`，`by` 是 system/user/step:<id>，最多 50 条）。

步骤级 `status`：`pending → ready → running → done | failed | skipped`。`ready` 表示依赖已满足但子任务还没创建；创建后进 `running`。

失败策略：step 新字段 `onFailure: "retry" | "skip" | "abort"`，默认 `retry`。`retry` 复用 T3 的重试（子任务自己重试，最多按 T3 的次数），重试仍失败按 `abort` 处理；`skip` 标 skipped 并继续；`abort` 把 plan 标 `failed`，其余 pending 步骤标 skipped，父任务恢复并在回复里只说一句哪一步失败、要不要换人重来。取消：`POST /tasks/:id/plan {action:"cancel"}` 把 plan 标 cancelled，正在跑的子任务走现有 stop，父任务恢复并告知用户。

### C. 结果图

- 子任务完成时，把它的结构化结果摘要写进对应 step：`step.result = {summary, conclusion?, evidence?, artifacts?: [{taskId, path|url, label}]}`，`summary` 不超过 600 字，其余字段有就带。`bots.py` 里已有结构化结果（结论 / 证据 / 改动 / 未完成 / 下一步）就直接映射，没有就只填 `summary`。
- `_resume_children` 改为生成 `resumeText` 时按步骤编号列出 `summary`，并在 task 上存 `childResults[]`（与 `steps[].result` 同源，便于前端一次读到）。
- 父任务恢复后的一次回复就是合并结论；`merge` 仍是 `owner`，不引入 reviewer Bot。合并完成时 plan 进 `done`。

### D. 重启与幂等

- `_advance_plan` 创建子任务前按 `(parentTaskId, step.id)` 查重：已有就把 `step.taskId` 指回去，不再建。
- 服务重启后 `tick` 对 `running` 的 plan 只做推进，不重发已完成的步骤，不重复恢复父任务（`planExecutedAt`、`resumedAt` 双重保护）。
- 单测里用假 executor 模拟：重启两次、子任务乱序完成、其中一个失败三种情况，父任务恢复恰好一次。

### 接口

- `POST /api/v1/tasks/:id/plan`：`action` 扩为 `approve | reject | cancel | retry-step | skip-step`，后两者带 `stepId`。`retry-step` 只对 failed 步骤有效，重新创建子任务；`skip-step` 标 skipped 并推进。
- `GET /api/v1/tasks/:id`（现有）返回的 `coordinatorPlan` 带上 `history`、`steps[].result`、`steps[].onFailure`；task 上带 `childResults`。
- `types.ts` 同步这些字段。

## 只许改

- `mms_web/bot_coordinator.py`：新增 `looks_multi_goal`、状态迁移辅助函数（纯函数，带表驱动的合法迁移表）。
- `mms_web/bots.py`：新增方法承载状态机、去重、结果映射；不重排已有函数；`plan_task` / `_advance_plan` / `_resume_children` 只做最小改动调用新方法。
- `mms_web/bot_executor.py`：只允许改 planner prompt 里 roster 的组装。
- `mms_web/server.py`：只扩 `/tasks/:id/plan` 的 action 分发。
- `apps/mms-web/src/types.ts`：加字段。
- `apps/mms-web/src/BotPlan.tsx`：**只做最小接线**，让新状态和 `step.result.summary` 能显示出来、failed 步骤有"重试 / 跳过"两个按钮、plan 有"取消"按钮，样式沿用现有 class，不新增 css。视觉整理由 T2c 做。
- `tests/test_mms_bot_coordinator.py`、`tests/test_mms_bot_runtime.py`、`tests/test_mms_web_bots.py`：新增用例。
- `docs/mms-web/BOTS.md`：追加"计划状态机"一节，把两张状态表和失败策略写进去。

## 不许改

- `Bot.tsx`、`BotStudio.tsx`、`bot*.css`、`bot-plan.css`。
- `bot_notify.py`、`bot_memory.py`、`sessions.py`。
- 受保护文件；真实 `~/.config/mms*`。
- 不引入 planner / worker / reviewer 常驻 Bot；不引入外部编排库；后端只用标准库。

## 验收

1. 单测（focused 集合只增不减，当前 150 passed）：
   - `looks_multi_goal` 正例 5 条、反例 5 条（含"列出 txt 文件"、"三句话解释 git rebase"）。
   - 状态迁移表：非法迁移抛错或返回 False，`history` 追加且封顶 50。
   - `onFailure` 三种策略各一条；`cancel` 一条。
   - 重启幂等三条（见 D）。
   - 接口：`retry-step` 对非 failed 步骤返回 4xx；`skip-step` 推进依赖。
2. 真实链路，在独立实例（端口 61800，state-root `/tmp/bot-verify-T2b`，不碰 60824）：建三个 Bot A/B/C（真实模型，小任务），给 A 派"分别给我：1）三句话介绍 git rebase；2）三句话介绍 git merge"。要看到：plan 由 `looks_multi_goal` 触发、B/C 各领一步、A 最后只回一条合并结论、`GET /tasks/:id` 里 `coordinatorPlan.history` 从 running 到 done、两个 `steps[].result.summary` 非空。截图放 `docs/mms-web/design/t2b/`，三份脱敏 JSON 一起放。
3. 反向：同一实例给 A 派"用三句话解释什么是 git rebase"，必须 direct，不建子任务。
4. 失败路径：把 C 的 preset 指向一个不存在的模型，重跑第 2 条，看到 C 步 failed、A 恢复并说明哪步失败；再用 `retry-step` 修好后跑通。
5. `python3 -m compileall -q mms_web`、focused pytest、`node --test apps/mms-web/tests/*.test.mjs`（≥83）、`npx tsc --noEmit -p apps/mms-web`、`npm run build --workspace @mms/web`。
6. 汇报按 README 格式写进 worktree 的 `walls.md`，列出：哪些 UI 需要 T2c 跟进（你只做接线，把觉得难看或放不下的地方写出来）。

## 并行规则

沿用 README：`git worktree add ../wt-T2b -b bot/T2b-planner codex/stride-370e87ec37e741df`，端口 61800，不提交、不 push、不 merge，不重启 60824，不写真实配置。做完汇报 `git diff --stat`、测试命令与结果、截图路径、未完成项。
