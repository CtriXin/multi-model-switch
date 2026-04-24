#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET="$REPO_ROOT/mindkeeper/hooks/token-monitor-hook.sh"

[ -f "$TARGET" ] || exit 0
exec /bin/bash "$TARGET" "$@"
