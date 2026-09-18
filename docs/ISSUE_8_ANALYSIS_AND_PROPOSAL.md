## Root Cause Analysis

**Status**: ✅ **ANALYSIS COMPLETE - RFC APPROVED**

**Updated Document**: For the complete, up-to-date analysis and implementation plan, see:
- 📄 **RFC Document**: [`RFC_OPENCODE_SESSION_SWITCHING_FIX_2026-06-15.md`](RFC_OPENCODE_SESSION_SWITCHING_FIX_2026-06-15.md)
- 📄 **Implementation Guide**: [`ISSUE_8_OPENCODE_SESSION_FIX_GUIDE.md`](ISSUE_8_OPENCODE_SESSION_FIX_GUIDE.md)

**Committee Status**: All 5 committee members approved the RFC with modifications (2026-06-15)

---

### Observation
The OpenCode session switcher shows **"No results found"** when using the MMS OpenCode profile. This is profile-specific and does not occur with the `omo` / `heavy_omo` profile.

### Root Cause

1. **Session Isolation via Soft-Home (`opencode_set_soft_home`)**
   - In `mms_opencode_env.py:17-29`, `opencode_set_soft_home` sets:
     - `XDG_CONFIG_HOME = <session_home>/.config`
     - `XDG_CACHE_HOME = <session_home>/.cache`
     - `XDG_DATA_HOME = <session_home>/.local/share`
     - `XDG_STATE_HOME = <session_home>/.local/state`
   - This means **every OpenCode session gets its own isolated XDG directories** under `~/.config/mms/opencode-gateway/s/<pid>/`.

2. **OpenCode Stores Session History in XDG State/Data**
   - OpenCode's internal session database (SQLite or JSON) is stored under `XDG_STATE_HOME` or `XDG_DATA_HOME` by default.
   - Because each MMS-launched OpenCode session uses a **different `XDG_STATE_HOME`**, the session history written by one process is **invisible to another**.

3. **Session Catalog Only Indexes `claude` and `codex`**
   - In `mms_session_catalog.py:443-454`, `list_session_records` only scans:
     - `claude` roots (`projects/*/claude/state/sessions/*.json` and raw JSONL)
     - `codex` roots (`~/.codex/session_index.jsonl`, `~/.config/mms/codex-gateway/...`)
   - **There is no `opencode` branch** in `list_session_records`. The catalog does not know how to find OpenCode sessions at all.

4. **MMS Does Not Record OpenCode Session Starts**
   - `mms_session_index.py` only has `record_claude_session_start` and `finalize_claude_session`.
   - `mms_launchers.py:11639` (`launch_opencode`) does **not** call any session-index recording function (unlike `launch_claude` which calls `record_claude_session_start`).

5. **Profile Difference**
   - The `omo` / `heavy_omo` profile uses `opencode_global_omo_env` (`mms_opencode_env.py:144-170`), which sets `XDG_STATE_HOME = ~/.local/state` (real home). OpenCode sessions share the same state directory and can see each other.
   - Non-OMO profiles (agent, review, committee, raw) use `opencode_gateway_env` with isolated `XDG_STATE_HOME`, causing the empty session list.

### Summary
The bug is a **combination of two missing pieces**:
- **Missing piece A**: MMS isolates OpenCode session state per PID, so OpenCode cannot read its own global session history.
- **Missing piece B**: MMS does not index OpenCode sessions into `mms_session_catalog`, so even MMS-level tools (WebUI, `mms resume`) cannot find them.

---

## Proposed Solution

### Option A: Unify OpenCode State Directory (Recommended)
**Goal**: Make non-OMO OpenCode profiles share a single session state directory, just like `omo` does, while keeping config isolated per session.

**Specific Changes**:

