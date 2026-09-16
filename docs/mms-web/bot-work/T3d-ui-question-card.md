# T3d-ui · 等你回复：提问卡、头部与侧栏

Date: 2026-09-15
Task: Stride 370e87ec37e741df
起点：任务分支 `codex/stride-370e87ec37e741df` 当前 HEAD（ba03ad7c 或之后，T3d 后端已合入）
建议模型：gemini3.6
来源：`T3d-waiting-contract.md` 的"前端"一节，后端字段已定

## 后端已提供的字段与接口（已合入，可直接用）

- `GET /api/v1/bots` 每个 bot 有 `pendingQuestion: { taskId, question, options: string[], since } | null`。只有带真实问题的 `waiting/user` 任务才会出现。
- task 对象上有 `waitQuestion`、`waitOptions`、`waitSince`；旧脏任务 `waitQuestion` 为空串。
- `POST /api/v1/tasks/:id/wait`，body `{ action: "answer", text }` 恢复任务（返回 `status: queued`），`{ action: "dismiss" }` 按完成收尾（返回 `waitDismissed: true`）。非等待任务返回 409。

## 要做成什么

1. 聊天底部固定一张提问卡（在输入框上方，随聊天滚动不消失）：问题文本（支持换行与简单 Markdown）、`options` 逐个渲染成按钮，点按钮直接以该文本回答；输入框自动聚焦，placeholder 改成"回答它的问题…"；两个动作"回复"（把输入框内容发到 `/wait answer`）和"结束等待"（`dismiss`）。回答后卡片消失，任务恢复的进度照常显示。
2. 头部状态：有 `pendingQuestion` 时显示"等你回复"，替代"待命"；侧栏卡片第二行同样显示"等你回复"，两处都只读 `pendingQuestion`。
3. 从侧栏点进有 `pendingQuestion` 的 Bot，自动滚到提问卡并高亮一次。
4. 旧任务：`status=waiting && waitReason=user && !waitQuestion` 的任务，原来那个只有小标签的"等待你补充信息"（`Bot.tsx` 里 `waitReasonLabel` 的两处）改成一行"这条旧任务在等待，但没有留下问题"加"结束等待"按钮（`dismiss`）。
5. `types.ts` 加 `pendingQuestion` 与三个 wait 字段的类型。

## 只许改

`apps/mms-web/src/Bot.tsx`、`apps/mms-web/src/BotStudio.tsx`（只改卡片第二行取值）、`apps/mms-web/src/bot.css`（hex 12）、`apps/mms-web/src/types.ts`、`apps/mms-web/tests/` 新增一个纯函数测试（从 bot 与 tasks 算"头部状态文案"的函数）。

## 不许改

任何 Python；`BotPlan.tsx`、`BotCommunications.tsx`；受保护文件；真实 `~/.config/mms*`。

## 验收

- 复制 60824 的 state 到独立实例。三种状态各一张截图：有问题（用真实小任务让 Bot 提问，例如"先问我一个问题再开始：我要 A 还是 B？"）、旧任务无问题、回复后恢复。
- 头部与侧栏文案一致；点 options 按钮能恢复任务；`dismiss` 后卡片消失。
- 400px 提问卡不遮住输入框。
- `npx tsc --noEmit -p apps/mms-web` 0；`node --test apps/mms-web/tests/*.test.mjs` 全过且 ≥ 94；`npm run build --workspace @mms/web` 通过；hex 12。

## 并行规则

沿用 README：`git worktree add ../wt-T3d-ui -b bot/T3d-waiting-ui codex/stride-370e87ec37e741df`，端口 61704，不碰 60824，不提交、不 push、不 merge。
