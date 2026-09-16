# T7f · 删掉一条已排队的「引导」，它还是会送出去

机主原话（2026-09-16）：

> 还是那个会话间插入引导的功能 当我发送后 点了删除 这条"引导"还是会发送出去.

也就是：任务跑着的时候插一条引导 → 它进队列，卡片上写「引导已排队 · 当前这批工具调用结束后送达」→ 点删除 → 卡片改成「已取消，未执行」→ **Pi 照样把它送给了模型**。

界面说的和实际发生的是两回事。这是 T7e 同一类的缺陷：**界面对用户撒谎**。

---

## base 分支判定

**base = `origin/main`（4.22 稳定线）。**

`mms_web/sessions.py` 的 `_rewrite_queue`、`queue`、`send` 三段在 `origin/main` 和 `origin/dev` 上**逐字节相同**，只差一个 **+39 行**的整体偏移。`apps/mms-web/src/MessageQueue.tsx` 两条分支**完全一致**（`diff` 为空）。

所以这是两条线共有的缺陷，按机主定的流向规则（4.x 的改动默认进入 5.x），修在 `main` 上，之后随 main → dev 合流带过去。

**下面所有行号都给两套。** 动手前在你的 base 上逐条复核，凡与本文件不一致的都要在交付里列出来。

---

## 症状与触发条件

1. 会话正在跑（`state == "running"`），且**没有**待确认的审批（有审批时 steer 会被 `APPROVAL_PENDING` 挡掉，见 `sessions.py` main `704` / dev `743`）。
2. 用户用「引导」模式发一条消息。它落进 `pending_prompts`，`event["status"] = "queued"`，`event["mode"] = "steer"`，同时用 `command="steer"` 交给 Pi（main `735-740` / dev `774-779`）。
3. 卡片上显示「引导已排队 · 当前这批工具调用结束后送达」（`message-control.ts:146-147`，两条分支同）。
4. 用户点删除 → `POST /sessions/{id}/queue {action:"remove", id}`（`App.tsx` main `2127` / dev `2177`；`SessionTools.tsx:377` 两条分支同）。
5. 卡片变成「已取消，未执行」（`message-control.ts:138`）。
6. **Pi 还是把它送出去了。**

---

## 根因

### 已查明的部分（D1，代码层面确定，不需要实测就能看出来）

`mms_web/sessions.py` 的 `_rewrite_queue`（main `821` / dev `860`）。Pi 没有按条删除，唯一的原语是 `clear_queue`：整队清空并把清掉的文本按 lane 交回来。所以「删一条」= 清空 + 把该留的按顺序重新入队。

```python
cleared = driver.clear_queue()                          # main 824 / dev 863
waiting = {*cleared["steering"], *cleared["followUp"]}   # main 827 / dev 866
with session.lock:
    texts = dict(session.pending_prompts)
    modes = dict(session.pending_modes)
    if removed:
        event = session.event_index.get(removed)
        if event and event.get("status") == "queued":
            event["status"] = "cancelled"                # main 834 / dev 873  ← 无条件
        session.forget_pending(removed)
restored: list[str] = []
for queued_id in order:
    text = texts.get(queued_id)
    # Pi delivered it while the queue was being rewritten: leave it
    # gone rather than sending the same message a second time.
    if text is None or text not in waiting:              # main 841 / dev 880  ← 幸存者有这个检查
        continue
```

**幸存的消息有 `text not in waiting` 这道检查**，查不到就说明 Pi 已经把它取走了，于是跳过重发，并在函数末尾标成 `delivered`（main `866` / dev `905`）。

**被删的那一条没有这道检查。** 它被**无条件**标成 `cancelled`，然后 `forget_pending`。

于是只要那条消息在 `clear_queue` 的一刻已经不在 Pi 的可清队列里（Pi 刚取走，或者它压根就不在可清的 lane 里 —— 见 D2），服务端就会在自己都没能撤回的情况下，告诉用户「已取消，未执行」。

**这条无论 D2 的答案是什么都必须修。** 撤回成功与否是可以判定的事实，不该假定成功。

### 必须先实测确定的部分（D2 —— 这条决定整个修法的形状）

**Pi 的 `clear_queue` 到底会不会清掉 steering lane？**

仓库里这件事**没有任何真实证据**：