1. **`mms_opencode_env.py` — Split state from config isolation**
   - Modify `opencode_set_soft_home` to keep `XDG_STATE_HOME` and `XDG_DATA_HOME` pointing to a **stable** OpenCode gateway directory instead of the per-PID `session_home`.
   - Keep `XDG_CONFIG_HOME` per-session (so `opencode.json` and plugins remain isolated).

   ```python
   def opencode_set_soft_home(env, session_home, *, real_user_path, set_session_home_hint):
       real_home = real_user_path()
       env["HOME"] = real_home
       env["XDG_CONFIG_HOME"] = os.path.join(session_home, ".config")
       # Stable shared state so OpenCode session history is visible across sessions
       gateway_state = real_user_path(".config", "mms", "opencode-gateway", "state")
       env["XDG_CACHE_HOME"] = os.path.join(session_home, ".cache")
       env["XDG_DATA_HOME"] = gateway_state
       env["XDG_STATE_HOME"] = gateway_state
       env["MMS_HOME_ISOLATION_MODE"] = "soft"
       env["MMS_SOFT_HOME"] = "1"
       env["MMS_OPENCODE_SOFT_HOME"] = "1"
       set_session_home_hint(env, session_home)
       return env
   ```

2. **`mms_session_catalog.py` — Add OpenCode session scanning**
   - Add `opencode_roots()` function similar to `codex_roots()`.
   - Scan `~/.config/mms/opencode-gateway/state/` for OpenCode session databases or JSONL files.
   - Add `opencode` branch in `list_session_records`.

   ```python
   def opencode_roots() -> list[Path]:
       home = _real_user_home()
       roots = []
       for env_name in ("XDG_STATE_HOME", "XDG_DATA_HOME"):
           value = str(os.environ.get(env_name) or "").strip()
           if value:
               roots.append(Path(value))
       roots.extend([
           home / ".config" / "mms" / "opencode-gateway" / "state",
           home / ".local" / "state" / "opencode",
           home / ".config" / "opencode" / "state",
       ])
       return [path for path in _dedupe_paths(roots) if path.exists()]
   ```

   - Update `list_session_records`:
     ```python
     if cli in {"all", "opencode"}:
         for root in opencode_roots():
             records.extend(_opencode_index_records(root))
             records.extend(_opencode_jsonl_records(root))
     ```

3. **`mms_session_index.py` — Add OpenCode session recording**
   - Add `record_opencode_session_start` and `finalize_opencode_session` analogous to the Claude versions.
   - Call them from `mms_launchers.py:launch_opencode`.

   ```python
   def record_opencode_session_start(*, cwd, account_id, pid, runtime_kind, slot_home, resume_model=""):
       # Similar to record_claude_session_start but cli="opencode"
       ...

   def finalize_opencode_session(*, cwd, pid, account_id="", exit_code=None, stale_cleanup=False):
       # Similar to finalize_claude_session but cli="opencode"
       ...
   ```

4. **`mms_launchers.py` — Wire up OpenCode session recording**
   - In `launch_opencode`, after `_opencode_gateway_env` returns, call `record_opencode_session_start` with the session home and PID.
   - Register an exit callback to call `finalize_opencode_session`.

### Option B: Side-Runner Alias Index (RFC #10 Fallback)
If OpenCode's internal session list remains unreliable, the side-runner RFC already proposes maintaining its own alias-to-session index. This is **complementary** to Option A, not a replacement.

---

## Implementation Plan

### Phase 1: Fix OpenCode State Visibility (P0 — fixes #8)
1. **Modify `mms_opencode_env.py`**
   - Change `opencode_set_soft_home` to use a stable `XDG_DATA_HOME` / `XDG_STATE_HOME` under `~/.config/mms/opencode-gateway/state/`.
   - Ensure `XDG_CONFIG_HOME` remains per-session.

2. **Add OpenCode session catalog support in `mms_session_catalog.py`**
   - Implement `opencode_roots()`.
   - Implement `_opencode_index_records()` and `_opencode_jsonl_records()` (OpenCode stores sessions in JSONL under `conversations/` or similar).
   - Add `opencode` to `list_session_records`.

3. **Add OpenCode session index in `mms_session_index.py`**
   - Add `record_opencode_session_start` and `finalize_opencode_session`.

4. **Wire in `mms_launchers.py`**
   - Call `record_opencode_session_start` at launch.
   - Call `finalize_opencode_session` on exit.

5. **Tests**
   - Add `test_opencode_session_index.py` verifying:
     - Two sequential OpenCode sessions can list each other in `mms_session_catalog`.
     - Session config remains isolated (different `opencode.json`), but state is shared.

