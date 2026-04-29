#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MMS_HOME="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_NAME="token-monitor-hook.sh"

resolve_real_home() {
  for candidate in "${MMS_REAL_HOME:-}" "${REAL_HOME:-}" "${ORIGINAL_HOME:-}" "${HOME:-}"; do
    [ -n "${candidate:-}" ] || continue
    printf '%s\n' "$candidate"
    return
  done
}

root_has_target() {
  local root="$1"
  [ -n "${root:-}" ] && [ -f "$root/hooks/$TARGET_NAME" ]
}

resolve_brainkeeper_root() {
  local dev_root real_home candidate

  for candidate in "${BRAINKEEPER_HOME:-}"; do
    if root_has_target "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  dev_root="$(cd "$MMS_HOME/.." && pwd)"
  for candidate in "$dev_root/brainkeeper"; do
    if root_has_target "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  real_home="$(resolve_real_home)"
  for candidate in "${real_home:-}/.local/share/brainkeeper"; do
    if root_has_target "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  for candidate in "${MINDKEEPER_HOME:-}" "$dev_root/mindkeeper" "${real_home:-}/.local/share/mindkeeper"; do
    if root_has_target "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done
}

BRAINKEEPER_ROOT="$(resolve_brainkeeper_root)"
TARGET="${BRAINKEEPER_ROOT:+$BRAINKEEPER_ROOT/hooks/$TARGET_NAME}"
[ -n "${TARGET:-}" ] && [ -f "$TARGET" ] || exit 0
exec /bin/bash "$TARGET" "$@"
