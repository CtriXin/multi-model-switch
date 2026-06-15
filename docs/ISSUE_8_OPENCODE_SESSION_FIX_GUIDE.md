# Issue #8: OpenCode Session Switching Fix - Complete Analysis & Implementation Guide

Date: 2026-06-15
Status: **RFC Approved - Ready for Implementation**
Related Issues: Issue #8, RFC #10 (Side-Runner Pilot)

## Overview

This document provides a comprehensive record of the analysis, review, and implementation plan for fixing Issue #8: "OpenCode profile cannot switch sessions; session list is empty". It serves as a complete reference for any agent working on this fix.

## Issue Summary

**Problem**: When using MMS OpenCode profiles (agent/review/committee/lite/raw), the OpenCode session switcher shows "No results found" and cannot discover any prior session records.

**Impact**: Blocks core workflow continuity and prevents the side-runner RFC (#10) from functioning correctly.

**Root Cause**: Per-PID XDG state isolation in `mms_opencode_env.py:opencode_set_soft_home()` redirects OpenCode's XDG state directories into PID-keyed ephemeral directories.

## Analysis Timeline

### 1. Initial Analysis (2026-06-15)
- **Action**: Distributed Issue #8 to all 5 committee members for analysis
- **Members**: deepseek-v4-pro-7, glm-5-2-7, kimi-k2-7-code-7, minimax-m3-7, qwen3-7-max-7
- **Result**: All members identified the same root cause and proposed similar solutions

### 2. RFC Creation (2026-06-15)
- **Action**: Created detailed RFC document
- **Document**: `docs/RFC_OPENCODE_SESSION_SWITCHING_FIX_2026-06-15.md`
- **Content**: Root cause analysis, proposed solutions, implementation plan, risk assessment

### 3. Committee Review (2026-06-15)
- **Action**: Parallel review of RFC by all 5 committee members
- **Result**: All members approved with modifications
- **Key Feedback**:
  1. Mandatory `profile_id` parameter (no fallback to "default")
  2. XDG-compliant path (`~/.local/share/mms-opencode`)
  3. Add `MMS_OPENCODE_ISOLATE_DATA=1` kill-switch
  4. Separate Track B into follow-up PR
  5. One-time data migration helper

### 4. RFC Update (2026-06-15)
- **Action**: Updated RFC based on all committee feedback
- **Changes**: Implemented all required modifications
- **Status**: Approved with modifications

## Technical Details

### Root Cause Analysis

**Primary Cause**: `mms_opencode_env.py:opencode_set_soft_home()` (lines 17-29)
```python
env["XDG_DATA_HOME"] = os.path.join(session_home, ".local", "share")
env["XDG_STATE_HOME"] = os.path.join(session_home, ".local", "state")
```
Where `session_home = ~/.config/mms/opencode-gateway/s/<pid>/`

**Impact**: Each MMS OpenCode launch gets a fresh, empty `XDG_DATA_HOME`, so OpenCode's session database (`opencode.db`) is isolated per-PID.

**Secondary Cause**: MMS session catalog lacks OpenCode scanning
- `mms_session_catalog.py:list_session_records()` only scans `claude` and `codex`
- No `opencode` branch exists

**Tertiary Cause**: Missing session index integration
- `mms_session_index.py` only has Claude-specific functions
- `launch_opencode` never calls session recording functions

### Comparison with OMO Profile

OMO profile works because it uses real user directories:
```python
env["XDG_DATA_HOME"] = real_user_path(".local", "share")
env["XDG_STATE_HOME"] = real_user_path(".local", "state")
```

## Proposed Solution

### Track A: Core Fix (Phase 1)

**Strategy**: Share OpenCode data directory across MMS launches while preserving config isolation.

**Implementation**: Modify `opencode_set_soft_home()` to use shared state directory at `~/.local/share/mms-opencode/state/<profile_id>`

**Key Changes**:
1. Mandatory `profile_id` parameter (raise ValueError if missing)
2. XDG-compliant shared state path
3. `MMS_OPENCODE_ISOLATE_DATA=1` kill-switch for rollback
4. One-time data migration helper

### Track B: MMS Session Catalog Integration (Phase 2 - Separate PR)

**Strategy**: Extend MMS session catalog to include OpenCode sessions for MMS-level tooling.

**Implementation**:
1. Add OpenCode scanning to `mms_session_catalog.py`
2. Add session index functions to `mms_session_index.py`
3. Integrate with `launch_opencode()` for session recording

**Note**: Track B will be implemented in a separate PR after Phase 1 is stable.

## Implementation Plan

### Phase 1: Core Fix (Immediate)

**Files to Modify**:
1. `mms_opencode_env.py` - Update `opencode_set_soft_home()`
2. `mms_launchers.py` - Update caller chain with `profile_id` threading
3. `tests/test_opencode_launcher.py` - Update tests

**Key Implementation Details**:
```python
def opencode_set_soft_home(env, session_home, *, real_user_path, set_session_home_hint, profile_id):
    if not profile_id:
        raise ValueError("profile_id is required")
    
    # Shared state directory (XDG-compliant)
    state_root = real_user_path(".local", "share", "mms-opencode", "state", profile_id)
    os.makedirs(state_root, exist_ok=True)
    
    env["XDG_DATA_HOME"] = state_root  # Shared across launches
    env["XDG_STATE_HOME"] = state_root  # Shared across launches
    
    # Kill-switch for rollback
    if os.environ.get("MMS_OPENCODE_ISOLATE_DATA") == "1":
        env["XDG_DATA_HOME"] = os.path.join(session_home, ".local", "share")
        env["XDG_STATE_HOME"] = os.path.join(session_home, ".local", "state")
```

### Phase 2: Track B (Separate PR)

**Files to Create/Modify**:
1. `mms_session_catalog.py` - Add `opencode_roots()` and `_opencode_db_records()`
2. `mms_session_index.py` - Add `record_opencode_session_start()` and `finalize_opencode_session()`
3. `mms_launchers.py` - Integrate session recording in `launch_opencode()`

**OpenCode Database Schema** (verified by committee):
```sql
CREATE TABLE session (
    id TEXT PRIMARY KEY,
    title TEXT,
    directory TEXT,  -- NOT 'cwd'
    time_created INTEGER,  -- epoch milliseconds
    time_updated INTEGER,  -- epoch milliseconds
    model TEXT  -- JSON object
);
```

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Concurrent SQLite writes | Medium | Profile sharding isolates writes; WAL mode enabled |
| Cross-profile privacy leaks | Low | Mandatory `profile_id` sharding |
| Breaking isolation expectations | Low | `MMS_OPENCODE_ISOLATE_DATA=1` kill-switch |
| Data migration complexity | Low | One-time migration helper runs automatically |
| OpenCode schema changes | Low | Track B will include schema version check |

## Verification Steps

### Manual Verification
1. Cross-launch session visibility
2. Profile isolation (agent vs review)
3. Kill-switch functionality
4. Migration of existing sessions

### Automated Verification
```bash
pytest tests/test_opencode_launcher.py -v
python3 scripts/regression_fresh_user_gate.py --quick
```

## Success Criteria

### Phase 1
1. OpenCode session switcher shows prior sessions
2. Profile isolation works correctly
3. Kill-switch restores old behavior
4. No regressions in Claude/Codex functionality
5. All tests pass

### Phase 2
1. MMS `session list` includes OpenCode sessions
2. Cross-CLI session discovery works
3. Schema resilience implemented

## Related Documents

- **Issue #8**: Bug: OpenCode profile cannot switch sessions; session list is empty
- **RFC #10**: Pilot OpenCode side-runner for managed background sessions
- **RFC Document**: `docs/RFC_OPENCODE_SESSION_SWITCHING_FIX_2026-06-15.md`
- **Provider Profiles**: `docs/PROVIDER_PROFILES.md`
- **User Preferences**: `docs/MMS_USER_PREFERENCES.md`

## Committee Decisions

All 5 committee members approved the RFC with modifications:
1. **deepseek-v4-pro-7**: Approved with modifications
2. **glm-5-2-7**: Approved with modifications  
3. **kimi-k2-7-code-7**: Approved with modifications
4. **minimax-m3-7**: Approved with modifications
5. **qwen3-7-max-7**: Approved with modifications

## Next Steps for Implementation

1. **Start Phase 1**: Implement core fix in `mms_opencode_env.py`
2. **Update Tests**: Modify `tests/test_opencode_launcher.py`
3. **Verify Functionality**: Run manual and automated tests
4. **Deploy**: Merge Phase 1 fix
5. **Plan Phase 2**: Create follow-up RFC for Track B

## Notes for Fresh Session Agents

When starting work on this issue:
1. Read this document first for complete context
2. Review the RFC document: `docs/RFC_OPENCODE_SESSION_SWITCHING_FIX_2026-06-15.md`
3. Check Issue #8 on GitHub for latest comments
4. Follow the implementation plan exactly as specified
5. Verify all success criteria before considering work complete

This document is the authoritative source for Issue #8 implementation details.