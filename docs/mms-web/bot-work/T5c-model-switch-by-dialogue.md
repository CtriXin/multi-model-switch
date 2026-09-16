# T5c · 在对话里换 Bot 的模型

Date: 2026-09-16
Task: Stride 370e87ec37e741df
分支：`bot/T5c-model-switch-dialogue`，**必须从 T5a 完成后的 HEAD 开**（不是 `dev` / `dev-pre` 的 HEAD）。T5a 的 base 是 `dev`（重组后 `dev` 即 5.x 线）；重组尚未完成时用 `origin/dev-pre`（本次刷新基准 `77f2fd8a` = 5.0.1）
建议模型：k3 或 deepseek（后端为主，UI 是最小接线）
来源：owner 2026-09-16——切模型能力其实存在，但 Bot 不知道，也只能去 Bot 编辑器里改

先读：`docs/mms-web/bot-work/README.md`（并行规则、通用验收）、`docs/mms-web/bot-work/T5a-schedule-backend.md`（命令清单从 parser 生成那一节，本包直接依赖它）、本文件、然后按下面"要读的代码"逐处确认。

## 前置依赖与落地顺序（不可绕过）

**必须排在 T5a 之后，从 T5a 完成后的 HEAD 开分支。**

T5c 动的是 `bot_executor.py` 的提示词和 `bot_client.py` 的 parser——**和 T5a 是同一批文件**。两个模型同时改这两个文件必然冲突，而且 T5a 已经把"命令清单从 parser 生成"这条基础设施做掉了，T5c 只要往 parser 里加子命令，提示词自动就有，不需要再手写一遍。

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch
git worktree add .worktrees/wt-T5c -b bot/T5c-model-switch-dialogue bot/T5a-schedule-backend
cd .worktrees/wt-T5c && npm install
```

落地顺序：**T5a → T5b / T5c**。T5b 和 T5c 都从 T5a 的 HEAD 开，彼此不重叠（T5b 纯前端 `apps/mms-web/**`，T5c 后端为主）。三个包都验收完才一起合进 base 分支，**后端不单独进主线**。

## 目标一句话

用户在对话里就能换 Bot 的模型，Bot 自己知道有这个能力、知道有哪些模型可用、换不了会如实说，界面上看得见换成了什么。

## 要读的代码（只读，先看完再动手）

| 位置 | 看什么 |
| --- | --- |
| `mms_web/model_switch.py`（**214 行，2026-09-16 复核未变**，全读） | 会话级切模型的完整实现，模块注释 `"""Explicit model changes in one Web conversation, preserving Pi native history."""`；`DeferredSink`（**13-39**，`activate` 34）挡候选进程在切换提交前发状态；`rpc`（**42-49**）/ `route_identity`（51-55）/ `verify`（**57-65**）/ `apply_native`（**67-83**）/ `switch_model`（86-187）/ `prepare_runtime`（190-214）；错误码 `MODEL_SWITCH_FAILED`（47/130/138/179）、`MODEL_NOT_APPLIED`（61）、`EFFORT_NOT_APPLIED`（63） |
| `mms_web/session_actions.py:182` | `switch_model(session_id, payload)` 入口（def 在 **182**，183-184 行转调 `model_switch.switch_model`，import 在方法体内）—— 行号复核未变 |
| `mms_web/server.py:535` | `methods = {..., "model": "switch_model", ...}`，即 `POST /api/v1/sessions/:id/model` —— 行号复核未变 |
| `apps/mms-web/src/TaskSettings.tsx` **109 / 125-131** | Pilot 会话的切模型 UI：`locked` 在 **109**；`QuickModelMenu` 在 **125-126**；`change={presetId => action(`/sessions/${detail.session.id}/model`, {presetId})}` 在 **127**；`disabled` 条件（含 `["running","waiting"].includes(detail.session.state)`）在 **128**；notice 文案 `本轮完成或停止后可切换模型。` 在 **129-131**。同文件 51-88 还有另一处 `QuickModelMenu`（不同组件），别改错 |
| `mms_web/bot_executor.py` 23-35 行 | `validate(bot)`：27 行按 `bot["presetId"]` 查，29 行回落到第一个 `harness == "pi"` 且 `available` 的 preset，30 行再断言一次；**35** 行返回 `{"model": preset["name"], "channel": preset["channel"], "presetId": preset["id"]}`。**31** 行是 `BOT_MODEL_REQUIRED` 的唯一抛出点（`bot_retry.py:28` 把它列为永久不可重试码） |
| `mms_web/bots.py:396-402` | `update_bot`（def **396**）的 `active` 判定（**399**）+ `BOT_BUSY`（**401**）：`WebError("BOT_BUSY", "Bot 正在执行当前任务，模型将在本轮结束后才能切换。", 409)`。**注意它是 preset 作用域的**：只有 `"presetId" in payload and payload.get("presetId") not in (None, "", bot.get("presetId"))` 才触发。`delete_bot` 459 行还有一个同码不同文案的 `BOT_BUSY`，别混 |
| `mms_web/bots.py:436` | **订正**：436 行实际写的是 `updated.update(self.executor.validate(updated))`（变量叫 `updated`，不叫 `bot`）；旧包引的 `bot.update(self.executor.validate(bot))` 那个拼写在 `create_bot` 的 **379** 行。两处都是"用解析结果**覆盖** `presetId` / `model` / `channel`" |
| `mms_web/bots.py:1170-1171` | 计划步骤的 `presetId` 落成子 task 的 `presetIdOverride`（1170 是 `if step.get("presetId"):`，1171 是赋值） |
| `mms_web/bots.py:1618-1619` | `_launch`（def 在 **1551**）里 `if task.get("presetIdOverride"): bot = {**bot, "presetId": task["presetIdOverride"]}`——**子任务级分模型的机制已经存在**。行号复核未变 |
| `mms_web/bots.py:1856-1919` | `worker(task_id, payload)`：`bot_client` 子命令在这里落成 `action` 分支 |
| `mms_web/bot_client.py` **140-205** 行 | `_build_parser`（140-205）、`with_request_id`（149-158）、`_command_payload`（208-276）；现有 15 个子命令注册在 160-205。T5a 之后这里还有命令清单的生成入口 |
| `apps/mms-web/src/Bot.tsx` **1020-1034** | `parseBotSettingCommand`：**前端已经有一条"在对话里换模型"的捷径**，正则（1025-1026）拦住"把模型改成 X"。**订正**：这个函数本身**不调** `onUpdateBot`，它 `return { patch: { presetId: preset.id }, message: ... }`（**1031**）；真正的 `onUpdateBot(bot.id, setting.patch)` 在 **1902** 行、`sendMessage`（1885-1933）内的 1897-1906 块里。**消息从不发给 Bot** 这一点仍然成立 |
| `apps/mms-web/src/Bot.tsx` **69-87** | `BotDefinition` 的字段：`presetId: string \| null`（**74**）、`wakeEnabled: boolean`（77）、`modelName?: string`（**79**）。**没有 `model` 字段** |
| `apps/mms-web/src/BotStudio.tsx:261-274` | Bot 编辑器里的模型下拉：`label.bot-model-field`（261）、`默认模型`（262）、`ModelPicker`（263-272）、**273** 行 `模型和通道分开选择；留空时使用 MMS 默认模型。` —— 行号复核未变 |

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

### 1. 【必读】T5c 改 `bot_executor.py`，PR #270 也改它 —— 以 #270 合并后的版本为基准

PR #270（`fix/bot-compact-pilot-restart` → `dev-pre`，**尚未合并**）在 `mms_web/bot_executor.py` 上是 +39/−12，同时动 `mms_web/bots.py`（+2/−3）和 `mms_web/service.py`（+9/−2），新增 `tests/test_mms_bot_compaction.py`。内容是把 Pi 0.85.1 已经是 0–100 的 `contextUsage.percent` 上那次多余的 `*100` 去掉，并把 `Nothing to compact (session too small)` / `Already compacted` 从阻塞错误改成 no-op。

- **本包要改的是同一个 `bot_executor.py`**（抽 `available_presets(catalog)` 纯函数、可能补一句行为性指示）和同一个 `bots.py`（`worker()` 的 `action == "model"`、`_launch` 1618-1619 的优先级、Bot 实体字段）。
- **要求：开工前先确认 #270 是否已合。**
  - 已合 → 从合并后的 `dev` / `dev-pre` HEAD 开 T5a，T5c 再从 T5a 的 HEAD 开。
  - 未合 → 照常开，但交付里写明"基于未含 #270 的版本"，并在 #270 合入后跑一次 `git merge` 确认 `bot_executor.py` / `bots.py` 无语义冲突。
- **不要碰 #270 的那批行**（compact 百分比、`service.py` 的 Pilot 端口记忆）。那不在本包范围。
- PR #270 的说明里明确写了它不碰前端选项胶囊那条链路（"避免与另一个 Agent 的 PR 重复或冲突"），所以 #270 **与 T5b 零重叠**，只和 T5a / T5c 抢 Python 文件。

### 2. T5a 和 T5c 抢同一批文件 —— 这就是 T5c 不能和 T5a 并行的原因

`bot_executor.py`、`bot_client.py`、`bots.py:worker()` 三处 T5a 和 T5c 都要动。T5a 先把"命令清单从 parser 生成"这条基础设施做掉之后，T5c 只需往 parser 加 `model list` / `model switch`，提示词自动就有。**T5c 必须从 T5a 完成后的 HEAD 开分支。**

T5a 那条门禁测试（遍历 parser 真实注册结果，断言每个子命令都出现在提示词清单里）在本包加了 `model` 之后会自动覆盖新命令。**不允许为了让它过而改它的断言逻辑**——那等于把 T5a 刚立的门拆了。

### 3. T5c 的前端接线与 `f8c21cb2` 撞在同一个函数体里

`f8c21cb2` 把 `submit(event)` 拆成了 `sendMessage(textToSend: string)`（`Bot.tsx` **1885-1933**）+ 一层薄 `submit(event)`（**1934-1937**）。

**本包要改的 `parseBotSettingCommand` 的调用点就在 `sendMessage` 里面**：`Bot.tsx` **1897-1906** 块，`onUpdateBot(bot.id, setting.patch)` 在 **1902** 行。同一个函数体里，`f8c21cb2` 还加了胶囊的 `onSelectOption={sendMessage}` 这条入口（挂载点 2409-2414 / 2484-2489），T5b 也要在 **1914** 行改定时提交。

**三个包都要碰 `sendMessage`。** 处理方式：

- T5c 只改 1897-1906 这一块（把捷径改成写 `pendingPresetId`、复用同一套匹配与文案），**不要动 1914 行的 `runAt` 分支**（那是 T5b 的）、**不要动胶囊的 `onSelectOption`**（那是 gemini 的）。
- 合并时按各自"只许改"清单逐行核对。
- **注意副作用**：胶囊点击直接调 `sendMessage`，所以用户点一个内容恰好是"换成 X"的胶囊，也会走 `parseBotSettingCommand`。本包改完捷径语义后，这条路径要一起验证（真实验证第 7 条覆盖了手打输入，**再补一条点胶囊的**）。

### 4. `parseBotSettingCommand` 本身的复核结果

- 位置 **1020-1034**（旧包写的 1019-1033 略有偏移）。
- **订正一个语义**：它**不调** `onUpdateBot`，只 `return { patch: { presetId: preset.id }, message: ... }`（**1031**）。调用在 1902 行。旧包写的"直接 `onUpdateBot`"要按这个理解。
- 归一化写法在 **1028** 行，逐字是 `.trim().replace(/[吧。！!]+$/, "").toLowerCase().replace(/[\s._:/-]+/g, "")`；匹配在 1029-1030 行，字段范围 `[item.id, item.name, item.modelId, item.channel]`，筛选 `item.harness === "pi" && item.available`。**后端的匹配函数要和这套完全一致**，本包要求两边共用同一套规则并有单测断言一致性。

### 5. `bot.modelName` 的既存 bug 与 `8fc1adf8` 的 `ModelPicker` 改动

- `bot.modelName` 恒为 undefined 这件事 2026-09-16 在 `77f2fd8a` 复核**仍然成立**（后端 `bot_executor.py:35` 返回 `model`，前端 `Bot.tsx:79` 声明 `modelName?`，渲染在 `Bot.tsx:794`）。本包照原计划改前端去对齐后端。
- `8fc1adf8` 重写了 `styles.css` 里 `.model-picker-trigger` 的几何（`width:100%`、flex、单 `span` + 省略号 + 不收缩的 `svg`）。`BotStudio.tsx` **263** 行用的就是这个 `ModelPicker`。本包要在它旁边显示"待生效模型"，**要按新的几何来排**，不要假设它还是原来的 `strong`/`small` 两行结构。

### 6. `mms_web_static/` 是提交进仓库的构建产物

`8fc1adf8` / `5be8649a` / `f8c21cb2` / `88114765` / `6d9001d6` 每一个都重写了 `mms_web_static/build.json`、`index.html` 和带 hash 的 asset 文件名。本包在 worktree 里 build 用于验证，**但不要 stage `mms_web_static/`**，否则 rebase 必然文本冲突。

## 已定的设计决策（不要改）

### 做成下一轮生效，不做 mid-round 切换

Bot 正在用那个模型思考，换掉它等于把执行者中途抽走。而 `bots.py:401` 那句 `BOT_BUSY` 文案——"模型将在本轮结束后才能切换"——已经定下了"本轮结束后生效"的语义，顺着它走最自然，也**不需要碰 `model_switch.py` 那套候选进程 / `DeferredSink` 逻辑**。

**明确禁止**：在 Bot 执行中调用会话级 `switch_model`（`POST /sessions/:id/model`）。那条路是给 Pilot 会话的，Bot 的 Pi 会话不走它。本包不改 `model_switch.py`、`session_actions.py`、`TaskSettings.tsx`。

实现形状：在 Bot 上加一个待生效字段（建议 `pendingPresetId`），下一轮 `_launch`（def 1551）取模型时消费它（`bots.py:1618-1619` 那个 `presetIdOverride` 分支的同一处，见下面的优先级），消费后清空并写一条 system 消息说明"本轮起使用 X"。

### 完成线（硬验收项，不是后续）

按 owner 的"要么做完要么不做"，下面每一条都要在本包里做完：

1. **Bot 要有切模型的 CLI 子命令**，并且能拿到当前通道里**实际可用**的模型列表——参考 `bot_executor.py` 的 `validate()` 是怎么从 `catalog.snapshot()` 里挑 `harness == "pi"` 且 `available` 的 preset 的。**不能让 Bot 凭印象写一个模型名。**
2. **请求的模型不可用时要有明确报错**，并且 Bot 要把这个情况**如实告诉用户**——不能静默忽略，不能假装换了。
3. **切换结果要在 UI 上看得见**：Bot 当前用的是哪个模型、下一轮会换成哪个。用户在对话里换完，界面不能还显示旧模型。
4. **口语模型名的匹配策略要定清楚边界**：允许对可用列表做名称匹配，**匹配不到就问用户，不要猜**。
5. **和 `presetIdOverride` 的交互要写明**（见下面"与 presetIdOverride 的优先级"）。

## 要做成什么

### 1. 两条命令：先看再换

在 `bot_client.py` 的 parser 里加（T5a 之后，提示词会自动带上这两条）：

```
model list                      # 列出当前通道里实际可用的 Pi 模型
model switch <query...>         # 把 Bot 的默认模型换成匹配到的那个，下一轮生效
```

对应 `bots.py` 的 `worker()`（1856-1919）新增 `action == "model"` 分支，按 `payload["op"]` 走 `list` / `switch`，照现有 `action == "status"` 那段（**1897**）的 scope 检查写法，只允许操作 `task["botId"]` 自己。兜底分支 `BOT_ACTION_UNKNOWN` 在 1919 行，新分支要插在它之前。

**`model list` 的数据来源必须是 catalog 的真值**，不是 Bot 自己的记忆、不是硬编码名单：

```python
catalog = self.executor.catalog.snapshot()
[p for p in catalog.get("presets", []) if p.get("harness") == "pi" and p.get("available")]
```

返回每条的 `id` / `name` / `channel`，并标出哪一条是当前 Bot 在用的、哪一条是待生效的。`bot_executor.py` 里已经有这套筛选逻辑（`validate()` 23-35 行），**抽一个 `available_presets(catalog)` 纯函数出来给两边共用**，不要复制粘贴第二份筛选条件。

### 2. 匹配策略：匹配不到就问，不要猜

用户说的是"用 Claude"、"换个便宜的"、"用那个思考深一点的"。定死边界：

- **只在 `model list` 返回的那批可用 preset 上做名称匹配**，字段范围是 `id` / `name` / `modelId` / `channel`。可以借用前端 `parseBotSettingCommand`（`Bot.tsx` **1028**）已有的归一化写法，逐字是：
  ```js
  const query = model[1].trim().replace(/[吧。！!]+$/, "").toLowerCase().replace(/[\s._:/-]+/g, "");
  ```
  匹配在 1029-1030 行，字段范围是 `[item.id, item.name, item.modelId, item.channel]`，筛选条件是 `item.harness === "pi" && item.available`。后端要和这套规则一致。
- **恰好匹配到 1 条**：换。
- **匹配到多条**：**不要挑第一个**。返回候选列表，让 Bot 用 `wait` 把选项给用户（`wait` 支持"选项：A | B"，最多 4 个——`bot_client.py` 196-197 行注册 `--option`，上限由 `bots.py:142` 的 `MAX_WAIT_OPTIONS = 4` 在服务端强制）。
- **匹配到 0 条**：报错，错误里带上可用列表的名字，Bot 照实转述。**不要做模糊猜测、不要做语义打分、不要接第二个模型来判断"哪个更便宜"**——这一轮不做能力/价格语义匹配，"换个便宜的"这类说法就走"匹配不到 → 列出可选项让用户挑"。
- 错误码建议：`BOT_MODEL_NOT_FOUND`（404，"没有找到匹配的可用模型。"）、`BOT_MODEL_AMBIGUOUS`（409，"有多个模型匹配，请说得更具体。"）、`BOT_MODEL_UNAVAILABLE`（409，"这个模型当前不可用。"）。照 `WebError(code, 中文句子, http)` 的现有风格。

### 3. 下一轮生效

- `model switch` 在 Bot 上写 `pendingPresetId`，**不动 `presetId`**（因为 `update_bot` 会 `bot.update(self.executor.validate(bot))` 立刻覆盖并让当前视图变，那就变成"看起来换了但这一轮没换"）。
- 同时立刻返回给 Bot 一句明确的结果："已记录，下一轮起使用 `<name> · <channel>`；本轮仍是 `<当前 name>`。" Bot 要把这句如实转述给用户。
- 下一轮 `_launch`（def 1551）取模型时消费 `pendingPresetId`（`bots.py` **1618-1619** 行，和 `presetIdOverride` 同一处），消费后把 `presetId` 正式落成它、清空 `pendingPresetId`、写一条 system 消息。
- **不要绕过 `executor.validate()`**：消费时仍然校验一次，模型在这期间变得不可用要走现有 `BOT_MODEL_REQUIRED` 路径，不要静默回退到默认模型。

### 4. 与 `presetIdOverride` 的优先级

子任务级分模型的机制已经存在（`bots.py` **1170-1171** 写入、**1618-1619** 消费）：计划步骤带 `presetId` → 子 task 的 `presetIdOverride` → 启动时覆盖 Bot 的模型。**新功能不要和它打架。**

定死优先级，**从高到低**：

1. `task["presetIdOverride"]` —— 计划明确为这一步指定的模型。**最高**，因为那是计划作者对这一步的具体安排，不该被 Bot 级的默认切换覆盖。
2. `bot["pendingPresetId"]` —— 用户在对话里刚换的，下一轮生效。
3. `bot["presetId"]` —— Bot 的默认模型。

并且：

- **带 `presetIdOverride` 的任务里，`model switch` 仍然可以调用**，但它改的是 Bot 的默认模型（第 2 档），**不影响当前这个被计划指定的子任务**。返回语里必须说清楚这一点："这一轮是计划指定的 `<override name>`，你的切换从下一个没有被计划指定模型的任务开始生效。" 不说清楚，用户会以为没生效。
- `pendingPresetId` **不因为一个带 override 的任务跑完就被消费掉**——只有实际用上它的那一轮才清空。否则用户的切换会被一个无关的计划子任务吃掉。
- 这条优先级要在 `bots.py` **1618-1619** 那一处用一段短注释写死，并有测试覆盖三档的组合。

### 5. UI 上看得见

范围控制在最小接线，不要顺手重构面板：

- Bot 头部 / 编辑器里显示**当前模型**和**待生效模型**。已有的显示位是 `BotStudio.tsx:261-274` 的下拉和 `Bot.tsx` **794** 行的 `{bot.modelName ? ` · ${bot.modelName}` : ""}`（在 `BotDispatchForm` 里）。
- **注意 `Bot.tsx` 794 行的 `bot.modelName` 目前恒为 undefined**：后端 `validate()` 返回的字段叫 `model`（`bot_executor.py:35`），前端 `BotDefinition` 声明的是 `modelName?`（`Bot.tsx` **79**），两边对不上，所以那个 `· 模型名` 从来没显示过（2026-09-16 在 `77f2fd8a` 复核仍然如此）。本包顺手对齐（**改前端的字段名去对齐后端的 `model`**，不要改后端字段名——那会动到 `worker()` 的 `list` 返回和其它读取点）。
- 有 `pendingPresetId` 时显示成"当前 X · 下一轮 Y"，用现有 token 和 class，**不要新增颜色字面量**（`apps/mms-web/src/bot*.css` 的 hex 去重计数**必须仍是 12**——2026-09-16 在 `77f2fd8a` 实测就是 12）。
- **`parseBotSettingCommand` 的前端捷径要处理，不能留成第二条并行路径。** 它现在拦住"把模型改成 X"返回一个 `{patch:{presetId}}`，由 `Bot.tsx` **1902** 行（`sendMessage` 内）调 `onUpdateBot`，消息从不发给 Bot，且走的是 `update_bot` → 执行中直接 `BOT_BUSY` 报错（不是"下一轮生效"）。本包默认做法：**保留这条捷径作为快速路径，但让它改成写 `pendingPresetId`、复用同一套匹配函数和同一套文案**，这样两条入口语义一致。匹配不到时它现在返回的"我没找到…你可以说得更具体一点"要改成列出可用模型。**不允许留下两套不同语义的切模型路径。**

## 只许改 / 不许改

**只许改**：

- `mms_web/bot_client.py`：新增 `model list` / `model switch` 子命令与 payload 翻译
- `mms_web/bots.py`：`worker()`（1856-1919）新增 `action == "model"` 分支（≤ 25 行）、`_launch`（1618-1619）取模型那处的优先级（≤ 10 行）、Bot 实体加 `pendingPresetId` 字段（`create_bot` 343-382 / `update_bot` 396 / `_load` 的 `setdefault` 各 1 行）
- `mms_web/bot_executor.py`：抽出 `available_presets(catalog)` 纯函数供两边共用；**提示词不需要手写改动**（T5a 之后命令清单自动生成），但如果需要补一句行为性指示（例如"用户要求换模型时先 `model list` 再 `model switch`，匹配不到就问用户"），那句是手写的，写在行为性指示那一段
- 新增 `tests/test_mms_bot_model_switch.py`
- `tests/test_mms_web_bots.py`、`tests/test_mms_bot_client.py`、`tests/test_mms_bot_transport.py`：补断言
- `apps/mms-web/src/Bot.tsx`：`BotDefinition` 字段对齐、`parseBotSettingCommand` 改写、头部显示
- `apps/mms-web/src/BotStudio.tsx`：模型下拉旁边显示待生效模型（最小接线）
- `apps/mms-web/src/bot.css`：hex 保持 12
- `apps/mms-web/tests/`：`parseBotSettingCommand` 的匹配单测
- `docs/mms-web/BOTS.md`：追加一节说明对话换模型的契约和"下一轮生效"语义

**不许改**：

- `mms_web/model_switch.py`、`mms_web/session_actions.py`、`apps/mms-web/src/TaskSettings.tsx`、`apps/mms-web/src/QuickModelMenu.tsx`（会话级切模型是另一条路，本包不碰）
- `mms_web/bot_schedules.py`、`mms_web/bot_coordinator.py`、`mms_web/bot_memory.py`、`mms_web/bot_communications.py`、`mms_web/bot_notify.py`、`mms_web/bot_retry.py`
- `BotCommunications.tsx`、`BotPlan.tsx`、`BotMemoryPanel.tsx`、`BotPresetPanel.tsx`、T5b 正在动的 `BotSchedulePanel.tsx` / `bot-schedules.ts` / `bot-visual-system.ts`
- 受保护文件：`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`
- 真实 `~/.config/mms*`（测试和验证用临时 state-root）
- 不加依赖
- **不要重启 60824，不要动 8767**（owner 在用的实例）；自己另起端口

## 测试要求

1. **可用模型列表来源**：`model list` 只返回 `harness == "pi"` 且 `available` 的 preset；catalog 里混入 `harness != "pi"` 和 `available: false` 的条目，断言它们不出现。
2. **标注当前与待生效**：列表里当前 Bot 在用的那条和 `pendingPresetId` 那条各有标记。
3. **匹配恰好 1 条** → 换成功，返回文案含新旧两个模型名。
4. **匹配多条** → 报 `BOT_MODEL_AMBIGUOUS`，错误里带候选，**没有静默挑第一个**。
5. **匹配 0 条** → 报 `BOT_MODEL_NOT_FOUND`，错误里带可用列表。
6. **不可用** → 显式指定一个存在但 `available: false` 的 preset id，报 `BOT_MODEL_UNAVAILABLE`，**不静默回退默认模型**。
7. **切换在下一轮生效而非当前轮**：调用 `model switch` 后，当前 task 的实际启动 preset 不变；下一个 task 启动时才用新的。
8. **执行中不走会话级 switch**：断言 `model_switch.switch_model` 在整条路径上没有被调用（mock / spy）。
9. **消费后清空**：下一轮用掉 `pendingPresetId` 后它被清空、`presetId` 落成新值、有一条 system 消息。
10. **与 `presetIdOverride` 的优先级**：三档组合各一条——只有 `presetId`、`presetId + pendingPresetId`、`presetId + pendingPresetId + presetIdOverride`，断言实际启动用的是预期那个。
11. **`pendingPresetId` 不被带 override 的任务吃掉**：一个带 override 的任务跑完后，`pendingPresetId` 仍在。
12. **越界**：A Bot 的 worker 不能改 B Bot 的模型。
13. **CLI 翻译**（`tests/test_mms_bot_client.py`）：`model list` / `model switch <query>` 的 argv → payload。
14. **提示词**（`tests/test_mms_bot_transport.py`）：T5a 那条门禁测试（parser 的每个子命令都出现在提示词清单里）在加了 `model` 之后仍然过——**这就是 T5a 那条测试存在的意义，不要为了让它过而去改它的断言逻辑**。
15. **前端**：`parseBotSettingCommand` 的匹配单测（命中 / 多候选 / 未命中），断言它和后端用同一套归一化规则。

**基线（2026-09-16 在 `origin/dev-pre` = `77f2fd8a` = 5.0.1 实测，T5a 之后会更高，以 T5a 交付里的数字为准）**：

```
PYTHONPATH=. python3 -m pytest -q \
  tests/test_mms_web_bots.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py \
  tests/test_mms_bot_client.py tests/test_mms_bot_computer.py tests/test_bot_memory.py \
  tests/test_mms_bot_coordinator.py tests/test_mms_bot_notify.py tests/test_mms_bot_retry.py
# -> 202 passed
```

`node --test apps/mms-web/tests/*.test.mjs` → **121 pass / 0 fail**；`npx tsc --noEmit -p apps/mms-web` → 0；hex → 12。这几个数字都只增不减。

**旧包写的 203 / 114 已过期**：203 从来就不对（同一批测试文件在 `66b7fc16` 和 `77f2fd8a` 上逐字节相同，两处重测都是 202）；114 是 gemini 新增三个测试文件之前的数。

## 门禁

```bash
# 1. 定向 pytest（上面那一组 + T5a 的 tests/test_mms_bot_schedules.py + 你新增的 tests/test_mms_bot_model_switch.py）
PYTHONPATH=. python3 -m pytest -q \
  tests/test_mms_web_bots.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py \
  tests/test_mms_bot_client.py tests/test_mms_bot_computer.py tests/test_bot_memory.py \
  tests/test_mms_bot_coordinator.py tests/test_mms_bot_notify.py tests/test_mms_bot_retry.py \
  tests/test_mms_bot_schedules.py tests/test_mms_bot_model_switch.py

# 2. 语法
python3 -m py_compile mms_web/bots.py mms_web/bot_client.py mms_web/bot_executor.py

# 3. 前端
npx tsc --noEmit -p apps/mms-web
node --test apps/mms-web/tests/*.test.mjs
grep -ohE '#[0-9a-fA-F]{3,8}\b' apps/mms-web/src/bot*.css | sort -u | wc -l   # 必须是 12
npm run build --workspace @mms/web

# 4. 回归对比（base 用 T5a 的 HEAD）
python3 scripts/ci_pytest_regression.py --base bot/T5a-schedule-backend

# 5. 新用户 gate
python3 scripts/regression_fresh_user_gate.py
```

第 4、5 条的实际结果要写进交付。gate 在这台机器上本来就有既存失败项，**用 diff 判断，不看绝对值**。

## 真实验证（不是可选项）

自己的 worktree + 自己的端口，**不要碰 60824，也不要碰 8767**（owner 在用）：

```bash
cd .worktrees/wt-T5c
npm install
npm run build --workspace @mms/web
PYTHONPATH=$PWD python3 -P -m mms_web --port 61753 \
  --state-root /tmp/bot-verify-t5c \
  --config-root ~/.config/mms-next \
  --static-root $PWD/apps/mms-web/dist
```

要实际跑通并留证据（截图 / curl 输出放 `docs/mms-web/design/t5c/`）：

1. 在对话里问 Bot"你现在用的是什么模型，能换吗"，它应当回答能，并说得出可用列表。**不是回答"我没有切换模型的能力"。** 这是本次要修的核心症状，截图留证。
2. 在对话里说"换成 <某个真实可用模型>"，Bot 执行 `model switch`，回复里说清"下一轮起使用 X，本轮仍是 Y"。截图。
3. 界面上看到"当前 Y · 下一轮 X"。截图。
4. 再发一条任务，实际启动用的是 X（看 Pilot 会话的模型名 / `GET /api/v1/bots` 的 `model`），界面不再显示旧模型。截图。
5. 说一个不存在的模型名，Bot **如实告诉用户没找到**并列出可选项，**没有假装换了**。截图。
6. 说一个能匹配多条的模糊词，Bot 用 `wait` 把候选给用户选，不是自己挑一个。截图。
7. 前端捷径路径：直接在输入框里打"把模型改成 X"，走 `parseBotSettingCommand`，语义与第 2 条一致（下一轮生效，不是 `BOT_BUSY` 报错）。截图。
8. 计划派下来的带 `presetIdOverride` 的子任务里调用 `model switch`：当前子任务仍用计划指定的模型，Bot 的回复说清了这一点，`pendingPresetId` 没被吃掉，下一个普通任务才生效。截图 + 接口返回。

## 交付格式

照 README 的通用验收，写进 worktree 的 `walls.md`（追加，不改旧条目）：

```
包：T5c
分支 / worktree：（从 bot/T5a-schedule-backend 开）
改动文件：git diff --stat 输出
bots.py 实际改动行数：worker +N / _launch 优先级 +N / Bot 实体字段 +N
测试：命令 + 通过数（对比 T5a 交付里的数字）
门禁：ci_pytest_regression 结果、fresh-user gate 结果（与既存失败集的 diff）、tsc / node --test / hex / build
真实验证：端口、上面 8 条逐条结果、证据路径
未完成 / 未验证：逐条
需要 Fable 确认：逐条
```

**不提交、不 push、不 merge。** T5a / T5b / T5c 都验收完才一起合进 base 分支，**后端不单独落地。**

## 需要 Fable 确认

下面是写包时对照现有代码发现的、设计里没覆盖或与现状有张力的点。**不要自己改设计**；按包里给出的默认做法实现，同时把你的实际处置写回交付里。

1. **"下一轮生效"和现有 `BOT_BUSY` 的语义其实不一样。** `bots.py:401` 那句文案是"模型将在本轮结束后才能切换"——它读起来像"稍后可以切"，但代码行为是**直接拒绝请求**（`raise WebError(..., 409)`），不是"记下来下一轮用"。设计说"顺着 BOT_BUSY 的语义走"，本包把它实现成**延后生效**（新增 `pendingPresetId`，请求被接受而不是被拒），因为 Bot 的 `model switch` 只能在一轮执行期间调用（`authorize_worker` 要求 task 处于 `starting`/`running`/`waiting`），如果沿用"直接拒绝"，Bot 这条命令就永远不可能成功。同时这意味着 `update_bot` 的 `BOT_BUSY` 分支要么保持原样（对话路径走新字段，绕开它），要么一并改成延后。本包默认**保持 `update_bot` 的 `BOT_BUSY` 原样不动**，只让新路径走 `pendingPresetId`——请确认这不算"两套语义"。
2. **前端已经存在一条"在对话里换模型"的捷径，设计里没提。** `Bot.tsx` **1020-1034** 的 `parseBotSettingCommand` 用正则（1025-1026）拦住"把模型改成 X"/"换成 X"，返回 `{patch:{presetId}}`，由 **1902** 行（`sendMessage` 内）调 `onUpdateBot(bot.id, setting.patch)`，**消息从不发给 Bot**，Bot 也永远不知道用户换过模型。本包默认把它改成写 `pendingPresetId` 并复用同一套匹配与文案，不留第二条语义。另一个选项是彻底删掉这条捷径、让所有换模型都经过 Bot（语义最干净，但用户少了一条不消耗模型额度的快路径）。请确认取哪个。
3. **`bot.modelName` 前后端字段名对不上（既存 bug，2026-09-16 复核仍在）。** 后端 `validate()` 返回 `{"model", "channel", "presetId"}`（`bot_executor.py:35`），前端 `BotDefinition` 声明的是 `modelName?: string`（`Bot.tsx` **79**），所以 `Bot.tsx` **794** 行的 `· 模型名` 从来没显示过。本包默认**改前端去对齐后端的 `model`**。
4. **"换个便宜的"这类语义诉求本包不做。** 设计要求"匹配不到就问用户，不要猜"，本包据此把范围收成纯名称匹配：能力/价格/速度的语义匹配（需要模型元数据或第二个模型来判断）**不在本包范围**，"换个便宜的"会走"匹配不到 → 列出可选项让用户挑"。如果 owner 期望的是真的能听懂"便宜的"，那是另一个包。
5. **`model switch` 之后 Bot 需要主动告诉用户，但这依赖 Bot 照做。** 命令返回值里会带明确的中文结果句，提示词里也会有行为性指示要求如实转述，但最终是否说出口由模型决定。硬保证的做法是在 `worker()` 里同时写一条 system 消息到当前 task（用户在界面上一定看得见），本包默认**两条都做**（返回值 + system 消息），这样即使模型没转述，界面也有记录。
6. **优先级第 1 档（`presetIdOverride` 高于 `pendingPresetId`）是本包定的。** 设计只说"要写明"，没说谁高。本包的理由写在上面"与 presetIdOverride 的优先级"里：计划对某一步的具体安排不该被 Bot 级默认切换覆盖。如果 owner 认为用户刚说的话应该最大，需要反过来——请确认。
7. **T5a 的门禁测试会因为本包新增子命令而变严。** T5a 那条"parser 的每个子命令都出现在提示词清单里"的测试，在本包加了 `model` 之后会自动覆盖新命令。**不允许为了让它过而改它的断言逻辑**——那等于把 T5a 刚立的门拆了。这条已写进测试要求第 14 条，这里再点一次。
8. **`available_presets(catalog)` 抽函数会动到 `bot_executor.validate()`。** `validate()` 是 Bot 创建、更新、每次启动都会走的路径（`bots.py` 里多处调用），抽函数属于行为等价重构但落在热路径上。本包要求**只抽筛选条件、不改 `validate()` 的返回形状和错误码**，并靠现有 `tests/test_mms_bot_runtime.py` / `tests/test_mms_web_bots.py` 兜底。如果实现时发现无法做到行为等价，就不要抽，改成两处各自保留但加注释互指——请在交付里说明实际做法。
