# Core / Launcher 下一轮瘦身 Worktree Handoff

Date: 2026-05-27
Owner: Codex
CLI: codex
Model: gpt-5.5
Status: active

## 结论

下一轮瘦身已经准备在独立 worktree 继续，不再占用已合并的 OpenCode 分支，也不在 dirty main 上直接开发。

- 下一轮 worktree：`/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/.worktrees/core-launcher-slimming-next`
- 下一轮 branch：`refactor/core-launcher-slimming-next`
- 起点 commit：`b126b23 merge: opencode agents module`
- 旧 OpenCode 分支：`refactor/opencode-agents-module`，已经合并进 `main`
- main 当前已知 unrelated dirty：`docs/MMF_CONFIG_ROOT_V2_DB_TRUTH.md`，不要碰

## 现在已经做完什么

OpenCode 瘦身阶段已经完成并合并：

- `mms_launchers.launch_opencode` 已缩成 wrapper。
- OpenCode 主流程已拆到 `mms_opencode_*.py`。
- 可见 OpenCode profile 已收敛为 `agent` / `omo` / `raw`。
- 旧 `lite_pro*` / `backend` / `acp` / `pro solo` 等只保留 compatibility alias，不再作为主要 UI 面。
- `[opencode.agent_models]` 与 `[opencode.agent_roster]` 已进入 launcher 消费路径，WebUI 后续可以接上。
- 旧 numbered scene selector 已退役。

合并与验证证据：

- merge commit：`b126b23 merge: opencode agents module`
- OpenCode branch handoff doc：`docs/CORE_LAUNCHER_SLIMMING_ROADMAP.md`
- main merge regression report：`.ai/regression-reports/2026-05-27-opencode-module-main-merge.md`
- issue-tracking：`/Users/xin/issue-tracking/issues/multi-model-switch/mms-core-launcher-slimming-merge-20260527/issue.md`
- post-merge focused validation：`153 passed`

## 下一轮我要负责什么

下一轮只做 Core / Launcher 减负，不扩展新产品模式。

优先顺序：

1. Claude env / launch 拆分
   - 目标模块：`mms_claude/env.py`、`mms_claude/launch.py`
   - 从 `mms_launchers.py` 移出 `_claude_gateway_env` 和 `launch_claude` 的大块实现。
   - 保留 `mms_launchers.launch_claude` wrapper，避免破坏调用方和 tests monkeypatch。

2. Codex env / launch 拆分
   - 目标模块：`mms_codex/env.py`、`mms_codex/launch.py`
   - 从 `mms_launchers.py` 移出 `_codex_gateway_env` 和 `launch_codex` 的大块实现。
   - 保留 `mms_launchers.launch_codex` wrapper。

3. shared launcher export helpers
   - 目标模块：`mms_launcher/export.py`
   - 只搬通用 export/env host-tool 注入，不把 CLI-specific 行为过早抽象掉。

4. TUI launcher flow 拆分
   - 目标模块：`mms_tui_launcher_flow.py`
   - 从 `mms_core.py` 移出 `_handle_tui_launcher_selection` 的主流程。
   - 不改变 TUI 返回结构、不改默认 source/account/provider 选择语义。

## 第一刀怎么做

第一刀建议只做 Claude extraction 的安全搬迁，不改行为。

执行边界：

- 先定位 `launch_claude`、`_claude_gateway_env`、Claude settings/hooks materialization 的调用关系。
- 新增 `mms_claude/env.py`，把纯 env/settings/helper 代码搬进去。
- 新增 `mms_claude/launch.py`，把 launch flow 主体搬进去。
- `mms_launchers.py` 只保留兼容 wrapper 和必要 re-export。
- 每次搬一块就跑 targeted tests，不把 Claude/Codex/TUI 同时混在一个 commit。

最低验证：

- `rtk python3.13 -m py_compile mms_launchers.py mms_claude/env.py mms_claude/launch.py`
- Claude 相关 focused tests，至少覆盖 hardening / visibility / launcher path。
- `git diff --check`
- 如果启动 smoke 触发 MMS Snapshot Guard，不执行 `guard accept`，只记录被阻止。

## 安全边界

必须遵守：

- 不写真实 `~/.config/mms/**`。
- Claude config 是 `human-only`，只允许读、比对、生成建议，不自动落盘。
- 不改变 `auth_mode` 语义。
- 不改变 provider/account resolution order。
- 不引入 real HOME / global OAuth fallback。
- 不改变 Anthropic/OpenAI transport default 或 cache-sensitive routing。
- 不重引入 `ccs` entrypoint、`~/.config/ccs`、`CCS_*`。
- 不碰 main 的 unrelated dirty `docs/MMF_CONFIG_ROOT_V2_DB_TRUTH.md`。

## 当前已知风险

