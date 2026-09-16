# T5a · 定时从"一次性字段"换成真正的周期调度（后端）

Date: 2026-09-16
Task: Stride 370e87ec37e741df
分支：`bot/T5a-schedule-backend`，从 **`dev`** 开（重组后 `dev` 即 5.x 线）；重组尚未完成时用 **`origin/dev-pre`**（本次刷新的基准：`77f2fd8a` = 5.0.1）
建议模型：k3 或 deepseek（纯后端 Python）
来源：owner 2026-09-16 反馈——"跟 Bot 说每三小时查一次机票，它回答自己没有后台定时能力"

先读：`docs/mms-web/bot-work/README.md`（并行规则、通用验收）、本文件、然后按下面"要读的代码"逐处确认。

## 共同背景（T5a / T5b 共享，必读）

Bot 现在的"定时执行"只是 task 上的一个 `runAt` 字段：`create_task`（`bots.py` 497 行起，`run_at = parse_time(...)` 在 **519**、`"status": "scheduled" if run_at else "queued"` 在 **525**）看到 `runAt` 就把 task 建成 `status="scheduled"`；调度线程 `_loop` → `tick`（唤醒分支在 `bots.py` **1485-1489** 行）到点把它转成 `queued`，同时 `runAt=None`。

所以：

- 它**只能触发一次**，本质是"定时发送"，跑完就没了，用户下一轮还要手动发起。
- owner 明确否掉这种做法。
- owner 同时否掉了"Bot 跑完自己再约下一次"的取巧方案：漏一轮就断，而且依赖 Bot 每次都记得重约。

owner 的硬约束：**功能要么做完，要么不做。**

- T5a（后端）和 T5b（前端）**不允许分开落地**。
- T5b 从 T5a 完成后的 HEAD 接着做。
- 两个包都验收完才**一起**合进任务分支。
- **后端单独进任务分支是被禁止的。**

同批还有 **T5c**（`T5c-model-switch-by-dialogue.md`，在对话里换 Bot 的模型）。它动的是 `bot_executor.py` 的提示词和 `bot_client.py` 的 parser——**和本包是同一批文件**，所以它也必须从 T5a 完成后的 HEAD 开分支，不能和本包并行。落地顺序：**T5a → T5b / T5c**（T5b 纯前端、T5c 后端为主，两者彼此不重叠，可以并行）。三个包都验收完才一起合进任务分支。本包新做的"命令清单从 parser 生成"正是 T5c 直接依赖的基础设施。

已知并已被 owner 接受的能力边界：**Pilot 是本机进程，它不运行定时就不触发。** 这一点要在实现和文档里写明，并按下面"策略 2：错过的触发"处理。**不要引入 launchd / systemd / 开机自启方案**，本轮不做常驻守护。

## 目标一句话

把定时从 task 上的一个一次性字段，换成独立的 schedule 实体 + 真正的周期调度；Bot 自己能建，跑完的结果会送到用户眼前。

## 要读的代码（只读，先看完再动手）

| 位置 | 看什么 |
| --- | --- |
| `mms_web/bots.py` 约 272 行 | 调度线程 `mms-bot-scheduler` 的创建方式 |
| `mms_web/bots.py` 1439-1449 行 | `_loop`：0.5s `self._changed.wait()`、异常后设 `_load_error` 暂停派发 |
| `mms_web/bots.py` 1451 行起 | `tick`（1452 行的 `if self._load_error or self._stop.is_set(): return` 是入口守卫）：轮询、`_deliver_mailbox`、孤儿检查、**1485-1489 行的 `status=="scheduled"` 唤醒分支**、waiting 超时、`_advance_plan`、并发与队列派发 |
| `mms_web/bots.py` 497-544 行 | `create_task`：`run_at = parse_time(payload.get("runAt"))`（**519**）、`"status": "scheduled" if run_at else "queued"`（**525**） |
| `mms_web/bots.py` 343-382 行 | `create_bot` 的 Bot 实体字段清单（`wakeEnabled` 默认 `True` 在 **364**；`validate()` 覆盖在 **379**）。注意 5.x 上该实体还带 `memoryEnabled` / `memoryBudgetTokens` / `autoCompact` / `compactAtPercent` / `orchestrationPolicy` / `planner` / `avatarId` / `avatarColor`，新增字段时不要挤掉它们 |
| `mms_web/bots.py` 196-264 行 | `__init__`（196-214）/ `_load`（216-247）/ `_persist`（249-263）：`state.json`、**222 行 `if data.get("schema") != 2: raise ValueError("Unsupported bot record")`**、246-247 行把它吞成 `_load_error = "Bot 记录无法读取…"`、250-251 行 `_load_error` 一旦置位 `_persist` 直接 `WebError("BOT_STORE_INVALID", ..., 409)`、254-260 行 `owner.lock` flock |
| `mms_web/bots.py` 703-718 行 | `_migrate_wait_contracts`：现有的"加载时迁移旧记录"写法，照它的形状写迁移 |
| `mms_web/bots.py` 488-495 行 | `_message(task_id, kind, content, ...)`：**消息以 taskId 为 key**，没有 task 就没有地方写消息；截断用 `MAX_MESSAGES = 500`（**37** 行定义，493-494 行 `del rows[:-MAX_MESSAGES]`） |
| `mms_web/bots.py` 1856-1919 行 | `worker(task_id, payload)`：`bot_client` 的每个子命令在这里落地成一个 `action` 分支（现有分支：`list` 1860、`memory_list`/`memory_search` 1862、`memory_remember` 1870、`memory_forget` 1879、`message`/`reply` 1882、`inbox` 1884、`dispatch` 1887、`screenshot` 1890、`browser` 1892、`status` 1897、`complete`/`fail`/`wait` 1906，兜底 `BOT_ACTION_UNKNOWN` 1919） |
| `mms_web/bots.py` 945-950 行 | `_notify(task, event_type)`：best-effort，异常吞掉，不让通知拖垮任务。`_finish` 在 886 行，尾部 942-943 行调用它 |
| `mms_web/errors.py` + 全文 `WebError` | 错误码风格：`WebError("BOT_LIMIT", "最多创建 50 个 Bot。", 409)`，大写下划线码 + 简体中文用户可读句子 + HTTP 码 |
| `mms_web/bot_client.py` | `_build_parser`（**140-205**）/ `with_request_id`（**149-158**）/ `_command_payload`（**208-276**）三段的写法。**现有 15 个子命令**：`list` 160、`memory-list` 162、`memory-search` 163、`memory-remember` 165、`memory-forget` 167、`dispatch` 170、`message` 174、`reply` 177、`inbox` 180、`screenshot` 182、`browser` 185、`status` 190、`wait` 193、`complete`/`fail` 199-205。`main()` 在 285-305、`__main__` 守卫在 307-308，模块级只有常量与函数定义，**import 是安全的** |
| `mms_web/bot_executor.py` 46-88 行 | `start()`（def 在 **46**）里那段系统提示词字符串（**49-88**），尤其 **62-63** 行的"子命令：…"两行（**不是旧包写的 51 行**） |
| `mms_web/bot_notify.py` **25** 行、105-116 行 | `EVENT_TYPES = ("task.completed", "task.failed", "task.waiting", "task.retrying")` 固定元组、`emit_task(bot, task, event_type, wait_reason=None, note="")`（payload 在 111-116 行拼出 `type/botId/botName/taskId/title/summary/waitReason/link`） |
| `mms_web/server.py` 305-326 行、430-459 行 | Bot 相关 GET（`def get` 在 **304**）/ POST（`def _post` 在 **429**）路由的写法（`parts == [...]` 匹配；POST 在 449-459 行用 `getattr(self.bots, action + "_task")` 做方法名映射） |

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

