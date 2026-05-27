# Core / Launcher Slimming Handoff And Roadmap

Date: 2026-05-27
Owner: Codex
CLI: codex
Model: gpt-5.5
Status: active

## Executive Summary

`refactor/opencode-agents-module` is a merge-ready slimming milestone, not the final healthy architecture. It should be merged to `main` now so WebUI and feature work can iterate on the new OpenCode baseline; Claude, Codex, and TUI/core slimming should continue in a new follow-up branch.

## User Intent

The user wants MMS to stay effective and fast without becoming an OMO-sized orchestration product inside the launcher.

Concrete goals:

- Keep MMS focused on launcher/session/runtime management.
- Reduce `mms_core.py` and `mms_launchers.py` until high-risk launch logic is easier to review and test.
- Let WebUI configure OpenCode agent behavior without hardcoded agent-name coupling in the launcher.
- Keep default OpenCode usage simple: `agent`, `omo`, and `raw` profiles are enough for the visible product surface.
- Avoid blocking ongoing main-branch feature work just because future slimming is still possible.

Non-goals:

- Do not rebuild a heavy OMO-style workflow engine inside MMS launcher.
- Do not silently change provider/account/auth fallback behavior while refactoring.
- Do not write or migrate real `~/.config/mms/**` during this work.
- Do not auto-modify Claude-related real config; Claude config remains `human-only`.

## Current Pain Points

`mms_core.py` and `mms_launchers.py` are still too large for long-term maintenance.

Observed after the OpenCode extraction milestone:

- `mms_core.py`: about `13801` lines, down from main's previous `14772` lines.
- `mms_launchers.py`: about `10586` lines, down from main's previous `11672` lines.
- `mms_core._handle_tui_launcher_selection`: about `1011` lines.
- `mms_core.main`: about `574` lines.
- `mms_launchers.launch_claude`: about `460` lines.
- `mms_launchers._claude_gateway_env`: about `343` lines.
- `mms_launchers._codex_gateway_env`: about `380` lines.
- `mms_launchers.launch_codex`: about `136` lines.
- `mms_launchers.launch_opencode`: about `21` lines after extraction.

Conclusion: OpenCode is now structurally healthier; Core, Claude, Codex, and TUI launcher flow are not yet healthy.

## Current State

### Branch State

- Milestone branch: `refactor/opencode-agents-module`.
- Code readiness checkpoint before this handoff doc: `e2667ba refactor(opencode): extract export env helpers`.
- Relationship to `main` at readiness check: ahead `17`, behind `0`.
- Tracked worktree status at readiness check: clean.
- Known main dirty file during merge preparation: `docs/MMF_CONFIG_ROOT_V2_DB_TRUTH.md`; unrelated and must not be touched by this merge.

### Completed OpenCode Extraction

OpenCode launch logic has been pulled out of the largest files into focused modules:

- `mms_opencode_agents.py`
- `mms_opencode_config.py`
- `mms_opencode_env.py`
- `mms_opencode_health.py`
- `mms_opencode_launch.py`
- `mms_opencode_preflight.py`
- `mms_opencode_profiles.py`
- `mms_opencode_resolver.py`
- `mms_opencode_roster.py`
- `mms_opencode_routes.py`
- `mms_opencode_session.py`

The remaining `mms_launchers.launch_opencode` wrapper delegates to `mms_opencode_launch.launch_opencode`.

### OpenCode Product Surface

Visible OpenCode profiles are intentionally simple:

- `agent`: default Agent mode.
- `omo`: global OMO mode.
- `raw`: pure OpenCode mode.

Retired or older names such as `lite_pro*`, `backend`, `acp`, and `pro solo` are compatibility aliases only and should not reappear as the primary user-facing surface.

### WebUI Compatibility

The branch supports the WebUI path for OpenCode configuration:

- `[opencode.agent_models]` can override provider/model for named agents.
- `[opencode.agent_roster]` can define enabled agents and role/order behavior.
- Empty overrides should be omitted from draft config rather than persisted as blank values.
- WebUI should present this as an advanced configuration surface, not as the default casual setup experience.

Important UX direction from the discussion:

- Ordinary users should see automatic route status and a small summary.
- Advanced users may open per-agent controls.
- Agent roster should not force every future model choice to depend on old hardcoded names such as `explore_qwen`.
- The launcher should consume roster/config data generically; WebUI can provide clearer labels, grouping, ordering, and reset actions.

### Retired Legacy Launcher Surface

The old numbered scene selector has been retired:

- `MMS -- 选择场景` is removed.
- `SCENES`, `show_scenes`, `select_scene_fallback`, and direct numeric scene target support are removed.
- `mms --presets` no longer shows the old built-in scenes list.
- `mms 1` should now be an unknown target instead of a hidden scene launch path.

## Boundaries

### What This Milestone Owns

This milestone owns OpenCode launch modularization and the simplified OpenCode profile surface.

It does not own a full architectural cleanup of all launchers.

### What Remains In Launcher

`mms_launchers.py` still owns too much:

- Claude session/env materialization.
- Codex session/env materialization.
- Host export-env construction.
- Provider/account runtime launch glue.
- Compatibility wrappers for launcher entrypoints.

### What Remains In Core

`mms_core.py` still owns too much:

