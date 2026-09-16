# T7c · 把 MMF 挡下来的真实原因说给用户听

Date: 2026-09-16
Task: Stride 370e87ec37e741df
建议模型：k3 / deepseek（后端为主，前端只有渲染核对）
来源：owner 2026-09-16——同事在一台装过旧版本的电脑上删除通道，弹出「MMF 未允许这组修改，未保存。请检查是否移除了全部可用模型，或重新加载配置后再试。」这句话是猜的，而且方向很可能是错的

先读：`docs/mms-web/bot-work/README.md`（并行规则、通用验收）、本文件，然后按下面"要读的代码"逐处确认。

**本包与 T7d 互相独立，可以并行。** 改动面零重叠：T7c 只动 `mms_web/model_settings_worker.py` 加一个新的映射模块，前端只核对 `ChannelModels.tsx` 已有的三处渲染点；T7d 只动 `mms_web/server.py` 的 `set_remote_access` / `_send` 与 `RemoteAccess.tsx`。两个包没有任何共享文件。

---

## base 分支判定（2026-09-16 实测）

### 结论

| 项目 | 分支 | 依据 |
| --- | --- | --- |
| **实现 PR 的 base** | **`main`（4.22.1，`6c62a656`）** | 本包要改和要读的代码在两条线上**逐字节相同**；owner 定的流向是"4.x 的所有改动默认进入 5.x"，修在 4.22.x 会自动流到 5.x，反过来不会回到 4.x |
| 本工作包文档所在分支 | `dev`（5.x，`e5d32243`） | `docs/mms-web/bot-work/` 整棵树**只存在于 `dev`**，`origin/main` 上没有这个目录 |

和 T6a / T6b / T7a / T7b 是同一个形状。

### 实测证据

owner 指定的那条 diff，实际结果：

```
$ git diff --stat origin/main origin/dev -- \
    mms_web/model_settings_worker.py mms_web/model_settings.py mms_web/server.py \
    mms_web/remote_access.py apps/mms-web/src/ChannelModels.tsx apps/mms-web/src/SettingsPage.tsx

 apps/mms-web/src/SettingsPage.tsx | 138 ++++++++++++++++++++++++++++++++------
 mms_web/server.py                 | 117 ++++++++++++++++++++++++++++++--
 2 files changed, 231 insertions(+), 24 deletions(-)
```

六个文件里**只有两个有差异**，而且**这两个都不在 T7c 的改动面上**：

- `mms_web/server.py` 的 117 行差异全部是 5.x 的 Bot 工作台接线（`BotRuntime` / `PiBotExecutor` / `EgoComputer` 的构造、`/bots` 与 `/tasks` 路由、`bot-worker` 内部接口、CSP 放 `blob:`、`_visible_sessions` 过滤 Bot 会话）。与 `model-settings` 这条链路无关。
- `apps/mms-web/src/SettingsPage.tsx` 的 138 行差异是 T6b 那个"运行环境"tab 的回流差，同样与本包无关。

逐文件 blob hash（`git rev-parse origin/<b>:<path>`）：

| 文件 | main | dev | 判定 |
| --- | --- | --- | --- |
| `mms_web/model_settings_worker.py` | `504795f0` | `504795f0` | **逐字节相同** |
| `mms_web/model_settings.py` | `2bc7df4c` | `2bc7df4c` | **逐字节相同** |
| `mms_registry_cli.py` | `ab6a93fe` | `ab6a93fe` | **逐字节相同** |
| `mms_state_io.py` | `fa9210f8` | `fa9210f8` | **逐字节相同** |
| `mms_config_web.py` | `e0d69b5a` | `e0d69b5a` | **逐字节相同** |
| `apps/mms-web/src/ChannelModels.tsx` | `5dea6516` | `5dea6516` | **逐字节相同** |
| `apps/mms-web/src/api.ts` | `5ba09216` | `5ba09216` | **逐字节相同** |
| `tests/test_mms_web_model_settings.py` | `f2d4399e` | `f2d4399e` | **逐字节相同** |
| `mms_web/server.py` | `cbcb9855` | `f9c3c5a3` | 差异全在 Bot 接线，不在本包改动面 |