### 1. T5a / T5c 改 `bot_executor.py`，PR #270 也改它 —— 以 #270 合并后的版本为基准

PR #270 在 `mms_web/bot_executor.py` 上是 +39/−12，落点是 Pi 0.85.1 的 `contextUsage.percent` 已经是 0–100、旧代码多乘了一次 100，以及把 `Nothing to compact (session too small)` / `Already compacted` 从阻塞错误改成 no-op。它同时动 `bots.py`（+2/−3）和 `service.py`（+9/−2）。

- **本包要改的是同一个 `bot_executor.py`**（51→**62-63** 行那段提示词）。虽然改的行不同（#270 动的是 compact 逻辑，本包动的是提示词字符串），但同文件必然在 rebase 时需要人工确认。
- **要求：开工前先确认 #270 是否已合。**
  - 已合 → 直接从合并后的 `dev` / `dev-pre` HEAD 开分支。
  - 未合 → 仍从 `dev` / `dev-pre` HEAD 开，但在交付里写明"本包基于未含 #270 的版本"，并在 #270 合入后跑一次 `git merge` 确认 `bot_executor.py` 无语义冲突。
- **不要自己去改 #270 的那批行。** compact 逻辑不在本包范围。

### 2. `mms_web_static/` 是提交进仓库的构建产物

`8fc1adf8` / `5be8649a` / `f8c21cb2` / `88114765` / `6d9001d6` 每一个都重写了 `mms_web_static/build.json`、`index.html` 和带 hash 的 asset 文件名。本包是纯后端，**不要跑 `npm run build` 然后把 `mms_web_static/` 一起提交**——那会和任何并行分支产生必然的文本冲突，而且本包根本不改前端。真实验证需要页面时，本地 build 但不 stage。

### 3. `bots.py` 的改动面在 5.0.1 上比旧包估算时更挤

PR #270 也在 `bots.py` 上有 +2/−3。本包对 `bots.py` 的"最小接线"清单（`tick` ≤ 25 行、`create_task` ≤ 15 行、`worker` ≤ 20 行、删唤醒分支 −6 行、5 个薄方法）不变，但交付时**要按行数逐项报**，方便和 #270、T5c 的 `bots.py` 改动对账。T5c 也要动 `worker()`（新增 `action == "model"`）和 `_launch`（1618-1619 的优先级），两个包都在 `bots.py` 里插分支，合并时按各自"只许改"清单核对。

### 4. `memory-*` 提示词窟窿已复核仍在

`bot_client.py` 162-168 行确实注册了 `memory-list` / `memory-search` / `memory-remember` / `memory-forget`，`bots.worker()` 1862 / 1870 / 1879 行确实实现了它们，而 `bot_executor.py` 62-63 行的提示词一个字没提。**本包的"命令清单从 parser 生成"就是为了让这类窟窿不能再出现**，T5c 直接依赖它。

## 数据模型

新实体，**独立于 task**：

```
schedule: {
  id:             "sch_" + uuid4().hex[:16]
  botId:          str
  prompt:         str            # 到点时用来新建 task 的指令，长度上限照 create_task 的 32000
  rule:           dict           # 见下面"规则表达"
  timezone:       str            # IANA 名，例如 "Asia/Singapore"，必填
  enabled:        bool           # 单条 schedule 的开关
  overlapPolicy:  "skip" | "queue"
  nextRunAt:      ISO8601 UTC | None
  lastRunAt:      ISO8601 UTC | None
  lastTaskId:     str | None
  recentTaskIds:  [str]          # 最近产生的 task，上限 10 条，超出丢最旧
  createdBy:      "user" | "bot"
  createdAt:      ISO8601 UTC
  updatedAt:      ISO8601 UTC
}
```

