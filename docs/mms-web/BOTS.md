# MMS Pilot Bot 工作台（v2.1）

Bot 工作台运行在当前 MMS Pilot 进程中。每个 Bot 拥有独立身份和长期会话；`presetId` 可以留空，执行任务时再解析当前可用的默认 Pi preset。所有 Bot 默认使用共享电脑的全局 `default` workspace。任务由现有 Pi session 执行，结果、事件和成果保存在 Web 的 task-private `state_root/bots` 下。

## 从 Pilot 开始

1. 启动 MMS Pilot，打开 Bot 工作台。
2. 点击“创建 Bot”会直接生成一个可用的“新 Bot”并进入聊天；头像会随机匹配形状和颜色。第一次对话会用轻量问题了解你的习惯，名称、职责、默认模型也可以直接在聊天里逐步修改。MMS Pi 模型组合（`presetId`）可以不设置，留空时执行任务会使用当前可用的 MMS 默认 Pi preset。Bot 不要求用户管理 folder 或工作目录；底层使用共享电脑的 `default` workspace。
3. 在 Bot 聊天窗口直接说目标。窗口按 Bot 聚合历史任务，自动路由的新任务和指定 Bot 的任务都会接在同一条对话里；不需要切换任务块。
4. 名称和模型可以直接说：“你以后叫小天才”“把默认模型换成 glm-5.3”“用 glm5.3 吧”。模型按当前可用的 Pi preset 匹配；模型切换在当前执行结束后生效。首次 onboarding 的每个回答会立即保存，已回答的卡片和顶部“预设”按钮都可以重新打开修改。
5. `waiting` 状态可以继续发送消息或手动唤醒；执行中的任务可以取消。取消请求需要等待 Pi 确认；15 秒后仍未停止会结束该 Bot 自有进程，只有实际停止后才记为 cancelled。
6. 任务状态仍会显示 `queued`、`starting`、`running`、`waiting`、`completed`、`failed`、`interrupted` 或 `cancelled`，但主聊天只呈现用户消息、Bot 回复、成果和等待提示。

Bot 聊天窗口只展示面向用户的消息、交接、结果、错误和等待状态。`bash`、`exit`、Pi 收到任务、内部 `list`/`wait` 等 CLI 诊断不会出现在主聊天里，但仍保留在任务事件数据中供技术排查。

Bot 主界面保持聊天软件的连续对话感，不把任务聚合成控制台式 Board。任务状态、成果和协作仍然可以从对应对话进入；需要用户处理的事项通过轻量等待提示呈现。

v2 会保存结果原文并尝试提取结论、证据、改动、未完成事项和下一步字段，但主聊天优先显示自然语言原文。Bot 默认用 1-3 句像同事一样回报，只有确实需要时才展开 Markdown 细节。

Bot 可以从内部 worker 分发子任务。子任务完成后，结果消息回写父任务，父任务进入后续执行；分发链最多五层，不能沿同一链再次调用同一个 Bot。任务中的 `requestId` 用于幂等重试，相同 ID 对应不同内容会被拒绝。

每个新任务都会保存一份轻量 `coordinatorPlan`：简单目标保持 direct，检测到明确协作意图时记录候选 Bot 和待确认的 delegate steps。它只提供可读的计划和执行上下文，不启动额外的 planner session，也不会把临时 worker 变成永久 Bot。排队任务按 `priority`（0–100，数值越大越先执行）排序，并在任务详情中显示当前等待资源原因。

### Coordinator 计划层（2026-09-12，T2）

计划从 Pi 提示词里拿出来，成为落库、可见、可执行的对象。任务启动前，`BotRuntime.plan_task` 用任务所属 Bot 自己的 preset 发一次短 planner 请求（用完即弃，结束后自动停止并归档，不常驻 planner session），输入是用户目标、可用 Bot 列表和该 Bot 的相关记忆摘要，要求输出严格 JSON（`mode` / `reason` / `steps[].botId/goal/dependsOn/presetId` / `merge`）。解析失败、模型不可用或超过 20 秒都退回关键词计划并标记 `source: "fallback"`，任何情况下不阻塞任务启动。

