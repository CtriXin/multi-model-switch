# T6a · 4.x ↔ 5.x 双向切换门禁

Date: 2026-09-16
Task: Stride 370e87ec37e741df
分支：`bot/T6a-channel-switch-gate`，**从 4.22.x 线开**（重组后是 `main`；重组尚未完成时用 `origin/dev`，本次基准 `1f466eea` = 4.22.1，等同 tag `v4.22.1`）
建议模型：k3 或 deepseek（后端 + 回归脚本，无前端）
来源：owner 2026-09-16 定下的新发布模型

先读：`docs/mms-web/bot-work/README.md`（并行规则、通用验收）、本文件，然后按下面"要读的代码"逐处确认。

## 背景：owner 定下的发布模型

- `main` = **4.22.x 永久稳定线**，不含 Bot。
- `dev` = **5.x**，含 Bot 工作台。
- 用户可以在设置里在两条线之间**升级和降级**，**同一台机器不能同时装两个**。
- 底层 mms 终端能力两条线**完全相同**（已验证，见下），配置共用 `~/.config/mms-next`。

**`~/.config/mms-next` 是单一配置根，这是 `docs/AGENT_GUARDRAILS.md` 里的 Single Config Root 硬规则。本包不许改它**，不许新增第二个配置来源，不许恢复 `~/.config/mms` 作为配置来源。

### 终端能力一致性：已验证，不要重新论证

2026-09-16 用 blob hash 逐文件比对 `v4.22.1` ↔ `origin/dev-pre`（5.0.1）：

```
IDENTICAL  mms_core.py
IDENTICAL  mms_launchers.py
IDENTICAL  mms_tui.py
IDENTICAL  mms
IDENTICAL  install.sh
IDENTICAL  mms_platform.py
```

五个受保护文件加 `mms_platform.py` **全部逐字节相同**。两条线之间**非新增**的 Python 差异只有四个文件：

| 文件 | 差异 |
| --- | --- |
| `mms_version.py` | `4.22.1` ↔ `5.0.1` |
| `mms_web/server.py` | Bot 路由、会话列表的 Bot 过滤、CSP `blob:` |
| `mms_web/sessions.py` | `owner` / `botId` 的写入 |
| `mms_web/updates.py` | `release_history()`，27 行 |

其余全是纯新增（9 个 `mms_web/bot*.py`、`browser_provider.py`、9 个测试文件）。

**⚠️ 分支现状订正**：`origin/main` 现在是 **4.10.0**（HEAD `ca6c09eb`），**不是 4.22 线**。重组完成前，4.22 的真值是 `origin/dev` / tag `v4.22.1`。上面那句"终端能力一致"对 `v4.22.1` 成立，**对当前的 `origin/main` 不成立**——重组必须先做完，否则这条发布模型的前提就是假的。**这一条要在交付里明确复述。**

## 问题：降级会出事，升级不会

用户在 5.x 里建了 Bot、定时、bot memory，退回 4.22 时那些记录 4.22 完全不认识。本包要把这条路做成可验证的门禁。

### 先说一个调查结论：`state.json` 的 schema 其实不是降级风险

`mms_web/bots.py:222` 那条 `if data.get("schema") != 2: raise ValueError("Unsupported bot record")` 是硬校验，错了就整份记录不可写（246-247 置 `_load_error`，249-251 起所有 `_persist` 抛 `BOT_STORE_INVALID` 409）。**但它守的那个文件，4.22 根本不会打开**——4.22 的 `mms_web/` 里一个 `bots` 路径字面量都没有。

所以：**不要把本包的预算花在防御这条校验上**，改成加一条"5→4.22→5 往返后这些文件原封不动"的断言即可。**同时，那条"5.x 永远不许升 schema"的约束仍然成立且必须写成验收项**——它防的不是降级，是"5.x 自己升了版之后，装着旧 5.x 的机器读不了新 5.x 写的记录"。

### 真正的风险只有一处：`sessions/<id>.json`