到点时调度器**新建一个 task**（走现有 `create_task` 的语义：`status="queued"`、`_message(task_id, "instruction", prompt)`、`coordinatorPlan` 照常算），**而不是唤醒一个旧 task**。这样：

- 每次运行有独立 transcript、独立成果、独立 outcome；
- schedule 本身可以暂停、修改、删除，不影响历史运行记录；
- 删掉 schedule 不会删掉已经跑出来的 task。

`recentTaskIds` 上限固定 **10**（新建时 append，超过就 `del rows[:-10]`，照 `_message` 里 `MAX_MESSAGES` 的写法）。

## 规则表达

**不用 cron 表达式。** 用户说的是"每 3 小时"、"每天 9 点"，不是 `0 */3 * * *`。四种，别的都拒：

```
{kind: "once",     at: "2026-09-17T09:00:00+08:00"}    # ISO8601，必须带时区
{kind: "interval", everySeconds: 10800}                 # 整数秒
{kind: "daily",    atLocalTime: "09:00"}                # HH:MM，24 小时制
{kind: "weekly",   weekday: 0, atLocalTime: "09:00"}    # weekday 0=周一 … 6=周日，写进文档别让人猜
```

`timezone` **必须显式存**（默认取用户本机时区，前端用 `Intl.DateTimeFormat().resolvedOptions().timeZone` 传上来；REST 缺省时后端用服务器本机时区并把解析结果回写进 schedule，不允许存空）。否则"每天 9 点"跨夏令时会漂。用标准库 `zoneinfo.ZoneInfo`，**不加依赖**；`zoneinfo.ZoneInfoNotFoundError` 要转成 `WebError("INVALID_TIMEZONE", ...)` 而不是 500。

以后要复杂表达式再加 `kind: "cron"`，**这次不做**，但校验函数里要留一条明确的"未知 kind → 报错"分支，不要静默当 once。

## 新模块：`mms_web/bot_schedules.py`

**下一次触发的计算必须是纯函数**，和调度线程解耦，可以单独单元测试。至少这些：

```python
def normalize_rule(rule: dict) -> dict          # 校验 + 规范化，非法抛 WebError
def normalize_timezone(value: str | None) -> str
def validate_schedule(payload, existing_count)  # 最小间隔、条数上限、prompt 长度
def next_run_at(rule, timezone, *, after: datetime, previous: datetime | None = None) -> datetime | None
def advance(schedule, *, now: datetime) -> tuple[dict, int]   # 返回 (新 schedule, 跳过的次数)
```

要求：

1. **`next_run_at` 从规则推，不能从 now 推。** `interval` 的下一次是 `previous + everySeconds`（`previous` 就是本该触发的那个时刻，不是"实际跑起来的时刻"），`daily` / `weekly` 是在目标时区里把本地时刻投到下一个未来日期。否则每次触发的微小延迟会累积漂移。
2. `once` 触发过一次后 `nextRunAt = None`；**schedule 不自动删除**，保留成一条 `enabled` 仍为 true 但已无下次的记录，由用户或 API 删除（这样 UI 能显示"已执行完"，不会凭空消失）。
3. 夏令时：`daily 09:00` 在 DST 切换日仍然是本地 09:00。跳过的本地时刻（春季前跳）取切换后的第一个有效时刻；重复的本地时刻（秋季回拨）取第一次出现。写进注释。
4. `advance` 是把"错过"和"推进"合成一步的唯一入口，返回跳过次数供调用方写 system 消息。

**`bots.py` 里只做最小接线。** `bots.py` 的那个线程同时管邮箱投递、重试退避、孤儿检查、waiting 超时和计划推进，改它有真实回归风险。要求：

- `tick` 里新增的 schedule 段落**不超过 25 行**；
- CRUD / 校验 / 时间计算全在 `bot_schedules.py`；
- `bots.py` 的预期改动量级：`tick` 新增 ≤ 25 行、`_load` 迁移调用 1 行、`_persist` 的 dict 加 1 个 key、`worker()` 新增一个 `schedule` action 分支 ≤ 20 行、`_load` 删掉旧唤醒分支 -6 行、新增 5 个薄方法（`create_schedule` / `list_schedules` / `update_schedule` / `delete_schedule` / `set_schedule_enabled`）各 ≤ 15 行。**交付时按这个清单逐项报实际行数。**

## 持久化

`_persist()`（249-263 行）写的 `state.json` 有固定 key 列表并在 261-263 行硬写 `"schema": 2`；`_load()` 在 **222** 行看到 `schema != 2` 直接 `raise ValueError("Unsupported bot record")`，被 246 行的 `except` 吞成 `_load_error = "Bot 记录无法读取，原文件已保留；请检查记录后再写入。"`，此后 `_persist` 每次都抛 `WebError("BOT_STORE_INVALID", ..., 409)` → 整份 Bot 记录不可写。

要求：**保持 `schema` 为 2**，`_persist` 里加 `"schedules": self._schedules`，`_load` 里用 `self._schedules = data.get("schedules", {})` 向后兼容读。**不要升 schema 3**——那会让已有安装的 Bot 记录直接变成"无法读取"，用户的 Bot 全部消失。

## 三条必须实现的策略

### 1. 重叠

到点了，但这个 Bot 上一轮还在跑。