**结论：本包改动面 100% 两线一致，base 定 `main`，没有需要在包里说明的差异。**

---

## 症状

owner 的同事在一台装过旧版本的电脑上删除通道，弹出：

> MMF 未允许这组修改，未保存。请检查是否移除了全部可用模型，或重新加载配置后再试。

这句话是**猜的**。而且很可能猜错了方向：那台机器上这条红字在打开删除弹窗**之前就已经显示在通道设置页上**，说明被挡的不是这次删除，而是这台机器上的**任何写操作**。

## 根因

### 一句话

`blocked_reasons` 被算出来，只当布尔值用，**内容一个字都没传给用户**。

`mms_web/model_settings_worker.py`（main 与 dev 行号相同）：

| 行 | 代码 |
| --- | --- |
| 426 | `guard = plan.get("registry_v2_save_plan", {}).get("blocked_reasons", [])` |
| 427 | `if not plan.get("ok") or guard:` |
| 428 | `raise WebError("CONFIG_PLAN_BLOCKED", "MMF 未允许这组修改，未保存。请检查是否移除了全部可用模型，或重新加载配置后再试。", 409)` |

owner 给的是"约 427-428"，实测 `guard` 在 **426**，`if` 在 **427**，`raise` 在 **428**。**两条线一致。**

### MMF 实际产生的三类原因

`mms_registry_cli.py` 759-765（**只读，禁止修改这个文件**），main 与 dev 行号相同，与 owner 给的行号完全吻合：

```python
759    blocked_reasons: list[str] = []
760    if root_status.get("legacy_root"):
761        blocked_reasons.append("stable_root_human_only")
762    if not has_changes:
763        blocked_reasons.append("no_draft_changes")
764    if guard_blocked:
765        blocked_reasons.append(str(guard.get("reason") or "route_publish_guard_blocked"))
```

| 代码 | 条件 | 真实含义 |
| --- | --- | --- |
| `stable_root_human_only` | `root_status["legacy_root"]` 为真 | 配置根被判定为 legacy root，只允许人工修改，Pilot 一律不许写。**这台机器上所有写操作都会失败，和具体改了什么无关。** |
| `no_draft_changes` | `has_changes` 为假 | 这组改动实际上没产生任何变化 |
| `guard.get("reason")` 或 `route_publish_guard_blocked` | 路由发布守卫 `ok is False` | 路由发布被守卫拦下，具体原因在 `reason` 里 |

### `legacy_root` 到底怎么判出来的（实现者必须知道，否则文案写不准）

`mms_state_io.py`：

```python
166  def is_retired_legacy_root(config_dir):
      ...
173      root = os.path.normpath(str(config_dir or ""))
174      return os.path.basename(root) == LEGACY_CONFIG_ROOT_NAME     # "mms"
176  def mms_config_root_status(command=None, config_dir=None, env=None):
      ...
183          "legacy_root": is_retired_legacy_root(root),
      ...
```

**判定依据只有一个：解析出来的配置根目录名字是不是字面量 `mms`。** 也就是说，一台机器上只要 `MMS_CONFIG_ROOT` / `MMS_CONFIG_DIR` / `XDG_CONFIG_HOME` 还指向 `~/.config/mms`（或任何叫 `mms` 的目录），`legacy_root` 就恒为真，**这台机器上的每一次写都会被挡**，删通道、改模型、改 effort、改 Key 全都一样。这正好解释 owner 观察到的"红字在打开弹窗之前就已经在了"。

配置唯一来源是 `~/.config/mms-next`，见 `docs/AGENT_GUARDRAILS.md` 的 **Single Config Root（2026-09-10，#177）**一节（**只读**）：legacy `~/.config/mms` 已退出配置来源，不做自动导入、不做回退、`MMS_CONFIG_ROOT_MODE=stable` 被忽略。

### 第三类不是裸代码，是一句英文长句（**owner 给的表里没写，必须按实测来**）

