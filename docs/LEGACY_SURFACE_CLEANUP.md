# Legacy Surface Cleanup

MMS is now launcher-first. The old built-in `chat` / `discuss` / post-action-bar product line has been physically removed from the default codebase.

## Removed

- `mms chat` command handling
- `mms discuss` command handling
- `MMS_ENABLE_LEGACY_CHAT_DISCUSS` escape hatch
- legacy chat session resume under `mms session resume`
- `mms_chat.py`
- `mms_discuss.py`
- `mms_action_bar.py`
- `mms_session.py`
- runtime API `/api/chat/stream` and `/api/discuss/stream` routers
- chat/discuss Pydantic request/response schemas and mock session fixtures
- stale product proposal docs for native chat/discuss/Judge/mobile discuss directions

## Kept

| Surface | Status | Reason |
| --- | --- | --- |
| `mms` TUI launcher | Keep | Primary product path. |
| Provider/account/model config | Keep | Required by launcher runtime resolution. |
| Skills / MCP / session surfaces / bypass / hooks | Keep | Launch-time capability injection direction. |
| `doctor`, `smoke`/`test`, `exposure`, `logs`, `guard` | Keep | Recovery and validation tools for launcher/runtime failures. |
| Registry / OpenRouter truth | Keep as admin surface | Supports model/source truth for launcher routing. |
| `mms review-launch` | kept as future multi-review adapter | Launcher-owned reviewer dispatch handshake; not part of removed chat/discuss UI. |
| `mmc_*` internals | Keep | Safety-critical Claude isolation/proxy/session helpers still used by launchers. |
| `mms_usage.py` | Keep | Usage metadata remains useful for launcher recency/defaults. |

## Product Boundary

Do not rebuild a native MMS chat client or multi-model discuss UI in core. Future multi-review should grow through `review-launch` or a launcher-owned adapter surface that starts external reviewer CLIs/runtimes and emits evidence, not through the removed `chat` / `discuss` stack.

## Validation Pointers

```bash
PYTHONPATH=. pytest -q tests/test_legacy_surface_cleanup.py tests/test_mms_toon.py tests/test_tui_launcher_flow.py
python3 -m py_compile mms_core.py mms_tui_settings_actions.py mmc_core.py apps/runtime-api/main.py apps/runtime-api/models/schemas.py apps/runtime-api/routers/bootstrap.py
```