- 默认 `overlapPolicy = "skip"`：**跳过这一轮**，并留下一条可见的"上一轮仍在运行，已跳过"记录，同时照规则把 `nextRunAt` 推到下一次。
- **不能默认排队。** 查机票这类任务堆积毫无意义，只会把 Bot 卡死。
- `"queue"` 作为显式可选项，给必须每轮都执行的场景：照常新建 task，让现有队列逻辑（`busy` 1506 / `busy_bots` **1507** / `busy_workspaces` **1508**、排序 1509-1514、派发循环 **1515-1546**、起线程 1547-1550）自然排队。
- "上一轮还在跑"的判定复用 `tick` 里已有的 busy 集合语义：该 Bot 有 task 处于 `starting` / `running`，或 `waiting` 且 `waitReason` 不在 `{children, manual, user, plan-approval}`，或 `orphanAlive`。不要自己另发明一套。

### 2. 错过的触发（Pilot 没开、进程重启）

- 不能把停机三天的 72 次触发全补上。
- 规则：**错过超过一个周期就不补**，直接把 `nextRunAt` 推到下一个未来时刻（`advance` 的返回值就是跳过次数），并留下一条说明"跳过了 N 次"的记录。
- 恰好错过一次（`nextRunAt` 已过但还在一个周期内）：**补这一次**，立即触发。
- `once` 错过就直接触发一次（用户约的是一个确定动作），触发后 `nextRunAt=None`。
- 这条策略在 `_load` 之后、第一次 `tick` 时生效即可，不需要在 `_load` 里就跑触发。

### 3. 限额

- 最小间隔 **300 秒**，不允许更短：`interval.everySeconds < 300` 报错。`daily` / `weekly` 天然大于这个值。
- 单个 Bot 的 schedule 条数上限 **20**。
- 超限用现有 `WebError` 风格报错，码名给出建议：`SCHEDULE_INTERVAL_TOO_SHORT`（400，"定时间隔最短 5 分钟。"）、`SCHEDULE_LIMIT`（409，"一个 Bot 最多 20 条定时。"）、`SCHEDULE_NOT_FOUND`（404）、`INVALID_SCHEDULE_RULE`（400）、`INVALID_TIMEZONE`（400）。
- 这条是防止一条"每 10 秒"把模型额度烧干，**不是可选的**。

## 旧机制迁移，不留两套

owner 要求去掉取巧做法。做法：

1. 在 `_load()` 里（紧接 `_migrate_wait_contracts()`，照它的形状写一个 `_migrate_scheduled_tasks()`）把任何仍处于 `status == "scheduled"` 且带 `runAt` 的 task **迁移成一条 `kind:"once"` 的 schedule**（`prompt` 取 task 的 `prompt`，`timezone` 取本机，`createdBy="user"`），然后把那个 task 本身从 `scheduled` 里放出来——**不要让它继续卡在 `scheduled`**。推荐把它改成 `waiting` + `waitReason="manual"` + `runAt=None`（现有 UI 已经能显示"等待你手动唤醒"，见 `bot-visual-system.ts` 的 `waitReasonLabel`），并写一条 system 消息说明它已被迁移成定时。
2. **删掉 `bots.py` `tick` 里那个 `status=="scheduled"` 唤醒分支**（**1485-1489** 行）。
3. 迁移要有测试覆盖：喂一份带旧 `scheduled` task 的 `state.json`，断言迁出了一条 schedule、且那个 task 不再处于 `scheduled`。
4. **不允许保留两条并行的定时路径。**

### `create_task` 的 `runAt` 入参怎么办（必须处理，别漏）

删掉唤醒分支之后，`create_task` 仍然接受 `runAt`（519 行解析、525 行定状态）并把 task 建成 `scheduled`——那会造出一批**永远不会被唤醒**的 task（只能手动"立即唤醒"）。所以必须同时改 `create_task`：

- 收到 `runAt` 时（`create_task` 519 行解析、525 行定状态），**不再建 `scheduled` task**，而是建一条 `kind:"once"` 的 schedule 并返回它；
- 现有调用点要一起看：`server.py` 的 `POST /bots/:id/tasks` 与 `POST /tasks/:id/dispatch`、`Bot.tsx` 两处 `runAt` 提交（735/762/816 的 `BotDispatchForm`、1858 的 composer）。**T5a 只负责后端语义与响应形状保持可用**（返回体里要能让前端区分"建了 task"还是"建了 schedule"，例如带一个 `kind: "task" | "schedule"` 字段），UI 改造在 T5b。
- 子任务分发（`parentTaskId` 存在）**不允许带 `runAt`**：定时子任务没有语义，直接报错。

这一段和"`bots.py` 改动面压到最小"有张力，是已知的必要代价——`create_task` 里的改动控制在 ≤ 15 行，逻辑仍放在 `bot_schedules.py`。

## `wakeEnabled` 的语义

它现在门控旧的唤醒分支（`tick` **1485** 行 `self._bot(task["botId"])["wakeEnabled"]`）。**迁移后它门控 schedule 的触发**，是 Bot 级总开关：

- `wakeEnabled == False` 时，这个 Bot 的所有 schedule 都不触发；
- 但 `nextRunAt` 仍然照规则往前推（关开关不是"攒起来以后补"），并且不写"已跳过"消息（用户自己关的，不需要被刷提示）；
- `enabled`（schedule 级）和 `wakeEnabled`（Bot 级）是两层，任一为 false 就不触发；
- **默认值行为不变**：`create_bot` 仍然默认 `wakeEnabled=True`（`bots.py` 364 行），类型校验不动。

## 两条入口

### REST

`server.py` 加路由，风格照现有 Bot 路由（`parts == [...]` 匹配 + 直接调 `self.bots.xxx`）：

