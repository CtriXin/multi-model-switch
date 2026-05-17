# Deleted CWD Fallback Regression - 2026-05-17

## Scope

MMS should not crash when launched from a terminal whose current directory has been deleted or moved.

## Fix

- Added `resolve_current_workdir()` in `mms_state_io.py`.
- Replaced launcher/core `os.getcwd()` call sites with the safe resolver.
- Fallback order: live cwd -> existing `PWD` -> existing `OLDPWD` -> explicit fallback -> real HOME.

## Validation

- `python3.13 -m py_compile mms_state_io.py mms_launchers.py mms_core.py`
- `python3.13 -m pytest -q tests/test_mms_context.py tests/test_claude_hardening_regressions.py tests/test_codex_history_growth.py tests/test_opencode_launcher.py -q`
