# T5b 返工 01 — 合并前必须清掉的两条（+ 一条 T5a 遗留）

**基线**:`bot/T5b-schedule-ui` = `1b0db061`,base = `bot/T5a-schedule-backend` = `e3e0d4ff`。行号按这两个 tip,已逐条复核。

**先说结论**:功能面逐条实测都是对的,挡在合并前的只有两条,都很窄,不是重做。

实测通过的部分(不用再碰):四种周期都能建;`一次` 走 `/tasks`+`runAt` 变成 `once` schedule 且**不产生 task**(`GET /api/v1/tasks` 实测 `tasks: 0`);`每天/每周/每 N 小时` 走 `/schedules`,小时换算正确;暂停/恢复/编辑/删除四个端点全部调对(`/disable`、`/enable`、编辑 POST 不带 `enabled` 所以不撞后端那条 400、`/delete`);四态分得开,「已到点但被挂起」没有被显示成逾期或出错,`lastSkip.reason` 五个取值全部有说法;两层闸分得清(总闸 banner + 每行 `is-gated` + 卡片第二行);`Bot.tsx` base 886-887 那处 `task.status === "scheduled"` 的死代码已经清掉,改成了 `task.scheduleId`。合并链两步实测走通、零冲突、合后 142/142 + fresh-user gate 718 PASS。

---

## 必改 1 · 暂停后的定时,列表里仍然写「待触发」

### 问题

`apps/mms-web/src/bot-schedules.ts` 的 `scheduleRunState`(def 在 `:230`):

```
:278    if (future) {
:279      return { kind: "upcoming", label: "待触发", detail: "" };
:280    }
:281    if (!schedule.enabled) {
:282      return { kind: "disabled", label: "已暂停", ... };
```

`future` 判断在 `!schedule.enabled` **之前**。任何重复规则被暂停后 `nextRunAt` 仍在未来,于是永远命中 `upcoming`。

而且不只是被 `future` 挡住 —— `:284` 的 `if (past)` 也返回 `{ kind: "upcoming", label: "待触发" }`。所以 `kind: "disabled"` 这一支**只在"既没有 `nextRunAt`、又没有任何 `lastSkip`"时才可达**,对真实数据基本是死支。

真机实测(隔离实例,点列表第一条的「暂停」之后):

```
POST /api/v1/bots/<bot>/schedules/<sid>/disable     ← 端点是对的
ROW0 AFTER PAUSE:
  class = "bot-schedule-row is-upcoming is-paused"
  text  = "每天 09:00 | 待触发 | … | 下次 今天 09:00 | … | 上一轮在跑就跳过 | … | 恢复 | 编辑 | 删除"
```

用户暂停了一条定时,列表告诉他「待触发 · 下次 今天 09:00」。唯一的线索是按钮变成「恢复」,加 `.is-paused` 带来的一层背景色(`bot.css:3385-3388` 只改了 `background: var(--soft)`)。另造一条持久的 `enabled=false` + 未来 `nextRunAt`(S8),渲染同样是「待触发」。

交付里写的「暂停 → 卡片『定时已暂停』」指的是**侧栏卡片第二行**(`getBotSecondLine`,而且只在全部暂停时才出现),不是列表行。列表行这条没有被检查过,`bot-schedules.test.mjs` 里也没有 disabled+future 的用例。

### 期望

`!schedule.enabled` 必须能盖住 `future` 和 `past`。但**不要简单地提到函数最前面** —— 那会吃掉两条用户必须知道的信息:

1. **hold 的补跑承诺要保住。** 一条定时到点时被暂停拦住(`lastSkip.reason === "paused"`),现在处于暂停态,用户需要同时知道两件事:它现在不会触发,**而且**恢复后会把错过的那次补跑。所以 `!enabled` 且有 hold skip 时,label 走「已暂停」,detail 必须仍然带"恢复后会补跑这一次"的意思。
2. **`invalid` 不能被改坏。** 现在 `nextRunAt=null` + `enabled=false` + `lastSkip.reason==="invalid"` 渲染成「记录损坏 · 这条定时读不出来,改规则或时区后再启用」且恢复按钮 disabled。改完之后这条必须**逐字不变**。

要满足的契约,按这三条验:

- `!enabled` → label **必须**是「已暂停」,不能是「待触发」
- `!enabled` 且 `lastSkip.reason ∈ {paused, busy}` → label 是「已暂停」,detail 里仍然说明恢复后会补跑
- `!enabled` 且 `lastSkip.reason === "invalid"` → 仍然是「记录损坏」那一套,不变

具体用哪种实现(把 enabled 判断提前并在里面分叉,还是给 `upcoming` 带一个 paused 标记)你定,写清理由就行。

### 验证

- `bot-schedules.test.mjs` 补三条断言,对应上面三条契约。**其中 disabled+future 那条是现在完全缺失的用例。**
- mutation:把你的改动还原成原顺序 → 那三条必须红
- 真机重跑一次:点暂停,截图列表行,label 是「已暂停」

---

## 必改 2 · 测试只 grep 源码文本,整块面板可以删光而全绿

### 问题