```
GET  /api/v1/bots/:id/schedules                     -> {"schedules": [...]}
POST /api/v1/bots/:id/schedules                     -> 新建一条
POST /api/v1/bots/:id/schedules/:sid                -> 修改（prompt / rule / timezone / overlapPolicy）
POST /api/v1/bots/:id/schedules/:sid/enable         -> 启
POST /api/v1/bots/:id/schedules/:sid/disable        -> 停
POST /api/v1/bots/:id/schedules/:sid/delete         -> 删
```

沿用现有约定：写操作全是 POST（这个仓库没有 PUT/DELETE 路由），`delete` 走 `.../delete` 后缀（照 `POST /bots/:id/delete`）。`requestId` 幂等复用 `_replay` 的现有写法。

### Bot 自己的 CLI 子命令（这条才是 owner 真正要的）

在 `bot_client.py` 加：

```
schedule create <prompt...> --every <3h|180m|10800s> | --daily <HH:MM> | --weekly <mon..sun> <HH:MM> | --once <ISO8601>
                            [--overlap skip|queue] [--timezone <IANA>]
schedule list
schedule pause <schedule_id>
schedule resume <schedule_id>
schedule delete <schedule_id>
```

这样用户直接跟 Bot 说"每天早上九点扫一遍这个文档"，Bot 能自己建。

- 子命令注册照现有 `with_request_id(commands.add_parser(...))` 的写法（`bot_client.py` **160-205** 行，`with_request_id` 本身在 **149-158**）。`schedule` 用一个二级 `add_subparsers`。
- `_command_payload` 里把它翻译成 `("schedule", {...})`，`botId` / `taskId` 从 context 取，`createdBy="bot"`。
- **注意：`bot_client.py` 只是构造 payload 发到 `/api/v1/bot-worker`，实际实现在 `bots.py` 的 `worker()` 分发**（1856-1919 行；`authorize_worker` 在 1849-1854 行，要求 task 处于 `{starting, running, waiting}`）。所以必须同时在 `worker()` 加一个 `action == "schedule"` 分支，按 `payload["op"]` 走 create/list/pause/resume/delete，并把 schedule 限定在 `task["botId"]` 自己名下（照 `action == "status"` 那段的 scope 检查写法，越界报 `WebError("BOT_SCOPE", ...)`）。
- `--every` 的人类写法（`3h` / `180m` / `10800s` / 纯数字按秒）解析放 `bot_schedules.py`，带单测。

## 系统提示词必须同步改（`bot_executor.py` **62-63** 行那段）

提示词字符串在 `start()`（def 在 46 行）内的 49-88 行。现在列给 Bot 的命令原文逐字是（**62-63** 行，旧包写的 51 行已过期）：

```
"子命令：list；dispatch BOT_ID '任务'；message BOT_ID '消息'；reply MESSAGE_ID '回复'；inbox；"
"screenshot --url 'http(s)://...'；browser goto/snapshot/click/fill/press；status；complete '结果'；wait '要问用户的问题'；fail '错误'。\n"
```

**一个字没提定时**，所以 Bot 会直接回答用户"我没有后台定时调度能力"——这是本次要修的核心症状之一。要求：

1. 把 `schedule` 子命令写进"子命令：…"那一行，并在紧随的行为约束里明确指示：**用户要求周期性 / 反复 / 每隔多久做一次的工作时，用 `schedule create` 建一条定时，不要回答做不到，也不要靠自己在任务末尾重新约下一次。**
2. 顺手把 `bot_client.py` 里**已经存在但提示词从没提过**的 `memory-list / memory-search / memory-remember / memory-forget` 也补进去（同一类问题：能力存在但 Bot 不知道）。**这条在 2026-09-16 于 `77f2fd8a` 复核仍然成立**：`bot_client.py` 162-168 行确实注册了这四条，`bots.worker()` 1862/1870/1879 行确实实现了它们，而 62-63 行的提示词一个字没提。
3. 提示词是字符串拼接，注意不要破坏前后的换行和转义；改完跑一遍 `tests/test_mms_bot_transport.py`（那里有对提示词内容的断言）。

### 命令清单改成从 parser 生成（本包一并做掉，不是可选项）

上面第 1、2 条只是补窟窿。窟窿的成因是：`bot_executor.py` 那段提示词把 Bot 可用的内部命令**手写成了一段散文**，而真正的命令注册在 `bot_client.py` 的 argparse parser 里，**两边没有任何约束关系**。同一个问题已经出现三次——`memory-*` 存在但提示词没提、定时能力（本包）存在但提示词没提、切模型能力（T5c）存在但提示词没提。Bot 因此会直接回答用户"我没有这个能力"。

所以本包再加一条要求：**命令清单从 parser 的注册信息生成，不再手写。**

