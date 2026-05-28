#!/bin/bash
# Clean leaked install artifacts from older MMS installer runs.
# Default mode is dry-run; pass --apply to remove detected artifacts.

set -euo pipefail

APPLY=0
TARGET_HOME="${MMS_REAL_HOME:-${REAL_HOME:-${ORIGINAL_HOME:-${HOME:-}}}}"

usage() {
    cat <<'EOF'
Usage:

  bash scripts/cleanup_dirty_install.sh
  bash scripts/cleanup_dirty_install.sh --apply
  bash scripts/cleanup_dirty_install.sh --home /path/to/home

Behavior:

- dry-run by default
- scans MMS gateway session homes for leaked installer artifacts
- only removes obvious dirty-install targets when --apply is set:
  - <session-home>/.mms
  - <session-home>/.nvm
  - <session-home>/.config/mms
  - <session-home>/.local/bin/mms
  - <session-home>/.local/bin/mmf
  - <session-home>/.local/bin/mmc
  - <session-home>/.local/bin/ccs
  - ~/.local/bin/mms, ~/.local/bin/mmf, ~/.local/bin/mmc, or ~/.local/bin/ccs when they still point into a gateway session path
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
    if [[ "$raw" == */.config/mms/*/s/* ]]; then
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
    ACTION_KIND+=("$1")
    ACTION_PATH+=("$2")
    ACTION_REASON+=("$3")
}

path_contains_gateway_session() {
    local value="$1"
    [[ "$value" == *"/.config/mms/"*"/s/"* ]]
}

collect_session_artifacts() {
    local session_home="$1"
    local candidate=""

    for candidate in \
        "$session_home/.mms" \
        "$session_home/.nvm" \
        "$session_home/.config/mms"
    do
        if [ -e "$candidate" ]; then
            add_action "dir" "$candidate" "leaked installer directory inside gateway session home"
        fi
    done

    for candidate in \
        "$session_home/.local/bin/mms" \
        "$session_home/.local/bin/mmf" \
        "$session_home/.local/bin/mmc" \
        "$session_home/.local/bin/ccs"
    do
        if [ -e "$candidate" ] || [ -L "$candidate" ]; then
            add_action "file" "$candidate" "leaked launcher link inside gateway session home"
        fi
    done
}

collect_real_home_bin_artifacts() {
    local candidate=""
    local resolved=""

    for candidate in \
        "$TARGET_HOME/.local/bin/mms" \
        "$TARGET_HOME/.local/bin/mmf" \
        "$TARGET_HOME/.local/bin/mmc" \
        "$TARGET_HOME/.local/bin/ccs"
    do
        if [ ! -L "$candidate" ]; then
            continue
        fi
        resolved="$(python3 - "$candidate" <<'PY'
import os
import sys
path = sys.argv[1]
try:
    print(os.path.realpath(path))
except OSError:
    print("")
PY
)"
        if [ -n "$resolved" ] && path_contains_gateway_session "$resolved"; then
            add_action "file" "$candidate" "stale real-home launcher link still points into a gateway session"
        fi
    done
}

remove_action() {
    local kind="$1"
    local path="$2"
    if [ "$kind" = "dir" ]; then
        rm -rf "$path"
    else
        rm -f "$path"
    fi
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --apply)
            APPLY=1
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

for session_root in \
    "$TARGET_HOME/.config/mms/claude-gateway/s" \
    "$TARGET_HOME/.config/mms/codex-gateway/s"
do
    [ -d "$session_root" ] || continue
    for session_home in "$session_root"/*; do
        [ -d "$session_home" ] || continue
        collect_session_artifacts "$session_home"
    done
done

collect_real_home_bin_artifacts

log "MMS dirty-install cleanup"
log "target_home: $TARGET_HOME"
log "mode: $([ "$APPLY" -eq 1 ] && printf 'apply' || printf 'dry-run')"

if [ "${#ACTION_PATH[@]}" -eq 0 ]; then
    log "result: no leaked install artifacts detected"
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
log "cleanup applied: removed ${#ACTION_PATH[@]} artifact(s)"