- `docs/mms-web/REGRESSION-T2-MESSAGE-CONTROL.md:15` 写的是「整队清空，返回被清掉的 `steering` 与 `followUp` 文本」—— 这是**契约声明**，不是实测记录。
- `tests/test_mms_web_message_control.py` 的进程内 driver double（`steer()` 会往 `self.queued_steering` 里塞，`clear_queue()` 会清它）**建模成可清**。但 double 是照着上面那句话写的，它证明不了 Pi 的真实行为。
- **线级 fake Pi 从来不模拟**：`tests/fixtures/mms_web/t2/pi_wire_child.py:245` 对 `clear_queue` **永远返回 `{"steering": [], "followUp": []}`**。所以走真实 RPC 的那套测试一次都没验过非空清空。
- Pi 自己对 steer 的语义是「消息只在当前 assistant 回合的工具调用跑完之后、**下一次 LLM 请求之前**送达」（`mms_web/drivers/pi_rpc.py:243-252` 的 docstring 转述 rpc.md）。这句话没有说 steer 在被接受之后还留在一个**可撤回**的队列里 —— 它完全可能在 RPC 返回的那一刻就已经进了会话，只是等到下一次请求才呈现给模型。

**要求实现者用真实的 Pi 把这件事测出来，不许靠推理。** 最小实验：

1. 起一个真实会话，让它跑一个够长的工具（比如 `bash sleep 60`）。
2. 用 `steer` 发一条独特文本（例如 `T7F-PROBE-<随机串>`）。
3. 直接对 driver 调 `clear_queue()`，**把原始返回打印出来**。
4. 看 `steering` 里有没有那条文本。
5. 然后等这一轮跑完，看模型**有没有**收到它。

把这五步的原始输出贴进交付。这是本包最重要的一条证据，没有它后面的修法都是猜。

### 测试覆盖缺口（D3）

`tests/test_mms_web_message_control.py` 里四处 `action: "remove"`（main/dev 同：`530` / `582` / `607` / `617`）**全部**建立在 `queue_two()` 这个 fixture 上，而 `queue_two` 发的是两条不带 `mode` 的消息 —— 也就是两条 **followUp**。

**整个仓库没有一条测试删除过一条 `mode == "steer"` 的排队消息。**

有一条 `test_a_promoted_message_says_it_is_steering_now` 把 followUp 提升成 steer，但提升完就断言 `mode`，没有接着删它。

---

## 要做成什么

### A. 撤回结果必须如实反映（无论 D2 的答案是什么，这条都要做）

`_rewrite_queue` 里被删的那一条，要和幸存者走**同一套判定**：

- 它的文本**在** `waiting` 里 → 撤回成功 → `status = "cancelled"`，卡片说「已取消，未执行」。
- 它的文本**不在** `waiting` 里 → **没撤回成功**，Pi 已经拿走了 → 状态必须是一个如实的值（`delivered`，和幸存者被 Pi 取走时用的是同一个），并且**不能**显示「已取消，未执行」。

界面不许在服务端没能撤回的情况下说已取消。

### B. 用户要知道「来不及了」

A 做完之后，点删除但没撤回成功，用户至少不会被骗。但他会看到一条自己明明点了删除、却显示成已送达的消息，需要一句解释。

`message-control.ts` 的 `deliveryLabel()`（`137-150`，两条分支同）要能表达这个状态。文案自己定，但必须说清楚两件事：这条已经送给模型了；删除来晚了。

**不要**把它做成弹窗或红条 —— 这是个既成事实的说明，不是错误。

### C. 如果 D2 的答案是「steer 不可撤回」

那么「删除」这个按钮对一条已被 Pi 接受的 steer 就是**做不到的承诺**。`MessageQueue.tsx:124-126`（两条分支同）现在对**所有**行都渲染删除按钮，没有按 `item.mode` 区分：

```tsx
aria-label={`删除第 ${index + 1} 条`}
onClick={() => (editable && remove ? remove(item.id) : clear?.())}
```

这种情况下要么按 `item.mode === "steer"` 禁用/隐藏它并说明原因，要么保留按钮但事先就讲清楚它可能来不及。**选哪个、以及文案，交给你判断，但要在交付里写明理由。**

如果 D2 的答案是「steer 可撤回，只是有竞态窗口」，那就只做 A 和 B，C 不用做。

### D. 硬验收项：不许把 followUp 的删除弄坏

followUp 的删除现在是好的，有测试覆盖。改完之后：

- 删一条 followUp，仍然正常撤回、仍然标 `cancelled`、其余的仍然按原顺序重新入队；
- `move` 和 `steer`（提升）两个 action 的行为一个字都不许变；
- `clearQueue`（整队清空）不许变。

