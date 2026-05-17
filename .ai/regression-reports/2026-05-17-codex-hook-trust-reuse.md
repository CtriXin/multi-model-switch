# Codex Hook Trust Reuse Regression - 2026-05-17

## Scope

- MMS-launched Codex session HOME isolation no longer forces the same hooks to be trusted again every session.
- Trust is copied only when the generated session hook command/fingerprint matches a previously trusted hook.
- Real `~/.codex/config.toml` is read as a seed but is not written by MMS.

## Fix

- Mirror trusted `[hooks.state."..."]` rows from real Codex config, active/stale MMS session configs, and MMS-local gateway cache into the new session-local `hooks.json` path.
- Persist MMS session hook trust back to `~/.config/mms/codex-gateway/.codex/config.toml` and `hooks.json` during bounded resume writeback, so future isolated sessions can reuse it after stale session cleanup.
- Preserve fail-closed behavior: only matching hook payload/command receives the known trusted hash.

## Validation

- `python3.13 -m py_compile mms_launchers.py mms_core.py mms_bridge.py`
- `python3.13 -m pytest -q tests/test_claude_hardening_regressions.py -q`
- `python3.13 -m pytest -q tests/test_codex_history_growth.py tests/test_mms_context.py tests/test_opencode_launcher.py tests/test_gateway_bridge_model_override.py tests/test_claude_model_visibility.py -q`
- `git diff --check`
