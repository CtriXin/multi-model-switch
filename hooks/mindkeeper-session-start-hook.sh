#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MMS_HOME="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_NAME="session-start.sh"

resolve_real_home() {
  for candidate in "${MMS_REAL_HOME:-}" "${REAL_HOME:-}" "${ORIGINAL_HOME:-}" "${HOME:-}"; do
    [ -n "${candidate:-}" ] || continue
    printf '%s\n' "$candidate"
    return
  done
}

resolve_mindkeeper_root() {
  if [ -n "${MINDKEEPER_HOME:-}" ] && [ -d "${MINDKEEPER_HOME:-}" ]; then
    printf '%s\n' "$MINDKEEPER_HOME"
    return
  fi

  local dev_root sibling_repo real_home installed_root
  dev_root="$(cd "$MMS_HOME/.." && pwd)"
  sibling_repo="$dev_root/mindkeeper"
  if [ -f "$sibling_repo/hooks/$TARGET_NAME" ]; then
    printf '%s\n' "$sibling_repo"
    return
  fi

  real_home="$(resolve_real_home)"
  installed_root="${real_home:-}/.local/share/mindkeeper"
  if [ -f "$installed_root/hooks/$TARGET_NAME" ]; then
    printf '%s\n' "$installed_root"
    return
  fi
}

MINDKEEPER_ROOT="$(resolve_mindkeeper_root)"
TARGET="${MINDKEEPER_ROOT:+$MINDKEEPER_ROOT/hooks/$TARGET_NAME}"
[ -n "${TARGET:-}" ] && [ -f "$TARGET" ] || exit 0
exec /bin/bash "$TARGET" "$@"