- 在 `bot_client.py` 里暴露一份可供 `bot_executor.py` 读取的命令清单（子命令名 + 一句用途 + 参数形状），**来源就是 `add_parser` 注册的那批**，不要再维护第二份列表。可行做法：给 `_build_parser()` 拆一个 `command_catalog()`，遍历 `parser._subparsers` / 自己在注册时顺手记一份结构化元数据（后者更稳，argparse 的私有属性会随版本变），关键是**注册和清单只有一处真值**。
- **注意导入方向。** `bot_client.py` 是 Bot 通过 bash 以 `python -m mms_web.bot_client` 独立进程调用的脚本；`bot_executor.py` 跑在 Pilot 服务端进程里。服务端直接 `import` 那个脚本模块，要确认不会引入循环依赖（`bot_client` 目前只依赖标准库，方向上是安全的），也不会把脚本的副作用带进服务端进程（`bot_client.py` 现在的模块级只有常量和函数定义，`main()` 在 `__main__` 守卫里，所以 import 是干净的——**动手前自己再确认一遍**）。如果实现中发现直接 import 有风险，就改成把命令元数据抽到一个**纯数据模块**（例如 `mms_web/bot_commands.py`，只有常量和纯函数），由 `bot_client.py` 和 `bot_executor.py` 共享。这两种做法都可以，选哪个在交付里说明。
- **提示词里的行为性指示保持手写**，不要一起生成。例如"需要协作时先 list 再 dispatch"、"不要循环轮询"、"wait 的内容必须是一个明确、需要用户回答的问题"、"complete 不是用户验收"、"不要读取内部 context 凭据文件"——这些是策略，不是命令目录。**生成的只是"有哪些命令、各自干什么、参数长什么样"这份清单。**
- **加一条门禁测试**（放 `tests/test_mms_bot_transport.py` 或 `tests/test_mms_bot_client.py`）：断言 parser 注册的**每一个**子命令名都出现在生成的提示词清单里。这条测试就是防止以后再飘的门禁——以后任何人加子命令忘了同步，测试直接红。断言要遍历 parser 的真实注册结果，不能自己再写死一份名单去比对，否则等于把同一个问题搬了个家。

## 结果必须送到用户眼前

周期任务跑完不能只静静躺在任务列表里，否则用户还是得手动去看，体感依旧是"没用"。

- schedule 触发产生的 task，完成 / 失败时要走 `bot_notify.py`。现有 `_finish` 末尾已有 `self._notify(task, "task.completed" | "task.failed")`（`bots.py` 约 943-944 行），所以**只要让 schedule 新建的 task 走正常 `_finish` 路径就自动有通知**——要在测试里断言这条确实发生了，不要假设。
- 事件里要能看出"这是定时触发的"：给 task 加一个 `scheduleId` 字段，`emit_task` 的 payload 里带上（`bot_notify.py` 105-116 行加一个 key），前端和 webhook 接收方都能区分。
- **建议不新增 `EVENT_TYPES`**（`bot_notify.py` 24 行是固定元组，加类型要同步改校验和前端）：复用 `task.completed` / `task.failed`，"跳过"用 system 消息而不是通知。如果实现时发现必须新增，写进"需要 Fable 确认"。
- **这条不做，整个功能等于没做。** 这是硬验收项：验收时必须给出"定时触发 → 任务完成 → 通知里出现该事件"的实际证据。

## 只许改 / 不许改

**只许改**：

- 新增 `mms_web/bot_schedules.py`
- 新增 `mms_web/bot_commands.py`（只在你选"共享纯数据模块"那条路时才建）
- 新增 `tests/test_mms_bot_schedules.py`
- `mms_web/bots.py`：按上面"最小接线"清单的几处，逐项报行数
- `mms_web/bot_client.py`：新增 `schedule` 子命令与 payload 翻译；暴露命令清单
- `mms_web/bot_executor.py`：**只改** 51 行起那段提示词字符串（命令目录改成生成，行为性指示仍手写）
- `mms_web/bot_notify.py`：**只加** `emit_task` payload 里的 `scheduleId`
- `mms_web/server.py`：只加上面列出的 schedule 路由
- `tests/test_mms_web_bots.py`、`tests/test_mms_bot_client.py`、`tests/test_mms_bot_transport.py`、`tests/test_mms_bot_notify.py`：补断言
- `docs/mms-web/BOTS.md`：追加一节说明 schedule 契约和"Pilot 不开就不触发"的边界

**不许改**：

- 任何 `apps/mms-web/**`（前端是 T5b）
- `mms_web/bot_coordinator.py`、`mms_web/bot_memory.py`、`mms_web/bot_communications.py`、`mms_web/bot_retry.py`
- 受保护文件：`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`
- 真实 `~/.config/mms*`（测试和验证用临时 state-root）
- 不加依赖，时区用标准库 `zoneinfo`
- **不要重启 60824**（owner 的验证实例）；自己另起端口

## 测试要求

`bot_schedules.py` 纯函数单测（`tests/test_mms_bot_schedules.py`），必须覆盖：

1. 四种 rule kind 各自的 `next_run_at`：`once` / `interval` / `daily` / `weekly`（含 weekday 边界：周日到周一）。
2. **夏令时切换**：在一个有 DST 的时区（例如 `America/New_York` 或 `Europe/London`）上，`daily 09:00` 跨切换日仍是本地 09:00；春季被跳过的本地时刻和秋季重复的本地时刻各一条。
3. **`interval` 不漂移**：给一个"实际触发时刻比 `nextRunAt` 晚 7 秒"的场景，断言下一次仍然是 `previous + everySeconds`，不是 `now + everySeconds`。
4. **错过多个周期**：`nextRunAt` 在 3 天前、`interval=3h`，断言只推到下一个未来时刻、跳过次数正确、不产生 24 个 task。
5. 恰好错过一次：立即补触发。
6. 最小间隔（299 / 300 / 301）与条数上限（19 / 20 / 21）校验，断言错误码。
7. `--every` 人类写法解析（`3h` / `180m` / `10800s` / `10800` / 非法输入）。
8. 未知 `kind` 报错，不静默当 once。

调度循环（`tests/test_mms_web_bots.py` 或新文件）：

9. **用注入时钟**（照现有测试里对 `bots.py` 的时间处理方式；必要时把 `now` 作为 `advance` 的显式参数传入，不要给 `bots.py` 加全局时钟 patch），测重叠 `skip` 与 `queue` 两种策略：Bot 有 running task 时到点，`skip` 不建 task 且 `nextRunAt` 已推进，`queue` 建了 task 且它在 `queued` 里排队。
10. 触发 → 新建 task → 正常 `_finish` → `list_notifications` 里出现该事件且带 `scheduleId`。
11. `wakeEnabled=False` 时不触发，但 `nextRunAt` 仍推进。

