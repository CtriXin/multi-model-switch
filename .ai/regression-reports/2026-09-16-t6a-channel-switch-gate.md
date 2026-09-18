# Regression Report · T6a channel-switch gate

- Timestamp: 2026-09-16 12:13 +08 (Asia/Singapore)
- Task/scope: Stride 370e87ec37e741df · 包 T6a（`docs/mms-web/bot-work/T6a-channel-switch-gate.md`）——4.x ↔ 5.x 双向切换门禁 + 降级泄漏内部会话的前向兼容修复。
- Branch/base: `bot/T6a-channel-switch-gate` ← `origin/main` `6c62a656`（4.22.1 稳定线 HEAD；重组已完成，`origin/dev` = 5.0.1）。
- Worktree: `.worktrees/main-4.22`（与 T6b 会话共用，提交时只 add 本包路径）。

## Changed files

```
docs/mms-web/CHANNEL-SWITCHING.md            | 新增契约文档
mms_web/server.py                            |   4 +   (all_sessions 允许式过滤)
mms_web/sessions.py                          |  13 +-  (session_view 如实回显 owner；get_session 拒绝未知 owner)
scripts/regression_fresh_user_gate.py        | 330 +++  (channel-switch-round-trip 场景 + 2 个 pytest 目标)
tests/test_mms_channel_switch_contract.py    | 新增（schema 字面量钉住 + foreign state root 忽略）
tests/test_mms_session_owner_forward_compat.py | 新增（D 修复测试，5 例）
```

## Expected behavior

- 5.x 写的 `owner != "web"` 会话在 4.x：不出现在 `/api/v1/sessions` 列表、按 id 查询 404、文件逐字节不动；`owner` 缺省或 `"web"` 的会话不受影响；cli 会话路径不受影响。
- `<state_root>/bots/` 子树对 4.x 完全不可见，降级往返后内容与 mtime 不变；升回 5.x 后 bot / schedule / memory 可读，schema 仍为 2，无 `_load_error`。

## Regression risk / blast radius

- `session_view()` 的 `owner` 从硬写 `"web"` 变为如实回显：本线所有持久化路径只写 `"web"`（`_build_meta` 硬写），视图层唯一变化是旧外来文件不再被洗值。`update_handoff` 不消费 `owner`；前端只判 `=== "cli"` / `!== "cli"`，未知值到不了前端（列表层已挡）。
- `all_sessions()` 过滤影响 `claimed` 集合（cli 去重）：外来 owner 会话不再屏蔽同名 cli 行——正是期望行为。
- `get_session()` 的 404 拒绝**只覆盖详情查询**。按 id 的 mutation 端点仍可达：2026-09-16 经 owner 实测，带合法 CSRF 的 `POST /api/v1/sessions/<id>/manage` 对未知 owner 会话返回 200 并改写了该会话文件（`session_actions.py` / `model_switch.py` / adopt 等路径不经 `get_session()` 的 guard）。这是 D2 (b) 的已知残留——列表与详情被挡住，但拿到 id 的调用者仍能 mutate；本包按范围只修列表 + 详情两处。
- gate 场景需要本机 git refs（`origin/dev` / `origin/main`）与 ephemeral 端口；不触网（`MMS_WEB_UPDATE_CHECK=0`）。

## Commands run

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=. python3 -m pytest -q tests/test_mms_channel_switch_contract.py tests/test_mms_session_owner_forward_compat.py` | **9 passed**（含 owner=="cli" 防误伤端到端断言） |
| 同上文件在真 5.x 树（`/tmp/t6a-5x` = `origin/dev` 5.0.1）上跑 contract 测试 | **3 passed**（schema 分支真实命中 5.x 字面量） |
| `PYTHONPATH=. python3 -m pytest -q tests/test_mms_web_server.py tests/test_mms_web_sessions_service.py tests/test_mms_web_sessions_launch.py tests/test_mms_web_sessions_pi_driver.py` | base 基线 64 passed + 4 subtests → 改后 **64 passed + 4 subtests**（无下降） |
| `PYTHONPATH=. python3 -m pytest -q tests/test_mms_web_adopt_cli_session.py tests/test_mms_web_cli_sessions.py tests/test_mms_session_packet.py tests/test_mms_web_session_heartbeat.py` | base 41 passed → 改后 **41 passed** |
| `python3 scripts/regression_fresh_user_gate.py`（完整版） | base：1 failed / 698 passed（`test_pi_launcher.py::test_launch_pi_rewrites_deprecated_antigravity_gemini_alias_to_live_replacement`，既存）；改后：**1 failed / 707 passed**，失败集 diff 为空；新增 `channel-switch-round-trip` 场景在完整版内通过 |
| `python3 scripts/regression_fresh_user_gate.py --quick` | **exit 0 / 141 passed**；`channel-switch-round-trip` 按代码条件跳过（只进完整版） |
| `python3 scripts/regression_fresh_user_gate.py --list-scenarios` | **16 条**（基线 15 + 新增 1） |
| 变异检查：stash 掉 `sessions.py`/`server.py` 修复后单跑新场景 | **如预期失败**："a session owned by something this line does not know leaked into the list" |
| `python3 -m py_compile`（全部改动到的 .py） | 通过 |

## Known unrelated failures / skipped

- `tests/test_pi_launcher.py::test_launch_pi_rewrites_deprecated_antigravity_gemini_alias_to_live_replacement` 在 base 上既存失败（base 完整 gate 日志 `/tmp/t6a-gate-baseline.log`），与本包无关。
- 前端未改（D 是纯后端修复，`types.ts:88` 联合类型保持不含 `"bot"`），故未跑 `node --test` / `tsc`。
- 场景端到端起了真 4.x 服务器（ephemeral 端口、临时 HOME/state root），未触碰 60824 / 8767，未读写真实 `~/.config/mms*`。

## Final status

PASS（相对 base 基线无回归；既存失败集 diff 为空）。

## 2026-09-16 复审后修订（owner 反馈，PR #279）

1. `walls.md` 已从提交中整个摘除——walls 是任务本地日志，不进长期分支（本地原件保留在 `.worktrees/main-4.22/walls.md`，未提交）。
2. mutation 残留句已按实测证伪修订（见上「Regression risk」末条）。
3. `channel-switch-round-trip` 此前在 `main()` 里无条件调用、`--quick` 也会跑；已改为 `if not args.quick` 条件调用，与「只进完整版」的交付描述一致。
4. `tests/test_mms_session_owner_forward_compat.py` 顶部补 CONVERGENCE 注释（三条 404 断言合流进 5.x 必然变红，这是预期信号）；并补 `owner=="cli"` 防误伤端到端断言。
