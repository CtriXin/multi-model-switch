# T5d — 让「计划里给某一步指定模型」真的生效

**base**:`dev`,**在 T5a(#278)/ T5b(#302)/ T5c 都落地之后**。不要提前开工,理由见最后一节。

**严重度**:P1。一个已经上线的能力在静默失效,而且失效形态正是 `docs/AGENT_GUARDRAILS.md` 反例第一条点名要避免的:**界面里选中了某个模型,但实际启动时用了另一个**。

---

## 症状

T2 的计划能力里,一个 step 可以带 `presetId`,意思是"这一步用这个模型跑"。它落成子 task 的 `presetIdOverride`(`mms_web/bots.py:1269`),启动时覆盖 Bot 的模型(`bots.py:1761-1762`)。

**这个覆盖对任何跑过一次任务的 Bot 都不生效,而且没有任何报错。**

实测(fake executor 忠实镜像真实 `start()` 的分支):

```
{"task": "…", "requested": "pi:alpha", "EFFECTIVE": "pi:beta", "reusedSession": true}
```

计划要求 `pi:alpha`,实际跑的是 `pi:beta` —— Bot 的默认模型。

用户看到什么:那一步用默认模型跑完了,`task.model` 显示的是旧模型名(来自被复用 session 的真实 `modelName`),所以是"计划里写的和实际跑的不一致",而且界面上没有任何线索说明为什么。

---

## 根因

`mms_web/bot_executor.py` 的 `start()`,`:159` 起:

```python
session_id = bot.get("sessionId")
before = 0
baseline = {}
if session_id:
    detail = self.sessions.get_session(session_id)
    ...
    detail = self.sessions.send(session_id, {"requestId": task["launchRequestId"], "text": prompt})
else:
    detail = self._launch_bot_session({
        "requestId": task["launchRequestId"], "workspaceId": bot.get("workspaceId") or "default",
        "presetId": selected["presetId"], "title": bot["name"], "prompt": prompt,
    }, bot["id"])
    session_id = detail["session"]["id"]
```

`selected["presetId"]`(也就是 `validate()` 算出来的那个模型)**只在 else 分支被使用**。复用已有 session 时,它被整个丢弃 —— 连检查都没有。

而 `_launch` 的 override 分支只做:

```python
if task.get("presetIdOverride"):
    bot = {**bot, "presetId": task["presetIdOverride"]}
```

不重置 `sessionId`。`bot["sessionId"]` 只在三处被清空:create(`:372`)、`update_bot` 改 preset/workspace(`:448`)、T5c 新增的 pending 消费。所以**只要这个 Bot 此前跑过任何一个任务,`sessionId` 就必定非空**,override 必定被忽略。只有"从未启动过的全新 Bot"能踩中它生效。

对比:T5c 的 `pendingPresetId` 路径踩到了同一个坑,作者真机发现后在消费时加了 `sessionId = None`,所以那条路是通的。**override 这条没人管。**

---

## 要做的事

### 1. 根本的那道防御(核心要求)

`bot_executor.start()` 在复用 session 时**不能静默丢掉算好的 preset**。加一道:被复用的 session 的实际 preset 和 `selected["presetId"]` 不一致时,必须做点什么,不能装作没这回事。

这条比修 override 本身更重要 —— 它让**将来任何**"临时换模型跑一个任务"的路径都不会再静默失效。现在这个洞是敞开的,T5c 的作者是靠真机跑出来才发现的,不该指望下一个人也这么走运。

实现上你需要先回答:**被复用 session 的实际 preset 从哪里读?** 可能的来源:`sessions.get_session(session_id)` 返回的 `session` 里有没有 preset / modelName;或者 Bot 上要记一个"当前 session 是用哪个 preset 起的"。选哪条、为什么,写清楚。

### 2. override 的子任务跑在自己的会话里 —— 这是我的裁决

**不要**照抄 pending 那几行。pending 的语义是"从下一轮起换默认模型",所以它把 `presetId` 落成新值、重置 session 是对的。override 不是 —— 它只作用于**这一个子任务**。

如果照抄:override 子任务前重置一次 session、跑完之后 `bot["sessionId"]` 指向的是一个跑着 override 模型的会话,下一个普通任务会复用它 → 又错了,而且方向反过来。要修就得前后各扔一次会话,把 Bot 的主对话历史切得碎碎的。

**改成:override 的子任务用它自己的一次性会话,不占 `bot["sessionId"]`。**

结构上是通的,`task["sessionId"]` 这个字段**已经存在**:
- `bots.py:542` 初始化成 `None`
- `bots.py:964`、`:1551` 用 `task.get("sessionId")` 做轮询筛选
- `bots.py:1928` artifacts 记的就是 `task["sessionId"]`
- 而 `bots.py:1784` 是把 launch 结果**回写到 bot** 的那一处:`self._bot(bot["id"])["sessionId"] = outcome["sessionId"]`

所以形状是:override 子任务启动时强制新会话(传给 executor 的 `bot` 里 `sessionId` 为 None),launch 成功后**只写 `task["sessionId"]`,不回写 `bot["sessionId"]`**。

裁决理由:
- **不同模型之间本来就不该共享 session。** 一个会话的历史是在某个模型上长出来的,换模型继续用它在语义上就是错的 —— 这也是为什么 `update_bot` 换 preset 时要清 session(`:448`)。
- **Bot 的主对话历史不该被计划的子步骤切碎。** 用户和 Bot 的连续对话是主线,计划子任务是旁支。
- **代价可接受**:override 子任务拿不到 Bot 主会话的对话历史。但它是计划里的一个独立步骤,本来就有自己的 `prompt`、`memoryContext`、`mailboxContext`、`resumeText` —— 该带的上下文都带了。而且它既然被指定了另一个模型,说明计划作者本来就把它当成一个独立的活。

**你需要先回答这四个问题再动手:**

1. `_maybe_compact(session_id, bot, task)` 现在只在复用分支里调。override 子任务每次都是新会话,压缩逻辑要不要跟着调整,还是本来就不适用?
2. artifacts:`bots.py:1928` 记的是 `task["sessionId"]`,所以子任务产出的 artifact 应该能正常取到。核实一遍,别想当然。
3. 轮询:`:964` 和 `:1551` 靠 `task.get("sessionId")` 筛,子任务有自己的 session id 之后这两处会不会漏掉或重复。
4. 一次性会话跑完之后怎么收尾 —— 会不会在 Pilot 的会话列表里留一堆孤儿?`executor.plan()` 那边已经有"跑完就 stop + archive"的先例(`bot_executor.py` 里 `plan()` 的注释),看能不能沿用同一套。

如果这四个里有任何一个让方案 B 走不通,**停下来说明,不要自己改成方案 A**。

### 3. 把 T5c 那条 characterization test 转正

T5c 返工时会留下一条如实记录当前(坏)行为的测试,名字大概是:

```
test_preset_override_is_chosen_but_a_reused_session_still_runs_the_old_model
```

它断言 override 那一轮 `hadSession is True`、effective 是旧 preset,并且注释里写明"修好之后这条会变红,那时候应该更新它,而不是当成回归"。

**你就是那个"修好之后"。** 这条测试必须改名 + 改断言,变成 override 真生效的正向测试:effective preset == override 值,`pendingPresetId` 仍然没被消费。

注意 T5c 那份 fake executor 已经被改成忠实的(会按 `bot.get("sessionId")` 分叉),所以你不需要再动它 —— 但要确认它对"task 有自己的 session"这个新形状仍然成立,不成立就跟着改。

---

## 真机验证

T5c 交付里那次 override 实验是无效的:证据 `docs/mms-web/design/t5c/14-override-done-pending-kept.json` 里 override 值和 Bot 当时的 `presetId` **恰好都是 `glm-5.3`**,那个实验在原理上区分不了"override 生效"和"override 被忽略、用了默认值"。

所以这次必须:

1. **override 值 ≠ Bot 当前 `presetId`**,而且两个模型的名字在 `task.model` 里肉眼可辨(比如一个 glm、一个 qwen)
2. **Bot 必须先跑过至少一个普通任务**(让 `sessionId` 非空),否则踩不到这个 bug
3. 造一个带 `presetId` 的计划步骤,让它派下子任务,证明:
   - 子任务实际跑的是 override 指定的模型(看 `task.model`,以及模型自己的自述)
   - Bot 的主会话没被换掉 —— override 子任务结束后,下一个普通任务仍然用 Bot 的默认模型,**而且能接上之前的对话历史**
   - `pendingPresetId`(如果当时有)没被吃掉
4. 修复之前先在 base 上复现一次,把"计划要 A、实际跑 B"这个错拍下来。**没有复现证据的修复不收。**

---

## 门禁

- 定向 pytest:bot 相关全部 + `test_mms_web_bots.py` / `test_mms_bot_schedules.py` / `test_mms_bot_client.py` / `test_mms_bot_transport.py` / `test_mms_bot_model_switch.py`,写 base/head 绝对数
- `npx tsc --noEmit -p apps/mms-web`
- `node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带**)
- `python3 scripts/ci_pytest_regression.py --base origin/dev`
- `python3 scripts/regression_fresh_user_gate.py`(完整,不加 `--quick`)。跑前 `env -u MMS_CONFIG_ROOT -u REAL_HOME -u ORIGINAL_HOME -u MMS_REAL_HOME -u XDG_CONFIG_HOME`。这个 gate 对并发敏感:`test_install_script_paths.py::test_installer_does_not_reuse_another_homes_web_instance` 会比对端口和 PID,并行跑会假失败;串行跑一次,红了单独复跑确认并如实写明
- mutation 必做:
  1. 把第 1 条那道防御删掉 → 必须红
  2. 把 override 的新会话逻辑删掉(退回原样)→ 必须红,而且红的是"effective preset"那条断言而不是别的
  3. 把"不回写 `bot['sessionId']`"改成回写 → 必须红(证明 Bot 主会话不被污染这件事被锁住了)

---

## 为什么必须等 T5a / T5b / T5c 落地

1. **base 会变。** T5c 动了 `bots.py` 的 `_launch`(pending 消费分支就在 override 分支旁边)、`bot_executor.py`(抽了 `available_presets` / `match_presets`)。在 T5c 之前的 base 上改,合并时必撞。
2. **那条 characterization test 是你的起点。** T5c 返工会把它建起来,你要在它的基础上转正。提前开工就没有这个起点。
3. 这不是紧急修复。这个 bug 已经在 dev 上待了一段时间,而且只影响"计划步骤分模型"这一条路径(计划本身默认是 `direct-first`,`delegate` 模式还要用户批准),不影响日常使用。按顺序来。

---

## 边界

- **不要**动 `presetIdOverride` 的写入端(`bots.py:1269`,计划步骤落成子任务那处)。写入是对的,坏的是消费。
- **不要**顺手改 `bot_coordinator.py` 的 plan 结构或 step schema。
- **不要**碰 `docs/AGENT_GUARDRAILS.md` 里列的保护文件。`mms_web/bots.py` 和 `mms_web/bot_executor.py` 不在保护列表,可以改,但按 guardrails 的要求:先说改动边界,再动手;交付里写清"用户选择的数据从哪里来、如何传递、在哪里生效"。
- 真机验证:端口用 61000-62000 的随机值,**绝不碰 8767 / 60824 / 8765 / 8766**(机主自己的 Pilot);绝不用 `pkill`,只 kill 自己启动的 PID;绝不写真实 `~/.config/mms*`。
