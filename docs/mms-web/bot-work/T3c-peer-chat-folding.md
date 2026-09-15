# T3c · Bot 间往来在主聊天里折叠，协作面板按任务分段

Date: 2026-09-15
Task: Stride 370e87ec37e741df
起点：任务分支 `codex/stride-370e87ec37e741df` 当前 HEAD
建议模型：gemini3.6（纯前端）
来源：owner 2026-09-15 截图反馈（调度 ↔ 大总管 问候）

## 问题

1. 让调度跟大总管打个招呼，主聊天出现了四条 Bot 发言加两个"已发消息给 …"按钮：`已向大总管发送："你好 我是调度" — 消息已排队投递…`、大总管的回复以调度头像之外的第二个头像出现在调度的聊天里、`已与 大总管 完成双向消息：它说 '…'，我回复 '…' 双方沟通完毕，无待办。`。用户不知道该不该看，主聊天应该只有用户消息、Bot 回复、成果、等待提示（CLAUDE-CONTINUATION 的边界）。
2. 协作面板已经按对方 Bot 选择（`BotCommunications.tsx` 的 `peers` / `selectedPeer`），但界面上看不出当前在看谁、怎么切换；同一个对方下，9 月 11 日的"结果"回传和今天的"消息"问候按时间平铺，混在一起。

## 要做成什么

### A. 主聊天：一个任务里与同一个对方的往来折叠成一张卡

- 位置：现在 `Bot.tsx` 2205 到 2250 行渲染 `bot-chat-event` 事件流和 `communicationGroups` 的 `bot-communications-marker` 按钮。改成：每个 `(conversationTask, peer)` 只渲染一张折叠卡 `<details class="bot-peer-thread">`，summary 是 `与 大总管 的往来 · 3 条`，右侧一个小时间；展开后在原位按时间列出这几条消息，每条带发送方小头像和名字，样式沿用协作面板里的消息卡但去掉"已处理"标签。默认收起。
- 卡片仍可跳到协作面板：summary 右侧加一个"在协作面板查看"文字按钮，调用现有 `onOpenCommunications(peer.id)`。
- 事件流里与 peer 往来相关的 `bot-chat-event`（投递、送达、回复到达）不再单独渲染，归进这张卡。
- Bot 自己的转述句（`Bot.tsx` 429 / 434 / 1720 行的正则已经在过滤"已向…说""协作者…打招呼"），把这些被过滤掉的句子也放进折叠卡尾部，标成"Bot 的说明"，不再丢弃。过滤正则不要再加长；如果你发现还有明显漏网的固定句式，写进汇报，不要自己扩正则。
- Bot 给用户的最后一句结论照常显示，不折叠。

### B. 协作面板：对方切换可见，按任务分段

- 顶部加对方 Bot 的切换条：头像 + 名字 + 未读/最近时间，当前项高亮；只有一个对方时也显示，让用户知道在看谁。
- 段落按任务分：每个 `taskId` 一段，段头是任务的第一句用户请求（截 60 字）+ 日期，段内按时间排消息；没有 `taskId` 的归到"未关联任务"段。最新任务在最上。
- `kind` 区分：`result` 的卡加"结果"标签且允许折叠长文本（超过 6 行折叠，点开展开），`message` 保持现在的样式，`dispatch` 标"任务"。
- 面板副标题"调度 与其他 Bot 的消息往来"改成"调度 与 大总管"跟随当前对方。
- 日期分隔：不同天之间插一条细分隔线，只显示日期。

## 只许改

`apps/mms-web/src/Bot.tsx`（2205 到 2250 行的事件与 marker 渲染，加一个折叠卡组件，可放在同文件底部）、`apps/mms-web/src/BotCommunications.tsx`、`apps/mms-web/src/bot.css`（新 class 用现有 token，hex 计数保持 12）、`apps/mms-web/tests/` 新增一个纯函数测试文件（分组函数：按 task 分段、按天分隔，各一条断言）、`docs/mms-web/DESIGN.md` 如需补 class 说明。

## 不许改

`mms_web/` 任何 Python；`BotStudio.tsx`、`BotPlan.tsx`；消息数据结构（不改 `BotCommunication` 字段）；受保护文件；真实 `~/.config/mms*`。

## 验收

- 用 60824 上已有的调度 ↔ 大总管 问候记录（不要新发任务）：调度的聊天里只剩用户消息、一张收起的"与 大总管 的往来 · 3 条"卡、调度给用户的最后一句；展开后能看到三条；截图收起与展开各一张。
- 协作面板：顶部能看到对方切换；大总管下 9 月 11 日的"结果"和 9 月 15 日的"消息"分在不同任务段，中间有日期分隔；截图。
- 窄窗 400px 折叠卡和面板不溢出，截图。
- `node --test apps/mms-web/tests/*.test.mjs` 全过且数量 ≥ 84 加你新增；`npx tsc --noEmit -p apps/mms-web` 0 错误；`npm run build --workspace @mms/web` 通过；bot css hex 12。

## 并行规则

沿用 README：`git worktree add ../wt-T3c -b bot/T3c-peer-folding codex/stride-370e87ec37e741df`，验证实例端口 61702，state-root 可以复制 60824 的 state 目录到 `/tmp/bot-verify-T3c` 只读使用，不碰 60824，不提交、不 push、不 merge。