---

## 要读的代码（只读，先看完再动手）

| 文件 | main | dev | 看什么 |
|---|---|---|---|
| `mms_web/sessions.py` `send()` | `704` | `743` | 有审批时 steer 被拒 |
| 同上 | `735-737` | `774-776` | `status="queued"` + `pending_prompts` + `pending_modes` |
| 同上 | `739-740` | `778-779` | `mode=="steer" and previous_state=="running"` → `command="steer"` |
| 同上 `queue()` | `757` | `796` | `remove` / `steer` / `move` 三个 action 的入口；`QUEUE_ITEM_GONE` 的判定 |
| 同上 `_rewrite_queue()` | `821` | `860` | **主战场** |
| 同上 | `824` / `827` | `863` / `866` | `clear_queue()` 与 `waiting` 集合 |
| 同上 | `831-835` | `870-874` | 被删项的处理 —— 缺检查的地方 |
| 同上 | `841` | `880` | 幸存者的 `text not in waiting` 检查 |
| 同上 | `860-866` | `899-905` | 末尾把没重发成功的标 `delivered` |
| `mms_web/drivers/pi_rpc.py` | `243-282` | 同 | `steer` / `follow_up` / `clear_queue` 的真实 RPC 形状与 docstring |
| `apps/mms-web/src/message-control.ts` | `137-150` | 同 | `deliveryLabel()` |
| `apps/mms-web/src/MessageQueue.tsx` | `124-126` | 同 | 删除按钮，对所有 mode 一视同仁 |
| `apps/mms-web/src/App.tsx` | `2127` | `2177` | dock 里的 remove 调用 |
| `apps/mms-web/src/SessionTools.tsx` | `377` | 同 | 侧栏里的 remove 调用 |
| `tests/test_mms_web_message_control.py` | `477-490` | 同 | `queue_two()` fixture —— 它只造 followUp |
| 同上 | `530/582/607/617` | 同 | 四处 remove 测试，全部建立在 followUp 上 |
| `tests/fixtures/mms_web/t2/pi_wire_child.py` | `244-245` | 同 | 线级 fake 的 `clear_queue` 永远返回空 |

---

## 只许改

- `mms_web/sessions.py` —— 只许改 `_rewrite_queue`，以及（仅当 D2 要求时）`queue()` 里 `remove` 分支的前置判定。
- `apps/mms-web/src/message-control.ts` —— 只许改 `deliveryLabel()`。
- `apps/mms-web/src/MessageQueue.tsx` —— 仅当 C 适用时。
- `apps/mms-web/src/transcript.css` 或 `styles.css` —— 仅当新增状态需要样式时，且只许加新 class，不许改既有 class 的值。
- `tests/test_mms_web_message_control.py` —— 加测试。
- `tests/fixtures/mms_web/t2/pi_wire_child.py` —— 仅当你要让线级 fake 真正建模 `clear_queue` 时。

## 不许改

- `mms_web/drivers/pi_rpc.py` 的 RPC 形状（`steer` / `follow_up` / `clear_queue` 发出去的 command 结构）。要改先说。
- `send()` 的投递语义、`APPROVAL_PENDING` 的判定、`abort` / `interrupt` 的语义。
- `move` / `steer`（提升）/ `clearQueue` 三个 action 的行为。
- 任何受保护文件：`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`。
- 任何 `mms_web/bot*.py`（这是 4.22 线，不许带 Bot）。
- `walls.md` —— `origin/main` 上没有这个文件，**不要把它加进提交**（`origin/dev` / `origin/dev-pre` 上有，那边是正常追加，但这个包 base 是 main）。交付写进 PR 描述。

---

## 门禁

```bash
# 1. 类型
npx tsc --noEmit -p apps/mms-web

# 2. 前端单测（glob 必须带，不带会直接报错）
node --test apps/mms-web/tests/*.test.mjs

# 3. 构建
npm run build --workspace @mms/web

# 4. 消息控制的定向 pytest
PYTHONPATH=. python3 -m pytest -q tests/test_mms_web_message_control.py tests/test_mms_web_t2_message_control.py

# 5. 回归对比
python3 scripts/ci_pytest_regression.py --base origin/main

# 6. 完整 fresh-user gate（不是 --quick）
python3 scripts/regression_fresh_user_gate.py
```

跑之前先在你的 worktree 里 `npm install`，否则 `markdown-reading.test.mjs` 会因为找不到 `unified` 直接红，那不是你的问题。