`mode == "delegate"` 时由 runtime 而不是提示词执行计划：按 `dependsOn` 顺序为每个 step 创建子任务（沿用现有 dispatch 路径、五层深度和同链不重复守卫），父任务进入 `waiting/children`；子任务全部终态后父任务只恢复一次，恢复提示携带各子任务的 `outcome.summary`。step 可指定 `presetId` 覆盖目标 Bot 的模型，为空则沿用其 preset。重启后按已有子任务终态判断是否恢复，`taskId` 对账保证不重复创建子任务；子任务失败不自动重试，失败摘要交给 owner 决定。

计划在聊天里以计划块可见（`BotPlan`）。Bot 设置项：`planner` = `model`（默认）/ `keywords` / `off`（off 时恒为 direct 单步）；`orchestrationPolicy` = `direct-first`（默认，计划生成后直接执行，30 秒内可在计划块撤回）/ `plan-approve`（先生成计划等用户确认）/ `off`（关闭自动分工）。`POST /api/v1/tasks/:id/plan` 接受 `approve` / `reject` / `replace`，replace 的计划按真实 Bot 名单重新校验。

Bot 之间还有独立的 `message`/`reply` mailbox。`dispatch` 用于有依赖的工作分工；`message` 用于通知、澄清和追问，不会伪装成用户消息。接收方空闲时自动投递，忙时排队；每条消息有 `queued`、`delivered`、`processed`、`waiting`、`failed` 回执。`reply MESSAGE_ID` 只能回复发给当前 Bot 的消息，连续自动往返超过 8 跳会暂停，避免 Bot 互相空转。

## 记忆与上下文

每个 Bot 有独立的持久化记忆，位于 `state_root/bots/memory/<botId>/memory.json`，与 Pi 会话和 workspace 分开。因此切换模型、重启服务或继续另一条会话不会混用 Bot 记忆。记忆分为用户/Bot 保存的事实和已完成任务的短摘要；最多保留 100 条事实、200 条任务摘要，每条最多 2,000 字。新任务会按关键词检索相关内容，在“单轮记忆预算（估算）”内作为参考资料注入；当前用户指令优先，记忆内容不增加权限。

Bot 设置里的自动记忆、单轮记忆预算和“整理阈值”可调整。整理阈值是软触发：当 Pi 回报的 context usage 达到阈值，下一轮在安全的 idle boundary 调用 Pi 原生 `compact`，并保留目标、未完成事项、文件路径和结果。Pi 未回报 context usage 时界面显示“未知”，不会伪造硬上限；压缩失败也不会删除会话记录。

## 定时与自动唤醒

任务可以带有带时区的 `runAt`。当时间到达且目标 Bot 的 `wakeEnabled` 为 `true`，Pilot 调度器会把任务从 `scheduled` 转为可执行状态。关闭自动唤醒后，计划任务不会被后台自动启动，可以手动唤醒。

自动唤醒只发生在 MMS 服务进程和当前电脑都保持运行时。它不会开机、唤醒睡眠中的电脑，也不保证无人值守网页登录、验证码或账号会话始终有效。

默认最多同时运行 3 个任务。调度器会让不同 workspace 的任务并行，并让同一 Bot 或同一 workspace 的任务串行。这是协调规则，不是操作系统级沙箱：Bot 使用当前用户权限，workspace 之间不能被当作安全隔离边界。

## 截图与成果

Pi Bot 在 worker 中执行 `screenshot` 后，截图会保存为 task-private artifact。列表只返回成果元数据和受保护的内容 URL；裸本地路径不会通过 HTTP 读取，路径越界、文件改变或大小超过限制都会失败。图片内容通过 `/api/v1/tasks/:taskId/artifacts/:artifactId/content` 读取，服务端会按 artifact 的 hash 和目录边界复核。

