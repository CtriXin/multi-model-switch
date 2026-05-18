#!/usr/bin/env bash

set -euo pipefail

REAL_HOME="${MMS_REAL_HOME:-${REAL_HOME:-${ORIGINAL_HOME:-$HOME}}}"
MAP_INSTALL_DIR="${MAP_INSTALL_DIR:-$REAL_HOME/.local/share/map}"
HOOK_SCRIPT="${MAP_INSTALL_DIR}/dist/hooks/session-start.js"

if ! command -v node >/dev/null 2>&1; then
  exit 0
fi

if [ ! -f "$HOOK_SCRIPT" ]; then
  exit 0
fi

# Codex treats stdout that starts like JSON (for example "[map] ...") as hook
# JSON and reports invalid output. Keep optional Map progress off stdout.
if output="$(node "$HOOK_SCRIPT" 2>&1)" && [ -n "$output" ] && [ "${MMS_MAP_HOOK_DEBUG:-0}" = "1" ]; then
  printf '%s\n' "$output" >&2
fi

exit 0