`mms_registry_cli.py` 2249-2262：

```python
2249  def _route_publish_guard_message(reason, current, candidate) -> str:
2250      current_count = int(current.get("route_count") or 0)
2251      candidate_count = int(candidate.get("route_count") or 0)
2252      if reason == "stale_preview_bundle_revision":
2253          return ("stale_preview_bundle_revision: latest-approved bundle changed since this "
                     "WebUI draft was loaded; refresh the WebUI before publishing")
2257      if reason == "route_shrink_guard":
2258          return ("route_shrink_guard: candidate would shrink latest-approved route groups "
                     f"from {current_count} to {candidate_count}; refresh WebUI or use an explicit recovery flow")
2262      return reason or "route_publish_guard_blocked"
```

所以 `blocked_reasons` 里第三类元素**不是** `"route_shrink_guard"` 这样的裸代码，而是 `"route_shrink_guard: candidate would shrink latest-approved route groups from 5 to 0; refresh WebUI or use an explicit recovery flow"` 这样**带冒号前缀的整句英文**（这是 `_registry_v2_route_publish_guard_from_candidate`，`mms_registry_cli.py:2265`，写进 `guard["reason"]` 的形状）。

**这条直接决定映射表怎么写**：不能用 `code in TABLE` 精确匹配，必须**先按第一个 `:` 切出前缀**再查表。这是本包最容易做错的一点。

### 三条 `if` 互相独立 ⇒ **可以同时出现多条**

这是 owner 要求调查的问题，结论是**可以，而且现实中很常见**：

- 760 / 762 / 764 是三条平行的 `if`，没有 `elif`，没有 `return`，任何组合都会累加进同一个列表。
- 最容易同时出现的是 `stable_root_human_only` + `no_draft_changes`：legacy root 上 `has_changes` 经常同时为假（删掉最后一处差异、或草稿等于当前状态），两条一起进列表。
- `stable_root_human_only` + guard reason 也可以同时成立：`guard_blocked` 与 root 判定完全无关。
- 理论上三条可以同时出现。

**定义：多条时全部显示，按 `blocked_reasons` 原顺序，不要只取第一条，也不要去重成一句。**

### 错误怎么从 worker 走到红字（实现者要知道改哪一层）

完整链路，每一跳都实测过：

1. `mms_web/model_settings_worker.py:428` `raise WebError(...)` —— 注意这个文件是**独立子进程**（末尾 `if __name__ == "__main__":` 从 stdin 读 JSON）。
2. 同文件 445：`except WebError as error: _emit(stream, {"ok": False, "code": error.code, "message": error.message, "status": error.status})` —— **只有 `code` / `message` / `status` 三个字段跨得过子进程边界。任何想带给前端的东西都必须塞进 `message`。**
3. `mms_web/model_settings.py:88`：`raise WebError(result.get("code", ...), result.get("message", ...), result.get("status", 400))`。
4. `mms_web/server.py` `_error()`（main **548**，dev **634**）：`self._json(exc.status, {"error": {"code": exc.code, "message": exc.message}})`。
5. `apps/mms-web/src/api.ts:56`：`throw new ApiError(payload.error?.message || "操作未完成，请重试。", payload.error?.code || "UNKNOWN")`。
6. `apps/mms-web/src/ChannelModels.tsx`：`setError((e as Error).message)`（第 234 / 287 / 308 / 333 / 384 / 407 / 440 行共 7 处 `catch`）。

**结论：修点在第 1 步，`message` 里写什么，用户就看到什么。**

### "两处红字"实测：是同一个 state，不需要改两处

`ChannelModels.tsx` 只有**一个** `error` state（158 行 `const [error, setError] = useState("")`），渲染在**三处**：

| 行 | 位置 | 条件 |
| --- | --- | --- |
| 491-494 | 通道设置页顶部 | `{error && !preview && (...)}` |
| 1094-1097 | **删除通道弹窗**内 | `{error && (...)}` |
| 1162-1165 | 变更预览/确认弹窗内 | `{error && (...)}` |

（main 与 dev 行号相同，blob 一致。）