### Phase 2: Side-Runner Resilience (P1 — RFC #10)
1. Implement `.opencode/side-runner/state.json` alias index as described in RFC.
2. Verify `/side status` works even when OpenCode TUI session switcher is empty.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Shared state corruption** | Multiple concurrent OpenCode sessions writing to same SQLite/JSONL | Use file-level locking or rely on OpenCode's own concurrency handling. OpenCode is designed for single-writer; concurrent sessions are rare in MMS. Document limitation. |
| **Privacy leak between profiles** | Agent profile sees committee session history | Acceptable: all OpenCode sessions belong to the same user. If needed, add `MMS_OPENCODE_STATE_NAMESPACE` env var to shard by profile. |
| **Breaking existing session isolation** | Users relying on per-session clean state | Keep `XDG_CONFIG_HOME` per-session. Only state (history) is shared. Add `preferences.toml` flag `opencode.session_state_isolation = true` to opt back into old behavior. |
| **OpenCode state schema changes** | Future OpenCode versions move state path | Abstract `opencode_state_roots()` in `mms_session_catalog` so we can add new paths without changing callers. |
| **Regression in OMO profile** | OMO already uses real home state; changing soft-home might conflict | OMO uses `opencode_global_omo_env`, not `opencode_set_soft_home`. No overlap. |

---

## Verification Steps

1. **Fresh session visibility**
   ```bash
   mms opencode --profile agent
   # In OpenCode TUI, open Sessions panel → should show previous sessions (if any)
   ```

2. **Cross-session resume**
   ```bash
   # Session A
   mms opencode --profile agent --once -m "echo hello A"
   # Session B
   mms opencode --profile agent
   # In TUI, search for "hello A" → should find Session A
   ```

3. **MMS catalog includes OpenCode**
   ```bash
   python3 -c "from mms_session_catalog import list_session_records; print([r['cli'] for r in list_session_records()])"
   # Should contain 'opencode' entries
   ```

4. **Config isolation preserved**
   ```bash
   # Check that two sessions have different opencode.json but same state dir
   python3 -c "
   import os, json
   print('CONFIG:', os.environ['XDG_CONFIG_HOME'])
   print('STATE:', os.environ['XDG_STATE_HOME'])
   "
   ```

5. **Side-runner fallback (RFC #10)**
   ```bash
   # Even if OpenCode TUI shows no results, side-runner alias index should work
   /side new review "test"
   /side status
   # Should show 'review' alias with session ID
   ```

6. **Regression gate**
   ```bash
   python3 scripts/regression_fresh_user_gate.py --quick
   # Ensure Claude/Codex session indexing still works
   ```

---

## ⚠️ Important Note

**This document is historical.** For the complete, up-to-date analysis and implementation plan, please refer to:

### Primary Documents:
1. **RFC Document**: [`RFC_OPENCODE_SESSION_SWITCHING_FIX_2026-06-15.md`](RFC_OPENCODE_SESSION_SWITCHING_FIX_2026-06-15.md)
   - Complete root cause analysis
   - Committee review and decisions
   - Implementation plan with Phase 1 and Phase 2
   - Risk assessment and verification steps

2. **Implementation Guide**: [`ISSUE_8_OPENCODE_SESSION_FIX_GUIDE.md`](ISSUE_8_OPENCODE_SESSION_FIX_GUIDE.md)
   - Step-by-step implementation instructions
   - Code snippets and file locations
   - Testing procedures
   - Notes for fresh session agents

### GitHub Issue:
- **Issue #8**: [Bug: OpenCode profile cannot switch sessions; session list is empty](https://github.com/CtriXin/multi-model-switch/issues/8)
- **Latest Comment**: RFC update and implementation ready status

### Committee Decisions (2026-06-15):
- ✅ Track A Option 1 (Shared State Directory) approved
- ✅ Mandatory `profile_id` parameter
- ✅ XDG-compliant path: `~/.local/share/mms-opencode/state/<profile_id>`
- ✅ Kill-switch: `MMS_OPENCODE_ISOLATE_DATA=1`
- ✅ Track B separated into follow-up PR

**For any agent starting work on this issue**: Please read the RFC document and Implementation Guide first. This historical document provides background context but is not the authoritative source for implementation details.
