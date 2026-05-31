#!/usr/bin/env bash
set -euo pipefail
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:${PATH:-}"

# Link the maintainer's local command matrix without touching ~/.config/mms.
# mms = public installed copy, mmd = stable worktree, mmf = dev worktree,
# mmg = canary worktree, mmm = main worktree.

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
MAIN_ROOT_DEFAULT="$REPO_ROOT"
case "$REPO_ROOT" in
  */.worktrees/*) MAIN_ROOT_DEFAULT="${REPO_ROOT%%/.worktrees/*}" ;;
esac
DEV_ROOT_DEFAULT="$MAIN_ROOT_DEFAULT/.worktrees/dev"
CANARY_ROOT_DEFAULT="$MAIN_ROOT_DEFAULT/.worktrees/canary"
STABLE_ROOT_DEFAULT="$MAIN_ROOT_DEFAULT/.worktrees/stable-v3.3-no-db"
if [ "$(basename "$REPO_ROOT")" = "dev" ] && [ "$(basename "$(dirname "$REPO_ROOT")")" = ".worktrees" ]; then
  DEV_ROOT_DEFAULT="$REPO_ROOT"
fi
if [ "$(basename "$REPO_ROOT")" = "canary" ] && [ "$(basename "$(dirname "$REPO_ROOT")")" = ".worktrees" ]; then
  CANARY_ROOT_DEFAULT="$REPO_ROOT"
fi
if [ "$(basename "$REPO_ROOT")" = "stable-v3.3-no-db" ] && [ "$(basename "$(dirname "$REPO_ROOT")")" = ".worktrees" ]; then
  STABLE_ROOT_DEFAULT="$REPO_ROOT"
fi

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
MAIN_ROOT="${MMS_MAIN_ROOT:-$MAIN_ROOT_DEFAULT}"
DEV_ROOT="${MMS_DEV_ROOT:-$DEV_ROOT_DEFAULT}"
CANARY_ROOT="${MMS_CANARY_ROOT:-$CANARY_ROOT_DEFAULT}"
STABLE_ROOT="${MMS_STABLE_ROOT:-$STABLE_ROOT_DEFAULT}"
MANAGED_PYTHON="${MMS_MANAGED_PYTHON:-$REAL_HOME_VALUE/.mms/.venv/bin/python}"
PREVIEW_CONFIG_ROOT="$REAL_HOME_VALUE/.config/mms-next"
UPDATE_SCRIPT="${MMS_LOCAL_CHANNEL_UPDATE_SCRIPT:-$REPO_ROOT/scripts/local_channel_update.py}"

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
  local branch="$5"
  local cadence="$6"
  local target="$BIN_DIR/$name"
  require_file "$name entry" "$root/$entry"
  rm -f "$target"
  cat > "$target" <<EOF_WRAPPER
#!/bin/sh
set -eu
ROOT="$root"
ENTRY="$entry"
PYTHON="$MANAGED_PYTHON"
UPDATER="$UPDATE_SCRIPT"
UPDATE_BRANCH="$branch"
UPDATE_CADENCE="$cadence"
export MMS_COMMAND_NAME="$name"
EOF_WRAPPER
  if [ "$config_mode" = "preview" ]; then
    cat >> "$target" <<EOF_WRAPPER
export MMS_CONFIG_ROOT="$PREVIEW_CONFIG_ROOT"
export MMS_PREVIEW_MODE="$name"
EOF_WRAPPER
  else
    cat >> "$target" <<'EOF_WRAPPER'
unset MMS_CONFIG_ROOT || true
unset MMS_CONFIG_DIR || true
unset MMS_PREVIEW_MODE || true
EOF_WRAPPER
  fi
  cat >> "$target" <<'EOF_WRAPPER'
run_update_hook() {
  [ -f "$UPDATER" ] || return 0
  UPDATE_PYTHON="$PYTHON"
  [ -x "$UPDATE_PYTHON" ] || UPDATE_PYTHON="python3"
  if [ "${1:-}" = "update" ]; then
    shift
    exec "$UPDATE_PYTHON" "$UPDATER" update --command "$MMS_COMMAND_NAME" --kind worktree --root "$ROOT" --branch "$UPDATE_BRANCH" --cadence "$UPDATE_CADENCE" "$@"
  fi
  [ -t 1 ] || return 0
  case "${1:-}" in -h|--help|help) return 0 ;; esac
  case " $* " in *" --json "*) return 0 ;; esac
  "$UPDATE_PYTHON" "$UPDATER" remind --command "$MMS_COMMAND_NAME" --kind worktree --root "$ROOT" --branch "$UPDATE_BRANCH" --cadence "$UPDATE_CADENCE" || true
}

run_update_hook "$@"

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
PYTHON="$MANAGED_PYTHON"
UPDATER="$UPDATE_SCRIPT"
export MMS_COMMAND_NAME="mms"
unset MMS_CONFIG_ROOT || true
unset MMS_CONFIG_DIR || true
unset MMS_PREVIEW_MODE || true
if [ -f "\$UPDATER" ]; then
  UPDATE_PYTHON="\$PYTHON"
  [ -x "\$UPDATE_PYTHON" ] || UPDATE_PYTHON="python3"
  if [ "\${1:-}" = "update" ]; then
    shift
    exec "\$UPDATE_PYTHON" "\$UPDATER" update --command "mms" --kind public --cadence daily --public-entry "$PUBLIC_ENTRY" "\$@"
  fi
  if [ -t 1 ]; then
    case "\${1:-}" in -h|--help|help) ;; *) case " \$* " in *" --json "*) ;; *) "\$UPDATE_PYTHON" "\$UPDATER" remind --command "mms" --kind public --cadence daily --public-entry "$PUBLIC_ENTRY" || true ;; esac ;; esac
  fi
fi
exec "$PUBLIC_ENTRY" "\$@"
EOF_WRAPPER
  chmod 755 "$target"
}

write_public_mms_wrapper
write_python_wrapper "mmd" "$STABLE_ROOT" "mms" "stable" "release/stable-v3.3-no-db" "weekly"
write_python_wrapper "mmf" "$DEV_ROOT" "mmf" "preview" "dev" "daily"
write_python_wrapper "mmg" "$CANARY_ROOT" "mms" "preview" "canary" "always"
write_python_wrapper "mmm" "$MAIN_ROOT" "mms" "stable" "main" "daily"

cat <<EOF_SUMMARY
linked local MMS command matrix in $BIN_DIR:
  mms -> public installed copy: $PUBLIC_ENTRY
  mmd -> stable worktree:      $STABLE_ROOT/mms
  mmf -> dev worktree:         $DEV_ROOT/mmf  (MMS_CONFIG_ROOT=$PREVIEW_CONFIG_ROOT)
  mmg -> canary worktree:      $CANARY_ROOT/mms  (MMS_CONFIG_ROOT=$PREVIEW_CONFIG_ROOT)
  mmm -> main worktree:        $MAIN_ROOT/mms
EOF_SUMMARY
