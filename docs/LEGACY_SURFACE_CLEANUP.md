# Legacy Surface Cleanup / TUI-Only Migration

Status: TUI-only migration phase. Legacy modules are not physically deleted,
but direct `mms chat` / `mms discuss` entrypoints are disabled by default.

## Goal

MMS is launcher/TUI-first. Legacy user surfaces stay available only for
dependency-preserving maintenance or explicit one-off compatibility opt-in
until tests prove they can be physically removed.

This phase adds:

- dependency audit for `mms_chat.py`, `mms_discuss.py`, `mmc_*`,
  `mms_action_bar.py`, and `mms_usage.py`;
- default tombstone/migration messages for `mms chat`, `mms discuss`, and
  `mmc_core` help;
- backend-only TUI Settings/Maintenance action descriptors in
  `mms_tui_settings_actions.py`;
- tests that keep `review-launch` and the default TUI launcher path out of the
  legacy cleanup blast radius.

## Dependency Audit

Audit command:

```bash
rg -n "\\bmms_chat\\b|chat_main|parse_chat_args|run_compare|select_models_tui|stream_model|strip_markdown|_current_view_state" .
rg -n "\\bmms_discuss\\b|discuss_main|parse_discuss_args|run_discussion|_select_discuss_models" .
rg -n "\\bmmc\\b|mmc_core|mmc_|MMC" .
rg -n "\\bmms_action_bar\\b|post_action_bar|run_chat_loop|_readline|_print_all_columns" .
rg -n "\\bmms_usage\\b|usage_main|usage \\.{3}|--refresh" .
```

### Findings

| Surface | Entrypoint | Current use | First-phase action | TUI replacement | Risk | Test coverage |
|---|---|---|---|---|---|---|
| Chat | `mms chat`, `mms_chat.py::chat_main` | Module still exports `stream_model`, `select_models_tui`, `strip_markdown`, `run_compare`, and shared view state used by `mms_discuss.py` and `mms_action_bar.py`. | Direct command is disabled by default and shows a TUI migration tombstone; module remains importable. Temporary opt-in: `MMS_ENABLE_LEGACY_CHAT_DISCUSS=1`. | Default `mms` TUI launcher for new CLI sessions; future `Legacy Tools / Emergency Debug` panel for compatibility access if still needed. | High if physically deleted: `mms_discuss.py` and `mms_action_bar.py` still import helpers directly. | `tests/test_legacy_surface_cleanup.py` checks tombstone, notices, and legacy imports. |
| Discuss | `mms discuss`, `mms_discuss.py::discuss_main` | `mms_action_bar.py` imports `REFINE_SYSTEM_PROMPT`, `phase3_synthesize`, and can route a legacy chat continuation into `discuss_main`. | Direct command is disabled by default and shows a TUI migration tombstone; module remains importable. Temporary opt-in: `MMS_ENABLE_LEGACY_CHAT_DISCUSS=1`. | Default `mms` TUI launcher for CLI startup; broad planning/execution belongs to external orchestrators, not MMS core. | High if physically deleted: action bar convergence/discuss paths still import symbols. | `tests/test_legacy_surface_cleanup.py` checks tombstone, notices, and importability. |
| Action bar | `mms_action_bar.py` | Not a standalone public command; post-chat/post-discuss curses event loop and continuation helpers. | Keep as dependency; no user-surface hide in this phase. | Future TUI maintenance descriptors may replace only operational actions, not chat UI internals. | Medium/high: tightly coupled to chat/discuss session flows. | Legacy import test keeps module loadable. |
| Usage | `mms usage`, `mms_usage.py::usage_main` | CLI stats and optional `--refresh` provider model refresh; imported only by `mms_core.py` and tests. | Keep command; do not deprecate in this phase. Document migration target for refresh/usage display. | `Refresh Sources` and `Usage / Last Used / Health overlay view` descriptors. | Medium: `--refresh` can touch provider cache and needs a real implementation plan before moving. | Existing `tests/test_command_smoke.py`; settings action descriptor tests. |
| MMC internal adapter | `mmc_core.py`, `mmc_project_store.py`, `mmc_proxy_guard.py`, `mmc_proxy_routes.py`, `mmc_session_index.py` | Public `mmc` shim is already retired by install docs, but `mms_launchers.py` still has launcher-owned MMC delegate code and tests cover isolation/proxy/session helpers. | Keep all modules; add help migration notice only; no physical deletion. | Normal users enter through `mms` TUI launcher. Emergency/debug access remains available until dependency removal is proven safe. | Very high: OAuth Claude isolation, local proxy guard, session home cleanup, and human guard semantics are safety-critical. | Existing MMC tests plus `tests/test_legacy_surface_cleanup.py` help/import checks. |
| Emergency/debug | `mms doctor`, `mms logs`, `mms guard`, `mms fake-upstream`, `mms exposure`, `mms session prune` | Recovery and diagnostics when launcher/config paths fail. | Keep visible enough for recovery; do not remove or fully hide. | `Registry Doctor`, `Interrupted Sessions / Rescue`, and `Legacy Tools / Emergency Debug` descriptors. | High if hidden too far: users lose recovery path during failure. | Default help test verifies `review-launch` remains outside legacy cleanup; existing command tests cover nearby paths. |
| Review launch | `mms review-launch`, `mms_review_launch.py` | Launcher-owned adapter surface for multi-review reviewer dispatch. | Keep. It is not a legacy chat/discuss cleanup target. | None; stays as adapter handshake. | High if misclassified: review dispatch would break. | `tests/test_legacy_surface_cleanup.py` and `tests/test_review_launch.py`. |

## TUI Settings/Maintenance Scaffold

Backend descriptors live in `mms_tui_settings_actions.py`. They are pure data:
no config writes, no credential reads, no launcher side effects.

Stable first-phase labels:

- `Refresh Sources`
- `Probe Selected / Small Health Check`
- `Registry Doctor`
- `Recoverable Models`
- `Interrupted Sessions / Rescue`
- `Export Approved Bundle`
- `Legacy Tools / Emergency Debug`
- `Usage / Last Used / Health overlay view`

Future TUI work can render these descriptors under Settings/Maintenance and
attach implementations one action at a time.

## Deletion Policy

Do not physically delete these in the safe first phase:

- `mms_chat.py`
- `mms_discuss.py`
- `mms_action_bar.py`
- `mms_usage.py`
- `mmc_core.py`
- `mmc_project_store.py`
- `mmc_proxy_guard.py`
- `mmc_proxy_routes.py`
- `mmc_session_index.py`
- emergency/debug command paths

Physical deletion requires a later dependency audit showing no imports, updated
TUI replacement behavior, and tests proving launcher/default/review paths are
unchanged.

## Validation Plan

Required first-phase checks:

```bash
PYTHONPATH=. pytest -q tests/test_registry_contract_docs.py tests/test_tui_registry_asset_manager.py tests/test_legacy_surface_cleanup.py
python3 -m py_compile mms_core.py mms_tui_settings_actions.py mms_chat.py mms_discuss.py mmc_core.py
git diff --check
```

If `mms_core.py` changes, also run the legacy cleanup tests that exercise help
and default TUI dispatch without starting an interactive TUI.
