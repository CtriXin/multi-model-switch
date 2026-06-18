#!/usr/bin/env bash
# NSR Codex hook wrapper for MMS-managed and global sessions.

set -euo pipefail

resolve_real_home() {
  for candidate in "${MMS_REAL_HOME:-}" "${REAL_HOME:-}" "${ORIGINAL_HOME:-}" "${HOME:-}"; do
    [ -n "${candidate:-}" ] || continue
    [ -d "$candidate" ] || continue
    printf '%s\n' "$candidate"
    return
  done
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MMS_HOME="$(cd "$SCRIPT_DIR/.." && pwd)"
REAL_HOME="$(resolve_real_home)"
AUTO_SKILLS_ROOT="$(cd "$MMS_HOME/../.." 2>/dev/null && pwd || true)"
MMS_PARENT="$(cd "$MMS_HOME/.." 2>/dev/null && pwd || true)"
BUILTIN_HOOK="$SCRIPT_DIR/nsr-builtin-hook.py"
GLOBAL_NSR_WRAPPER="$REAL_HOME/.mms/hooks/nsr-stop-wrapper.py"
BUNDLED_NSR_WRAPPER="$SCRIPT_DIR/nsr-stop-wrapper.py"

# Prefer the user's installed global NSR payload; MMF worktree copies are only
# fallback so dev branch experiments do not silently override local policy.
if [ -f "$GLOBAL_NSR_WRAPPER" ] && command -v python3 >/dev/null 2>&1; then
  exec python3 "$GLOBAL_NSR_WRAPPER" codex
fi

# Local override for older hand-installed machines; kept only as fallback.
LOCAL_NSR_WRAPPER="$REAL_HOME/.nsr/nsr_stop_hook.py"
if [ -f "$LOCAL_NSR_WRAPPER" ] && command -v python3 >/dev/null 2>&1; then
  exec python3 "$LOCAL_NSR_WRAPPER"
fi

candidates=(
  "${MMS_NSR_ROOT:-}"
  "${NSR_ROOT:-}"
  "${NSR_HOME:-}"
  "$REAL_HOME/auto-skills/shared-skills/nsr"
  "$AUTO_SKILLS_ROOT/shared-skills/nsr"
  "$MMS_PARENT/shared-skills/nsr"
  "$MMS_HOME/vendor/non-stop-run"
  "$REAL_HOME/auto-skills/Non-Stop-Run"
  "$REAL_HOME/auto-skills/shared-skills/looop.deprecated"
  "$AUTO_SKILLS_ROOT/shared-skills/looop.deprecated"
  "$MMS_PARENT/shared-skills/looop.deprecated"
)

for root in "${candidates[@]}"; do
  [ -n "${root:-}" ] || continue
  hook="$root/loop_hook.py"
  if [ -f "$hook" ] && command -v python3 >/dev/null 2>&1; then
    NSR_LOOP_HOOK="$hook" exec python3 "$BUNDLED_NSR_WRAPPER" codex
  fi
  hook="$root/scripts/codex_hook.py"
  if [ -f "$hook" ] && command -v python3 >/dev/null 2>&1; then
    exec python3 "$hook"
  fi
done

if [ -f "$BUNDLED_NSR_WRAPPER" ] && command -v python3 >/dev/null 2>&1; then
  exec python3 "$BUNDLED_NSR_WRAPPER" codex
fi

if [ -f "$BUILTIN_HOOK" ] && command -v python3 >/dev/null 2>&1; then
  exec python3 "$BUILTIN_HOOK" codex
fi

exit 0
