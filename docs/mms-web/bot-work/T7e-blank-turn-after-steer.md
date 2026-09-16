# T7e · 被中断的回合：界面看不见发生了什么

Date: 2026-09-16
Task: Stride 370e87ec37e741df
建议模型：gemini3.6（纯前端；由 owner 决定实际派发）
来源：owner 2026-09-16 两张截图

> "这个任务在一次 btw 和我引导之后 不显示过程了"
> "这个任务都完成了 我都不知道他回复什么 结果是什么"

先读：`docs/mms-web/bot-work/README.md`（并行规则、通用验收）、本文件，然后按下面"要读的代码"逐处在你自己的 base 上复核行号。

**优先级：高于 T7a / T7b / T7c / T7d。** 那四条是"烦人"：红条闪、卡片自己展开、错误文案猜错、当前窗口被踢。这一条是**一轮工作被打断了，或者还在跑，而界面上什么都看不见**——用户会判定它卡死、或者以为它成功了然后去找根本不存在的结果。这是唯一一条会让用户对会话状态做出**错误判断并因此做出错误处置**的缺陷。

**本包与 T7a / T7b / T7c / T7d 的改动面零重叠**：那四个包没有一个碰 `Transcript.tsx`、`SessionStatus.tsx` 或 `transcript.css`。唯一共享文件是 `App.tsx`，本包只允许在其中**三处**做最小接线（见"只许改"）。

---

## 这个包要修的是两张截图，同一条链路

| | 截图一（引导之后） | 截图二（重启之后） |
| --- | --- | --- |
| 用户看到 | transcript 最后一段**整片空白**：没有过程、没有回答、连"正在工作"的占位都没有 | 一条用户消息标着**「已取消，未执行」**（12:07）、上面一张已回答的 BTW 卡（12:06）、**没有任何 assistant 回复** |
| 状态栏同时在说 | **执行工具 · bash　正在执行终端工具…** | **本轮已完成** |
| 用户会怎么做 | 以为卡死 → 去点停止 / 重开会话 / 杀进程 | 以为成功 → 去找产出，找不到 |
| 实际发生了什么 | 任务还在跑 | 那一轮被服务重启打断了，排队的消息被作废，从来没有产出过回答 |

**两张截图的放大器是同一个**：`Transcript.tsx` 把"这一回合完成没有"从**位置**推出来，把"会话忙不忙"只从 `session.state` 读，然后在三个渲染槽位全部落空时**返回 `null`**。

**触发器不同**：截图一是回合切分被一条中途消息切开；截图二是服务重启把队列作废、把状态改写。

**修渲染是必须的**——它决定了用户能不能看见发生了什么；**但只修渲染不够**——被作废的消息要能救回来，被打断的回合不能对用户说"已完成"。

---

## base 分支判定（2026-09-16 实测）

### 结论

| 项目 | 分支 | 依据 |
| --- | --- | --- |
| **实现 PR 的 base** | **`dev`（5.0.1，`f04d740e`）** | 本包的渲染修复所依赖的代码**只存在于 5.x**；工单点名要补单测的 `apps/mms-web/tests/turn-working-status.test.mjs` 在 `origin/main` 上**不存在** |
| 本工作包文档所在分支 | `dev` | `docs/mms-web/bot-work/` 整棵树只存在于 `dev`，`origin/main` 上没有这个目录 |

**这个结论与 owner 给的默认规则（"能在 4.22.x 上修的就 base 在 `main`"）有一处偏离，理由写在"为什么不是 `main`"，实现者不要自行改回 `main`。**

### 实测证据一：owner 指定的四文件 diff

```
git diff origin/main origin/dev -- apps/mms-web/src/Transcript.tsx \
  apps/mms-web/src/SessionStatus.tsx apps/mms-web/src/transcript.css apps/mms-web/src/App.tsx
```

实测结果（`origin/main` = `6c62a656` = 4.22.1，`origin/dev` = `f04d740e` = 5.0.1）：

```
 apps/mms-web/src/App.tsx           | 64 +++++++++++++++++++++++++++++----
 apps/mms-web/src/SessionStatus.tsx | 52 ++++++++++++++++++---------
 apps/mms-web/src/Transcript.tsx    | 67 +++++++++++++++++++++++++++++++---
 apps/mms-web/src/transcript.css    | 73 ++++++++++++++++++++++++++++++++++++--
 4 files changed, 226 insertions(+), 30 deletions(-)
```

逐文件 blob hash（`git rev-parse origin/<b>:<path>`）：

| 文件 | main | dev | 判定 |
| --- | --- | --- | --- |
| `apps/mms-web/src/Transcript.tsx` | `70e7c11e` | `dcbece7c` | 差 67 行 |
| `apps/mms-web/src/SessionStatus.tsx` | `8e676814` | `cf5611e1` | 差 52 行 |
| `apps/mms-web/src/transcript.css` | `b9a243f0` | `0df78dd6` | 差 73 行 |
| `apps/mms-web/src/App.tsx` | `beed496a` | `e8b89e91` | 差 64 行 |
| `apps/mms-web/src/message-control.ts` | `b80b3df0` | `b80b3df0` | **逐字节相同** |
| `apps/mms-web/src/components.tsx` | `b0330996` | `b0330996` | **逐字节相同** |
| `apps/mms-web/src/ToolEvent.tsx` | `119eef1a` | `119eef1a` | **逐字节相同** |
| `apps/mms-web/tests/turn-working-status.test.mjs` | **不存在** | `9099f77b` | 5.x 独有 |
| `mms_web/sessions.py` | `63500e17` | `07960e46` | 差（行号见对照表） |
| `mms_web/drivers/pi_rpc.py` | `ab7facec` | `ab7facec` | **逐字节相同** |

### 实测证据二：哪一半是两线共有的，哪一半是 5.x 独有的

**两线共有（逐字复制，只是行号平移）——放大器就在这里：**

- 回合切分：`for (const event of …) { if (!turns.length || event.kind === "user") turns.push([]); … }`
- `const active = ["running", "waiting"].includes(props.detail.session.state);`
- `completed={index < turns.length - 1 || !active}`
- `collapsed = … : props.autoCollapseProcess && completed && !!answer;`
- `pending` 那段（`queued` / `cancelled` / `error` / `failed` / `interrupted` 挑出去单独渲染）
- `message-control.ts` 的 `deliveryLabel()` 和 `steerLinks()`（整文件逐字节相同）

**触发器侧（`mms_web/sessions.py`）两线也是同一套逻辑**，只是行号不同：重启恢复时把 `queued` 改写成 `cancelled`、`finish_pending_tools()`、`state` 兜底成 `stopped`、`_resume()` 把 `state` 置回 `idle`——四处在 `main` 和 `dev` 上语义一致。