所以**只要后端把 message 改对，三处同时变对**，不需要分别改。owner 要求的"两处都显示"是天然满足的。但实现者**必须实际核对并截图这三处**，不许只看代码推断——顶部那处有 `&& !preview` 条件，预览弹窗打开时顶部会隐藏，这是既有行为，不要动它。

### 删除通道确实走 `plan`

`ChannelModels.tsx` 419-440 `deleteChannel()` 先 `POST /model-settings/preview`（映射到 worker 的 `plan` action），再 `POST /model-settings/apply`。所以删除通道踩的就是 426-428 这个分支。确认无误。

### 一个必须查清、不许猜的疑点

`tests/test_mms_web_model_settings.py:148` `test_stable_real_root_is_not_a_preview_write_target` 显示：把配置放到 `~/.config/mms` 后，`ModelSettings.available()` 返回 `False`，`read()` 抛的是 `CONFIG_UNAVAILABLE`「该配置来源没有已批准的 MMF 模型目录。」（`model_settings.py:68`），**而不是** `CONFIG_PLAN_BLOCKED`。

也就是说，在这个测试构造的场景里，用户根本进不到 `plan` 这一步。**那同事那台机器是怎么进到 426-428 的？** 实现者必须先把这个搞清楚再写文案，可能的方向：

- 该机器的 `root_status` 来自 MMF 侧的 `mms_config_root_status`，取的 root 与 `ModelSettings.available()` 判的不是同一个值；
- 或者 `available()` 过了（`~/.config/mms-next` 里有已批准目录），但 MMF 在 build plan 时解析出的 root 名字是 `mms`（例如进程环境里 `MMS_CONFIG_DIR` 指向旧目录）。

**不许把这个疑点当成已知事实写进文案。** 交付时必须写明实际复现出的是哪一种，以及 `stable_root_human_only` 的文案是按哪一种写的。如果两种都复现不出来，如实说明，文案按代码语义写，并在交付里标为"未在真机复现"。

---

## 要做成什么

### A. 新增映射（新文件 `mms_web/config_block_reasons.py`，纯函数，可测）

不要把映射表塞进 `model_settings_worker.py` 的 `run()` 里——那个文件是子进程入口，单测起来别扭。新开一个没有副作用的小模块：

```python
def describe_blocked_reasons(reasons: list[str]) -> str:
    """把 MMF 的 blocked_reasons 变成用户能照着做的中文。"""
```

要求：

1. **一种代码一句话**，不要再用那句通用猜测兜住已知代码。
2. **匹配规则**：先取元素本身查表；查不到时按第一个 `":"` 切出前缀再查表（见上面"第三类不是裸代码"）。
3. **未知代码不吞掉**：映射表里没有的，把**代码原文**带在消息里，例如 `MMF 拒绝了这组修改（原因代码：<原文>）。请把这行原文发给维护者。`。这样以后排查有抓手。
4. **多条全列出**，按原顺序，用 `；` 或换行连接（见 D 的样式说明）。
5. **只带 `blocked_reasons` 里的代码和映射后的文案**。禁止把整个 `plan` 结构、`root_status`、`config_root` / `stable_root` / `preview_root` 这些真实路径、或任何内部字段倒给前端。文案里出现的 `~/.config/mms-next` 是写死的静态文字，不是从 plan 里读出来的值——这两件事不要混。
6. `reasons` 为空但 `plan["ok"]` 为假时，仍然要有一句可用的兜底（现在那句可以留作**这一种情况**的文案，因为这时确实没有已知结论）。

建议文案（实现者可润色，但四个要点不许丢：**是什么被挡了 / 为什么 / 是不是这次改动的问题 / 下一步干什么**）：