5.x 往共享的会话文件里写了两个 4.22 不认识的键：

- `"owner": "bot"`（`origin/dev-pre:mms_web/sessions.py:1533`，4.22 在 `v4.22.1:mms_web/sessions.py:1489` 硬写 `"owner": "web"`）
- `"botId": <bot_id>`（`origin/dev-pre:mms_web/sessions.py:1537-1538`）

两条线的 `schema` 都是 `1`（`v4.22.1:mms_web/sessions.py:338` ↔ `origin/dev-pre:mms_web/sessions.py:339-356`），加载器逻辑逐字相同（`v4.22.1:1496-1510` ↔ `origin/dev-pre:1543-1556`），只校验 `schema != 1` 和 `meta.get("id")`，**未知键原样带过，不会崩**。

**但是**：4.22 的 `list_sessions` 没有 Bot 过滤（`v4.22.1:mms_web/server.py:152` 是光秃秃的 `own = self._sessions().list_sessions() ...`；5.x 的过滤在 `origin/dev-pre:mms_web/server.py:163-180`，是 5.x 新加的），而 `session_view()`（`v4.22.1:mms_web/sessions.py:229-260`）硬写 `"owner": "web"`。

**⇒ 降级后，5.x 里每一个 Bot 用的 Pi 会话都会以普通聊天的身份出现在 4.22 的 Pilot 侧栏里，可点、可发消息、可删。** 用户一旦在 4.22 里动了它，`owner` 会被重新写成 `"web"`。再升回 5.x 时，靠 `server.py:163-180` 那个按 `bots/state.json` 的 `sessionId` 反查的兼容过滤才救得回来——**前提是那条 Bot / task 记录还在**。

### 两条次要问题（不致命，但用户看得见）

- `<state_root>/ui-preferences.json` 的 `whatsNewSeenVersion`（`ui_preferences.py:15`，两条线该模块逐字节相同）跑过 5.0.1 后是 `"5.0.1"`；降回 4.22.1 会让 4.22 的更新说明被判为"已读"而不显示。
- `<state_root>/updates/check.json` 缓存的 `latest` 是 5.x 的 tag；`updates.py:152-153` 的 `remote > current` 会让 4.22 立刻提示"有新版本"，一键就跳回 5.x。用户可能刚降级就被推回去。

## 要做成什么

### A. 把两条硬约束写成验收项

1. **5.x 永远不许升 `state.json` 的 `schema`。** 只能用 tolerant read 加新字段（`self._schedules = data.get("schedules", {})` 那种写法），`_persist` 里仍然硬写 `"schema": 2`。同理 `bot_memory.py` 的 `SCHEMA = 1`（`bot_memory.py:22`）、`bot_notify.py` 的 `{"schema": 1}`（`bot_notify.py:74`、`:173`）都不许升。
   **落地成一条测试**：断言这四处的 schema 字面量分别是 `2` / `1` / `1` / `1`。以后有人想升版，这条测试先红，逼他来读这份包。
2. **降级后 4.22 读到 Bot / schedule / memory 记录必须是忽略，而不是报错或白屏。** 门禁里要真的把 5.x 写出来的 state root 喂给 4.22 的加载路径，断言：进程能起、`GET /api/v1/bootstrap` 200、会话列表能返回、**没有 500、没有未捕获异常**。

### B. 把 Bot 数据落盘清单查清并写进包

不要凭这份包里的清单实现——**自己去代码里复核一遍**，把结果写进交付。已查到的（2026-09-16 在 `origin/dev-pre`）：