重启时，原来处于 `starting` 或 `running` 的任务会标为 `interrupted`，不会自动重放可能已经提交的副作用；`scheduled` 任务保留计划时间，服务恢复后按 `wakeEnabled` 再调度。继续 interrupted 任务必须由用户显式唤醒，继续提示会要求先检查已有记录和成果。如果记录中的原进程仍存在，会保留工作目录占用并阻止重复启动；不会按不明 PID 杀进程。外部副作用仍需按成果核验，不能保证任意外部系统 exactly-once。

## HTTP 简表

所有公开 mutation 仍需要同源 Host/Origin 检查和 `X-MMS-CSRF`。下面的路径均相对于 `/api/v1`：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/bots` | Bot 列表和执行能力 |
| GET | `/bots/status` | 执行器、并发和截图能力 |
| GET | `/bots/:botId/memory` | 查询该 Bot 的记忆、设置和 context usage |
| GET | `/bots/:botId/communications?peerBotId=...` | 查询该 Bot 与协作者的任务交接、消息和结果 |
| POST | `/bots` | 创建 Bot：`name`、可选的 `presetId`、`wakeEnabled`；`workspaceId` 可省略，默认使用共享电脑 |
| POST | `/bots/auto/tasks` | 从自然语言目标自动选择最合适的 Bot 并创建任务 |
| POST | `/bots/:botId` | 更新 Bot 模型或自动唤醒；workspace 仅作为内部兼容字段 |
| POST | `/bots/:botId/delete` | 删除 Bot 身份、该 Bot 的聊天任务、记忆、协作消息和截图成果；执行中或协作中的任务会拒绝删除 |
| POST | `/bots/:botId/memory` | `remember`/`forget` 一条记忆；正文为 `{ "action": "remember", "content": "..." }` |
| POST | `/bots/:botId/communications/:messageId/wake` | 手动继续投递处于等待状态的协作消息 |
| POST | `/bots/:botId/tasks` | 给指定 Bot 创建任务 |
| GET | `/bots/notifications?since=<iso>` | 拉取任务事件（完成/失败/等待/重试），`since` 之后的事件 |
| GET / POST | `/bots/notifications/config` | 读取或写入 webhook 列表（`state_root/bots/notify.json`） |
| GET | `/tasks`、`/tasks/:id` | 查询任务 |
| GET | `/tasks/:id/messages` | 查询任务事件和内部回传 |
| GET | `/tasks/:id/artifacts` | 查询成果元数据 |
| POST | `/tasks/:id/messages` | 继续任务，正文为 `{ "content": "..." }` |
| POST | `/tasks/:id/wake` | 手动唤醒 scheduled/waiting/interrupted 任务 |
| POST | `/tasks/:id/cancel` | 取消任务及其子任务 |
| POST | `/tasks/:id/accept` | 接受已完成结果并写入 `acceptedAt` |
| POST | `/tasks/:id/dispatch` | 由当前 Bot 创建带 `parentTaskId` 的子任务 |
| GET | `/tasks/:id/artifacts/:artifactId/content` | 读取已验证的图片或成果内容 |

示例（公开接口需要把 CSRF header 补上）：

```bash
curl -s http://127.0.0.1:8765/api/v1/bots
curl -s -X POST http://127.0.0.1:8765/api/v1/bots/bot_xxx/tasks \
  -H 'Content-Type: application/json' \
  -H 'X-MMS-CSRF: <bootstrap 返回的 token>' \
  -d '{"requestId":"demo-1","prompt":"检查页面并回报"}'