| 代码 | 文案 |
| --- | --- |
| `stable_root_human_only` | `这台电脑的配置来源是已退休的旧目录（名字叫 mms 的那个），Pilot 在这种目录上一律不允许写入——所以这台机器上任何修改都会被挡，不是这次改动的问题。配置的唯一来源是 ~/.config/mms-next：请检查 MMS_CONFIG_ROOT / MMS_CONFIG_DIR / XDG_CONFIG_HOME 有没有还指着旧目录，清掉后重开 Pilot。` |
| `no_draft_changes` | `这组改动和当前已保存的配置没有区别，没有需要写入的内容。` |
| `stale_preview_bundle_revision` | `页面加载之后，配置在别处被改过了。点"重新加载配置"拿到最新状态，再重做这次修改。` |
| `route_shrink_guard` | `这次修改会让已发布的模型路由数量减少，MMF 拦下了以防误删。确认确实要减少的话，先重新加载配置核对当前模型，再逐个调整。`（**如果实现者决定把 MMF 那句里的 `from N to M` 带出来，必须说明这两个数字来自 `guard["reason"]` 字符串本身，不是另外去读 plan**） |
| `route_publish_guard_blocked` | `路由发布被 MMF 的守卫拦下，未保存。请重新加载配置后重试；仍然失败请把这条消息发给维护者。` |
| 未知 | `MMF 拒绝了这组修改（原因代码：<原文>）。未保存。请把这行原文发给维护者。` |

### B. 接到 `model_settings_worker.py`（**唯一的一处改动**）

428 行那句写死的 message 换成 `describe_blocked_reasons(guard)` 的结果。`code` 保持 `CONFIG_PLAN_BLOCKED`，`status` 保持 `409`——前端没有按 code 分支，改 code 只会白白破坏兼容。

注意 427 行的条件是 `if not plan.get("ok") or guard:`，**两种情况共用这一个 raise**。`guard` 为空而 `plan["ok"]` 为假时走 A.6 的兜底。

### C. 前端：核对，不重写

不需要改 `ChannelModels.tsx` 的逻辑。要做的只有：

- 实测确认三处红字（491 / 1094 / 1162）都显示到了新文案，各截一张图。
- 顶部那处的 `&& !preview` 条件保持原样。

### D. 多条原因的显示（**这是唯一需要碰 CSS 的地方，而且可能不需要碰**）

`.form-error`（`styles.css`：main **1643**，dev **1668**）没有 `white-space` 声明，所以 message 里的 `\n` **会被折叠成空格**。两个选项，实现者二选一并在交付里说明理由：

1. **推荐**：在 `describe_blocked_reasons` 里用 `；` 连接，一行读完，不碰 CSS。
2. 用 `\n` 连接，同时给 `.form-error` 加 `white-space: pre-line`。**这会影响所有用到 `.form-error` 的页面**，属于共享样式改动，选它就要在交付里写清影响面并至少核对另外两个用到它的地方（`connections.css:257` 那条 `.connection-flow .form-error button`）。

---

## 只许改

- 新增 `mms_web/config_block_reasons.py`
- `mms_web/model_settings_worker.py` **只改 428 行那一句 message 的来源**（加 import）
- 新增 `tests/test_mms_web_blocked_reasons.py`
- 可选：`apps/mms-web/src/styles.css` 的 `.form-error` 一条声明（仅当选了 D.2）

## 不许改

- **`mms_registry_cli.py`、`mms_config_web.py`、`mms_core.py`、`mms_state_io.py` 一律只读。** 本包只做"把已有结论如实传达给用户"，**不碰 MMF 侧的判定逻辑**——不改 `blocked_reasons` 什么时候产生、产生哪几条、`legacy_root` 怎么判。
- `docs/AGENT_GUARDRAILS.md` 只读。
- 受保护文件（`mms_core.py` / `mms_launchers.py` / `mms_tui.py` / `mms_bridge.py` / `mms_account_state.py` / `mms_session.py` / `mms_adapter_registry.py` / `mms` / `ccs`）。
- 真实 `~/.config/mms*`。
- `ChannelModels.tsx` 的错误处理逻辑、`api.ts`、`WebError` 的 code / status 语义。
- `model_settings.py:88` 那条转发（它已经正确透传 message）。

---

## 验收

逐条可勾：

