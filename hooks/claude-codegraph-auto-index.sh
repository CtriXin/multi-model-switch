#!/usr/bin/env bash
set -euo pipefail

# Auto-register and sync CodeGraph for the current git worktree on session start.
# Mirrors the user's global Claude hook, but stays quiet for clean hook output.
# Skips if: not in a git repo, codegraph not installed, or init/index/sync fails.

CODEGRAPH_BIN="${CODEGRAPH_BIN:-codegraph}"

if ! command -v "$CODEGRAPH_BIN" >/dev/null 2>&1; then
  exit 0
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$repo_root" ] || [ ! -d "$repo_root" ]; then
  exit 0
fi

if [ ! -d "$repo_root/.codegraph" ]; then
  "$CODEGRAPH_BIN" init "$repo_root" >/dev/null 2>&1 || true
  "$CODEGRAPH_BIN" index "$repo_root" >/dev/null 2>&1 || true
else
  "$CODEGRAPH_BIN" sync "$repo_root" >/dev/null 2>&1 || true
fi