| 路径（相对 state root） | 写它的地方 | schema | 4.22 会读吗 |
| --- | --- | --- | --- |
| `bots/state.json` | `bots.py:197`（root）、`:217`（path）、`:222`（校验）、`:261`（写 `"schema": 2`） | 2 | **否** |
| `bots/owner.lock` | `bots.py:254`（flock，占用报 `BOT_STORE_BUSY` 409） | — | **否** |
| `bots/memory/<botId>/memory.json` | `bot_memory.py:70`（root）、`:78-81`（per-bot）、`:22`（`SCHEMA = 1`）、`:100-101`（校验） | 1 | **否** |
| `bots/memory/<botId>/owner.lock` | `bot_memory.py:78-81` | — | **否** |
| `bots/notifications.json` | `bot_notify.py:51-52`、`:74` | 1 | **否** |
| `bots/notify.json` | `bot_notify.py:51-52`、`:173` | 1 | **否** |
| `bots/contexts/<taskId>.json` | `bots.py:1620-1621`（endpoint URL + task token） | — | **否** |
| `bots/screenshots/<taskId>/` | `bots.py:464`、`:1824`；`bot_computer.py:190-194`（0o700） | — | **否** |
| `bots/ego-spaces.json` | `bot_computer.py:43-44`、`:187` | version 1 | **否** |
| `bots/space-creation/<taskId>.json` | `bot_computer.py:70`、`:125` | — | **否** |

**整个 `<state_root>/bots/` 子树都是 Bot 专属，4.22 看不见——这是最安全的形状，本包要保住它。**

不写自己文件的 Bot 模块（状态落在 `bots/state.json` 里）：`bot_communications.py`（mixin）、`bot_coordinator.py`、`bot_retry.py`、`bot_executor.py`。

**共享文件才是风险点**（4.22 会读的）：`sessions/<id>.json`（**唯一真风险**）、`artifacts/<digest>/index.json`、`runtimes/<hex>/`、`ui-preferences.json`、`updates/check.json`、`config/`、`workspaces.json`、`model-settings/`、`attachments/`、`project-materials/`、`previews/`、`launch-home/`、`remote-access.json`。

**交付里要给出一张\"5.x 会往哪些共享文件里写 Bot 相关内容\"的确认清单**，并对每一条回答"4.22 读到会怎样"。上面只确认了 `sessions/<id>.json` 一条，**其余要自己核实，不要照抄**。

### C. 给 `scripts/regression_fresh_user_gate.py` 加一条双向切换场景

场景（顺序不许改）：

```
装 4.22 → 升 5.x → 建 Bot 和定时 → 降回 4.22
  → 确认能正常启动且不报错
  → 再升回 5.x → 确认 Bot 数据还在
```

**怎么加（照它现有 scenario 的写法，不要自创）：**

- `_SCENARIO_MATRIX` 是模块级 `list[dict]`，在 **114-191** 行，每条只有 `id` / `state` / `coverage` 三个字符串键。
- **它只是文档，不会自动派发。** `main()` 在 **553-558** 行按名字手动调 `_smoke_*` 函数。**所以加一条场景是两处改动**：矩阵里加一条 + 写一个 `_smoke_*` 函数并在 `main()` 里接上。
- 照抄的样板是 **126-130** 行那条 `shared-config-root-default`，它的实现是 **254-304** 行的 `_smoke_shared_config_root_default()`，在 `main()` **554** 行被调用。
- 现成的 helper：`_SCRUB_ENV_KEYS`（**29-44**，清掉 `MMS_CONFIG_ROOT` / `REAL_HOME` / `ORIGINAL_HOME` / `MMS_REAL_HOME` / `XDG_CONFIG_HOME` 等 14 个键）、`_base_env()`（**194-199**）、`_env_for_home(home)`（**202-205**）、`_run(label, argv, env=)`（**208-224**，非零直接 `raise SystemExit`）、`_pytest_command()`（**227-231**）、`_safe_symlink()`（**307-313**）、`ROOT_DIR`（**25-27**）。
- 断言风格：**没有 `assert`、没有 unittest**。用 `tempfile.TemporaryDirectory(prefix="mms-...")` 造假 `HOME`，`_run` 跑真 CLI，`json.loads(completed.stdout)`，不符就 `raise SystemExit(f"...mismatch: {x} != {y}")`。跨进程探测用内联 `python3 -c` 片段（**290-301** 行有现成例子）——**这正是"用另一条线的代码去读这一条线写出来的 state root"要用的手法**。
- `--list-scenarios`（**544** 行声明，**547-549** 行处理）是纯打印零副作用，可以放心跑。`_print_scenarios()` 在 **535-538**。
- 今天是 **15 条场景**：`pi-isolated-global-policy`、`fresh-mmf-preview-root`、`shared-config-root-default`、`legacy-dirty-install-cleanup`、`reset-reinstall-state`、`repeatable-install-dry-run`、`retired-automatic-hooks`、`resume-explicit-only`、`retired-optional-pack-cleanup`、`retired-builtin-commands`、`npx-install-entry`、`install-entry-parity`、`one-question-install`、`pi-btw-bundled-extension`、`codex-hook-trust-and-history`。**没有一条覆盖降级、版本切换、或两条线共存**——这就是本包要填的洞。

