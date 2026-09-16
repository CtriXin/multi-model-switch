# T2c · 计划块视觉整理

Date: 2026-09-15
Task: Stride 370e87ec37e741df
起点：任务分支 `codex/stride-370e87ec37e741df` 当前 HEAD（ba03ad7c 或之后，T2b 已合入）
建议模型：gemini3.6
来源：k3 在 T2b 汇报里列的 UI 跟进项，加 Claude 验收截图 `docs/mms-web/design/t2b/`

## 现状

T2b 只做了最小接线：`BotPlan.tsx` 用现有 class 显示了计划状态标签（待确认 / 执行中 / 汇总中 / 已完成 / 已中止 / 已取消）、每步的 `result.summary`、failed 步骤的"重试 / 跳过"按钮、running 计划的"取消"按钮。数据字段见 `types.ts` 的 plan step（`status`、`result`、`onFailure`、`attempts`、`policyApplied`）与 task 的 `childResults`。

## 要修的

1. 步骤行里 Bot 名字竖排逐字换行（"验收助手乙"占三行），行高被撑大。名字列给固定最小宽度并 `white-space: nowrap`，超长省略。
2. `step.goal` 与 `result.summary` 连排显示挤在一起。改成两行：第一行 goal，第二行 summary 用次级颜色；summary 超过 2 行折叠，点"展开"看全文。
3. failed 步骤的"重试 / 跳过"按钮跟在 goal 文本流后面，位置随文本长度漂移。固定到行尾的操作列，与状态点对齐。
4. 计划头的状态标签只用了通用 `bot-plan-tag`，六种状态没有视觉区分。用现有 token 做三档：进行中（执行中 / 汇总中）用 accent，完成用 muted，异常（已中止 / 已取消 / 待确认）用 warning 色系；不新增 hex。
5. `history` 现在不显示。在计划块的 `<details>` 里加一行时间线："auto → running 10:58 → merging 11:02 → done 11:03"，只显示时间不显示日期。

## 只许改

`apps/mms-web/src/BotPlan.tsx`、`apps/mms-web/src/bot-plan.css`（或 `bot.css`，二选一，hex 总数保持 12）、`docs/mms-web/DESIGN.md`。

## 不许改

`Bot.tsx`、`types.ts`、任何 Python、受保护文件、真实 `~/.config/mms*`。

## 验收

- 用 `docs/mms-web/design/t2b/` 里的 JSON 形状造一个三步计划（一步 done、一步 failed、一步 skipped）在独立实例上渲染，桌面与 400px 各截一张；名字不再竖排，按钮在行尾，标签三档可分辨，时间线可见。
- `npx tsc --noEmit -p apps/mms-web` 0；`node --test apps/mms-web/tests/*.test.mjs` 全过（当前 93）；`npm run build --workspace @mms/web` 通过；hex 12。

## 并行规则

沿用 README：`git worktree add ../wt-T2c -b bot/T2c-plan-visual codex/stride-370e87ec37e741df`，端口 61706，不碰 60824，不提交、不 push、不 merge。