```

## Bot worker 命令与内部 HTTP

浏览器能力由 Ego 提供。安装了 `ego-browser` 的用户，Bot 应通过已加载的 Ego skill 或 `ego-browser nodejs` 直接使用 Ego 的公开 TaskSpace/Page 能力；MMS 只负责传入 Bot 上下文、接收结果和保存成果，不维护第二套浏览器引擎。为兼容简单任务，worker 仍提供 `browser goto URL`、`browser snapshot`、`browser click SELECTOR_OR_REF`、`browser fill SELECTOR_OR_REF TEXT` 和 `browser press SELECTOR_OR_REF KEY` 这层薄桥；随后可用 `screenshot` 保存证据。页面和登录态留在该任务的 Ego space 中，不通过 worker 输出 cookies 或原始凭据。未安装 Ego 时明确显示浏览器能力不可用，不模拟浏览器。

Pi session 启动后会收到一个私有 context 文件。内部 CLI 使用这个 context 调用受限 worker，并在 CLI 响应中隐藏 Bearer token。任务 API 不返回 token。原始 context 文件须保持私有，不能主动打印或分享。

```bash
python -m mms_web.bot_client --context /private/context.json list
python -m mms_web.bot_client --context /private/context.json memory-list
python -m mms_web.bot_client --context /private/context.json memory-search "截图"
python -m mms_web.bot_client --context /private/context.json memory-remember "用户偏好中文结果"
python -m mms_web.bot_client --context /private/context.json memory-forget mem_xxx
python -m mms_web.bot_client --context /private/context.json dispatch bot_child "检查并回报"
python -m mms_web.bot_client --context /private/context.json message bot_child "补充说明"
python -m mms_web.bot_client --context /private/context.json reply comm_xxx "收到，我继续处理"
python -m mms_web.bot_client --context /private/context.json inbox
python -m mms_web.bot_client --context /private/context.json screenshot --url https://example.com
python -m mms_web.bot_client --context /private/context.json status
python -m mms_web.bot_client --context /private/context.json complete "结果和证据"
python -m mms_web.bot_client --context /private/context.json wait "等待子任务"
python -m mms_web.bot_client --context /private/context.json fail "无法确认结果"
```

这些命令最终向只接受本机连接的 `POST /api/v1/bot-worker` 发送 JSON，并携带 `Authorization: Bearer <context token>`。worker 会校验 token、任务归属和子任务范围；外部主机、跨站 Origin、无效 URL、越权状态查询和循环分发都会被拒绝。

## 验证

开发验证使用 task-private 临时目录和确定性的 executor，不读取真实 MMS 配置、不调用收费模型、不修改账号或发布环境：

```bash
PYTHONPATH=. pytest -q \
  tests/test_mms_web_bots.py \
  tests/test_mms_bot_runtime.py \
  tests/test_mms_bot_client.py \
  tests/test_mms_bot_computer.py \
  tests/test_mms_bot_transport.py