**场景要断言的东西（逐条）：**

1. 降回 4.22 后进程能起，`GET /api/v1/bootstrap` 200，不出 500。
2. 降回 4.22 后 `<state_root>/bots/` 下每个文件的**内容和 mtime 都没被动过**（4.22 不认识就不该碰）。
3. 再升回 5.x 后，Bot、schedule、bot memory 都还能读出来，`bots/state.json` 的 `schema` 仍是 `2`，没有 `_load_error`。
4. **降级后 Bot 会话在 4.22 侧栏里的表现**：按上面"真正的风险"那一节，5.x 写的 `owner:"bot"` / `botId` 会让 Bot 会话以普通聊天出现。断言这个事实**成立**（这是当前行为，不是 bug 修复），并在 `coverage` 文案里写明它是已知代价；**如果本包同时修了它**（见 D），就改成断言修好后的行为。
5. `ui-preferences.json` 的 `whatsNewSeenVersion` 在降级后的取值，以及它对 4.22 更新说明的影响。
6. `updates/check.json` 缓存的 tag 在降级后的取值。

### D. 关于"要不要顺手修 Bot 会话泄漏"

**本包默认不修，只把它变成一条被门禁盯住的已知行为。** 理由：修它要动 4.22 的 `server.py:152` 或 `sessions.py:246`，那是稳定线，超出"加门禁"的范围。

如果 owner 要求修，最小做法是在 **4.22** 的 `list_sessions` 里按 `meta.get("owner") == "bot"` 过滤掉——**不需要 4.22 知道 Bot 是什么，只要它认得这个字符串**。这条写进"需要 Fable 确认"，不要自己拍板。

## 关于 base 分支：为什么写在 4.x 侧

**base = 4.22.x 线**（重组后是 `main`；今天是 `origin/dev` / `v4.22.1`）。

理由：**owner 定的流向是"4.x 的所有改动默认进入 5.x"**。所以门禁写在 4.x 侧会自动流到 5.x，两条线都被覆盖；反过来写在 5.x 侧则永远不会回到 4.x，而**降级后跑的恰恰是 4.x 的代码**——门禁不在那一侧就等于没有。

`scripts/regression_fresh_user_gate.py` 在 `v4.22.1` 和 `origin/dev-pre` 上**逐字节相同**，所以在 4.x 侧加的场景能干净地流进 5.x，不会产生冲突。

## 只许改

- `scripts/regression_fresh_user_gate.py`：`_SCENARIO_MATRIX` 加一条 + 新增一个 `_smoke_*` 函数 + `main()` 里接上
- 新增 `tests/test_mms_channel_switch_contract.py`（A 的两条约束落成测试；schema 字面量断言写在这里）
- `docs/mms-web/` 下新增或追加一节说明双向切换的契约与已知代价
- 若 owner 确认要修 D，才允许动 4.22 的 `mms_web/server.py` 的 `list_sessions` 一处（≤ 5 行）

## 不许改