`apps/mms-web/tests/bot-schedule-ui-wiring.test.mjs` 92 行**全部**是 `readFileSync` + 正则,从不渲染 `BotSchedulePanel`。

实测(每条单独跑、跑完 `git checkout` 还原):

| 我改了什么 | 用户实际看到 | `node --test apps/mms-web/tests/*.test.mjs` |
|---|---|---|
| 在 panel 渲染开头插 `if (1 as number) return null;`,JSX 原文**全部留在文件里** | 整个定时面板什么都不渲染 | **135 pass / 0 fail** 全绿 |
| 把 `<span className={...}>{state.label}</span>` 那行**注释掉**,字符串仍在文件里 | 所有状态标签消失 | **135 pass / 0 fail** 全绿 |
| 调用点改成 `scheduleRunState({...schedule, nextRunAt: null, lastRunAt: "2026-01-01…", lastSkip: null})` | **每一行都显示「已执行完 · 这一次已经跑过,不会再触发。」** | **135 pass / 0 fail** 全绿 |
| `scheduleEnablePath(bot.id, schedule.id, schedule.enabled)`(去掉 `!`) | 点「暂停」调 `/enable`,什么都不发生 | **135 pass / 0 fail** 全绿 |

第三行就是必改 1 那个 P1 的形态 —— **它可以被引入而测试一条不红。**

你在追加段 D 里点名的那四条变异确实都会红,我复跑确认了(`* 3600 → * 60` 红、`mutate(scheduleEditPath(...))` 红、`scheduleRunState` 压成两态红、`?? true → || false` 红)。但它们红的原因是改动**恰好碰到了被正则断言的那段源码文本**,不是因为行为被测到。两者的区别就是上面这张表。

