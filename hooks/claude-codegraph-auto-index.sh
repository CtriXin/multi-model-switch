#!/usr/bin/env bash
set -euo pipefail

# Auto-init and sync CodeGraph for the current git worktree on session start.
# Skips if: not in a git repo, codegraph not installed, or sync/init fails.

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
  "$CODEGRAPH_BIN" init -i >/dev/null 2>&1 || true
else
  "$CODEGRAPH_BIN" sync >/dev/null 2>&1 || true
fi
