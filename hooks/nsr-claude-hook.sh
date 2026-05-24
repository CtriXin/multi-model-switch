#!/usr/bin/env bash
# NSR Claude hook wrapper for MMS-managed and global sessions.

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

candidates=(
  "/Users/xin/auto-skills/Non-Stop-Run"
  "${NSR_HOME:-}"
  "$REAL_HOME/auto-skills/shared-skills/looop.deprecated"
  "$AUTO_SKILLS_ROOT/shared-skills/looop.deprecated"
  "$MMS_PARENT/shared-skills/looop.deprecated"
)

for root in "${candidates[@]}"; do
  [ -n "${root:-}" ] || continue
  hook="$root/scripts/claude_hook.py"
  if [ -f "$hook" ] && command -v python3 >/dev/null 2>&1; then
    exec python3 "$hook"
  fi
done

exit 0