**这是这批包第三次栽在同一个地方**(#281、#286 各一次),而且这次踩在"四态区分"这块最要紧的 UI 上。所以这条不是可选的。

### 期望

补**至少一条真渲染测试**。`react-dom/server` 的 `renderToStaticMarkup` 就够,不需要引 jsdom(仓库里已有 `react-dom`,不要为这条加新依赖;如果发现必须加,先停下来说明)。

最低要覆盖:

1. **四/五态**:分别造 upcoming / held(paused 和 busy 各一) / completed / error / invalid 的 schedule 数据,渲染面板,断言渲染出来的**文本**含对应 label。这样"把状态 chip 注释掉"和"调用点塞假数据"都会红。
2. **面板真的渲染了内容**:断言渲染结果里有行元素、行数等于传入的 schedule 数。这样 `return null` 会红。
3. **启停路径**:点暂停走 `/disable`、点恢复走 `/enable`。如果真渲染里不方便触发点击,退一步:把 `scheduleEnablePath` 的返回值直接断言(`scheduleEnablePath(b, s, true)` 结尾必须是 `/disable`、`false` 必须是 `/enable`),再加一条断言调用点传的是 `!schedule.enabled`。这样去掉 `!` 会红。

现有的 92 行正则测试**保留**,它对"行号/命名没漂"仍然有价值,只是不能是唯一的看守。

### 验证

上面那张表的四条变异,改完之后**每一条都必须红**。请在交付里逐条写明你跑了、结果是红、红在哪条测试上。

---

## 必改 3 · T5a 遗留:被 error 挡住的 once,恢复后静默补触发

这条属于 T5a 后端(`#278` 已验收 PASS),但它就在你这个栈上,而且是一行加一条测试的事,顺手做掉。

### 问题

`mms_web/bots.py:1625`:

```python
if schedule["rule"]["kind"] == "once" and (schedule.get("lastSkip") or {}).get("reason") in {"paused", "busy"}:
    self._message(fired["id"], "system", f"这条定时原定 {format_local(due_at, updated['timezone'])} 触发，因暂停或上一轮未结束而延后，现在补触发。")
```

集合里没有 `"error"`。所以被 M1 那条新路径 parked 的 once(create 失败 → `defer_once(reason="error")`),等 executor 恢复后**静默补触发** —— 实测那条 task 上的消息只有 `['一次提醒', 'Pi 已接收任务。']`,没有任何"原定 X 触发,现在补触发"。

用户视角:一条设在昨天 21:00 的一次性提醒,因为当时模型不可用没建出来,今天 10:00 突然跑了,而且不说为什么。

### 期望

把 `"error"` 加进那个集合。**但文案要跟着分叉** —— 现有那句硬编码了原因("因暂停或上一轮未结束而延后"),对 error 来说是假的。按 `lastSkip.reason` 给出真实原因:

- `paused` / `busy` → 保持现有文案
- `error` → 说清是上次没能建出任务,例如「这条定时原定 X 触发,当时没能建出任务,现在补触发。」

顺带:M1 分支里 `defer_once(updated, stamp=now(), reason="error")` 的 `"error"` 是硬编码的。目前只有 create 失败能进这个分支(`advance()` 对 `once` 恒返回 `skipped=0`,见 `bot_schedules.py:262-264`),所以现在不算错。**加一行注释说明这个前提**,这样以后有人改 `advance` 对 once 的行为时能看到标签会说谎。

### 验证

- 一条测试:once 被 error parked → executor 恢复 → 下一个 tick 建出的 task 上**有**补触发消息,且消息里出现的原因是"没能建出任务"而不是"因暂停"
- mutation:把 `"error"` 从集合里拿掉 → 这条必须红
- 现有那条 `test_a_failed_create_does_not_consume_a_once_schedule` 不受影响,仍必须绿

---

## 三件小事(一起做掉)

**a. 截图数虚高,改掉文件名或补齐。** 22 个 png 只有 18 个唯一内容:

```
list-state-upcoming.png == list-state-held-paused.png == list-four-states.png   (sha256 前缀 c3f87e291da8)
list-state-completed.png == list-state-invalid.png                              (399ec407f61f)
card-second-line-all-paused.png == list-after-pause.png                         (61d58dac)
```

图本身是真的 —— 一张图里确实同时有四态,像素内容和实测渲染逐字一致。问题是用四个"每态一张"的文件名去声称覆盖。要么删掉重复文件、在交付里说明"四态在同一张图里",要么真的每态单独截一张。**这和 #277 那次重复截图是同一个问题,不要再重复。**

**b. 总闸行的 chip 字面矛盾。** `wakeEnabled=false` 时,每行 meta 写「被自动唤醒总闸拦住」,而同一行的 chip 仍然写「待触发」。建议给 gated 一个独立的 run state。这条如果和必改 1 的改法能合并处理就一起做,否则可以下一轮。

**c. `bot-schedules.test.mjs` 只测了 paused。** `holdReason: "busy"` 和 `error` 态没有断言。补上 —— 必改 2 的真渲染测试如果已经覆盖了这两态,这条就算完成。

---

## 不用改的两条(我看过,判定为可接受)

**`BotStudio.loadSchedules` 的 N+1 轮询。** 3 秒一次的 `sync` 里对每个 Bot 发一次 `GET /bots/:id/schedules`,并且 `await` 完才排下一次 poll。Bot 多了之后请求量和 poll 间隔都会被拖。这是真的,但改法牵扯到 sync 的整体形状,不该塞进这一轮。**单独记为 follow-up,不在本包内。** 顺带提一句:那个 `useCallback(..., [])` 的闭包里用了 `isPreview` 而依赖数组没写,这条是真缺陷但当前 `isPreview` 在挂载后不变,所以不炸 —— 加进 follow-up。

**composer 的「一次」和其他三种走两条不同链路。** `一次` → `POST /bots/:id/tasks`(`create_task` 先 `executor.validate()`),其他三种 → `POST /bots/:id/schedules`(不需要 executor)。后果是没配模型时能建「每天」但建不了「一次」。这符合 T5a 定的 API 形状,是个可见的不对称,但不是 bug,也不该在 UI 层绕过后端的形状。**保持现状。** 如果以后要统一,那是 T5a 的 API 改动。

**`DispatchForm` 两处入口和 `BotStudio` 编辑对话框的 checkbox 目前挂不上。** 你自己报了。`DispatchForm` 没有挂载点、`BotStudio` 的编辑对话框实际打不开(活的总闸是面板里的 `AutoWakeControl`)。改了但不可见 ≠ 错,保留即可,但**在交付里保持这个披露**,别让下一个人以为它们是活的。

---

## 交付要求

1. 三条必改 + 三件小事都做完
2. 每一条的 mutation 结果写明(改了什么 → 红还是绿 → 红在哪条测试上)。**必改 2 那张表的四条一条都不能少**,这是专门用来证明测试不再是理论的
3. 门禁全量重跑,写实测绝对数:`npx tsc --noEmit -p apps/mms-web`、`node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带**,否则 `markdown-reading.test.mjs` 会因为缺 `unified` 而失败)、`npm run build --workspace @mms/web`、`bot.css` 裸 hex 必须仍是 **12**、定向 pytest、`python3 scripts/ci_pytest_regression.py --base bot/T5a-schedule-backend`
4. `python3 scripts/regression_fresh_user_gate.py`(完整,不加 `--quick`)。跑前先 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`。**这个 gate 对并发敏感**:`test_install_script_paths.py::test_installer_does_not_reuse_another_homes_web_instance` 会比对端口和 PID,并行跑会假失败;串行跑一次,如果那一条红了单独复跑确认,并在交付里如实写明
5. 必改 1 和必改 3 改了用户可见行为,真机各验一次并存证据
6. 行号复核照你上一轮的做法保留 —— 那张 12 行对照表我抽查了两条都对(`BotStudio 138→实际 139`、`Bot.tsx 901-903→实际 886-887`),而且你主动标出了"`BotStudio 953-980` 的 `AutoWakeControl` 挂载点不存在"。这个习惯保持
7. 推到 `bot/T5b-schedule-ui`,#302 的 base 保持 `bot/T5a-schedule-backend` 不变 —— 合并链是 `#302 → T5a 分支 → #278 一起带进 dev`,不要改 base

跑真机验证时:端口用 61000-62000 的随机值,**绝不碰 8767 / 60824 / 8765 / 8766**(机主自己的 Pilot);绝不用 `pkill`,只 kill 自己启动的 PID;绝不写真实 `~/.config/mms*`。