- [ ] `mms_registry_cli.py` 759-765 在实现者自己的 base 上复核过，行号写进交付
- [ ] 三类代码各自映射出预期文案，未知代码保留原文，全部有单测
- [ ] 带冒号前缀的 guard reason（`route_shrink_guard: candidate would shrink...`）能正确匹配到 `route_shrink_guard`，有单测
- [ ] 多条同时出现时**全部显示**且**保持原顺序**，有单测（至少覆盖 `stable_root_human_only` + `no_draft_changes` 这一对）
- [ ] `blocked_reasons` 为空而 `plan["ok"]` 为假时有可用兜底，有单测
- [ ] 断言"不泄漏"：单测验证输出里**不含** `config_root` / `stable_root` / `preview_root` 的真实路径值，也不含 plan 的其他字段
- [ ] 真机构造 legacy root 场景，实测通道设置页顶部红字（491）显示新文案，截图
- [ ] 同一场景打开删除通道弹窗，实测弹窗内红字（1094）显示同一段新文案，截图
- [ ] 变更预览弹窗（1162）同样核对，截图
- [ ] 上面"一个必须查清、不许猜的疑点"有明确结论写进交付
- [ ] 选了 D.1 还是 D.2，理由写进交付；选 D.2 的话影响面核对结果一并写

## 门禁

**实测基线**（2026-09-16，两条线各跑一遍）：

| 门禁 | `origin/main` = `6c62a656` = 4.22.1 | `origin/dev` = `e5d32243` = 5.x |
| --- | --- | --- |
| `PYTHONPATH=. python3 -m pytest -q tests/test_mms_web_model_settings.py tests/test_mms_web_remote_access.py tests/test_mms_web_lan_switch.py tests/test_config_web.py` | **204 passed / 2 failed / 3 skipped** | **204 passed / 2 failed / 3 skipped** |
| `npx tsc --noEmit -p apps/mms-web` | **0 错** | **0 错** |
| `node --test apps/mms-web/tests/*.test.mjs` | **tests 56 / pass 56 / fail 0** | **tests 121 / pass 121 / fail 0** |
| `npm run build --workspace @mms/web` | 通过，css 148.95 kB / js 660.01 kB | 通过，css 223.13 kB / js 793.19 kB |

⚠️ **那 2 个 failed 是两条线上都已存在的既有失败，与本包无关**，不许当成自己引入的，也不许顺手去修：

```
FAILED tests/test_config_web.py::test_config_web_model_capability_defaults_are_profile_backed_not_hardcoded
FAILED tests/test_config_web.py::test_config_web_provider_model_fetch_returns_policy_capabilities
```

两条都是 `assert caps["reasoning"] is True` 失败（`test_config_web.py:4563` 一带），属于 model capability profile 的既有问题。**本包的门禁标准是：这个数字不变，且这两条仍然是唯一的 failed。**

本包必跑：

```bash
PYTHONPATH=. python3 -m pytest -q \
  tests/test_mms_web_model_settings.py tests/test_mms_web_blocked_reasons.py tests/test_config_web.py
npx tsc --noEmit -p apps/mms-web
node --test apps/mms-web/tests/*.test.mjs      # 必须带 *.test.mjs glob
npm run build --workspace @mms/web
```

`node --test apps/mms-web/tests/` **不带 glob 会直接报 `fail 1`**（README 已记录，2026-09-16 实测）。

跑前端门禁之前先在 worktree 里 `npm install`。

覆盖 `model_settings` 的测试文件，实现者已知的入口是 `tests/test_mms_web_model_settings.py`（**33** 个测试）与 `tests/test_config_web.py`（`test_config_web.py:2701` 有 `assert v2_plan["root"]["legacy_root"] is True`，是构造 legacy root plan 的现成参考）。实现者需自己确认是否还有别的文件覆盖到这条链路，并把最终清单写进交付。

## 并行规则

```
git worktree add ../wt-T7c -b bot/T7c-blocked-reasons origin/main
```

自己另起端口，**不碰 8767 和 60824**，不动 `.worktrees/main-4.22`。不提交、不 push、不 merge，等 owner 验收。
