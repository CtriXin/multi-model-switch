#!/bin/bash
# Reset MMS-owned install artifacts so the user can reinstall from scratch.
# Default mode is dry-run; pass --apply to remove detected artifacts.

set -euo pipefail

APPLY=0
INCLUDE_SHELL_RC=0
TARGET_HOME="${MMS_REAL_HOME:-${REAL_HOME:-${ORIGINAL_HOME:-${HOME:-}}}}"

usage() {
    cat <<'EOF'
Usage:

  bash scripts/reset_mms_install.sh
  bash scripts/reset_mms_install.sh --apply
  bash scripts/reset_mms_install.sh --apply --include-shell-rc
  bash scripts/reset_mms_install.sh --home /path/to/home

Behavior:

- dry-run by default
- removes MMS-owned install/config surfaces when --apply is set:
  - ~/.mms
  - ~/.config/mms
  - ~/.local/bin/mms
  - ~/.local/bin/ccs
  - ~/.local/bin/mmslogs
- does not touch shared Claude/Codex config, global OAuth state, or ~/.claude / ~/.codex
- --include-shell-rc only removes the exact "# Added by MMS" PATH block from:
  - ~/.zshrc
  - ~/.bashrc
  - ~/.bash_profile
EOF
}

normalize_home() {
    local raw="$1"
    raw="${raw/#\~/$HOME}"
    raw="$(python3 - "$raw" <<'PY'
import os
import sys
print(os.path.abspath(os.path.expanduser(sys.argv[1])))
PY
)"
    if [[ "$raw" == */.config/mms/* ]]; then
        raw="${raw%%/.config/mms/*}"
    fi
    printf '%s\n' "$raw"
}

log() {
    printf '%s\n' "$*"
}

ACTION_KIND=()
ACTION_PATH=()
ACTION_REASON=()

add_action() {
    local kind="$1"
    local path="$2"
    local reason="$3"
    local i=""
    for i in "${!ACTION_PATH[@]}"; do
        if [ "${ACTION_KIND[$i]}" = "$kind" ] && [ "${ACTION_PATH[$i]}" = "$path" ]; then
            return 0
        fi
    done
    ACTION_KIND+=("$kind")
    ACTION_PATH+=("$path")
    ACTION_REASON+=("$reason")
}

path_contains_gateway_session() {
    local value="$1"
    [[ "$value" == *"/.config/mms/"*"/s/"* ]]
}

path_exists_or_link() {
    local path="$1"
    [ -e "$path" ] || [ -L "$path" ]
}

resolved_path() {
    python3 - "$1" <<'PY'
import os
import sys
try:
    print(os.path.realpath(sys.argv[1]))
except OSError:
    print("")
PY
}

file_mentions_mms_surface() {
    local path="$1"
    python3 - "$path" "$TARGET_HOME" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
target_home = sys.argv[2]
try:
    text = path.read_text(encoding="utf-8")
except Exception:
    sys.exit(1)

needles = [
    f"{target_home}/.mms",
    f"{target_home}/.config/mms",
    "/.config/mms/",
]
sys.exit(0 if any(needle in text for needle in needles) else 1)
PY
}

collect_core_artifacts() {
    local candidate=""
    for candidate in \
        "$TARGET_HOME/.mms" \
        "$TARGET_HOME/.config/mms"
    do
        if [ -e "$candidate" ]; then
            add_action "dir" "$candidate" "MMS-owned install/config directory"
        fi
    done
}

collect_launcher_artifacts() {
    local candidate=""
    local resolved=""

    for candidate in \
        "$TARGET_HOME/.local/bin/mms" \
        "$TARGET_HOME/.local/bin/ccs" \
        "$TARGET_HOME/.local/bin/mmslogs"
    do
        if ! path_exists_or_link "$candidate"; then
            continue
        fi
        if [ -L "$candidate" ]; then
            resolved="$(resolved_path "$candidate")"
            if [ -n "$resolved" ] && { [[ "$resolved" == "$TARGET_HOME/.mms/"* ]] || path_contains_gateway_session "$resolved"; }; then
                add_action "file" "$candidate" "launcher link points into MMS install or gateway-session path"
            fi
            continue
        fi
        if [ -f "$candidate" ] && file_mentions_mms_surface "$candidate"; then
            add_action "file" "$candidate" "launcher file references MMS-owned paths"
        fi
    done
}

collect_shell_rc_artifacts() {
    local candidate=""
    [ "$INCLUDE_SHELL_RC" -eq 1 ] || return 0
    for candidate in \
        "$TARGET_HOME/.zshrc" \
        "$TARGET_HOME/.bashrc" \
        "$TARGET_HOME/.bash_profile"
    do
        if [ ! -f "$candidate" ]; then
            continue
        fi
        if grep -Fq "# Added by MMS" "$candidate"; then
            add_action "shell_rc" "$candidate" "contains the exact MMS PATH marker block"
        fi
    done
}

remove_shell_rc_marker() {
    python3 - "$1" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
marker = "# Added by MMS"
path_line = 'export PATH="$HOME/.local/bin:$PATH"'
new_lines = []
i = 0
changed = False
while i < len(lines):
    line = lines[i]
    if line == marker:
        changed = True
        i += 1
        if i < len(lines) and lines[i] == path_line:
            i += 1
        continue
    new_lines.append(line)
    i += 1

if changed:
    content = "\n".join(new_lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")
PY
}

remove_action() {
    local kind="$1"
    local path="$2"
    case "$kind" in
        dir)
            rm -rf "$path"
            ;;
        file)
            rm -f "$path"
            ;;
        shell_rc)
            remove_shell_rc_marker "$path"
            ;;
    esac
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --apply)
            APPLY=1
            shift
            ;;
        --include-shell-rc)
            INCLUDE_SHELL_RC=1
            shift
            ;;
        --home)
            if [ "$#" -lt 2 ]; then
                echo "error: --home requires a path" >&2
                exit 2
            fi
            TARGET_HOME="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "error: unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ -z "$TARGET_HOME" ]; then
    echo "error: could not resolve target home" >&2
    exit 2
fi

TARGET_HOME="$(normalize_home "$TARGET_HOME")"

collect_core_artifacts
collect_launcher_artifacts
collect_shell_rc_artifacts

log "MMS install reset"
log "target_home: $TARGET_HOME"
log "mode: $([ "$APPLY" -eq 1 ] && printf 'apply' || printf 'dry-run')"
log "scope: core install/config + launcher links$([ "$INCLUDE_SHELL_RC" -eq 1 ] && printf ' + shell rc marker' || true)"
log "shared state: leaves ~/.claude, ~/.codex, and global OAuth untouched"

if [ "${#ACTION_PATH[@]}" -eq 0 ]; then
    log "result: no MMS-owned install artifacts detected"
    exit 0
fi

log "detected:"
for i in "${!ACTION_PATH[@]}"; do
    log "  - ${ACTION_PATH[$i]} :: ${ACTION_REASON[$i]}"
done

if [ "$APPLY" -ne 1 ]; then
    log ""
    log "dry-run only; rerun with --apply to remove the paths above"
    exit 0
fi

for i in "${!ACTION_PATH[@]}"; do
    remove_action "${ACTION_KIND[$i]}" "${ACTION_PATH[$i]}"
done

log ""
log "reset applied: removed or cleaned ${#ACTION_PATH[@]} MMS-owned artifact(s)"
