# Agent Release Notes

## 2026-05-22 - WT3 TUI registry asset manager scaffold

- Added a pure display scaffold for registry model assets: dataclasses, display states, recency-first ranking, long-tail folding, search, and stable TUI action descriptors.
- Added a thin in-memory TUI adapter contract that builds registry display state without touching runtime, launcher, bridge, config, credentials, or default model resolution.
- Added focused tests for recency over historical use count, Qwen long-tail searchability, recoverable/tombstoned visibility, candidate default-launch exclusion, degraded health display, and action labels.
- Validation: `PYTHONPATH=. pytest -q tests/test_registry_contract_docs.py tests/test_tui_registry_asset_manager.py`, `python3 -m py_compile mms_model_display.py mms_registry_tui_adapter.py`, and `git diff --check`.