```

这份说明描述当前实现边界和测试合同，不代表已经发布到生产，也不代表用户验收已完成。

## v2.2 chat-native interaction

Bot 工作台采用聊天软件式界面：左侧是 `Bots` 列表，主区只呈现连续对话、简短回报和必要附件。它不再展示 Mission Board、任务看板或内部执行日志。

聊天框里的每条新消息都会创建一个独立 Bot task。这样用户可以连续交给同一个 Bot 多个互不相关的目标，由执行器按并发上限同时推进；针对已有任务的补充仍从任务详情入口发送 follow-up。

Bot 的默认回报是 1–3 句自然语言。文件路径、截图和其他证据只有在确实需要时才作为附件或简短补充出现。视觉参考保存在 `docs/mms-web/design/bot-chat-v2-reference.png`。

### Pixel avatars

每个 Bot 可从 10 个内置的 7×7 pixel avatar 模板中选择，并独立选择 6 种颜色。头像是 Bot 身份的一部分，保存在 Bot 配置中；旧 Bot 会根据自身 id 稳定地获得默认模板和颜色。

### 模型与通道

Bot 编辑器复用 Pilot 的 `ModelPicker` / `ModelExplorer`：先从模型目录选模型，再在详情中选择实际通道；`Harness` 保持在路由信息中单独可见。Bot 最终保存的仍是精确 `presetId`，所以不会改变现有 MMS 启动解析链。

## v2.3 失败重试与结果送达

### 退避重试只在执行前发生

只有任务还没真正开始执行时才可能自动重试：`tick` 选中任务后的 `starting` 阶段，或 `_launch` 在把提示交给 Pi 之前抛错。退避固定为 30 秒、2 分钟、8 分钟，最多 3 次；用完仍失败则记为 `failed`，失败消息按时间列出三次重试和原因。任务上的 `retry` 记录 `count`、`nextAt`、`lastError` 以及每次尝试的时间、原因和错误码，`queueReason` 会显示“等待重试（第 n 次，原因：…）”。

`mms_web/bot_retry.py` 的 `classify(error_code, message)` 把失败分成 `transient` 和 `permanent`。基础设施类（`BOT_EXECUTOR_UNAVAILABLE`、`BOT_SESSION_BUSY`、`BOT_ENDPOINT_UNAVAILABLE`、Pi 未启动就退出、连接被拒绝/重置/超时、HTTP 429/502/503/504）可以重试；配置和用户决定类（`BOT_MODEL_REQUIRED`、`BOT_GLOBAL_WORKSPACE_REQUIRED`、模型明确拒绝、用户取消、Pi 正常结束但没有结果）立即失败。无法识别的错误按 permanent 处理，不做静默重放。

`running` 之后的失败永远不会自动重试：第一次尝试可能已经产生外部副作用，继续只能由用户显式唤醒。用户取消、显式唤醒或追加消息都会清空待执行的 `retry`；唤醒一个正在等待重试的任务会跳过剩余退避立即重新排队。

### 结果送达

任务完成、失败、进入等待（`approval` 或需要输入）或安排重试时，`mms_web/bot_notify.py` 会写入一条事件：Bot 名、任务一句话、结论摘要（`outcome.summary` 前 200 字）和任务链接 `#page=bots&bot=<botId>&task=<taskId>`。事件保存在 `state_root/bots/notifications.json`（最近 500 条），页面通过 `GET /bots/notifications?since=` 增量拉取，未读游标保存在浏览器本地；打开某个 Bot 的对话即清空它的未读，侧栏显示未读数量。

桌面通知只有在用户点击“开启桌面通知”并授予浏览器权限后才会在页面不在前台时弹出一次；没授权或关闭时只保留未读。

Webhook 配置保存在 `state_root/bots/notify.json`，形状为 `{"webhooks": [{"url": "...", "events": ["task.completed", "task.failed"], "secret": "..."}]}`，只允许 http(s) 地址，最多 10 个。投递是 5 秒超时、失败重试一次，并且永远不阻塞任务；请求体是事件 JSON，带 `X-MMS-Signature: sha256=<hmac_sha256(secret, body)>` 和 `X-MMS-Event`。`events` 留空表示全部事件。这个文件由 Bot 记忆面板的“通知”小节读写，不会写入真实 `~/.config/mms*`。

## v2.4 协作回执结构化

`dispatch` 出去的子任务结束时，回传给发起方 Bot 的消息不再是模型原文：正文取该任务 `outcome.summary`（没有结构化结论时取原文前 200 字），并附 `artifacts: [{id, name, kind, taskId}]` 索引；本地绝对路径、sha256 和 session artifact id 只留在任务内部记录里，不进入回执正文。`GET /bots/:botId/communications` 的结果行返回同样的 `content` 与 `artifacts` 字段，前端未改动（`kind: "system"` 的行按通用消息标签显示）。

运行状态不再冒充结果：任务被取消、进程中断，或 Pi 停止 / 报错导致 `failed` 时，投给对方的是一条 `system` 消息，正文为“<Bot 名> 的任务已中断，未产生结果”，归类为系统事件而不是结果；Bot 自己调用 `fail` 明确报告失败时仍按结果回传它的结论。Bot 提示词也要求向其他 Bot 回报时只写一句结论，证据和文件通过 `complete` 提交成果，不在正文贴路径或哈希。