API（`tests/test_mms_web_bots.py`）：

12. 增删改查启停全覆盖，每个错误码至少一条断言。
13. `requestId` 重放幂等。
14. 越界：A Bot 的 worker 不能操作 B Bot 的 schedule。

迁移：

15. 见上面"旧机制迁移"第 3 条。
16. 额外一条：`state.json` 里没有 `schedules` key（旧文件）能正常加载，不触发 `_load_error`。

CLI（`tests/test_mms_bot_client.py`）：

17. 每个 `schedule` 子命令的 argv → payload 翻译，照现有 client 测试的写法。

提示词（`tests/test_mms_bot_transport.py`）：

18. 断言提示词里出现 `schedule` 和 `memory-remember`。
19. **门禁测试**：遍历 `bot_client` parser 的真实注册结果，断言**每一个**子命令名都出现在生成的提示词清单里。不能自己再写死一份名单去比对。
20. 断言提示词里仍然保留手写的行为性指示（至少抽查"不要循环轮询"和"complete 不是用户验收"两句），确认改成生成清单时没把策略段落一起吃掉。

**基线（2026-09-16 在 `origin/dev-pre` = `77f2fd8a` = 5.0.1 实测）**：

```
PYTHONPATH=. python3 -m pytest -q \
  tests/test_mms_web_bots.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py \
  tests/test_mms_bot_client.py tests/test_mms_bot_computer.py tests/test_bot_memory.py \
  tests/test_mms_bot_coordinator.py tests/test_mms_bot_notify.py tests/test_mms_bot_retry.py
# -> 202 passed in ~17s
```

**这个数字只增不减。** 注意：旧包写的 203 是错的——这九个测试文件在 `66b7fc16` 和 `77f2fd8a` 上逐字节相同，在两个 commit 上重测都是 **202 passed**。以 202 为准。

## 门禁

```bash
# 1. 定向 pytest（上面那一组 + 你新增的 tests/test_mms_bot_schedules.py）
PYTHONPATH=. python3 -m pytest -q \
  tests/test_mms_web_bots.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py \
  tests/test_mms_bot_client.py tests/test_mms_bot_computer.py tests/test_bot_memory.py \
  tests/test_mms_bot_coordinator.py tests/test_mms_bot_notify.py tests/test_mms_bot_retry.py \
  tests/test_mms_bot_schedules.py

# 2. 语法
python3 -m py_compile mms_web/bot_schedules.py mms_web/bots.py mms_web/bot_client.py \
  mms_web/bot_executor.py mms_web/bot_notify.py mms_web/server.py

# 3. 回归对比（只对新破的测试负责）
python3 scripts/ci_pytest_regression.py --base origin/dev-pre   # 重组完成后改成 --base origin/dev

# 4. 新用户 gate
python3 scripts/regression_fresh_user_gate.py
```

第 3、4 条的实际结果要写进交付。gate 在这台机器上本来就有既存失败项，**用 diff 判断，不看绝对值**。

## 真实验证（不是可选项）

自己的 worktree + 自己的端口，**不要碰 60824**：

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch
git fetch origin
git worktree add .worktrees/wt-T5a -b bot/T5a-schedule-backend origin/dev-pre   # 重组完成后用 origin/dev
cd .worktrees/wt-T5a
npm install
npm run build --workspace @mms/web        # 后端包不改前端，但要能起页面看效果
PYTHONPATH=$PWD python3 -P -m mms_web --port 61751 \
  --state-root /tmp/bot-verify-t5a \
  --config-root ~/.config/mms-next \
  --static-root $PWD/apps/mms-web/dist
