# T3 · 失败重试与结果送达

Task: 370e87ec37e741df · 分支 `bot/T3-notify` · 建议模型 deepseek
先读：`docs/mms-web/bot-work/README.md`、`docs/mms-web/BOT-ROADMAP.md` P0-3、`mms_web/bots.py` 第 635 到 660 行（`_finish`）、第 805 到 910 行（`_observe` 里所有 `_finish(task, "failed", ...)` 调用点）、`mms_web/bot_executor.py` 的 `validate` 和 `start` 抛出的错误码。

## 目标一句话

定时任务能无人值守跑完，并且跑完了用户会知道。

## 现状
- Provider 暂时不可用、Pi 会话忙、Pi 启动失败，统一直接 `failed`。没有退避重试。
- 任务完成或进入 `waiting` 后，结果只在页面里。用户不开页面不知道。`runAt` + `wakeEnabled` 的价值因此打折。

## 要做成什么

### 1. 有限退避重试（只针对基础设施错误）
- 新增 `mms_web/bot_retry.py`：`classify(error_code, message) -> "transient" | "permanent"`。
  - transient：`BOT_EXECUTOR_UNAVAILABLE`、`BOT_SESSION_BUSY`、Pi 进程未启动就退出、连接类错误（connection refused / reset / timeout 字样）、HTTP 429 / 502 / 503 / 504。
  - permanent：`BOT_MODEL_REQUIRED`、`BOT_GLOBAL_WORKSPACE_REQUIRED`、模型明确拒绝、用户取消、Pi 正常结束但没有结果、任何"任务已经开始执行并产生副作用之后"的失败。
- 只在任务 **尚未真正开始执行**（`starting` 阶段、或 `_launch` 抛错）时重试；`running` 之后的失败一律不自动重试，交给用户显式唤醒。这是 P0-3 的幂等边界，不能破。
- 退避：30s、2min、8min，最多 3 次；任务上记录 `retry: {"count": n, "nextAt": iso, "lastError": "..."}`，状态回到 `queued`，`queueReason = "等待重试（第 n 次，原因：…）"`。
- 用完 3 次仍失败：`failed`，结果消息里写清三次时间与原因。
- 用户取消时清空重试。

### 2. 结果送达
- 新增 `mms_web/bot_notify.py`：`Notifier.emit(event)`，event 类型 `task.completed` / `task.failed` / `task.waiting`（waitReason 为 approval / input 时）/ `task.retrying`。
- 两个投递面：
  1. **页面通知**：新增 `GET /api/v1/bots/notifications?since=<iso>` 返回未读事件；前端 `BotStudio.tsx` 在已有轮询里拉取，浏览器页面不在前台时用 `Notification` API 弹一次（用户授权过才弹，没授权就只在侧栏 Bot 卡上加未读点）。用户点开该 Bot 对话即清未读。
  2. **Webhook**：`state_root/bots/notify.json` 里可配 `{"webhooks": [{"url": "...", "events": ["task.completed", "task.failed"], "secret": "..."}]}`，POST JSON，带 `X-MMS-Signature: sha256=<hmac>`，5 秒超时，失败重试一次，不阻塞任务。Feishu 之类的机器人用这条接。**只在 Bot 设置界面提供"通知"入口读写这个文件，不碰真实 `~/.config/mms*`。**
- 通知内容：Bot 名、任务一句话、结论摘要（`outcome.summary` 前 200 字）、任务链接（`#page=bots&bot=<id>&task=<id>`）。不带工具日志。

### 3. 前端最小改动
- `BotStudio.tsx`：拉通知、未读点、Notification 权限请求（首次在用户点击"开启桌面通知"按钮时请求，不自动弹）。
- `BotMemoryPanel.tsx` 或 Bot 编辑弹窗里加"通知"小节：桌面通知开关、webhook 列表（url、事件多选、secret）。样式跟 T1 token，T1 未合并前用已有 token。

## 只许改 / 不许改
只许改：新增 `mms_web/bot_retry.py`、`mms_web/bot_notify.py`、新增 `tests/test_mms_bot_retry.py`、`tests/test_mms_bot_notify.py`；`bots.py` 只允许 (a) `_finish` 前插入 `classify` 分支 (b) `tick` 里加 `retry.nextAt` 到期出队 (c) `_finish` 末尾调用 `self.notifier.emit`，三处各不超过 15 行；`server.py` 加两个路由（通知拉取、通知配置读写）；`BotStudio.tsx`、`BotMemoryPanel.tsx`、`types.ts` 最小改动；`docs/mms-web/BOTS.md` 追加一节。
不许改：`bot_coordinator.py`、`bot_executor.py`（T2 在改）、`Bot.tsx`、任何样式文件、受保护文件。不加依赖，HMAC 用标准库 `hmac`。

## 验收
1. 单元：classify 覆盖每个错误码；`starting` 阶段 transient 失败 → queued + nextAt；`running` 阶段失败不重试；三次后 failed 且消息含三次记录；取消清空重试；webhook 签名正确、超时不阻塞、失败重试一次；通知拉取 since 过滤。focused tests 只增不减。
2. 真实：自建实例，把一个 Bot 的 preset 指向不存在的通道使 `_launch` 失败，观察三次退避与最终 failed 消息；再恢复 preset，用一个 5 分钟后的 `runAt` 任务验证完成后页面通知和本地 webhook（用 `python3 -m http.server` 或一个 20 行的接收脚本）收到签名正确的 POST。截图和接收日志放 `docs/mms-web/design/t3/`。
3. 不重启 60824。
4. walls.md 汇报。
