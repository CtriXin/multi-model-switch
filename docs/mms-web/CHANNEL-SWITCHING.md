# 4.x ↔ 5.x 双向切换契约（T6a）

> Date: 2026-09-16 · Task: Stride 370e87ec37e741df · 包：`bot/T6a-channel-switch-gate`
> 适用对象：两条安装线共用同一个 state root 的发布模型——`main` = 4.22.x 永久稳定线（无 Bot 工作台），`dev` = 5.x（含 Bot 工作台）。用户可以在两条线之间升级和降级，同一台机器不能同时装两个。

## 前提

- `~/.config/mms-next` 是单一配置根（`docs/AGENT_GUARDRAILS.md` 的 Single Config Root 硬规则），两条线共用，本契约不改它、不新增第二个配置来源。
- 底层 mms 终端能力两条线逐字节相同（`mms_core.py` / `mms_launchers.py` / `mms_tui.py` / `mms` / `install.sh` / `mms_platform.py`，2026-09-16 已用 blob hash 比对验证）。
- 本包**不实现切换功能本身**，只钉住契约、门禁和一处前向兼容修复。真正实现降级要改 `mms_web/updates.py:14-17`（单一通道）、`updates.py:152-153`（严格大于才提示）、`update_coordinator.py:59`（目标必须等于缓存 latest）、`update_stage.py:19-22 / :101-103`（tag 正则 + codeload 拉包 + `validate_bundle` 断言版本等于 tag）这四处，那是另一个包。

## 硬约束（已落成测试）

1. **5.x 永远不许升 Bot store 的 schema。** `bots/state.json` 保持 `"schema": 2`，`bot_memory.py` 保持 `SCHEMA = 1`，`bot_notify.py` 两处保持 `"schema": 1`。新字段只能用 tolerant read（`data.get("schedules", {})` 式）添加。它防的不是降级（4.x 根本不打开 `bots/` 子树），而是"5.x 自己升版后，装着旧 5.x 的机器读不了新 5.x 写的记录"。
   测试：`tests/test_mms_channel_switch_contract.py::test_bot_store_schema_literals_are_pinned`——在 5.x 线上断言字面量，任一被改则测试红；在 4.x 线上反向断言 `mms_web/` 不存在这三个模块、且没有任何源码引用 `bots/` state 子树。
2. **降级后 4.x 读到 Bot / schedule / memory 记录必须是忽略，不是报错或白屏。** 整个 `<state_root>/bots/` 子树是 5.x 专属，4.x 一个 `bots` 路径字面量都没有——这是最安全的形状，必须保住。
   测试：同文件的 `ForeignStateRootIgnoreTests`，把含 5.x 形状（甚至故意损坏）的 `bots/` 子树的 state root 喂给 4.x，断言 bootstrap 200、会话列表 200、文件逐字节不动。
   门禁场景：`scripts/regression_fresh_user_gate.py` 的 `channel-switch-round-trip` 用真 5.x 代码写 state root、起真 4.x 进程验证、再用真 5.x 代码回读。

## 降级泄漏修复：忽略不认识的会话所有者

5.x 会往共享的 `sessions/<id>.json` 里写 4.x 不认识的键（`owner` 非 `"web"` 的值、以及 `botId`）。两条线的加载器对未知键都原样带过、不会崩，但 4.x 曾经的 `session_view()` 把 `owner` 硬写成 `"web"`，于是那些内部会话会以普通聊天的身份出现在 Pilot 侧栏，可点、可发消息、可删，用户一动它 `owner` 就被洗回 `"web"`。

修复形状（**通用前向兼容，不含任何 Bot 概念**——4.x 上不存在 Bot 这个词）：

1. `mms_web/sessions.py` `session_view()`：如实回显 `owner`，缺省仍是 `"web"`。**不改这一处，列表过滤就是死代码**——`list_sessions()` 返回的是 view 输出，view 曾把真值抹掉。
2. `mms_web/server.py` `all_sessions()`：允许式过滤，只保留 `owner` 是本线认识的会话（这条路径上唯一合法值是 `"web"`），其余一律忽略。注释写"忽略不认识的所有者"，不写"排除 Bot"。
3. `mms_web/sessions.py` `get_session()`：列表过滤挡不住直接按 id 打开，而 4.x 上没有任何正当消费者，所以详情查询一并拒绝（404）。
   **⚠️ CONVERGENCE：这一处故意与 5.x 不同**——5.x 保留按 id 寻址（Bot 任务详情要靠它）。改动处带醒目注释；合流时这一处必须被 5.x 的行为覆盖。
   **已知残留**：该 guard 只拦详情查询；按 id 的 mutation 端点（如 `POST /api/v1/sessions/<id>/manage`）不经 `get_session()`，仍可改写该会话文件（2026-09-16 实测）。本包范围只修列表 + 详情两处，mutation 面的收紧留给后续包。