```

要实际跑通并留证据（curl 输出 / 日志 / 截图放 `docs/mms-web/design/t5a/`）：

1. `POST /api/v1/bots/:id/schedules` 建一条 `{kind:"interval", everySeconds:300}`，等两次触发，`GET /api/v1/bots/:id/tasks`（或 `GET /api/v1/bots/status`）看到**两个独立 task**，`nextRunAt` 两次差正好 300 秒。
2. `GET /api/v1/bots/notifications` 里出现这两个 task 的完成事件，带 `scheduleId`。
3. `pause` 之后不再触发，`resume` 之后恢复。
4. `delete` 之后不再触发，**已产生的 task 仍在**。
5. `everySeconds: 60` 被拒，错误码和中文提示符合。
6. 第 21 条 schedule 被拒。
7. 停掉进程 30 分钟（或把 `state.json` 里 `nextRunAt` 手改到 3 天前再启动），断言只触发一次、system 消息写明跳过次数，**不是 72 个 task**。
8. 用 Bot 的 CLI 实跑一次：在一个真实任务里让 Bot 执行 `schedule create '每天检查一次' --daily 09:00`，`GET` 读回。
8b. 直接问 Bot"你能不能每天定时帮我做一件事"，它应当回答能并给出做法，**而不是回答"我没有后台定时调度能力"**。这是本次要修的核心症状，截图留证。
9. 旧机制迁移：手工造一份带 `status:"scheduled"` + `runAt` 的 `state.json`，启动后 `GET` 到一条 `once` schedule，那个 task 不再是 `scheduled`。

## 交付格式

照 README 的通用验收，写进 worktree 的 `walls.md`（追加，不改旧条目）：

```
包：T5a
分支 / worktree：
改动文件：git diff --stat 输出
bots.py 实际改动行数：tick +N / _load +N / _persist +N / worker +N / create_task +N / 删除唤醒分支 -N / 新增方法 +N
测试：命令 + 通过数（对比基线 **202**）
门禁：ci_pytest_regression 结果、fresh-user gate 结果（与既存失败集的 diff）
真实验证：端口、上面 9 条逐条结果、证据路径
未完成 / 未验证：逐条
需要 Fable 确认：逐条
```

**不提交、不 push、不 merge。** T5a 验收通过后，T5b 从 T5a 的 HEAD 开分支；**两个包一起才合进任务分支，后端不单独落地。**

## 需要 Fable 确认

下面是写包时对照现有代码发现的、设计里没覆盖或与现状有张力的点。**不要自己改设计**；按包里给出的默认做法实现，同时把你的实际处置写回交付里。

1. **"跳过这一轮"的 system 消息没有地方写。** `_message` 的第一个参数是 `task_id`，`self._messages` 是以 taskId 为 key 的字典（`bots.py` 488-495 行，上限 `MAX_MESSAGES = 500` 在 37 行）。`skip` 的定义就是不建 task，所以没有 task 可挂。本包的默认做法：挂到该 schedule 的 `lastTaskId`（即上一轮那个还在跑的 task）上，并在 schedule 实体上加一个 `lastSkip: {at, reason, skipped}` 字段供 UI 显示。另一个选项是给 schedule 开一条独立的消息流（`self._messages["sch_xxx"]`），但那会污染以 taskId 为 key 的语义。请确认取哪个。同一个问题也影响"错过 N 次"的消息。
2. **`create_task` 的 `runAt` 入参必须一起改，设计里没写。** 删掉 `tick` 的 `scheduled` 唤醒分支之后，`create_task`（497-544 行，`runAt` 解析 519、状态 525）仍会把带 `runAt` 的请求建成 `scheduled` task，那批 task 将永远不会自动开始。本包默认做法见上面"`create_task` 的 `runAt` 入参怎么办"：改成建 `once` schedule 并在响应里带 `kind` 区分。这会让 `POST /bots/:id/tasks` 的响应形状变化，`Bot.tsx` 两处提交点在 T5b 才跟进，中间态（T5a 单独跑起来时）前端的定时按钮会拿到一个 schedule 而不是 task。因为两个包必须一起落地，这个中间态不会到用户手上，但要确认可以接受。
3. **`state.json` 的 `schema` 是硬校验。** `_load` 在 222 行看到 `schema != 2` 就 `raise ValueError`，246-247 行把整份 Bot 记录判成"无法读取"，250-251 行起所有写入都被 `BOT_STORE_INVALID` 拒绝。**这条同时是 T6a（4.x ↔ 5.x 双向切换门禁）的核心风险点**，见 `T6a-channel-switch-gate.md`。本包默认**不升 schema**，用 `data.get("schedules", {})` 兼容读。如果 Fable 希望显式升版，需要同时写一个 2→3 的迁移并保证旧文件可读——本包没有采用。
4. **命令清单生成的落点有两个可选形状。** 本包要求"注册与清单只有一处真值"，但没有强行指定是 `bot_client.py` 直接暴露 `command_catalog()` 被服务端 import，还是抽一个纯数据模块 `mms_web/bot_commands.py` 被双方共享。实现者按导入安全性自行选择并在交付里说明。若最终选了新模块，`mms_web/bot_commands.py` 是本包新增的第 2 个文件。
5. **`bot_client.py` 的子命令必须配一个 `worker()` action 分支。** 设计只说"在 `bot_client.py` 加 `schedule create|list|pause|resume|delete`"，但 client 只负责构造 payload，实现落在 `bots.py` 的 `worker()`（1856-1919 行）。这不可避免地增加 `bots.py` 的改动面（估 ≤ 20 行），与"`bots.py` 改动面压到最小"有张力。本包已把它写进改动清单。
6. **Bot 只能在自己的一轮执行期间建 schedule。** `authorize_worker`（1849-1854 行）要求 task 处于 `{starting, running, waiting}` 且 token 用 `secrets.compare_digest` 比对，否则 `BOT_WORKER_UNAUTHORIZED` 403。所以 Bot 无法在"空闲时"自己改定时。这与设计一致，只是把边界写明。
7. **`recentTaskIds` 的上限设计里没给数字**，本包定为 10。
8. **`EVENT_TYPES` 是固定元组**（`bot_notify.py` **25** 行，四项：`task.completed` / `task.failed` / `task.waiting` / `task.retrying`）。本包默认不新增事件类型，复用 `task.completed` / `task.failed`，只在 payload 里加 `scheduleId`。若实现中发现"跳过"也必须进通知，需要新增类型并同步改前端（跨到 T5b），请确认。
9. **`wakeEnabled` 的前端默认值与后端不一致（既存问题，不在本包修）。** 后端 `create_bot` 默认 `True`（364 行），但 `BotStudio.tsx:138` 的编辑表单是 `useState(bot?.wakeEnabled || false)`，新建路径又在 845/859 行显式传 `true`。本包只保证后端默认不变；前端文案与默认值在 T5b 处理。
10. **`docs/mms-web/DESIGN.md` 不存在**（2026-09-16 在 `77f2fd8a` 复核），实际文件是 `apps/mms-web/DESIGN.md`；T1e / T1f / T2c / T3c 几个旧包里写的那个路径已过期，T5b 用后者。
11. **`BOT_MODEL_REQUIRED` 不在 `bots.py` 里。** 它只在 `bot_executor.py:31` 抛出，并在 `bot_retry.py:28` 被列为永久（不可重试）错误码。T5c 引用它时按这两处写。