**5.x 独有（gemini 在 `88114765` / `6d9001d6` 加的）：**

- `findActiveAnswer()`（`Transcript.tsx:23-30`）
- `TurnWorkingStatus`（`Transcript.tsx:32-70`）
- `streamingAnswer` / `isWorking` / `isRunning`（`:81` / `:97` / `:98`）
- 三槽位三元式 `answer ? … : isWorking ? … : null`（`:115-119`）
- `SessionStatus.tsx` 里导出的 `activityHints`（`:92-106`）与 `turnWorkingHint()`（`:108-118`）
- `transcript.css` 的 `.turn-working-*` / `.turn-process-live-dot` / `@keyframes turn-working-fade-in`（`:482-483`、`:505-560`）
- `apps/mms-web/tests/turn-working-status.test.mjs` 整个文件

在 `main` 上：`SessionStatus.tsx` **没有** `turnWorkingHint`，**没有**导出的 `activityHints`（文案内联在 `CurrentActivity` 的局部 `hints`，`main:100-114`）；`transcript.css` **一处** `turn-working` 都没有；`apps/mms-web/tests/` 只有 7 个文件。

### 为什么不是 `main`

owner 的规则是"4.x 的所有改动默认进入 5.x，能在 4.22.x 上修的就 base 在 `main`"。本包**不能整包在 `main` 上修**，理由三条：

1. **工单点名的验收载体在 `main` 上不存在。** 工单要求在 `apps/mms-web/tests/turn-working-status.test.mjs` 补单测。这个文件是 5.x 独有的。
2. **"不许渲染 `null`"在 `main` 上无处可落。** `main` 的答案槽是 `{answer && <EventView …>}`（`main:60`），没有第二个分支，也没有任何占位组件、占位文案、占位样式。在 `main` 上实现它 = 把 gemini 的整套 5.x 占位回流到 4.22.x，方向与 owner 定的流向相反，远超本包范围。
3. **改动落点的上下文两线不同。** `Turn()` 函数体在 5.x 上多了三个参与判定的局部量（`streamingAnswer` / `isWorking` / `isRunning`）。在 `main` 上改 `completed` 的来源再往 5.x 合，函数体必然逐行冲突，而且合完还得再决定新旧逻辑怎么配合——同一个决定做两遍。

### 残留：4.22.x 侧还有什么没被本包覆盖

诚实记下，**不属于本包，也不要顺手做**：

`main` 上同样存在"回合按位置被误判成 completed"和"重启作废消息只给一行小灰字"。在 4.22.x 上的可见后果是：

- 中途消息一落地，**正在跑的那个回合的过程被自动折叠**（`collapsed = autoCollapseProcess && completed && !!answer`，`main:31-32`）。
- 那个回合里一段**中间性质的 assistant 文字被当成最终回答**渲染出来（`main:30`）。
- "最后一段只剩用户气泡、底下什么都没有"同样会发生（`main:60` 的 `{answer && …}` 直接为假），只是 4.22.x 从来没有占位符，所以那不是回归，而是一直如此。
- 被重启作废的消息同样只有 `deliveryLabel()` 那一行小灰字，同样没有重新发送入口。

**是否把这一半回流 4.22.x，由 owner 决定，不在本包。** 本包的 PR 只进 `dev`。

### 下面所有行号都给两套

owner 给的行号是在 `origin/dev` 上读的。**以 `dev` 那一列为准（实现 base）**；`main` 那一列用于将来回流时定位。owner 给的行号**全部命中**，逐条核对见"行号核对"脚注。

---

## 要读的代码（行号对照）

### `apps/mms-web/src/Transcript.tsx`

| 代码 | main（4.22.1 `6c62a656`） | dev（5.0.1 `f04d740e`） |
| --- | --- | --- |
| `ProcessEvents()` | 10-20 | 11-21 |
| `findActiveAnswer()` | **不存在** | **23-30** |
| `TurnWorkingStatus()` | **不存在** | **32-70** |
| `Turn()` 签名 | 22-26 | 72-76 |
| `answer` / `completedAnswer`（只在 completed 时找） | **30** | **80** |
| `streamingAnswer`（只在 !completed 时找） | **不存在** | **81** |
| `const answer = completedAnswer \|\| streamingAnswer` | 不存在 | 82 |
| `collapsed = … autoCollapseProcess && completed && !!answer` | **31-32** | **83-84** |
| `process` / `after` / `pinned` | 34 / 36 / 37 | 86 / 88 / 89 |
| `hasProcess` | 44 | 96 |
| `isWorking = !completed && !answer && (collapsed \|\| !hasProcess)` | **不存在** | **97** |
| `isRunning = !completed` | 不存在 | 98 |
| `report(turnId, collapsed)` 的 effect | **45-47** | **99-101** |
| 过程块 `{!!process.length && <div className="turn-process">…}` | 56-59 | 111-114 |
| **答案槽（死分支所在）** | **60** | **115-119** |
| `steer-note` 及其注释 | **61-66** | **120-126** |
| `after.map(...)` | 67 | 126 |
| 事件过滤（含"空 assistant 事件被丢掉"） | **76-78** | **135-137** |
| **`pending`（queued / cancelled / error / failed / interrupted）** | **79** | **138** |
| **回合切分循环** | **80-84** | **139-143** |
| **`const active = ["running","waiting"].includes(session.state)`** | **85** | **144** |
| `steered` = `steerLinks(events)` | 86-89 | 145-148 |
| **`completed={index < turns.length - 1 \|\| !active}`** | **92** | **151** |
| **`pending-messages` 区块（"已取消，未执行"落在这里）** | **93-95** | **152-154** |

### `apps/mms-web/src/message-control.ts`（**两线逐字节相同，一套行号**）

| 代码 | 行号 |
| --- | --- |
| `deliveryLabel()`——`cancelled` → "已取消，未执行"，`interrupted` → "已被停止打断，未执行" | **137-150** |
| `SteerLink` / `steerLinks()` | 152-203 |
| `steerBadge()` | 205-212 |

### `apps/mms-web/src/SessionStatus.tsx`

| 代码 | main | dev |
| --- | --- | --- |
| `sessionStatus()` | 12-45 | 12-45（**这一段两线行号相同**） |
| `terminal = ["completed","stopped","error"].includes(state)` | 13 | 13 |
| **phase 优先级：`waiting` → `activity?.phase` → `state === "idle" ? "completed" : state`** | **14-23** | **14-23** |
| **`labels.completed = "本轮已完成"`（截图二那句）** | **33** | **33** |
| `labels.closed` / `stopped` / `error` | 34-36 | 34-36 |
| `Status()` | 47-90 | 47-90 |
| `activityHints`（导出） | **不存在**（内联在 `CurrentActivity` 的 `hints`，100-114） | **92-106** |
| `turnWorkingHint()` | **不存在** | **108-118** |
| `CurrentActivity()` | 92-125 | 120-146 |

