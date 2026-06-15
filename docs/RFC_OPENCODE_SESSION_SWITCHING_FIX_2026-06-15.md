# RFC: OpenCode Session Switching Fix

Date: 2026-06-15
Owner: Committee
CLI: opencode
Status: **approved with modifications** (2026-06-15)
Review Status: **Completed** - All 5 committee members approved with modifications

## Executive Summary

This RFC documents the root cause analysis, proposed solution, and implementation plan for fixing Issue #8: "OpenCode profile cannot switch sessions; session list is empty". The issue prevents users from switching between or resuming prior sessions when using MMS-managed OpenCode profiles (agent/review/committee/lite/raw).

## Problem Statement

When using MMS OpenCode profiles, the OpenCode session switcher shows "No results found" and cannot discover any prior session records. This blocks core workflow continuity and prevents the side-runner RFC (#10) from functioning correctly.

## Root Cause Analysis

### Primary Cause: Per-PID XDG State Isolation

The MMS OpenCode "soft home" isolation in `mms_opencode_env.py:opencode_set_soft_home()` redirects OpenCode's XDG state directories into PID-keyed ephemeral directories:

```python
# Current code in mms_opencode_env.py (lines 17-29)
def opencode_set_soft_home(env, session_home, *, real_user_path, set_session_home_hint):
    real_home = real_user_path()
    env["HOME"] = real_home
    env["XDG_CONFIG_HOME"] = os.path.join(session_home, ".config")
    env["XDG_CACHE_HOME"] = os.path.join(session_home, ".cache")
    env["XDG_DATA_HOME"] = os.path.join(session_home, ".local", "share")
    env["XDG_STATE_HOME"] = os.path.join(session_home, ".local", "state")
    env["MMS_HOME_ISOLATION_MODE"] = "soft"
    env["MMS_SOFT_HOME"] = "1"
    env["MMS_OPENCODE_SOFT_HOME"] = "1"
    set_session_home_hint(env, session_home)
    return env
```

Where `session_home` is constructed in `opencode_gateway_env()` (lines 86-87):
```python
gateway_base = real_user_path(".config", "mms", "opencode-gateway")
session_home = os.path.join(sessions_dir, str(getpid()))
```

**Impact**: OpenCode stores its session history database (`opencode.db`) under `$XDG_DATA_HOME/opencode/`. Since each MMS launch gets a fresh, empty `XDG_DATA_HOME`, OpenCode's built-in session switcher finds zero prior session records.

### Secondary Cause: MMS Session Catalog Gap

The MMS session catalog (`mms_session_catalog.py:list_session_records()`) only scans `claude` and `codex` sessions. There is no `opencode` branch, so MMS-level tools (`mms session list`, WebUI) cannot discover OpenCode sessions even if the XDG isolation were fixed.

### Tertiary Cause: Missing Session Index Integration

`mms_session_index.py` only has `record_claude_session_start` / `finalize_claude_session` functions. There are no corresponding OpenCode versions, and `launch_opencode` never calls any session index recording functions.

### Comparison with OMO Profile

The OMO profile uses `opencode_global_omo_env()` which sets:
```python
env["XDG_DATA_HOME"] = real_user_path(".local", "share")  # Real user directory
env["XDG_STATE_HOME"] = real_user_path(".local", "state")  # Real user directory
```

This is why OMO profile sessions can see each other - they share the real user's OpenCode database.

## Proposed Solution

### Strategy: Dual-Track Fix

**Track A (Primary)**: Share OpenCode data directory across MMS launches while preserving config isolation.
**Track B (Secondary)**: Extend MMS session catalog to include OpenCode sessions for MMS-level tooling.

### Track A: Fix XDG State Isolation

#### Option 1: Shared State Directory (Approved by Committee)

Modify `opencode_set_soft_home()` to use a shared, persistent state directory instead of per-PID directories:

**File**: `mms_opencode_env.py`
**Function**: `opencode_set_soft_home()`

```python
def opencode_set_soft_home(env, session_home, *, real_user_path, set_session_home_hint, profile_id):
    """Set soft home for OpenCode with shared state directory.

    Args:
        profile_id: Mandatory profile identifier for state sharding.
                   Must be non-empty to prevent cross-profile privacy leaks.
    """
    if not profile_id:
        raise ValueError("profile_id is required for OpenCode soft home isolation")

    real_home = real_user_path()
    env["HOME"] = real_home
    env["XDG_CONFIG_HOME"] = os.path.join(session_home, ".config")  # Session-local
    env["XDG_CACHE_HOME"] = os.path.join(session_home, ".cache")    # Session-local

    # Shared state directory for OpenCode session history (XDG-compliant path)
    state_root = real_user_path(
        ".local", "share", "mms-opencode", "state", profile_id
    )
    os.makedirs(state_root, exist_ok=True)
    env["XDG_DATA_HOME"] = state_root  # Shared across launches
    env["XDG_STATE_HOME"] = state_root  # Shared across launches

    env["MMS_HOME_ISOLATION_MODE"] = "soft"
    env["MMS_SOFT_HOME"] = "1"
    env["MMS_OPENCODE_SOFT_HOME"] = "1"
    env["MMS_OPENCODE_STATE_SHARED"] = "1"  # Diagnostic marker

    # Kill-switch for rollback: restore old per-PID behavior
    if os.environ.get("MMS_OPENCODE_ISOLATE_DATA") == "1":
        env["XDG_DATA_HOME"] = os.path.join(session_home, ".local", "share")
        env["XDG_STATE_HOME"] = os.path.join(session_home, ".local", "state")
        del env["MMS_OPENCODE_STATE_SHARED"]

    set_session_home_hint(env, session_home)
    return env
```

**Rationale**:
- `XDG_CONFIG_HOME` remains per-session to isolate MMS-generated `opencode.json` and plugins
- `XDG_DATA_HOME` and `XDG_STATE_HOME` are shared to enable session history persistence
- Profile-based sharding prevents cross-profile privacy leaks
- Mandatory `profile_id` prevents accidental defaulting to shared "default" namespace
- `MMS_OPENCODE_ISOLATE_DATA=1` provides kill-switch for rollback
- XDG-compliant path (`~/.local/share/mms-opencode`) follows standards

#### Option 2: Real User Directory Passthrough

Point `XDG_DATA_HOME` and `XDG_STATE_HOME` directly to the real user directories:

```python
env["XDG_DATA_HOME"] = os.path.join(real_home, ".local", "share")
env["XDG_STATE_HOME"] = os.path.join(real_home, ".local", "state")
```

**Pros**: Simplest change, restores OpenCode's default behavior
**Cons**: May break per-session skill/config isolation expectations

#### Option 3: Symlink Shared Data Directory

Create a shared OpenCode data directory and symlink from each session's `XDG_DATA_HOME`:

```python
def _share_opencode_data(session_home, *, real_user_path):
    shared_data_dir = real_user_path(
        ".config", "mms", "opencode-gateway", "shared-data", "opencode"
    )
    os.makedirs(shared_data_dir, exist_ok=True)

    xdg_data_home = os.path.join(session_home, ".local", "share")
    target_data_dir = os.path.join(xdg_data_home, "opencode")

    if not os.path.exists(target_data_dir):
        os.symlink(shared_data_dir, target_data_dir)
```

**Pros**: Preserves per-session isolation structure while sharing actual data
**Cons**: More complex, requires careful cleanup handling

### Track B: Extend MMS Session Catalog

#### Step 1: Add OpenCode Session Scanning

**File**: `mms_session_catalog.py`

```python
def opencode_roots() -> list[Path]:
    """Return paths to scan for OpenCode session records."""
    home = _real_user_home()
    candidates = [
        home / ".config" / "mms" / "opencode-gateway" / "state" / "default" / "opencode",
        home / ".local" / "share" / "opencode",
    ]
    return [path for path in _dedupe_paths(candidates) if path.exists()]

def _opencode_db_records(root: Path) -> list[dict]:
    """Scan OpenCode SQLite database for session records."""
    db_path = root / "opencode.db"
    if not db_path.exists():
        return []

    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute(
            "SELECT id, title, cwd, createdAt, updatedAt, modelID FROM session"
        )
        records = []
        for row in cursor:
            records.append({
                "cli": "opencode",
                "session_id": row[0],
                "title": row[1] or "",
                "cwd": row[2] or "",
                "updated_at": row[4] or "",
                "model": row[5] or "",
            })
        conn.close()
        return records
    except Exception:
        return []
```

#### Step 2: Update list_session_records

**File**: `mms_session_catalog.py`

```python
def list_session_records(cli: str = "all", query: str = "", limit: int | None = None) -> list[dict]:
    # ... existing code ...

    if cli in {"all", "opencode"}:
        for root in opencode_roots():
            records.extend(_opencode_db_records(root))

    # ... existing filtering and sorting ...
```

#### Step 3: Add Session Index Functions

**File**: `mms_session_index.py`

```python
def record_opencode_session_start(
    *,
    cwd: str,
    account_id: str = "",
    pid: int = 0,
    runtime_kind: str = "",
    slot_home: str = "",
    resume_model: str = "",
) -> dict:
    """Record OpenCode session start in MMS index."""
    # Implementation similar to record_claude_session_start

def finalize_opencode_session(
    *,
    cwd: str,
    pid: int = 0,
    account_id: str = "",
    exit_code: int | None = None,
    stale_cleanup: bool = False,
) -> None:
    """Finalize OpenCode session in MMS index."""
    # Implementation similar to finalize_claude_session
```

#### Step 4: Integrate with Launcher

**File**: `mms_launchers.py`

In `launch_opencode()` function, add session recording:

```python
def launch_opencode(...):
    # ... existing code ...

    # Record session start
    record_opencode_session_start(
        cwd=os.getcwd(),
        account_id=runtime.get("account_id", ""),
        pid=os.getpid(),
        runtime_kind=runtime.get("runtime_kind", ""),
        slot_home=env.get("MMS_SESSION_HOME", ""),
    )

    # Register session finalization
    def _finalize_session():
        finalize_opencode_session(
            cwd=os.getcwd(),
            pid=os.getpid(),
            account_id=runtime.get("account_id", ""),
        )

    atexit.register(_finalize_session)

    # ... rest of existing code ...
```

## Implementation Plan

### Phase 1: Core Fix (Must Have) - COMMITTEE APPROVED

**Timeline**: Immediate implementation after RFC approval
**Scope**: Fix Issue #8 user-facing symptom (OpenCode session switcher empty)

1. **Modify `mms_opencode_env.py`**:
   - Update `opencode_set_soft_home()` to use shared state directory at `~/.local/share/mms-opencode/state/<profile_id>`
   - Add mandatory `profile_id` parameter (raise ValueError if missing)
   - Add `MMS_OPENCODE_ISOLATE_DATA=1` kill-switch for rollback
   - Add `MMS_OPENCODE_STATE_SHARED=1` diagnostic marker

2. **Update caller chain with explicit `profile_id` threading**:
   - `opencode_gateway_env()`: Extract `runtime.get("opencode_profile", "lite")` and pass as `profile_id`
   - `mms_launchers.py:_set_opencode_soft_home()`: Add `profile_id` parameter and forward
   - Update function signatures and documentation

3. **Add one-time data migration helper**:
   - Script to copy existing per-PID `opencode.db` sessions to new shared location
   - Run automatically on first launch with new code
   - Handle edge cases (missing directories, permission issues)

4. **Update tests**:
   - `tests/test_opencode_launcher.py`: Update `XDG_DATA_HOME` assertions
   - Add new tests for shared state directory behavior
   - Add test for `MMS_OPENCODE_ISOLATE_DATA=1` kill-switch
   - Add test for cross-launch session visibility
   - Add test for profile isolation (different profiles don't see each other's sessions)

5. **Verification**:
   - Manual testing: Cross-launch session visibility
   - Automated testing: Updated test suite passes
   - Regression testing: `python3 scripts/regression_fresh_user_gate.py --quick`

### Phase 2: Track B (Separate PR) - DEFERRED

**Timeline**: After Phase 1 is stable and deployed
**Scope**: Extend MMS session catalog to include OpenCode sessions for MMS-level tooling

1. **Add OpenCode scanning to `mms_session_catalog.py`**:
   - Implement `opencode_roots()` with profile-aware scanning (glob `state/*/opencode`)
   - Implement `_opencode_db_records()` with corrected SQL schema
   - Add schema version check and graceful degradation
   - Update `list_session_records()` to include OpenCode

2. **Add session index functions to `mms_session_index.py`**:
   - Implement `record_opencode_session_start()` and `finalize_opencode_session()`
   - Handle exec path (OpenCode TUI uses `os.execvp`)
   - Add signal handlers for session finalization

3. **Comprehensive testing**:
   - Test cross-CLI session discovery (OpenCode sessions appear in `mms session list`)
   - Test exec path session recording
   - Test schema version compatibility

### Phase 3: Documentation and Cleanup (Optional)

**Timeline**: After Phase 2
**Scope**: Documentation updates and optional enhancements

1. **Update documentation**:
   - `docs/PROVIDER_PROFILES.md` → document new session visibility behavior
   - `docs/RFC_OPENCODE_SIDE_RUNNER_PILOT_2026-06-14.md` → note session visibility fix
   - Update this RFC with implementation notes

2. **Optional enhancements**:
   - Add `mms opencode-migrate` command for manual data migration
   - Add session cleanup for old shared state directories
   - Consider adding session preview support for OpenCode

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Concurrent OpenCode sessions writing same state DB | Medium | SQLite WAL mode already enabled; profile sharding isolates writes; document single-writer per profile guideline |
| Cross-profile privacy leaks | Low | Mandatory `profile_id` sharding prevents accidental sharing; no "default" fallback |
| Breaking existing isolation expectations | Low | `MMS_OPENCODE_ISOLATE_DATA=1` kill-switch provides instant rollback to old behavior |
| Cleanup of shared state directory | Medium | Shared state directory is outside `sessions_dir`; `_cleanup_stale_sessions()` only removes per-PID directories |
| OpenCode future schema changes | Low | Track B (separate PR) will include schema version check and graceful degradation |
| Existing tests assert old behavior | Medium | Explicit test updates documented in Appendix; new tests verify shared behavior |
| Data migration complexity | Low | One-time migration helper runs automatically; handles edge cases gracefully |
| `profile_id` validation | Low | Mandatory parameter with explicit validation prevents accidental misuse |

## Verification Steps

### Manual Verification

```bash
# 1. Test basic session visibility (core fix verification)
mms opencode --profile agent --once -m "echo hello-A"
mms opencode --profile agent
# Open Sessions panel → should show "hello-A" session

# 2. Test profile isolation
mms opencode --profile agent --once -m "echo agent-session"
mms opencode --profile review --once -m "echo review-session"
mms opencode --profile agent
# Sessions panel should show "agent-session" but NOT "review-session"

# 3. Test kill-switch rollback
MMS_OPENCODE_ISOLATE_DATA=1 mms opencode --profile agent --once -m "echo isolated"
MMS_OPENCODE_ISOLATE_DATA=1 mms opencode --profile agent
# Sessions panel should show "No results found" (old behavior restored)

# 4. Test config isolation preserved
python3 -c "import os; \
  print('CONFIG:', os.environ['XDG_CONFIG_HOME']); \
  print('STATE:', os.environ['XDG_STATE_HOME'])"
# CONFIG should differ between sessions; STATE should be the same

# 5. Test migration of existing sessions
ls -la ~/.local/share/mms-opencode/state/agent/opencode/opencode.db
# Should contain migrated sessions from previous per-PID directories
```

### Automated Verification

```bash
# Run OpenCode-specific tests
pytest tests/test_opencode_launcher.py -v

# Run session catalog tests (Phase 2)
pytest tests/test_session_catalog.py -v

# Run regression gate
python3 scripts/regression_fresh_user_gate.py --quick

# Full test suite
pytest tests/ -x

# Verify shared state directory structure
ls -la ~/.local/share/mms-opencode/state/
# Should show profile-based subdirectories (agent/, review/, etc.)
```

### Kill-Switch Verification

```bash
# Test that MMS_OPENCODE_ISOLATE_DATA=1 restores old behavior
export MMS_OPENCODE_ISOLATE_DATA=1
mms opencode --profile agent --once -m "test isolation"
mms opencode --profile agent
# Should show "No results found" (old per-PID behavior)

# Verify XDG paths reverted
python3 -c "import os; \
  print('DATA_HOME:', os.environ['XDG_DATA_HOME']); \
  print('Expected: session_home/.local/share (per-PID)')"
```

### Side-Runner RFC #10 Compatibility

```bash
# Test side-runner still works with shared state
mms opencode --profile agent
/side new review "test side runner"
/side status
# Alias works and session appears in switcher

# Verify side-runner uses shared state
ls -la ~/.local/share/mms-opencode/state/agent/opencode/
# Should contain side-runner session data
```

## Success Criteria

### Phase 1 Success Criteria (Immediate)

1. **Primary Success**: OpenCode session switcher shows prior sessions when using MMS profiles
2. **Profile Isolation**: Different profiles (agent/review/committee) do not see each other's sessions
3. **Kill-Switch Works**: `MMS_OPENCODE_ISOLATE_DATA=1` restores old per-PID behavior
4. **No Regressions**: Existing Claude/Codex session functionality unaffected
5. **Tests Pass**: All existing and new tests pass
6. **Migration Works**: Existing per-PID sessions are migrated to shared location

### Phase 2 Success Criteria (Separate PR)

1. **MMS Catalog Integration**: `mms session list` includes OpenCode sessions
2. **Cross-CLI Discovery**: OpenCode sessions appear in MMS WebUI session list
3. **Schema Resilience**: Graceful handling of OpenCode schema changes

### Overall Success Metrics

1. **User Impact**: Users can resume prior OpenCode sessions after MMS profile launches
2. **Workflow Continuity**: Side-runner RFC (#10) alias resume works correctly
3. **Performance**: No measurable impact on OpenCode launch time
4. **Reliability**: No SQLite corruption or locking errors in production

## Related Documents

- **Issue #8**: Bug: OpenCode profile cannot switch sessions; session list is empty
- **RFC #10**: Pilot OpenCode side-runner for managed background sessions
- **`docs/PROVIDER_PROFILES.md`**: Profile configuration documentation
- **`docs/MMS_USER_PREFERENCES.md`**: User preferences schema
- **`docs/RFC_OPENCODE_SESSION_SWITCHING_FIX_2026-06-15.md`**: This document (RFC)

## Changelog

- **2026-06-15**: Initial RFC creation
- **2026-06-15**: Updated with committee review feedback
  - Added review summary section with all 5 committee member feedback
  - Updated Track A Option 1 with mandatory `profile_id` and XDG-compliant path
  - Added `MMS_OPENCODE_ISOLATE_DATA=1` kill-switch to Phase 1
  - Separated Track B into follow-up PR
  - Updated risk mitigations and verification steps
  - Added OpenCode database schema appendix with corrected SQL
  - Added migration script example
  - Added test assertions to update

## Committee Review

### Review Summary (2026-06-15)

All 5 committee members reviewed this RFC and provided **"Approve with modifications"** feedback. The root cause analysis was verified as accurate, and Track A Option 1 (Shared State Directory) was unanimously recommended. Key modifications required before implementation:

### Required Modifications (Blocking)

1. **`profile_id` Threading Implementation**: Must specify exact code path from `launch_opencode()` → `opencode_gateway_env()` → `opencode_set_soft_home()`
2. **Track B SQL Schema Correction**: Actual OpenCode schema uses different column names and data types
3. **Add `MMS_OPENCODE_ISOLATE_DATA=1` Kill-Switch**: Implement in Phase 1, not as optional
4. **Separate Track B into Follow-Up PR**: Keep core fix focused and reduce review burden

### Recommended Modifications (Non-Blocking)

1. Consider XDG-compliant path (`~/.local/share/mms-opencode`) instead of `~/.config/mms/opencode-gateway/state`
2. Add schema version check and graceful degradation for Track B
3. Add one-time data migration helper in Phase 1
4. Explicitly list test files and assertions to update

### Detailed Review Feedback

#### deepseek-v4-pro-7:
- **Approved with modifications**
- Strengths: Precise root cause analysis, OMO comparison is illuminating, risk matrix is realistic
- Required: Specify `profile_id` threading path, make Track B profile-aware, add migration plan
- Recommended: Add schema-version guard, add concurrent access test

#### glm-5-2-7:
- **Approved with modifications**
- Strengths: Empirical confirmation of bug (16 trapped sessions), accurate test-impact analysis
- Required: Fix Track B SQL columns (`directory`, `time_created`, `time_updated`, `model`), make `profile_id` mandatory
- Recommended: Defer Track B to follow-up PR, add one-time data migration

#### kimi-k2-7-code-7:
- **Approved with modifications**
- Strengths: Balanced option comparison, clear dual-track strategy
- Required: Adjust shared state path to XDG standard, sanitize `profile_id`, promote migration to recommended
- Recommended: Implement Track B in follow-up PR, add rollback mechanism

#### minimax-m3-7:
- **Approved with modifications**
- Strengths: Precise root cause, good OMO comparison, realistic risk table
- Required: Add cleanup safety check, rename diagnostic marker to `MMS_OPENCODE_STATE_SHARED`
- Recommended: Defer Track B, add one-time migration in Phase 1, enumerate test updates

#### qwen3-7-max-7:
- **Approved with modifications**
- Strengths: Verified all three causes against source, balanced option comparison
- Required: Add `profile_id` plumbing details, verify `XDG_STATE_HOME` sharing necessity
- Recommended: Add kill-switch in Phase 1, separate Track B PR, test exec path

### Committee Decisions

Based on review feedback, the following decisions have been made:

1. **Track A Option 1 (Shared State Directory)** is approved with mandatory `profile_id` sharding
2. **Track B will be implemented in a separate PR** to keep the core fix focused
3. **`MMS_OPENCODE_ISOLATE_DATA=1` kill-switch** will be added in Phase 1
4. **One-time data migration helper** will be added in Phase 1 (not optional)
5. **Shared state path** will use XDG-compliant location: `~/.local/share/mms-opencode/state/<profile_id>`

### Updated Implementation Plan

Based on committee review, the implementation plan has been updated:

#### Phase 1: Core Fix (Must Have) - UPDATED
1. **Modify `mms_opencode_env.py`**:
   - Update `opencode_set_soft_home()` to use shared state directory at `~/.local/share/mms-opencode/state/<profile_id>`
   - Add mandatory `profile_id` parameter (no fallback to "default")
   - Add `MMS_OPENCODE_ISOLATE_DATA=1` kill-switch for rollback
   - Add `MMS_OPENCODE_STATE_SHARED=1` diagnostic marker

2. **Update caller chain with explicit `profile_id` threading**:
   - `opencode_gateway_env()`: Extract `runtime.get("opencode_profile", "lite")` and pass as `profile_id`
   - `mms_launchers.py:_set_opencode_soft_home()`: Add `profile_id` parameter and forward

3. **Add one-time data migration helper**:
   - Script to copy existing per-PID `opencode.db` sessions to new shared location
   - Run automatically on first launch with new code

4. **Update tests**:
   - `tests/test_opencode_launcher.py`: Update `XDG_DATA_HOME` assertions
   - Add new tests for shared state directory behavior
   - Add test for `MMS_OPENCODE_ISOLATE_DATA=1` kill-switch
   - Add test for cross-launch session visibility

#### Phase 2: Track B (Separate PR) - DEFERRED
- Will be implemented in a follow-up PR after Phase 1 is stable
- Will include corrected SQL schema and profile-aware scanning
- Will address exec path session recording

### Next Steps

1. ~~Committee review of this RFC~~ ✅ COMPLETED (2026-06-15)
2. ~~Decision on Track A implementation option~~ ✅ COMPLETED (Option 1 with modifications)
3. ~~Update RFC with required modifications~~ ✅ COMPLETED (current version)
4. **Implementation of Phase 1**: Start immediately
   - Modify `mms_opencode_env.py` with updated `opencode_set_soft_home()`
   - Update caller chain with explicit `profile_id` threading
   - Add one-time data migration helper
   - Update tests and verify kill-switch functionality
5. **Testing and validation**: Verify all success criteria
6. **Merge and deployment**: Deploy Phase 1 fix
7. **Create follow-up RFC for Track B**: After Phase 1 stability confirmed

## Appendix: OpenCode Database Schema

Based on committee verification, the actual OpenCode SQLite schema for the `session` table is:

```sql
-- Actual columns in opencode.db session table
CREATE TABLE session (
    id TEXT PRIMARY KEY,
    title TEXT,
    directory TEXT,  -- NOT 'cwd' as initially assumed
    time_created INTEGER,  -- epoch milliseconds, NOT ISO string
    time_updated INTEGER,  -- epoch milliseconds, NOT ISO string
    model TEXT  -- JSON object, NOT simple string
);
```

**Important**: Column names and data types differ from initial RFC assumptions:
- `directory` instead of `cwd`
- `time_created`/`time_updated` as epoch-ms integers (requires conversion to ISO)
- `model` as JSON object (requires parsing to extract model ID)

### Track B SQL Query (Corrected)

```python
def _opencode_db_records(root: Path) -> list[dict]:
    """Scan OpenCode SQLite database for session records."""
    db_path = root / "opencode.db"
    if not db_path.exists():
        return []

    try:
        import sqlite3
        import json
        from datetime import datetime, timezone

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute(
            "SELECT id, title, directory, time_created, time_updated, model FROM session"
        )
        records = []
        for row in cursor:
            # Convert epoch-ms to ISO format
            created_at = ""
            if row[3]:
                created_at = datetime.fromtimestamp(
                    row[3]/1000, tz=timezone.utc
                ).isoformat()

            updated_at = ""
            if row[4]:
                updated_at = datetime.fromtimestamp(
                    row[4]/1000, tz=timezone.utc
                ).isoformat()

            # Parse model JSON to extract ID
            model_id = ""
            if row[5]:
                try:
                    model_data = json.loads(row[5])
                    model_id = model_data.get("id", "")
                except (json.JSONDecodeError, AttributeError):
                    model_id = row[5]  # Fallback to raw string

            records.append({
                "cli": "opencode",
                "session_id": row[0],
                "title": row[1] or "",
                "cwd": row[2] or "",  # Map directory -> cwd for consistency
                "created_at": created_at,
                "updated_at": updated_at,
                "model": model_id,
            })
        conn.close()
        return records
    except Exception as e:
        # Log error but don't crash
        import logging
        logging.warning(f"Failed to read OpenCode DB at {db_path}: {e}")
        return []
```

### Migration Script Example

```bash
#!/bin/bash
# One-time migration of existing per-PID OpenCode sessions
# Run after installing updated MMS with Phase 1 fix

set -e

SHARED_DIR="$HOME/.local/share/mms-opencode/state"
PID_DIRS="$HOME/.config/mms/opencode-gateway/s"

echo "OpenCode Session Migration Tool"
echo "================================"

# Find all per-PID directories with opencode.db
PID_DBS=$(find "$PID_DIRS" -name "opencode.db" -type f 2>/dev/null || true)

if [ -z "$PID_DBS" ]; then
    echo "No existing per-PID OpenCode sessions found."
    echo "Nothing to migrate."
    exit 0
fi

echo "Found existing OpenCode sessions:"
echo "$PID_DBS" | while read -r db; do
    pid_dir=$(dirname "$db")
    pid=$(basename "$pid_dir")
    sessions=$(sqlite3 "$db" "SELECT COUNT(*) FROM session;" 2>/dev/null || echo "0")
    echo "  PID $pid: $sessions sessions"
done

# Create shared directory structure for default profile
mkdir -p "$SHARED_DIR/default/opencode"

# Use the most recent per-PID database as the source
LATEST_PID_DB=$(ls -t $PID_DBS | head -1)

if [ -n "$LATEST_PID_DB" ]; then
    echo ""
    echo "Migrating sessions from: $LATEST_PID_DB"

    # Copy database (simple approach)
    cp "$LATEST_PID_DB" "$SHARED_DIR/default/opencode/opencode.db"

    # Verify migration
    MIGRATED_SESSIONS=$(sqlite3 "$SHARED_DIR/default/opencode/opencode.db" "SELECT COUNT(*) FROM session;" 2>/dev/null || echo "0")
    echo "Migration complete. $MIGRATED_SESSIONS sessions migrated to shared location."
    echo ""
    echo "Shared database location: $SHARED_DIR/default/opencode/opencode.db"
    echo ""
    echo "Note: Old per-PID directories have not been deleted."
    echo "They can be manually removed after verifying the migration."
else
    echo "ERROR: Could not find a valid OpenCode database to migrate."
    exit 1
fi
```