- TUI launcher selection flow.
- CLI dispatch glue.
- Main command parsing and compatibility routing.
- Some branchy target/profile behavior that should eventually move to focused modules.

## Not Done Yet

Do not call the whole slimming project finished after this merge.

Explicit gaps:

- Claude launch/env code is still embedded in `mms_launchers.py`.
- Codex launch/env code is still embedded in `mms_launchers.py`.
- General export-env host-tool injection is still mixed with CLI-specific branches.
- TUI launcher selection flow is still too large inside `mms_core.py`.
- Full pytest has one known failure that also reproduces on `main`: `tests/test_claude_hardening_regressions.py::test_build_claude_session_settings_rewrites_caveman_hooks_per_session`.
- Live provider/OpenCode calls were not part of the final readiness gate.

## HumanGate / Safety

These constraints remain active for future slimming:

- Do not write real `~/.config/mms/**` automatically.
- Claude config is `human-only`; agents may inspect and propose, but must not persist real Claude config changes.
- Do not change default provider/account resolution order while moving code.
- Do not introduce fallback to real HOME/global OAuth state.
- Do not change `auth_mode` semantics during refactors.
- Do not alter cache-sensitive Anthropic/OpenAI transport selection silently.
- Do not reintroduce `ccs` entrypoints, `~/.config/ccs`, or `CCS_*` compatibility.
- Treat `mms_core.py`, `mms_launchers.py`, `mms_tui.py`, `mms_bridge.py`, `mms_account_state.py`, `mms_session.py`, `mms_adapter_registry.py`, and `mms` as protected surfaces.

## Proof Strategy

The OpenCode milestone readiness report is:

- `.ai/regression-reports/2026-05-27-opencode-module-merge-readiness.md`

Readiness validation already run before this handoff:

- `rtk python3.13 -m py_compile` on core launcher files and new `mms_opencode_*.py` modules: pass.
- Focused pytest suite covering OpenCode launcher, health, WebUI config, preview, runtime, Claude visibility, legacy surface cleanup, resume, xmem overlay, and context: `153 passed`.
- `rtk git diff --check`: pass.
- Full pytest: `807 passed, 4 skipped, 1 failed`; the single failure reproduces on `main` and is not introduced by this branch.

Minimum validation for future slimming branches:

- Run `python3 -m py_compile` on moved modules and wrappers.
- Run focused tests for the CLI being extracted.
- Run at least one default-path launch/help smoke that proves behavior did not change.
- Compare before/after env keys when extracting Claude or Codex env builders.
- Keep tests monkeypatch-compatible by preserving wrapper names until callers are migrated.

## Roadmap

### Stage 0: Merge This Milestone

Merge `refactor/opencode-agents-module` into `main` after this handoff doc lands.

Success criteria:

- Main contains the OpenCode module extraction.
- Main still preserves unrelated dirty local doc changes outside the merge.
- Main can be used by WebUI and feature work as the new baseline.

### Stage 1: Claude Extraction

Create a new branch from updated `main`.

Suggested modules:

- `mms_claude_env.py`: gateway/session env construction, Claude settings, hook materialization helpers.
- `mms_claude_launch.py`: launch flow orchestration and guarded wrapper around existing launcher entrypoint.

Rules:

- Move first, change behavior later only with explicit proof.
- Preserve `launch_claude` as the public wrapper until all callers/tests are updated.
- Do not touch real Claude config.
- Do not change global OAuth fail-closed behavior.

### Stage 2: Codex Extraction

Suggested modules:

- `mms_codex_env.py`: Codex gateway/session env, config/trust state materialization.
- `mms_codex_launch.py`: launch flow orchestration and bridge selection wrapper.

Rules:

- Preserve `launch_codex` wrapper.
- Keep Responses-vs-chat bridge behavior unchanged.
- Verify non-GPT bridge path and GPT direct path separately if practical.

### Stage 3: Shared Launcher Export Helpers

Suggested module:

- `mms_launcher_export.py`

Move generic host-tool and export-env logic that is not specific to OpenCode, Claude, or Codex.

Rules:

- Avoid hiding CLI-specific behavior behind a generic abstraction too early.
- Keep explicit per-CLI branches where behavior differs.

### Stage 4: Core / TUI Launcher Flow

Suggested module:

- `mms_tui_launcher_flow.py`

Move the large `_handle_tui_launcher_selection` flow out of `mms_core.py`.

Rules:

- Do not change TUI return structures while moving code.
- Do not change recent/default source selection semantics.
- Keep `mms_core.py` as dispatch/orchestration, not the owner of the full TUI flow.

## Future LMs Must Not Forget

- This OpenCode branch is merge-ready, not final architecture.
- Do not keep delaying main for perfect slimming; ship safe milestones.
- OpenCode is the model for the extraction pattern: wrapper stays, focused modules own the heavy logic.
- Claude/Codex extraction is riskier than OpenCode because auth, HOME isolation, hooks, and provider resolution are involved.
- WebUI should configure OpenCode roster/model overrides generically; do not force new UX to depend on legacy hardcoded agent names.
- Real MMS config and Claude config are protected human surfaces.
- Known full-suite failure in Claude hardening is pre-existing; do not attribute it to OpenCode extraction without rechecking on main.