- Full pytest 已知有一个 main 既有失败：`tests/test_claude_hardening_regressions.py::test_build_claude_session_settings_rewrites_caveman_hooks_per_session`。
- 这个失败和 OpenCode extraction 无关；后续若要处理，需要单独 scope。
- Claude/Codex extraction 风险高于 OpenCode，因为涉及 auth、HOME isolation、hooks、provider resolution。
- live launch smoke 可能被 MMS Snapshot Guard 阻止；不要为了 smoke 自动接受真实配置快照。

## Offduty 落点说明

worktree 项目里，`offduty` 的落点取决于执行时的 `--root` / 当前 cwd。

- 如果在原始 main 根目录执行，continuity 会写到：`/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/.agent.local/continuity/`
- 如果在下一轮 worktree 执行，并显式传 `--root /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/.worktrees/core-launcher-slimming-next`，continuity 会写到：`/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/.worktrees/core-launcher-slimming-next/.agent.local/continuity/`

本任务后续应以后者为准。

## 新会话恢复 Prompt

复制下面这段给新会话：

```text
继续 MMS Core/Launcher 下一轮瘦身。请进入 worktree：/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/.worktrees/core-launcher-slimming-next，分支 refactor/core-launcher-slimming-next。先读 AGENTS.md、docs/CORE_LAUNCHER_NEXT_WORKTREE_HANDOFF.md、docs/CORE_LAUNCHER_SLIMMING_ROADMAP.md、.agent.local/continuity/pickup.md。任务：从 Claude env/launch extraction 开始，只做行为不变的模块搬迁；不要写真实 ~/.config/mms/**；Claude config 是 human-only；不要碰 main 的 docs/MMF_CONFIG_ROOT_V2_DB_TRUTH.md。
```

## 快速恢复命令

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/.worktrees/core-launcher-slimming-next
python3 /Users/xin/auto-skills/shared-skills/handover/scripts/continuity.py status --root . --layout agent-local
sed -n '1,220p' .agent.local/continuity/pickup.md
```

---

## 2026-05-30 Human Gate Readiness Snapshot

Status: pre-human-gate candidate after latest `main` sync.

### Current Branch State

- Worktree: `/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/.worktrees/core-launcher-slimming-next`
- Branch: `refactor/core-launcher-slimming-next`
- Current HEAD: `0692a28 refactor(pi): group runner scripts`
- Latest synced `main` / `origin/main`: `f546903 fix(pi): fail-close live smoke regressions`
- Evidence: `main` and `origin/main` are ancestors of this branch after the 2026-05-30 sync.
- Worktree state at this snapshot: clean.

### What Changed Since The Original Handoff

- Synced `main` into the slimming branch twice and resolved Core/Launcher conflicts without re-inlining the extracted TUI/Core wrappers.
- Preserved `mms_core._handle_tui_launcher_selection` and `mms_launchers.get_export_env` as compatibility wrappers around focused modules.
- Carried forward latest Pi runner support, including provider compatibility, model availability filtering, selected-model export propagation, and smoke-matrix coverage.
- Grouped Pi-only script assets under `scripts/pi/`:
  - `scripts/pi/cli-wrapper.sh`
  - `scripts/pi/retry-extension.mjs`
  - `scripts/pi/smoke_matrix.py`

### Verified Gates

- `rtk python3.13 -m py_compile mms_core.py mms_launchers.py mms_command_tools.py mms_launcher/export.py mms_runtime/validation.py mms_tui_launcher_flow.py mms_tui_launcher_entry.py mms_display/confirm.py mms_pi/support.py`
- `rtk python3.13 -m pytest tests/test_pi_launcher.py tests/test_smoke_pi_matrix.py -q` -> `32 passed`
- isolated temp HOME/XDG full suite: `rtk python3.13 -m pytest -q` -> `1430 passed, 4 skipped`
- `git diff --check` -> pass

### Human Gate Smoke Scope

Manual gate can stay shallow. The user preference is “can open, no crash”; no real conversation is required.

Suggested launch-only checks:

- `mmg claude`
- `mmg codex`
- `mmg opencode`
- Optional if Pi is installed/desired: `mmg pi`

Stop before any real config mutation gate:

- Do not run live `guard accept`.
- Do not write real `~/.config/mms/**` automatically.
- Claude config remains `human-only`.
- Do not run installer, registry publish, or real proxy/egress smoke unless the human explicitly asks.

### Remaining Merge Notes

- This is close to a human-gate merge point: latest `main` is included, full isolated pytest is green, and the worktree is clean.
- Larger root-module folder migration is intentionally deferred. Moving flat `mms_*.py` modules into packages would reduce visual clutter but has higher import/install/test blast radius than is appropriate immediately before merge.
- The next safe cleanup after merge should be a dedicated package-layout migration plan with compatibility/import audit, not an opportunistic pre-gate move.

### Human Launch Smoke Result

- Timestamp: 2026-05-30T09:18:02+0800
- Result: human reported the suggested `mmg` launch entries can open without crashing.
- Scope: launch-only smoke; no real conversation required or recorded.
- Human gate status: passed for merge-readiness purposes.
