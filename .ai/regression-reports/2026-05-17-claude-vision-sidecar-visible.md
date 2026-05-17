# Claude Vision Sidecar Visibility Regression - 2026-05-17

## Scope

MMS-launched Claude should keep the vision sidecar path visible and active for text-only main models.

## Fix

- Resolve Claude vision sidecar before the launch confirmation screen, not only inside final launch.
- Show `Vision provider/model` in the confirmation context when a sidecar is available.
- Prefer direct MiMo `mimo-v2.5` as the default sidecar, then Kimi, then Qwen-compatible routes.
- Keep explicit `MMS_VISION_SIDECAR_MODEL` / `MMS_VISION_SIDECAR_PROVIDER` overrides.

## Validation

- `python3.13 -m py_compile mms_core.py mms_launchers.py mms_bridge.py`
- `python3.13 -m pytest -q tests/test_claude_model_visibility.py tests/test_gateway_bridge_model_override.py tests/test_mms_context.py tests/test_claude_hardening_regressions.py tests/test_opencode_launcher.py -q`
- `git diff --check`