前端不用改：带未知 `owner` 的行在列表层就被挡掉，不会有超出 `types.ts:88` 联合类型（`"web" | "cli" | "glint" | "external"`）的值到达前端，**不许**给该联合类型加 `"bot"`。

测试：`tests/test_mms_session_owner_forward_compat.py`（view 如实回显、列表隐藏、详情 404、普通 web 会话不误伤、文件不被改写、HTTP 端到端）。

## 合流提醒（4.x → 5.x 流向）

- 两边的列表过滤形状不同：4.x 是**允许式**（只留 `"web"`），5.x 是**排除式**（`owner != "bot"` 外加按 Bot 记录反查 `sessionId` 的 legacy 兜底）。对现存取值两者行为等价，但 5.x 的 legacy 兜底**更严**（能挡住 owner 标记引入之前创建、仍持久化成 `owner=web` 的旧 Bot 会话）。**合流时不许用 4.x 的简单过滤覆盖 5.x 的兜底。**
- `get_session()` 的拒绝同理：合流时必须让 5.x 的按 id 寻址行为赢。

## 已知代价（本包只记录，不修复）

降级后跑 4.x 时：

1. `<state_root>/ui-preferences.json` 的 `whatsNewSeenVersion` 存的是 5.x 的版本号（既存设计：存版本号不是布尔，让每次升级都能亮一次更新说明）——4.x 的更新说明会被判为"已读"而不显示。
2. `<state_root>/updates/check.json` 缓存的 `latest` 仍是 5.x 的 tag；`updates.py` 的 `remote > current` 会让 4.x 立刻提示"有新版本"，一键就跳回 5.x。是否要在未来真正实现降级的包里清掉这个缓存，留给那个包决定。

两条都在门禁场景 `channel-switch-round-trip` 里有断言（断言的是**现状**）：将来有人修掉其中一条，门禁会先红，逼他来更新这份契约。

## 5.x 会往哪些共享文件里写 Bot 相关内容（2026-09-16 复核）

| 共享路径（相对 state root） | 5.x 写入内容 | 4.x 读到会怎样 |
| --- | --- | --- |
| `sessions/<id>.json` | `owner` 非 `"web"` 的值、`botId` 键 | **唯一真风险，本包已修**：列表忽略 + 详情 404 + 文件不动 |
| `artifacts/<digest>/index.json` 等 | Bot 会话事件引用的成果 blob（内容寻址） | 4.x 只按自己会话的事件反查 digest，多余条目是惰性死数据，不会被读 |
| `runtimes/<hex>/` | Bot 会话的运行时快照（resume.json 等） | 4.x 只按自己会话 meta 里的 `runtimeRoot` 寻址，多余目录不被读 |
| `ui-preferences.json` | `whatsNewSeenVersion` = 5.x 版本 | 见"已知代价"1 |
| `updates/check.json` | 缓存 tag = 5.x | 见"已知代价"2 |
| `config/`、`workspaces.json`、`model-settings/`、`attachments/`、`project-materials/`、`previews/`、`launch-home/`、`remote-access.json` | 5.x 的 Bot 路径**不写**这些（已逐处复核：`bot*.py` 的落盘全部在 `bots/` 子树内；Bot 会话用 `workspaceId="default"` 这个内部提示，不写 workspaces.json） | 不适用 |

`<state_root>/bots/` 子树清单（全部 4.x 不可见）：`state.json`（schema 2）、`owner.lock`、`memory/<botId>/memory.json`（schema 1）+ 各自 `owner.lock`、`notifications.json`（schema 1）、`notify.json`（schema 1）、`contexts/<taskId>.json`、`screenshots/<taskId>/`（0o700）、`ego-spaces.json`（version 1）、`space-creation/<taskId>.json`。不写自己文件的 Bot 模块（状态落在 `bots/state.json` 里）：`bot_communications.py`、`bot_coordinator.py`、`bot_retry.py`、`bot_executor.py`。

## 门禁

```bash
PYTHONPATH=. python3 -m pytest -q \
  tests/test_mms_channel_switch_contract.py \
  tests/test_mms_session_owner_forward_compat.py
PYTHONPATH=. python3 -m pytest -q tests/test_mms_web_server.py \
  tests/test_mms_web_sessions_service.py tests/test_mms_web_sessions_launch.py \
  tests/test_mms_web_sessions_pi_driver.py
python3 scripts/regression_fresh_user_gate.py            # 完整版，含 channel-switch-round-trip
python3 scripts/regression_fresh_user_gate.py --list-scenarios
```