### `apps/mms-web/src/App.tsx`

| 代码 | main | dev |
| --- | --- | --- |
| `guideRequest` state（"把文字塞进 composer"的现成接缝） | — | **253** |
| `processForced` | 300-303 | 323-326 |
| `processTurns` | 304 | 327 |
| `reportProcessTurn` | 305-307 | 328-330 |
| 详情轮询 effect（1200ms，**无 `updatedAt` 门**） | **571-608** | **594-630** |
| `<Composer … guideRequest={guideRequest} …>` | — | **1765** |
| `<Transcript …>` 挂载 | 1979-1987 | 2029-2035 |
| 全局按钮 `collapseNext = Object.values(processTurns).some(c => !c)` | **2064** | **2114** |
| `{collapseNext ? "收起全部过程" : "展开全部过程"}` | 2083 | 2133 |

### `apps/mms-web/src/Composer.tsx`（**两线同名接缝**）

| 代码 | dev |
| --- | --- |
| `guideRequest?: { nonce: string; text: string }` prop | 78 / 88 |
| 消费 nonce 并 `setText(...)` + `focus()` 的 effect | **310-316** |
| `selectionRequest` 的同形接缝（另一个例子） | 317-320 |

### `apps/mms-web/src/transcript.css`

| 代码 | main | dev |
| --- | --- | --- |
| `prefers-reduced-motion` 里的 `.turn-working-message` / `.turn-process-live-dot` | **不存在** | 482-483 |
| `/* Working status placeholder … */` 起的整段 | **不存在** | **505-560** |

### `mms_web/sessions.py`（**只作证据，本包默认不改**）

| 代码 | main | dev |
| --- | --- | --- |
| `finish_pending_tools()`——残留 running 工具改成 `error`，文本追加"本轮已结束，未收到此工具的完成回报。" | **284-288** | **287-291** |
| `cancel_pending()`——"Queue cleared explicitly or invalidated by resume/restart: **cancelled**" | **308-316** | **311-319** |
| `interrupt_pending()`——"abort/stop removed these from the Pi queue mid-turn: **interrupted**" | **318-326** | **321-329** |
| `activity_view()`——`state in _FINAL_STATES` 时返回 `None` | 328-334 | 331-337 |
| `append_event` 推进 `updated_at` / `last_event_at` | 179-180 | **179-180** |
| `upsert_event` 推进 `updated_at` / `last_event_at` | 199-200 | **199-200** |
| `send()` 里 `previous_state` / `mode` / `status = "queued"` | 728-750 一带 | **767-789** |
| **重启恢复：`queued` → `cancelled`，然后 `finish_pending_tools()`** | **1519-1523** | **1566-1570** |
| **重启恢复：`state` 非终态时兜底成 `"stopped"`** | **1552-1554** | **1599-1601** |
| 重启恢复：未完成的 BTW 旁问改成 `cancelled` 并写 `error` 文案 | 1533-1540 一带 | **1580-1587** |
| `_resume()`——重新拉起 Pi，`state = "idle"`、`activity = None`、`cancel_pending()`、追加 notice"已恢复上次的上下文，可以继续工作。" | **870-915** | **909-954** |
| `_resume()` 的唯一调用点：`send()` 里 `if not session.alive()` | 718 一带 | **757** |
| `_apply_proto_state()` | 1340-1357 | **1381-1398** |
| `_apply_activity()` | 1359-1373 | **1400-1414** |

`mms_web/drivers/pi_rpc.py` **两线逐字节相同**（`ab7facec`），一套行号：`agent_start` → `set_proto_state("running")` 在 `556`；`agent_settled` → `set_proto_state("waiting"/"idle")` 在 `562`；`message_start` 先 upsert 一条**空** assistant 事件在 `570`；`_activity()` 在 `665`；`tool_execution_*` 的 activity 在 `642`、`654-657`；工具 `status` 写入在 `643` / `648` / `658`。

---

## 根因

分成**触发器**和**放大器**两层。触发器有两条路径，放大器只有一套，两条路径共用。

### 触发器 A（截图二，首选复现路径）：服务重启把队列作废、把状态改写

`mms_web/sessions.py:1566-1570`（main `1519-1523`），会话从持久化恢复的那条路径：

```python
live.events = [e for e in (payload.get("events") or []) if isinstance(e, dict)]
for event in live.events:
    if event.get("kind") == "user" and event.get("status") == "queued":
        event["status"] = "cancelled"
live.finish_pending_tools()
```

任何仍处于 `queued` 的用户消息，在恢复时一律改成 `cancelled`。**这个处理本身是对的**——进程没了、Pi 队列也没了，那条消息确实永远不会被送达，装作还在排队才是骗人。`finish_pending_tools()`（`287-291`）紧接着把挂着的工具收尾成 `error`。**本包不改这段。**

两个语义要分清楚（注释就写在代码里）：

| 方法 | 写成什么 status | 什么时候 | `deliveryLabel()` 的文案 |
| --- | --- | --- | --- |
| `cancel_pending()`（dev `311-319`） | `cancelled` | 队列被显式清空，**或被 resume / 重启作废** | 「已取消，未执行」 |
| `interrupt_pending()`（dev `321-329`） | `interrupted` | abort / stop 中途把它从 Pi 队列里拿掉 | 「已被停止打断，未执行」 |

`owner` 那台机器今天 Pilot 被重启过多次（另一个 agent 换过 8767 端口，PR #270 修的正是"重启后端口漂移"），时间与截图吻合。

**状态怎么变成"本轮已完成"的**——这一段要实测确认，本包只给出代码上可达的两条路：

- 重启恢复时 `state` 被兜底成 `"stopped"`（dev `1599-1601`）。此时 `activity_view()` 返回 `None`（`331-337`），`sessionStatus()` 走 terminal 分支 → phase `"stopped"` → 状态栏应显示**「已停止」**，不是「本轮已完成」。
- **「本轮已完成」对应的 phase 是 `"completed"`，它在 `sessionStatus()` 里只有一个来源：`session.state === "idle"` 且 `activity` 为空**（`SessionStatus.tsx:22-23` + `labels.completed` `:33`）。`state` 变成 `"idle"` 的路径是 `_resume()`（dev `938-939`）——**它只在 `send()` 发现会话已死时被调用**（`757`）——或者一次正常的 `agent_settled`（`pi_rpc.py:562`）。