- **`~/.config/mms-next` 的单一配置根规则**（`docs/AGENT_GUARDRAILS.md` 的 Single Config Root）。不许新增第二个配置来源，不许恢复 `~/.config/mms` 作为配置来源。
- 受保护文件：`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`、`ccs`、`install.sh`
- `mms_web/bots.py`、`bot_memory.py`、`bot_notify.py` 的 schema 值（本包是来钉住它们的，不是来改的）
- `mms_web/updates.py`、`update_coordinator.py`、`update_stage.py`、`update_install.py` —— **本包不实现切换功能，只加门禁**。真要做降级还得改这四处（见下），那是另一个包。
- 真实 `~/.config/mms*` 和真实 state root（一律用临时 `HOME`）
- 任何 `apps/mms-web/**`
- **不要重启 60824，不要动 8767**（owner 在用的实例）

### 附：真要实现降级得改哪四处（本包不做，写在这里免得下一个包再查一遍）

1. `mms_web/updates.py:14-17` —— 来源硬编码成 GitHub 的 `releases/latest` 单一通道，`TAG = re.compile(r'^v(\d+)\.(\d+)\.(\d+)$')` 不接受分支形式。
2. `mms_web/updates.py:152-153` —— `available = bool(remote and current and remote > current)`，**严格大于**，低版本永远不会 `updateAvailable`。
3. `mms_web/update_coordinator.py:59` —— `target != latest['latest'].get('tag')` 就抛 `UPDATE_UNAVAILABLE` 409，目标必须等于那个唯一的缓存 latest。
4. `mms_web/update_stage.py:19-22`、`:101-103` —— 同一套 tag 正则 + 按 tag 拉 codeload tarball；`validate_bundle`（**64-68**）还断言 `manifest['version'] == tag`。

现有唯一的"线"记录是 `install.sh` 写的 `$CONFIG_ROOT/version.json`（即 **`~/.config/mms-next/version.json`**，`install.sh:92-93` + `527-541`），里面有 `install_channel` / `resolved_ref` / `track_id` / `track_version` / `track_label`；`--channel stable|dev|canary` 的解析在 `install.sh:2552-2566`，ref 解析在 `613-628`（注意 `DEV_CHANNEL_REF` 默认是 **`dev`**，不是 `dev-pre`）。UI 上该放线切换的地方是 `apps/mms-web/src/UpdateCenter.tsx`（`App.tsx:1673` 挂载），`SettingsPage.tsx:114` 只是入口。

## 门禁

```bash
# 1. 新增的契约测试
PYTHONPATH=. python3 -m pytest -q tests/test_mms_channel_switch_contract.py

# 2. 完整版新用户 gate（必须过）
python3 scripts/regression_fresh_user_gate.py

# 3. 场景清单（确认新场景已注册）
python3 scripts/regression_fresh_user_gate.py --list-scenarios
```

**第 2 条必须跑完整版，不许只跑 `--quick`。** gate 在这台机器上本来就有既存失败项，**用与既存失败集的 diff 判断，不看绝对值**。

**加新场景后的实际用例数要报出来**（今天是 15；加完应当是 16，或者你拆成了几条就报几条）。

## 验收清单（逐条可勾）

调查：

- [ ] 复核并给出 Bot 数据落盘清单，逐条标注"4.22 会不会读"。与本包表格有出入的地方逐条说明。
- [ ] 给出"5.x 会往哪些共享文件里写 Bot 相关内容"的确认清单，每条回答"4.22 读到会怎样"。
- [ ] 复述并确认分支现状：`origin/main` 当前是 4.10.0 而非 4.22，重组未完成前本发布模型的前提不成立。

硬约束：

- [ ] `tests/test_mms_channel_switch_contract.py` 断言 `bots.py` 的 schema 字面量是 `2`、`bot_memory.py:22` 的 `SCHEMA` 是 `1`、`bot_notify.py` 两处是 `1`。任一被改则测试红。
- [ ] 门禁里真的用 5.x 写出来的 state root 喂 4.22 的加载路径，断言进程能起、bootstrap 200、无 500、无未捕获异常。

回归场景：

