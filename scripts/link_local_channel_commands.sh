#!/usr/bin/env bash
set -euo pipefail

# Link the maintainer's local command matrix without touching ~/.config/mms.
# mms = public installed copy, mmd = stable worktree, mmf = dev worktree,
# mmg = canary worktree, mmm = main worktree.

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

resolve_real_home() {
  local value="${MMS_REAL_HOME:-${REAL_HOME:-${ORIGINAL_HOME:-$HOME}}}"
  case "$value" in
    */.config/mms-next/*) value="${value%%/.config/mms-next/*}" ;;
    */.config/mms/*) value="${value%%/.config/mms/*}" ;;
  esac
  printf '%s\n' "$value"
}

REAL_HOME_VALUE="$(resolve_real_home)"
BIN_DIR="${MMS_LOCAL_BIN:-$REAL_HOME_VALUE/.local/bin}"
PUBLIC_ENTRY="${MMS_PUBLIC_ENTRY:-$REAL_HOME_VALUE/.mms/mms}"
MAIN_ROOT="${MMS_MAIN_ROOT:-$REPO_ROOT}"
DEV_ROOT="${MMS_DEV_ROOT:-$REPO_ROOT/.worktrees/dev}"
CANARY_ROOT="${MMS_CANARY_ROOT:-$REPO_ROOT/.worktrees/canary}"
STABLE_ROOT="${MMS_STABLE_ROOT:-$REPO_ROOT/.worktrees/stable-v3.3-no-db}"
MANAGED_PYTHON="${MMS_MANAGED_PYTHON:-$REAL_HOME_VALUE/.mms/.venv/bin/python}"
PREVIEW_CONFIG_ROOT="$REAL_HOME_VALUE/.config/mms-next"

mkdir -p "$BIN_DIR"

require_file() {
  local label="$1"
  local path="$2"
  if [ ! -f "$path" ]; then
    echo "missing $label: $path" >&2
    exit 2
  fi
}

write_python_wrapper() {
  local name="$1"
  local root="$2"
  local entry="$3"
  local config_mode="$4"
  local target="$BIN_DIR/$name"
  require_file "$name entry" "$root/$entry"
  rm -f "$target"
  cat > "$target" <<EOF_WRAPPER
#!/bin/sh
set -eu
ROOT="$root"
ENTRY="$entry"
PYTHON="$MANAGED_PYTHON"
export MMS_COMMAND_NAME="$name"
EOF_WRAPPER
  if [ "$config_mode" = "preview" ]; then
    cat >> "$target" <<EOF_WRAPPER
export MMS_CONFIG_ROOT="$PREVIEW_CONFIG_ROOT"
export MMS_PREVIEW_MODE="mmf"
EOF_WRAPPER
  else
    cat >> "$target" <<'EOF_WRAPPER'
unset MMS_CONFIG_ROOT || true
unset MMS_CONFIG_DIR || true
unset MMS_PREVIEW_MODE || true
EOF_WRAPPER
  fi
  cat >> "$target" <<'EOF_WRAPPER'
if [ -x "$PYTHON" ]; then
  exec "$PYTHON" "$ROOT/$ENTRY" "$@"
fi
exec "$ROOT/$ENTRY" "$@"
EOF_WRAPPER
  chmod 755 "$target"
}

write_public_mms_wrapper() {
  local target="$BIN_DIR/mms"
  require_file "public mms" "$PUBLIC_ENTRY"
  rm -f "$target"
  cat > "$target" <<EOF_WRAPPER
#!/bin/sh
set -eu
export MMS_COMMAND_NAME="mms"
unset MMS_CONFIG_ROOT || true
unset MMS_CONFIG_DIR || true
unset MMS_PREVIEW_MODE || true
exec "$PUBLIC_ENTRY" "\$@"
EOF_WRAPPER
  chmod 755 "$target"
}

write_public_mms_wrapper
write_python_wrapper "mmd" "$STABLE_ROOT" "mms" "stable"
write_python_wrapper "mmf" "$DEV_ROOT" "mmf" "preview"
write_python_wrapper "mmg" "$CANARY_ROOT" "mms" "preview"
write_python_wrapper "mmm" "$MAIN_ROOT" "mms" "stable"

cat <<EOF_SUMMARY
linked local MMS command matrix in $BIN_DIR:
  mms -> public installed copy: $PUBLIC_ENTRY
  mmd -> stable worktree:      $STABLE_ROOT/mms
  mmf -> dev worktree:         $DEV_ROOT/mmf  (MMS_CONFIG_ROOT=$PREVIEW_CONFIG_ROOT)
  mmg -> canary worktree:      $CANARY_ROOT/mms  (MMS_CONFIG_ROOT=$PREVIEW_CONFIG_ROOT)
  mmm -> main worktree:        $MAIN_ROOT/mms
EOF_SUMMARY