所以截图二最可能的完整序列是：**重启 → 排队消息被作废、该轮没有回答 → owner 又发了一条 → `send()` 触发 `_resume()`，`state` 置 `idle`、`activity` 清空 → 状态栏说「本轮已完成」，而 transcript 里那一轮从头到尾没有产出**。

**这条序列必须实测确认，不许照抄。** 见"第一步：必须先复现"的第 5 步。

### 触发器 B（截图一，次选复现路径）：中途消息切开回合

`Transcript.tsx:139-143`（main `80-84`）：

```tsx
const turns: SessionEvent[][] = [];
for (const event of events.filter(e => !pending.includes(e))) {
  if (!turns.length || event.kind === "user") turns.push([]);
  turns[turns.length - 1].push(event);
}
```

**每个 `kind === "user"` 事件都开一个新回合。** 中途补的引导消息就是一个 user 事件。

注意它**什么时候**落地：`send()`（dev `767-789`）在会话正忙时给这条消息打 `status = "queued"`；`:138` 把 `queued` 的 user 事件挑进 `pending`，`:139-143` 把 `pending` 排除在切分之外。所以**排队期间回合数不变**，等 Pi 真正消费掉它之后回合才突然多一个——这解释了症状为什么是"突然"出现的。

### 放大器 1：「已完成」是从位置推出来的

`Transcript.tsx:144` 与 `:151`（main `85` / `92`）：

```tsx
const active = ["running", "waiting"].includes(props.detail.session.state);
…
completed={index < turns.length - 1 || !active}
```

一个回合被判成 `completed`，只看**它后面有没有别的回合**，不看它实际跑没跑完。触发器 B 一发生，正在运行的那个回合立刻变成 `completed`。

### 放大器 2：`active` 只读 `session.state`，和状态栏不是同一套判定

这是 owner 两张截图里那个矛盾的直接来源。

`Transcript.tsx:144` 只看 `session.state ∈ {running, waiting}`。而 `sessionStatus()`（`SessionStatus.tsx:14-23`，**两线行号相同**）的优先级是：

```tsx
const phase = disconnected ? "disconnected"
  : terminal ? (session.state === "completed" ? "closed" : session.state)
  : session.state === "waiting" ? "waiting"
  : session.activity?.phase || (session.state === "idle" ? "completed" : session.state);
```

`session.activity?.phase` **排在 `state === "idle"` 前面**。所以只要 `state === "idle"` 而 `activity` 非空，状态栏说"执行工具 · bash"，transcript 说"全都完成了"（截图一）；反过来 `state === "idle"` 而 `activity` 为空，状态栏说"本轮已完成"，transcript 同样说"全都完成了"，而那一轮其实什么都没产出（截图二）。**两边用的根本不是同一个判定。**

后端侧这个组合是可达的，不是臆测：

- `_apply_activity()`（dev `1400-1414`）**只写 `session.activity`，一个字都不碰 `session.state`**。
- `_apply_proto_state()`（dev `1381-1398`）是 `state` 的唯一写入方；只有收到 `agent_settled`（`pi_rpc.py:562`）才写 `idle`。
- `agent_settled` 与下一个 `agent_start`（`pi_rpc.py:556`）之间，`state` 就是 `idle`；这个窗口里再来一个 `tool_execution_start`（`pi_rpc.py:642`），`activity.phase` 被写成 `tool` 而 `state` 留在 `idle`。

### 放大器 3：流式正文不再显示

`Transcript.tsx:81`（main 无此行）：

```tsx
const streamingAnswer = !completed ? findActiveAnswer(events) : undefined;
```

`findActiveAnswer` 只在 `!completed` 时跑。被误判成 `completed` 的回合，**正在打的字就不再被提升成回答**——它退回 `completedAnswer` 那条路径（`:80`），语义变成"这是本轮最终答案"，于是 `collapsed`（`:83-84`）也跟着判真，把用户正在读的过程**自动收起来**。

### 放大器 4：一条渲染死分支，结果是 `null`

`Transcript.tsx:97` 与 `:115-119`（main 无 `isWorking`，答案槽在 `60`）：

```tsx
const isWorking = !completed && !answer && (collapsed || !hasProcess);
…
{answer ? (
  <EventView {...props} event={{...answer, thinking: undefined}} turnStartedAt={user?.createdAt} />
) : isWorking ? (
  <TurnWorkingStatus detail={props.detail} disconnected={props.disconnected} />
) : null}
```

**一个 `completed=true`、`answer` 为空、`process` 又为空的回合，三个槽位全落空，渲染结果是 `null`——一片空白。** 占位之所以也不出现，正因为 `isWorking` 的条件里带着 `!completed`。

### 空白的精确成立条件（实现者用这个设计测试）

整片空白要同时满足：

1. 这个回合 `hasProcess === false`（否则 `:111-114` 的过程块会渲染出来）；
2. 没有任何 `kind === "assistant" && text.trim()` 的事件（否则 `answer` 有值）；
3. `completed === true`。

第 1 条比直觉容易满足：`Transcript.tsx:135-137` 的事件过滤会把 **`kind === "assistant"` 且 `text` 和 `thinking` 都为空**的事件整个丢掉。Pi 在 `message_start`（`pi_rpc.py:570`）就先 upsert 一条空 assistant 占位事件，所以从"消息被消费"到"模型吐出第一个字或第一个工具"这整段时间里，这个回合的事件列表**就只有那一条 user 事件**。

第 3 条：这个回合是最后一个回合，`index < turns.length - 1` 为假，所以 `completed === !active`，而 `active` 只看 `session.state`。**`state` 一旦不是 `running` / `waiting`，`completed` 就是 `true`。** 重启恢复（`stopped`）、`_resume()`（`idle`）、`agent_settled` 与下一个 `agent_start` 之间（`idle`），三条路径都满足。

结果：`<section className="conversation-turn">` 里只剩用户自己那条气泡，底下**什么都没有**。与 owner 描述逐条吻合。

---

## 已经排除的两条（省得实现者重走）

### 不是"前端不刷新"

`App.tsx` 的详情轮询（dev `594-630`，main `571-608`）每 1200ms 无条件 `getSession(selectedId)` 并 `setDetail(result)`，**没有任何 `updatedAt` / `lastEventAt` 门**。唯一的跳过条件是 `mutation.current`（正在提交别的操作）和 `generation.current` 变化（切了会话）。数据一直在进来。

### 不是 btw 分出 `lastEventAt` 导致的

