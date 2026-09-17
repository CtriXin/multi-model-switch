# T5c 返工 01 — 合并前必须清掉的五条

**基线**:`bot/T5c-model-switch-dialogue` 的当前未提交状态(worktree `.worktrees/wt-T5c`,base `bot/T5a-schedule-backend` = `e3e0d4ff`)。行号按这份未提交的树,已逐条复核。

**先说结论**:主功能验收通过。用户在 Bot 聊天框里说"换成 glm-5.3",能得到可预期、可见、下一轮真生效的结果;三种分支(恰好一条 / 多候选 / 找不到)都被 mutation 证明有测试锁住。你第一轮真机验证时自己挖出"持久 Pi session 复用导致 `task.model` 仍是旧模型",修了,还用 `hadSession is False` 把它锁进测试 —— 我删掉那两处 `sessionId = None`,测试立刻红。这是这批包里第一次做到"修了并且锁住了",记一笔。

下面五条是合并前的阻塞项。**第 4 条反转了你在 walls.md 里的确认项 3**,理由写在那一条里。

**不要做的事**:不要修 `presetIdOverride` 的 session 复用 bug。它是真 bug(见第 1 条),但属于 T2 计划链路的既有代码,修法和 pending 不同,我会另立一个包。你在 walls.md 里披露它、并按"不许改"没动它 —— 这个处置是对的,保持。

---

## 1. 那条为已损坏行为签发合格证的测试(必修)

### 问题

`tests/test_mms_bot_model_switch.py:275` 的 `test_preset_override_outranks_pending_and_does_not_consume_it`,第 285 行:

```python
assert executor.starts[-1]["presetId"] == "pi:gamma-pro"
```

这条断言报绿,但生产里 override **不生效**。

根因在你的 fake:`CatalogExecutor.start()`(`:60`)记录的是 `self.validate(bot)` 算出来的**请求值**。真实的 `PiBotExecutor.start()`(`mms_web/bot_executor.py:159-183`)不是这样:

```python
session_id = bot.get("sessionId")
if session_id:
    ...
    detail = self.sessions.send(session_id, {...})   # selected["presetId"] 被整个丢弃
else:
    detail = self._launch_bot_session({
        ..., "presetId": selected["presetId"], ...   # 只有这条分支用得上
    }, bot["id"])
```

`selected["presetId"]` **只在新建 session 那条分支被使用**。`_launch` 的 override 分支(`mms_web/bots.py:1761-1762`)只做 `bot = {**bot, "presetId": task["presetIdOverride"]}`,不重置 `sessionId`。而 `sessionId` 只在三处被清空:create(`:372`)、`update_bot` 改 preset/workspace(`:448`)、本包新增的 pending 消费(`:1770-1771`)。所以**只要这个 Bot 此前跑过任何一个任务,`sessionId` 就必定非空**,override 必定被忽略。

你的 fake 抹掉了这个分叉,所以测试和生产说的不是一件事。假绿比没有测试更坏:下一个人会信它。

### 期望

**a. fake 改成忠实。** `CatalogExecutor.start()` 按真实语义分叉:`bot.get("sessionId")` 非空时,effective preset 是**被复用的那个 session 当初启动时的 preset**,不是 `selected["presetId"]`;为空时才是 `selected["presetId"]`。同时记录 `hadSession`,和你已有的那条断言保持同一套字段。

**b. 那条测试改成如实记录当前行为**,并改名让名字自己说真话,例如:

```
test_preset_override_is_chosen_but_a_reused_session_still_runs_the_old_model
```

保留的断言:
- override 档**没有消费** `pendingPresetId`(`bot["pendingPresetId"] == "pi:beta"`、`bot["presetId"] == "pi:alpha"`)—— 这是 T5c 真实交付的契约,包文档 202 行要求的就是这半边
- 下一个普通任务才消费 pending,effective 是 `pi:beta`,新 session

改掉的断言:不要再声称 override 那一轮实际跑的是 `pi:gamma-pro`。如实断言它**复用了 session**(`hadSession is True`)、effective 仍是旧 preset。

测试体里写一段注释说明:这是已知缺陷的 characterization test,`presetIdOverride` 的真实生效需要重置 session,已另立包;**修好之后这条测试会变红,那时候应该更新它,而不是当成回归。**

### 验证

