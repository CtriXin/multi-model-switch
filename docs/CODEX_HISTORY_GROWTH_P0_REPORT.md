# Codex History Growth P0 Report

Date: 2026-04-25

## Conclusion

This was an MMS session-isolation bug, not a confirmed Codex upstream prompt bug.

Before `f6ca15d`, MMS-started Codex sessions could see full Codex resume/history stores via session symlinks. That does not prove every API request paid for all of it in tokens, but it did expose a large cross-project history tree to each MMS Codex session and made resume/history reads unbounded.

The fix changes MMS-started Codex from full history exposure to session-local bounded resume seeding. The current defaults are resume-friendly rather than maximally strict, because follow-up prompt-input experiments did not show startup-token benefit from very tight caps.

## Affected Surface

Affected:

- MMS-started Codex account/OAuth sessions.
- MMS-started Codex gateway/provider sessions.

Not affected:

- Direct Codex launches outside MMS.
- Real `~/.codex` contents.
- Real `~/.config/mms` config.
- Hive code.

## Pre-Fix Local Exposure

Measured on this machine on 2026-04-25:

| Path | Count | Bytes |
| --- | ---: | ---: |
| `~/.codex/history.jsonl` | 6341 lines | 2,430,825 |
| `~/.codex/session_index.jsonl` | 70 lines | 10,101 |
| `~/.codex/sessions/` | 2055 files | 1,371,244,129 |
| `~/.codex/shell_snapshots/` | 36 files | 2,523,803 |
| `~/.codex/archived_sessions/` | 14 files | 10,152,213 |

Total exposed global resume/history tree: about 1.386GB.

Important distinction:

- This was the file surface visible to MMS-started Codex.
- It is not proof that every request sent 1.386GB to the model.
- Exact per-request token usage requires bridge/API payload instrumentation.

## Post-Fix Policy

Resume-friendly defaults after the 2026-04-25 follow-up:

| Entry | Default |
| --- | ---: |
| `history.jsonl` | last 200 lines |
| `session_index.jsonl` | last 50 lines |
| `sessions/` | latest 25 files |
| `shell_snapshots/` | latest 20 files |
| `archived_sessions/` | 0 files |
| max copied session/snapshot file size | 2MB |

Each MMS-started Codex session now gets a local `.codex/mms-resume-seed.json` manifest with actual seeded lines, files, bytes, and skipped oversized files.

## Post-Fix Local Upper Bounds

Using the same local data and the resume-friendly defaults:

| Source | Seeded bytes |
| --- | ---: |
| global `~/.codex` fallback | 16,417,053 |

The global fallback number is much lower than the old 1.386GB exposure, but still an upper bound of seeded local files, not confirmed prompt tokens. It intentionally preserves more recent resume coverage than the temporary strict defaults.

Rough token intuition if a downstream component naively read all seeded text:

- global fallback seed: about 4.1M tokens at 4 chars/token if a downstream component naively read every seeded byte

Actual request token usage may be far lower, because Codex decides what history/resume files to read. The manifest now makes the local seed size auditable per session.

## Resume Impact

Different-folder resume is intentionally bounded for MMS-started Codex:

- Recent resume remains available within the bounded seed.
- Older or very large cross-folder resume may not appear inside MMS sessions.
- Direct Codex outside MMS keeps its original full resume behavior.

This is the intended tradeoff. MMS session isolation should not expose the full global history tree by default.

## Implementation

Commits:

- `f6ca15d fix(session): bound codex resume history`
- `120fd68 fix(session): tighten codex resume seed`
- later follow-up rebalanced the defaults toward resume coverage after startup prompt tests did not show token savings from very tight caps

Key files:

- `mms_launchers.py`
  - `_overlay_codex_shared_resume()`
  - `_seed_codex_bounded_resume()`
  - `_codex_gateway_env()`
- `tests/test_codex_history_growth.py`

Environment overrides remain available for controlled tuning:

- `MMS_CODEX_HISTORY_JSONL_MAX_LINES`
- `MMS_CODEX_SESSION_INDEX_JSONL_MAX_LINES`
- `MMS_CODEX_SESSIONS_MAX_FILES`
- `MMS_CODEX_SHELL_SNAPSHOTS_MAX_FILES`
- `MMS_CODEX_ARCHIVED_SESSIONS_MAX_FILES`
- `MMS_CODEX_RESUME_MAX_FILE_BYTES`

## Validation

Validated:

- bounded file tail copy
- resume-friendly default caps
- oversized session file skip
- account Codex path
- gateway Codex path
- existing Codex session skill overlays
- token-saver/context regressions

Commands run:

- `python3 -m py_compile mms_launchers.py tests/test_codex_history_growth.py`
- `PYTHONPATH=. python3 -m pytest -q tests/test_codex_history_growth.py`
- focused `tests/test_claude_hardening_regressions.py` Codex session overlay subset
- `PYTHONPATH=. python3 -m pytest -q tests/test_mms_context.py tests/test_install_script_paths.py`

## Remaining Unknown

Exact per-request token cost is not proven by file-size analysis. The next rigorous step would be payload instrumentation in the Codex bridge path to record request payload chars/tokens per request without storing sensitive content.