`mms_web/sessions.py` 的 `append_event`（`179-180`）和 `upsert_event`（`199-200`）**都会推进 `self.updated_at`**，`last_event_at` 只是紧跟着它赋值：

```python
self.updated_at = now()
self.last_event_at = self.updated_at
```

两条线行号相同。没有哪条路径能让 `last_event_at` 落后于 `updated_at`。

---

## BTW 是不是必要触发条件

**代码层面的判断：不是必要条件。** 依据两条：

1. `mms_web/sessions.py:134-135` 的注释和实现：

   ```python
   # /btw side questions live beside the transcript, never in events.
   self.side_questions: dict[str, dict] = {}
   ```

   旁问存在 `session.side_questions`，通过 `detail_view()` 以 `sideQuestions` 字段单独下发，**从不进 `self.events`**。`Transcript.tsx` 只读 `props.detail.events`，所以 BTW **不可能改变回合切分，也不可能改变任何一个回合的 `completed`**。

2. 上面"空白的精确成立条件"三条，没有一条需要 BTW 参与。

**但这不等于可以跳过实测。** 两条本包**没有**排除的可能：

- BTW 的 native 扩展路径（`_probe_btw_native`，dev `1245-1264`）在 `btwNative` 为真时是**在同一个 Pi 进程里**跑的。它会不会让 Pi 多发一次 `agent_settled` / 多写一次 activity、从而把放大器 2 那个窗口拉长，本仓库读不出来（`pi_rpc.py` 侧没有 btw 专用分支，Pi 进程内部怎么处理扩展调用不在本仓库）。
- 重启恢复时未完成的旁问也会被改成 `cancelled` 并写 `error` 文案（dev `1580-1587`），所以 BTW 与重启路径是**并发受害者**，不是因果。

**要求实现者：有 BTW 和没有 BTW 两种情况都试，交付里明确回答"BTW 是不是必要条件、是否显著提高复现概率"，各附证据。** 如果只有带 BTW 的路径能复现，本包的根因分析不完整，**停下来报 owner，不要硬改**。

---

## 第一步：必须先稳定复现，再动手

**没有复现就不许改代码。** 复现步骤要写进交付。

起一个**自己的** Pilot 实例，**另起端口**：

```bash
cd <你的 worktree>
npm run build --workspace @mms/web
PYTHONPATH=$PWD python3 -P -m mms_web --port 61712 \
  --state-root /tmp/t7e-verify \
  --config-root ~/.config/mms-next \
  --static-root $PWD/apps/mms-web/dist
```

**不要动 8767，不要动 60824**（owner 的实例）。不要重启任何已有 Pilot。

### 首选路径：停服务再拉起（对应截图二，不需要凑时序）

1. 发一个会跑较久的任务（真的要进 `tool_execution_start`，例如一条 `sleep 60` 的 bash，不要用纯思考型任务）。
2. **在它运行中途**再发一条消息，确认它落在 composer 上方显示为排队中（`status === "queued"`）。
3. **停掉你自己那个 61712 服务进程，再用同样的命令拉起来。**（只停你自己起的那个。不许用 `pkill`。记下你的 PID，用它退出。）
4. 刷新页面，打开同一个会话。观察：
   - 那条排队消息是不是变成了「已取消，未执行」；
   - 被打断的那一轮有没有 assistant 回复；
   - transcript 最后一段是不是空白；
   - 状态栏说什么。
5. **同时抓后端真值**，这是本包最重要的一次测量：

   ```bash
   curl -s localhost:61712/api/v1/sessions/<id> \
     | python3 -c 'import json,sys; d=json.load(sys.stdin)["session"]; print("state=",d["state"]); print("activity=",d.get("activity"))'
   ```

   分三个时刻各抓一次并贴进交付：**(a) 刚重启完刚打开会话时**、**(b) 又发了一条新消息之后**、**(c) 那条新消息跑完之后**。**明确回答：状态栏显示「本轮已完成」的那一刻，`state` 到底是 `idle` 还是 `stopped`，`activity` 是不是 `null`。**

### 次选路径：中途引导 / BTW（对应截图一）

6. 重新发一个长任务，运行中途再发一条消息，**不重启服务**，观察 transcript 最后一段是否空白、状态栏是否仍报"执行工具 · …"。同样抓 `state` / `activity`。
7. 重复一次，这次**先做一次 BTW 旁问再发引导**，对比两种情况的复现率。

录屏或连续截图存 `docs/mms-web/design/t7e/`（这个目录不存在，自己建）。

**如果复现不出来，停下来如实报告，不要凭代码推演就改。**

---

## 要做成什么

### A. 主修：`completed` 不能从位置推

`completed` 应该反映**这个回合的 assistant 是不是真的收尾了**，而不是"后面有没有人插过话"，也不是"会话现在是不是活的"。

实现者要查清可用的真实依据，给出方案并说明为什么可靠。**下面是本包已经核实过的、服务端真的在下发的状态来源**，按可靠度排：

| 来源 | 位置 | 说得准什么 | 注意 |
| --- | --- | --- | --- |
| `session.activity.eventId` | `types.ts:81`；后端 `_apply_activity` dev `1400-1414` | **当前正在产出的是哪一个事件**。含有这个 id 的那个回合就是正在跑的回合 | `tool_execution_start` 写 `t-<callId>`（`pi_rpc.py:642`），`message_start` 写 `m-<uuid>`（`:571`）。phase 为 `running` / `compacting` / `retrying` 时可能没有 `eventId` |
| 回合里是否有 `kind === "tool" && status === "running"` 的事件 | `types.ts:118-131`；后端 `pi_rpc.py:643/648/658` | **这个回合还有工具没跑完**；而且这个标记是被主动维护的：`finish_pending_tools()`（`sessions.py:287-291`）在本轮结束时把残留 running 工具改写成 `error` | **工具是唯一带真实生命周期 status 的事件种类** |
| `event.status === "error"` 且文本以「本轮已结束，未收到此工具的完成回报。」结尾 | `sessions.py:287-291` | **这一轮是被强行收尾的**，不是自然跑完 | 目前只能靠文本嗅探，脆；作为佐证而不是判据 |
| `event.mode === "steer"`（user 事件上） | `types.ts:110`；后端 `sessions.py:773` | **这条 user 消息是中途插进来的，不是新开一轮** | 历史事件可能没有 `mode`（`types.ts:108-109` 明说 "Absent on messages recorded before…"），要有缺省行为 |
| `steerLinks(events)` → `link.assistantId` / `event.steeredBy` | `message-control.ts:168-203`（**两线逐字节相同**） | **这条引导落进了哪一个回答**，即"这条引导属于哪一个回合" | 已经在 `Transcript.tsx:145-148` 被算出来用于 `steer-note`，可以复用 |
| `event.status`（user 事件）`cancelled` vs `interrupted` | `sessions.py:311-329` | **这条消息是被重启/清队作废的，还是被 stop 打断的** | 见下面 B / C |
| `session.activity.turnStartedAt` | `types.ts:85` | 当前这一轮什么时候开始的 | |
| `session.state` | `types.ts:69` | 只能说明**会话级**生死 | **不能单独用来判断"本轮跑完了"**——见放大器 2 |