- 改完 fake、还没改断言时,原断言必须变红,红的正是 override 那一轮 —— 这证明 fake 现在忠实了
- 改完断言后 `python3 -m pytest tests/test_mms_bot_model_switch.py -q` 全绿
- 你已有的 `test_pending_...` 那条(靠 `hadSession is False` 锁住 pending 档)不受影响,仍必须绿

---

## 2. 新增的那行 UI 可以整块删光而测试全绿(必修)

### 问题

`apps/mms-web/src/Bot.tsx:2051-2058`:

```tsx
{bot && (bot.model || bot.pendingPresetId) && (
  <p className="bot-chat-model-line" title="当前模型与下一轮待生效模型">
    ...
  </p>
)}
```

把这整块删掉,`node --test apps/mms-web/tests/*.test.mjs` 仍然 129/129 全过,`tsc` 0 错。

`apps/mms-web/tests/bot-model-switch.test.mjs` 只测 `bot-model-switch.ts` 的三个导出纯函数,既不渲染 `BotChat`,也不读 `Bot.tsx` 的源码。所以"下一轮 X 显示在头部"这个用户可见的交付物,没有任何东西看守它。

**这是这批 PR 第三次栽在同一个地方**(#281、#286 各一次),所以这条不是可选的。

### 期望

照**同目录已有的现成范式** —— `apps/mms-web/tests/bot-wait-controls.test.mjs:16-22`:

```js
function legacyDismissBlock() {
  const start = source.indexOf('className="bot-legacy-wait-dismiss"');
  assert.ok(start > 0, "legacy dismiss button should exist");
  const end = source.indexOf("</button>", start);
  assert.ok(end > start, "legacy dismiss button should be closed");
  return source.slice(start, end);
}
```

在 `bot-model-switch.test.mjs` 里加一条同形状的块断言:定位 `className="bot-chat-model-line"`,取到闭合 `</p>`,断言块内同时含 `当前 `、`下一轮 `、`bot.pendingPresetId`、`bot.model`。

### 验证

删掉 `Bot.tsx:2051-2058` 整块 → `node --test apps/mms-web/tests/*.test.mjs` **必须红**。这条 mutation 请在交付里写明你跑过、结果是红。

---

## 3. 待生效模型变得不可用时 Bot 被永久 brick(必修)

### 问题

`update_bot`(`mms_web/bots.py:411`)把 `pendingPresetId` 和 `presetId` 放进同一个白名单循环,但**只有 `presetId` 走 `executor.validate()` 的校验**,`pendingPresetId` 写什么都收。

然后在 `_launch` 的消费分支(`:1765-1774`):

```python
selected = self.executor.validate(bot)     # 这里抛
bot["sessionId"] = None
self._bot(bot["id"]).update(selected, pendingPresetId="", ...)   # 清空在抛出之后
```

`validate()` 抛在清空 `pendingPresetId` 之前,所以 **pending 永不自清**。实测:写入一个不可用的 pending 之后,`r2: interrupted / r3: interrupted / r4: interrupted` —— 之后每一个任务都失败,而 Bot 再也跑不起来,也就再也没法自己调 `model switch` 改回去。逃生口只剩聊天框捷径(走 `update_bot`,不需要任务)。

错误文案还说谎:「MMS 当前没有可启动的 Pi 模型,请先配置一个模型。」—— 有可用模型,只是 pending 那一个不可用。

这条路径现实存在:通道掉线、key 过期、provider 下架某个模型。

### 期望 —— 这里我反转你 walls.md 的确认项 3

你写的是"消费失败时 pending 保留待恢复"。**改成:清掉 pending,本轮退回 `presetId` 继续跑,并且说真话。**

理由:保留的收益是"通道临时恢复后自动生效",代价是"永久不可用时 Bot 停摆,且用户看不出为什么"。一个能把 Bot 弄死的字段不是"做完了"。而退回 `presetId` **不是**静默降级到语义不同的默认值 —— 那是用户自己此刻正在用的模型,而且必须带一条可见的 system 消息。

具体形状:

1. 消费分支里把 `validate()` 包起来。抛 `WebError` 时:
   - `pendingPresetId` 清空
   - `sessionId` **不动**(没换模型,就不该白扔会话历史,见第 4 条)
   - `bot` 退回原本的 `presetId`,本轮照常启动
   - 写一条 system 消息,**指名**:`待生效模型 <name 或 id> 当前不可用,已取消这次切换;本轮继续使用 <当前模型>。你可以重新切换。`
2. `update_bot` 收到非空 `pendingPresetId` 时,校验它在 `available_presets()` 里;不在就拒绝(新错误码,例如 `BOT_MODEL_UNAVAILABLE`,和 `_bot_model_switch` 里那条保持一致的文案口径)。这样无效值根本进不去。

### 验证

- 一条测试:写入不可用的 pending → 下一个任务**成功完成**、用的是原 `presetId`、`pendingPresetId` 已清空、system 消息里出现那个不可用模型的名字
- 一条测试:`update_bot` 传一个不存在的 `pendingPresetId` → 抛 `BOT_MODEL_UNAVAILABLE`,Bot 状态逐字节未变
- mutation:把清空那一步删掉 → 第一条测试必须红

---

## 4. 切到当前已经在用的模型,会白扔整个会话(必修)

### 问题

Bot 正在用 Alpha,用户说"换成 alpha"。`_bot_model_switch` 照样写 `pendingPresetId = "pi:alpha"`,返回「已记录,下一轮起使用 Alpha · c1;本轮仍是 Alpha」。下一轮消费分支照常执行 `sessionId = None` —— 模型一个字没变,Pi 的对话历史被清空了。

### 期望

两处都短路:

1. `_bot_model_switch` 里,匹配到的 preset `== self._current_preset_id(bot)` 时,**不写 pending**,直接返回一句「已经在用 <name> 了,没有需要切换的。」(不是错误,是正常返回)
2. 消费分支里也加一道:`pendingPresetId == presetId` 时只清 pending,**不动 `sessionId`**(防御另一条写入路径,比如捷径或 `update_bot`)

前端捷径 `resolveModelSwitch` 同样处理 —— 命中当前模型时不要发 patch。

### 验证

- 一条测试:Bot 用 Alpha,switch 到 alpha → 不写 pending,返回文案说"已经在用",`sessionId` 前后不变
- 一条测试:直接 `update_bot` 塞 `pendingPresetId == presetId` → 下一轮只清 pending,`sessionId` 前后不变(这条锁第 2 道防御)
- 前端一条:`resolveModelSwitch` 命中当前模型时 `patch` 为 null

---

## 5. "双端逐字一致"这句话现在是假的(必修,选一种做法)

### 问题

`bot_executor.py` 的 docstring 和 `docs/mms-web/BOTS.md` 都写了双端匹配规则"逐字一致 / character for character"。42 个 query 的差分实测 **5 条不一致**:

```
'﻿beta'  py 不剥 BOM → 无匹配   ts 剥 BOM → pi:beta
'beta﻿'  py 不剥 BOM → 无匹配   ts 剥 BOM → pi:beta
'\x85beta'    py 剥 NEL  → pi:beta   ts 不剥   → 无匹配
'beta\x85'    py 剥 NEL  → pi:beta   ts 不剥   → 无匹配
'BETA\x1c'    py 剥 FS   → pi:beta   ts 不剥   → 无匹配
```

根因是 Python `re` 的 `\s` / `str.strip()` 和 JS `\s` / `.trim()` 字符集不同。

实际用户影响低(只有不可见控制符和 BOM 粘贴才踩到;你点名验的那些边界 —— 纯数字、只有通道名、中文、大小写混合、`gpt-5.6-*`、全角 —— 42 条里全部一致)。

**真正的问题是漂移无人看守。** 两边的 `NORMALIZATION_SAMPLES` 是手抄的两份字面量、只有 3 条、只钉 `normalize` 不钉 `match`。mutation 证明了这点:我让 Python 侧多剥 `+~` 两个字符、match 时多搜一个 `description` 字段,`287 + 129` 全绿。而且 `test_normalization_matches_frontend_samples` 是拿 Python 的常量校验 Python 的函数 —— 对"和前端一致"零证明力。

### 期望

**不要**为了这 5 条改归一化实现(收益太小)。做这两件:

1. **样例抽成一份共享 fixture**,两边读同一个文件(例如 `apps/mms-web/tests/fixtures/model-match-cases.json`,Python 测试也读它)。扩到 15 条以上,覆盖你我都点名的那些边界。**断言 `match` 的结果 id 列表,不只是 `normalize` 的字符串。**
2. **改掉"逐字一致"的措辞**。改成说实话的版本,例如"两侧用同一套规则和同一份样例;`\s` 的字符集在 Python 和 JS 下有已知差异,只影响不可见控制符和 BOM,见 `<fixture 路径>` 的注释。"`bot_executor.py` 的 docstring 和 `BOTS.md` 都要改。

### 验证

F-drift mutation 必须红:在 Python 侧的分隔符集里多加两个字符(比如 `+~`),或者 match 时多搜一个字段 → 共享 fixture 那条测试必须红。请在交付里写明你跑了这条。

---

## 另外三件小事(一起做掉)

**a. `docs/mms-web/BOTS.md` 写错了可见位置。** 新增那节末尾说"Bot 编辑器的模型下拉旁边显示「当前 X · 下一轮 Y」"。那个编辑器**打不开** —— `BotStudio.tsx:373` 的 `editor` state 全文件只有一处 `setEditor`,是 `onClose={() => setEditor(null)}`,没有任何地方把它设成 bot 或 `"new"`,所以 `editor` 恒为 null。你在 walls.md 里主动披露了这点,但文档没跟着改。

改成描述**真正可见的那个位置**(Bot 头部,`Bot.tsx:2051`),并注明 BotEditor 目前无打开入口、那 8 行是预留接线。

顺带说明:`BotStudio.tsx:1082` 那行 `pendingPresetId: patch.pendingPresetId ?? current.pendingPresetId` **是活的且必需** —— `Bot.tsx:1883-1887` 的捷径 patch 靠它才不被丢掉。别跟着死代码一起清掉。

**b. walls.md 的数字对不上。** 你写"T5a 基线 265、新增 +22"。实测基线是 **267**(两次复跑稳定,`--collect-only` 也是 267),新增是 **+20**(model_switch 15 + client 3 + transport 1 + web_bots 1),267+20=287 自洽 —— 287 这个数字本身是对的,是基线和增量写错了。改成实测值。

**c. 真机验证第 1 条要重做一次。** 证据 `02-task1-ask-capability.txt` 的 instruction 是「…**用 model list 看看实际可用的模型**,一两句话告诉我」—— 命令名是你递过去的。要验的恰恰是 Bot **自己**知道有这个能力。

机制上我核过是到位的:`command_catalog_text()` 确实自动生成那两行,`bot_executor.py:132-135` 那两句行为指示有 `test_bot_prompt_teaches_honest_model_switching` 锁着。但机主的硬约束是"不能有 Bot 从来不知道自己有的能力",所以要有一次真机证据。

重跑一轮,instruction 用**不含任何命令名**的原始问法,例如:「你现在用的是什么模型?你能自己换模型吗?」看 Bot 会不会自己去调 `model list`。存成新的证据文件,旧的那份保留。

**真机验证第 8 条(override 实验)不用重做** —— 你的 `14-override-done-pending-kept.json` 里 override 值和 Bot 当时的 `presetId` 恰好都是 `glm-5.3`,那个实验在原理上区分不了"override 生效"和"override 被忽略、用了默认值"。但既然 override 的修复另立包了,这个实验也跟着挪过去,在那个包里做(而且那次必须让 override 值 ≠ Bot 当前 `presetId`)。T5c 这边只保留"pending 没被吃掉"这半边证据,那半边是有效的。

---

## 交付要求

1. 五条必修 + 三件小事都做完
2. 每一条的 mutation 结果写明(改了什么 → 红还是绿)。特别是第 2 条的"删掉 `<p>` 整块"和第 5 条的 F-drift,这两条是专门用来证明测试不是理论的
3. 门禁全量重跑,写实测数字:定向 pytest、`npx tsc --noEmit -p apps/mms-web`、`node --test apps/mms-web/tests/*.test.mjs`(**glob 必须带**)、`bot*.css` 裸 hex 必须仍是 12、`npm run build --workspace @mms/web`、`python3 scripts/ci_pytest_regression.py --base bot/T5a-schedule-backend`
4. `python3 scripts/regression_fresh_user_gate.py`(完整,不加 `--quick`)。**这个 gate 对并发敏感**:`test_install_script_paths.py::test_installer_does_not_reuse_another_homes_web_instance` 会比对端口和 PID,并行跑会假失败。串行跑一次;如果那一条红了,单独复跑确认,并在交付里如实写明
5. 第 3、4 条改了行为,真机各验一次,存证据
6. 还是**不提交、不 push、不 merge** —— 保持包约定,我来处理提交和 PR

跑真机验证时:端口用 61000-62000 的随机值,**绝不碰 8767 / 60824 / 8765 / 8766**;绝不用 `pkill`,只 kill 自己启动的 PID;绝不写真实 `~/.config/mms*`。