跑 gate 前清掉 `MMS_CONFIG_ROOT` / `REAL_HOME` / `ORIGINAL_HOME` / `MMS_REAL_HOME` / `XDG_CONFIG_HOME`。

**所有数字都要是你自己跑出来的。** 不要写"与基线一致"这种没有比较对象的话，直接写绝对数，并且 base 和 head 各跑一遍。

---

## 要补的测试

至少这几条，而且**必须是删除一条 `mode == "steer"` 的排队消息**，不能继续用 `queue_two()` 那个只造 followUp 的 fixture：

1. **删一条 steer，Pi 还没取走** → 撤回成功，`status == "cancelled"`，Pi 的 steering lane 里没有它，其余排队项按原顺序回到队列。
2. **删一条 steer，Pi 已经取走**（在 double 里把它从 `queued_steering` 移走，模拟竞态）→ `status` **不是** `cancelled`，`deliveryLabel()` 不返回「已取消，未执行」。
3. **删一条 followUp 的既有行为零回归**（现有四条测试必须继续绿）。
4. 如果 D2 的答案是「steer 不可撤回」：再加一条锁住 C 的行为（按钮禁用/隐藏，或前置提示）。

---

## 变异测试（硬要求，本轮新增）

交付之前，你自己把核心改动逐处撤销，确认对应的测试**变红**。撤销之后还全绿的，就说明那条测试没测到东西，要重写。

至少要覆盖：

- 把 `_rewrite_queue` 里被删项的判定改回无条件 `cancelled` → **必须红**。
- 把 `deliveryLabel()` 的新分支删掉 → **必须红**。
- 如果做了 C：把 `MessageQueue.tsx` 的 mode 判定删掉 → **必须红**。

把每一条变异和它的实际输出贴进交付。**这一段没有的交付直接退回。**

理由：前几个包里反复出现"把核心修复整个撤销，测试仍然全绿"的情况 —— 测试只测了纯函数，没锁住真正决定行为的那一层。

---

## 真实验证（不是可选项）

用 ego-browser + **隔离实例**（隔离 HOME / config root，端口自选 61000-62000 的空闲口）。

**绝不**重启或杀掉 8767 / 60824 上的 Pilot，那是机主自己的实例。**绝不**用 `pkill`。**绝不**写真实 `~/.config/mms*`。

要截的图：

1. 任务跑着、插一条引导 → 卡片显示「引导已排队 · 当前这批工具调用结束后送达」。
2. 点删除、撤回**成功** → 卡片「已取消，未执行」，并且**模型确实没收到**（贴出这一轮的实际回复，证明里面没有那条引导的内容）。
3. 点删除、撤回**失败**（Pi 已取走）→ 卡片显示的是新的如实状态，**不是**「已取消，未执行」。这一张是本包的核心证据。
4. 删一条普通的「补充」消息 → 行为和改动前一致（base / head 对照两张）。
5. 如果做了 C：按钮的禁用态或前置提示。

截图放 `docs/mms-web/design/t7f/`。**每一张都要是真实渲染，不许是中间构建或摆拍。** 文件名要和它实际证明的事情一致。

---

## 交付格式

写进 PR 描述（不要建 `walls.md`）。逐条，缺一条就是没交付完：

- **D2 的实测结论**：`clear_queue` 的原始返回、steering lane 里有没有那条探针文本、那一轮模型有没有收到它。贴原始输出。
- **行号复核**：本文件列的所有行号在你的 base 上逐条核对过；凡不一致的逐条列出。
- **改动边界**：改了哪些文件、哪些没动、为什么。
- **门禁实测数字**：base 和 head 各一遍，绝对数。
- **变异测试**：每条变异 + 实际输出。
- **未完成 / 未验证**：逐条。没有就写"无"，但请确认真的没有。
- **需要 Fable 确认**：逐条。
- **合流提示**：这个修复要随 main → dev 带进 5.x，5.x 上有没有额外影响（比如 bots 页的会话也走同一条 `_rewrite_queue`）。

---

## 需要 Fable 确认

先自己按上面做，做完把这几条列出来，不要停下来等：

1. D2 的实测结论是什么，以及它把修法推向了 A+B 还是 A+B+C。
2. 撤回失败时的状态值选了什么、文案写了什么。
3. 线级 fake（`pi_wire_child.py:245`）要不要真正建模 `clear_queue` —— 这会扩大改动面，但现在它让整套线级测试对这个 bug 完全无感。