**同时必须修的一件事：`active` 与状态栏对齐。** 现在 `Transcript.tsx:144` 和 `SessionStatus.tsx:14-23` 是两套独立判定。要求：**把"这个会话现在忙不忙"收成一个来源**——推荐从 `SessionStatus.tsx` 导出一个谓词（例如 `sessionIsBusy(session, disconnected)`），让状态栏和 transcript 都读它，而不是在 `Transcript.tsx` 里再写一遍 `["running","waiting"].includes(state)`。这样"状态栏说在跑、transcript 说全完了"在结构上就不可能再发生。`sessionStatus()` 已经把优先级写清楚了（terminal → waiting → `activity.phase` → `state`），复用它的 `phase` 比重写一遍安全。

### B. 被重启作废的消息必须可恢复

现在那条消息只得到 `deliveryLabel()` 的一行小灰字「已取消，未执行」（`message-control.ts:137-150`，渲染在 `Transcript.tsx:152-154` 的 `pending-messages` 区块）。**owner 完全没注意到，还在等回复。**

要求：**这条消息至少要有一个「重新发送」的入口，让用户一键把原文重新发出去。** 原文就在事件里（`event.text`，还有 `attachments` / `references` / `skills` / `fileSelections`），拿得到。

**措辞和放置交给实现者设计，但"能重新发出去"是硬验收项。**

现成的接缝（**不要另造一套**）：`App.tsx:253` 的 `guideRequest = {nonce, text}` → `App.tsx:1765` 传给 `Composer` → `Composer.tsx:310-316` 消费 nonce、`setText(...)`、`focus()`。同形的还有 `selectionRequest`（`Composer.tsx:317-320`）。把用户选中的消息原文塞回 composer，走同样的形状即可，**纯前端、不新增后端路由**。

实现者可以选择"填回 composer 由用户按发送"或"直接重发"；**推荐前者**——附件和引用能不能原样带回来需要实测，填回 composer 让用户看一眼再发，比静默重发安全。哪种都要在交付里说明为什么。

对 `interrupted`（被 stop 打断）的消息是否也给同一个入口，由实现者判断并说明；两者语义不同（一个是系统把它弄丢了，一个是用户自己停的）。

### C. 被打断的回合不许呈现成「本轮已完成」

明明是被重启打断、没有产出回答，状态栏却说完成了——用户看到"完成"就会去找结果，结果什么都没有。

要求**区分「正常收尾」和「被打断而结束」**，后者要说明白发生了什么、以及下一步能做什么。

**服务端信息够不够？本包的结论是"一半够，一半不够"，实现者必须按这个边界做：**

**够的部分**（前端现在就能算出来，不需要后端改）：

- 「这一轮没有产出回答」——回合里没有任何 `kind === "assistant" && text.trim()` 的事件。
- 「这一轮被强行收尾了」——回合里有 `kind === "tool" && status === "error"` 且文本以「本轮已结束，未收到此工具的完成回报。」结尾（`finish_pending_tools()`，`sessions.py:287-291`）。
- 「有消息因此被作废」——`pending` 里有 `status === "cancelled"` 的 user 事件；被 stop 打断的是 `"interrupted"`（`sessions.py:311-329`）。
- 「刚刚被 resume 过」——`_resume()` 会追加一条 notice 事件「已恢复上次的上下文，可以继续工作。」（dev `954`）。

**不够的部分**：

- 重启恢复那条路径（dev `1566-1601`）**不追加任何 notice 事件**，也**不在 session 上留任何标记**说"这个会话是被服务重启打断的"。它唯一的痕迹是 `state` 被兜底成 `"stopped"`，而这个痕迹**一旦用户再发一条消息触发 `_resume()`，就被 `state = "idle"` 覆盖掉了**（dev `938`）。
- 所以前端**可以**说"这一轮没有产出、被强行收尾了"，**不能**可靠地说"是因为服务重启"。

**据此定边界：**

- **默认做法（本包范围内）**：只用"够的部分"，把状态说成**事实**而不是**原因**——例如让那一轮的收尾态表达"这一轮没有产出回答"、"本轮被中断"，而不是「本轮已完成」；不要在前端猜"是重启还是别的"。
- **如果实现者认为必须让后端补信息**（例如在 `sessions.py:1566-1570` 那条恢复路径上追加一条 notice 事件，或在 session meta 上留一个"因重启而中断"的标记）：**这是一个明确的、单独的小改动，默认不做，必须先停下来报 owner 并拿到批准。** 边界写清楚：只在恢复路径追加一条 notice / 一个 meta 布尔值；**不改 `queued → cancelled` 这个处理本身**（那是对的）；不改 `state` 兜底成 `stopped`；不改 `finish_pending_tools()`。

### D. 约束：不要轻易改回合切分规则

"每个 user 事件开一个新回合"是整个 transcript 版式的**承重墙**。挂在它上面的有：

- `steer-note` 的归属（`Transcript.tsx:120-126`，那段注释说明了原意：引导可能落在被折叠的中间回答里，所以提示要挂在读者正在看的那个回合上）
- `after`（`:88` / `:126`）
- `autoCollapseProcess` 的自动折叠（`:83-84`）
- 折叠状态上报 `report(turnId, collapsed)`（`:99-101`），`turnId = events[0]?.id`（`:95`）——**回合的身份就是它第一个事件的 id**，切分一变，所有已记住的折叠状态全部作废
- `App.tsx:2114` 的全局按钮靠 `processTurns` 这张表判断"还有没有展开的回合"
- `GuidedTour.tsx:16` 用 `.conversation-turn:last-child` 作为引导锚点

**优先修 `completed` 的来源，而不是改怎么切回合。** 如果实现者认为必须改切分，**先把影响面写清楚并停下来问 owner**，不要自己往下做。

### E. 顺带堵死那条死分支

三个槽位（`answer` / `isWorking` 占位 / `null`）都落空时，**不允许渲染 `null`**。

- 一个**仍在运行**的回合，必须看得见"在做什么"。
- 一个**虽已结束、但既无过程又无回答**的回合（被重启打断、被 stop 打断、Pi 进程退出），必须让用户看见发生了什么，并且能看出它**不是**一次成功的收尾。

