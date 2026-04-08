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

node "$HOOK_SCRIPT" || true
