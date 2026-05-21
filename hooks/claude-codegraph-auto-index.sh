#!/usr/bin/env bash
set -euo pipefail

# Sync CodeGraph for the current git worktree on session start.
# First-time `codegraph init -i` stays manual so the repo does not gain a
# surprising `.codegraph/` directory just because an agent session started.
# Skips if: not in a git repo, codegraph not installed, not initialized, or sync fails.

CODEGRAPH_BIN="${CODEGRAPH_BIN:-codegraph}"

if ! command -v "$CODEGRAPH_BIN" >/dev/null 2>&1; then
  exit 0
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$repo_root" ] || [ ! -d "$repo_root" ]; then
  exit 0
fi

cd "$repo_root"

if [ ! -d ".codegraph" ]; then
  exit 0
fi

"$CODEGRAPH_BIN" sync >/dev/null 2>&1 || true