具体呈现交给实现者设计，但**结论必须是：`Turn` 在 `user` 气泡之后永远至少渲染一样东西**。

---

## 只许改

- `apps/mms-web/src/Transcript.tsx`
- `apps/mms-web/src/SessionStatus.tsx`（**只允许新增导出的纯函数 / 常量，以及 C 所需的收尾态文案**；不允许改 `sessionStatus()` 已有的 phase 优先级，不允许改 `Status` / `CurrentActivity` 的渲染结构或与本包无关的现有文案）
- `apps/mms-web/src/App.tsx` —— **只允许三处最小接线**：
  1. 新增一个 `{nonce, text}` 形状的 state（照 `253` 的 `guideRequest` 写）
  2. 把它传给 `Composer`（照 `1765`）
  3. 把 setter 传给 `Transcript`（`2029-2035`）
  轮询（`594-630`）、`processForced` / `processTurns` / `reportProcessTurn`（`323-330`）、全局折叠按钮（`2114-2133`）的语义**一概不动**。
- `apps/mms-web/src/transcript.css`（只允许新增或调整 `.turn-working-*` / 新占位与"重新发送"相关的类；**不许引入裸 hex**，沿用现有 token）
- `apps/mms-web/tests/turn-working-status.test.mjs`（补单测）
- 新增 `docs/mms-web/design/t7e/`（截图 / 录屏）

如果实现者判断需要在 `Transcript.tsx` 里导出纯函数供测试直接 import（**推荐**，现在的 `turn-working-status.test.mjs:96-112` 是用正则把函数体抠出来再 `vm` 跑的，脆），允许新增 `export`，但**不允许把 `Transcript.tsx` 拆成多文件**。

## 不许改

- `mms_web/` 任何 Python。**特别是 `sessions.py:1566-1570` 那条恢复逻辑本身不许改**——把作废的消息标成 `cancelled` 是对的。如果实现者认为服务端必须补信息，按 C 的规定**停下来报 owner**。
- `apps/mms-web/src/message-control.ts`（两线逐字节相同，改它会给 4.x↔5.x 合流制造冲突）。`deliveryLabel()` 的现有文案不动；"重新发送"是**新增的动作入口**，不是改写那行字。
- `apps/mms-web/src/Composer.tsx`（`guideRequest` 接缝已经存在，直接用；如果确实需要动，停下来说明）
- `components.tsx`、`ToolEvent.tsx`、`ConversationOutline.tsx`、`SideQuestions.tsx`、`side-questions.ts`、`MessageQueue.tsx`
- 受保护文件：`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`
- 真实 `~/.config/mms*`
- **端口 8767 和 60824**；不要重启任何**别人的** Pilot 实例；不许用 `pkill`
- 其它包的 worktree，特别是 `.worktrees/main-4.22`

不引入任何依赖（前端只用现有 react / lucide-react / esbuild）。

---

## 验收（逐条可勾）

### 复现与根因

- [ ] **首选路径（重启）稳定复现**：长任务运行中排队一条消息 → 停掉自己的服务再拉起 → 那条消息变成「已取消，未执行」、该轮没有 assistant 回复、transcript 那一段空白、状态栏说什么。录屏或连续截图存 `docs/mms-web/design/t7e/`，交付里写出复现步骤和复现率（试了几次成功几次）。
- [ ] **三个时刻的后端真值**都抓到并贴进交付：(a) 刚重启完打开会话、(b) 又发一条新消息之后、(c) 那条新消息跑完之后，各自的 `session.state` 与 `session.activity`。**明确回答：状态栏显示「本轮已完成」时 `state` 是 `idle` 还是 `stopped`，`activity` 是不是 `null`。**
- [ ] **次选路径（中途引导）也复现过**，并抓到对应的 `state` / `activity`。**明确回答：空白发生时 `state` 是不是非 `running`/`waiting` 而 `activity` 非空。**
- [ ] **有 BTW / 没有 BTW 两种路径都试过**，交付里明确回答"BTW 是不是必要条件、是否显著提高复现概率"，各附证据。
- [ ] 本文件列的所有行号在你的 base 上逐条复核过；**凡与本文件不一致的都在交付里列出来**。

### A 主修

- [ ] **一个正在运行的回合，在它后面出现新的 user 事件之后，仍然被当作运行中。** 它的过程继续实时显示、不被自动折叠，流式正文继续被提升成回答。录屏。
- [ ] **transcript 与状态栏不再互相矛盾**：状态栏显示任何"在跑"的 phase（`running` / `thinking` / `responding` / `tool` / `compacting` / `retrying`）时，transcript 的最后一段一定不是空白。在复现路径上实测，不能只靠单测。
- [ ] `Transcript.tsx` 里不再有"只看 `session.state` 判断会话忙不忙"的第二份逻辑；"忙不忙"只有一个来源，交付里写清楚是哪个函数、在哪个文件。
- [ ] **回合切分规则没有改**（`139-143` 那段循环的语义不变）。如果改了，说明为什么、并且已经事先问过 owner 且拿到答复。

### B 重新发送（硬验收）

- [ ] 被重启作废的那条消息**有一个可见的「重新发送」入口**，点了之后原文确实能重新发出去（填回 composer 或直接重发皆可，交付里说明选了哪种、为什么）。**端到端实测：点它 → 消息真的发出去 → 模型真的开始回答。** 录屏。
- [ ] 原文之外的附件 / 引用 / skills / 选段能不能带回来，实测并如实写明（带不回来就写带不回来，不许含糊）。
- [ ] 对 `interrupted`（被 stop 打断）的消息是否也给这个入口，做了判断并说明理由。
- [ ] `deliveryLabel()` 的现有文案没有被改写。

### C 被打断的回合

- [ ] **被重启打断、没有产出回答的那一轮，状态栏和 transcript 都不说「本轮已完成」**，而是说清楚"这一轮没有产出 / 被中断"，并指出下一步能做什么。截图。
- [ ] **正常跑完的一轮，收尾文案没有被改坏**——照旧显示原来的完成态。截图对比。
- [ ] 交付里明确写出：判据用的是"够的部分"里的哪几条；有没有在前端猜"是重启还是别的"（不许猜）。
- [ ] 如果认为后端必须补信息：**没有动手，而是停下来报了 owner**，并在交付里写清建议的最小改动与边界。

### E 死分支

- [ ] **`Turn` 在用户气泡之后永远至少渲染一样东西**，不存在返回 `null` 的路径。
- [ ] 仍在运行、但还没有任何过程和回答的回合：看得见"在做什么"。
- [ ] 已结束、但既无过程又无回答的回合：看得见发生了什么，且看得出**不是**一次成功的收尾。构造一次真实的"发消息后立刻停止"来验证，附截图。