- [ ] `_SCENARIO_MATRIX` 里多了一条双向切换场景，`id` / `state` / `coverage` 三个键齐全，文风与现有 15 条一致。
- [ ] 对应的 `_smoke_*` 函数已写，并在 `main()` 里接上（**两处都要，矩阵不会自动派发**）。
- [ ] 场景用临时 `HOME`，且清掉了 `_SCRUB_ENV_KEYS` 里那 14 个变量（用现成的 `_env_for_home`，不要自己拼 env）。
- [ ] 场景覆盖完整顺序：装 4.22 → 升 5.x → 建 Bot 和定时 → 降回 4.22 → 起得来不报错 → 升回 5.x → Bot 数据还在。
- [ ] 断言降级后 `<state_root>/bots/` 下的文件内容未被改动。
- [ ] 断言升回 5.x 后 `bots/state.json` 的 `schema` 仍是 2 且没有 `_load_error`。
- [ ] `ui-preferences.json` 的 `whatsNewSeenVersion` 与 `updates/check.json` 的缓存 tag 在降级后的取值各有一条断言或一条明确记录。
- [ ] Bot 会话在 4.22 侧栏里的表现有一条断言（或按 D 的确认结果改成修复后的行为）。

门禁：

- [ ] `python3 scripts/regression_fresh_user_gate.py` 完整版通过（与既存失败集 diff 为空）。
- [ ] `--list-scenarios` 的实际条数已报出（今天基线 15）。
- [ ] `PYTHONPATH=. python3 -m pytest -q tests/test_mms_channel_switch_contract.py` 全过。
- [ ] `python3 -m py_compile` 覆盖所有改动到的 Python 文件。
- [ ] 没有改 `~/.config/mms-next` 单一配置根规则，没有引入第二个配置来源。
- [ ] 没有重启 60824，没有动 8767。

## 并行规则

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch
git fetch origin
git worktree add .worktrees/wt-T6a -b bot/T6a-channel-switch-gate origin/dev   # 重组完成后用 origin/main
cd .worktrees/wt-T6a
```

端口 61754。不碰 60824 和 8767。**不提交、不 push、不 merge。**

## 交付格式

照 README 的通用验收，写进 worktree 的 `walls.md`（追加，不改旧条目）：

```
包：T6a
分支 / worktree / base ref（含实际 commit）：
改动文件：git diff --stat 输出
调查结论：Bot 数据落盘清单、共享文件风险清单、与本包表格的出入
新增场景：id、覆盖的断言、--list-scenarios 加完之后的条数
门禁：fresh-user gate 完整版结果（与既存失败集的 diff）、契约测试通过数、py_compile
未完成 / 未验证：逐条
需要 Fable 确认：逐条
```

## 需要 Fable 确认

1. **`origin/main` 还不是 4.22 线**（现在是 4.10.0）。本包的 base 写成"4.22.x 线（重组后是 `main`）"，今天实际用 `origin/dev` / `v4.22.1`。重组的时点和顺序由 owner 决定，本包不代做。
2. **Bot 会话泄漏到 4.22 侧栏，本包默认只加断言不修**（见 D）。要不要在 4.22 的 `list_sessions` 里按 `owner == "bot"` 过滤，请确认。
3. **降级后 `updates/check.json` 会立刻把用户推回 5.x**。要不要在本包里把它也变成一条断言并给出处置建议（例如降级时清掉该缓存），请确认——本包默认只记录现象。
4. **`whatsNewSeenVersion` 让降级后看不到 4.22 的更新说明**，属于既存设计（它存的是版本号不是布尔）。本包默认只记录，不改 `ui_preferences.py`。
5. **本包不实现切换功能本身**，只加门禁和契约。真正的降级实现要改上面列出的四处 update 链路代码，那是另一个包。请确认这个边界。
6. **场景跑一次要装两条线两次、切换两回**，在 gate 里是明显更慢的一条。如果 owner 希望它只进完整版不进 `--quick`，本包默认就是这样（`_QUICK_PYTEST_TARGETS` 在 95-112 行，不动它）。
