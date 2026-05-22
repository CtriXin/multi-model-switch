# WT3 TUI Registry Asset Manager Regression Report

Date: 2026-05-22
Branch: `feat/tui-registry-asset-manager`

## Scope

- Added `mms_model_display.py` for model display dataclasses, derived display states, recency scoring, family sorting, long-tail folding, search, and TUI action descriptors.
- Added `mms_registry_tui_adapter.py` as a thin in-memory adapter contract for building display state.
- Added `tests/test_tui_registry_asset_manager.py` for focused WT3 behavior.

## Guardrails

- Did not modify `mms_tui.py`, `mms_core.py`, `mms_launchers.py`, `mms_bridge.py`, runtime resolution, launcher behavior, bridge behavior, or default model/source/provider/account resolution.
- Did not write real `~/.config/mms/**`, credentials, OAuth state, Claude config, or runtime DB files.
- Kept candidate and recoverable/tombstoned assets display-only unless explicitly opted in or lazy validated.

## Validation

- `PYTHONPATH=. pytest -q tests/test_registry_contract_docs.py tests/test_tui_registry_asset_manager.py` -> 12 passed.
- `python3 -m py_compile mms_model_display.py mms_registry_tui_adapter.py` -> passed.
- `git diff --check` -> passed.

## Residual Risk

- No real TUI integration yet by design; WT3 only provides the testable display/adapter seam for later registry DB integration.
- Long-tail folding policy is intentionally conservative and may need UI tuning after real registry data lands.