### 不许破坏的既有行为

- [ ] **中途引导的 `steer-note` 仍然挂在读者正在看的那个回合上**（`:120-126` 那段注释说明了原意）。构造一次中途引导，确认提示位置与改之前一致，截图。
- [ ] **`autoCollapseProcess` 的自动折叠行为不变**：设置打开时，一个**真正跑完**的、有过程有回答的回合，过程仍然自动收起；设置关掉时仍然不收。两种都截图。
- [ ] **折叠状态上报 `report(turnId, collapsed)` 不变**：单个回合点"收起过程/展开过程"后，transcript 顶部那个"收起全部过程/展开全部过程"（`App.tsx:2133`）的文案仍然正确反映"还有没有展开的回合"。手点一遍，截图。
- [ ] **已完成的历史回合的渲染不变**：打开一个早就跑完的旧会话，逐屏对比改动前后截图，版式、折叠态、回答归属、`after` 区域全部一致。
- [ ] `turnId = events[0]?.id` 的身份没有变（否则用户已记住的折叠状态会全部作废）。
- [ ] `pending-messages` 区块仍然只收 `queued` / `cancelled` / `error` / `failed` / `interrupted` 这五种，没有把别的事件吸进去。

### 门禁

- [ ] `npx tsc --noEmit -p apps/mms-web` → **0 错**
- [ ] `node --test apps/mms-web/tests/*.test.mjs` → **pass ≥ 121 + 你新增的条数，fail 0**（**必须带 `*.test.mjs` glob**，不带 glob 会直接 `fail 1`）
- [ ] `npm run build --workspace @mms/web` → 通过
- [ ] `apps/mms-web/tests/turn-working-status.test.mjs` 里**新增**至少三条：
  - [ ] 运行中的回合**在后面出现新的 user 事件之后仍然被当作运行中**
  - [ ] **三个槽位都落空的情况不再渲染空白**
  - [ ] **一个既无过程又无回答、且带着被强行收尾痕迹的回合，不被表达成"正常完成"**
- [ ] `transcript.css` 新增部分不引入裸 hex（沿用 token；现有 `turn-working` 段落的断言在 `turn-working-status.test.mjs:81-94`，不要让它变红）

---

## 门禁基线（2026-09-16 在 base 上实测）

Base：`origin/dev` = **`f04d740e`**（`package.json` version = **5.0.1**）。跑之前先在 worktree 里 `npm install`。

| 门禁 | 实测值 |
| --- | --- |
| `npx tsc --noEmit -p apps/mms-web` | **0 错**（exit 0） |
| `node --test apps/mms-web/tests/*.test.mjs` | **tests 121 / pass 121 / fail 0**（19 个测试文件） |
| `npm run build --workspace @mms/web` | 通过；1916 modules；`dist/assets/index-*.css` **223.13 kB**（gzip 37.55）、`dist/assets/index-*.js` **793.19 kB**（gzip 255.72） |

参考：同一天在 `origin/main` = `6c62a656` = 4.22.1 上的对应基线是 tests **56 / 56 / 0**（7 个文件）、tsc 0 错、build css 148.95 kB / js 660.01 kB。**本包不在那条线上跑门禁。**

`apps/mms-web/tsconfig.json` 的 `include` 只有 `["src"]`，**`tsc` 不检查 `apps/mms-web/tests/*.mjs`**。

**Python 门禁**：本包不碰 Python，默认不需要跑 pytest。如果你出于别的原因跑了：`main` 和 `dev` 上都有**两条既有失败**（`tests/test_config_web.py` 里两条 `assert caps["reasoning"] is True`），**与本包无关，不许当成自己引入的，也不许顺手修**。

---

## 并行规则

沿用 README：

```bash
cd <5.x 集成 workspace>
git worktree add ../wt-T7e -b bot/T7e-interrupted-turn origin/dev
```

- 端口 **61712**（复现和验证都用这个）。**不碰 8767、不碰 60824**，不重启任何别人的 Pilot 实例，不许用 `pkill`。
- 不提交、不 push、不 merge。改完在 worktree 里给 `git diff --stat`，由 owner 批准提交。
- 不动 `.worktrees/main-4.22`（别的模型在里面工作）。
- 交付按 README 的"通用验收"格式写进 worktree 根目录的 `walls.md`（追加，不改旧条目）。

## 交付格式

```
包：T7e
base ref：origin/dev = <实际 commit>
分支 / worktree：
改动文件：git diff --stat 输出
复现（重启路径）：步骤、复现率（n/m）、录屏/截图路径
复现（引导路径 / BTW 对比）：同上 + BTW 是否必要条件的结论
后端真值：三个时刻各自的 session.state / session.activity
B 重新发送：选了哪种做法、为什么、附件与引用能不能带回来
C 被打断的回合：判据用了哪几条；有没有请求后端补信息（有则说明边界与 owner 答复）
门禁：tsc / node --test（数字）/ build（css、js 体积）
行号复核：与工单不一致的逐条
不许破坏项：逐条勾选结果 + 截图路径
未完成 / 未验证：逐条
```

---

## 行号核对（对工单给的行号）

owner 给的行号在 `origin/dev` 上**全部命中**：

| 工单写的 | 实测（dev `f04d740e`） | 判定 |
| --- | --- | --- |
| `Transcript.tsx` 回合切分 "约 139-143" | 139-143 | 命中 |
| `Transcript.tsx` completed "约 150-151" | `turns.map` 150，`completed=` 151 | 命中 |
| `Transcript.tsx` `streamingAnswer` "约 81" | 81 | 命中 |
| `Transcript.tsx` `isWorking` "约 97" | 97 | 命中 |
| `Transcript.tsx` 三槽位 "约 115-119" | 115-119 | 命中 |
| `Transcript.tsx` steer-note "约 120-126" | 120-126 | 命中 |
| `App.tsx` 详情轮询 "约 594-628" | 594-**630**（effect 结尾在 630） | 基本命中 |
| `sessions.py` `append_event` "约 179-180" | 179-180 | 命中 |
| `sessions.py` `upsert_event` "约 198-200" | 推进 `updated_at` 的是 **199-200**（198 是 `existing["updatedAt"]`） | 基本命中 |
| `sessions.py` 恢复路径 "约 1566-1569" | 1566-**1570**（`finish_pending_tools()` 在 1570） | 基本命中 |
| `sessions.py` `cancel_pending()` "约 311-319" | 311-319 | 命中 |
| `sessions.py` `interrupt_pending()` "约 321-" | 321-329 | 命中 |
