#!/usr/bin/env bash
set -euo pipefail

# MMS-owned xmem bootstrap. Silent/fail-open: hook output must not disturb agents.

resolve_xmem() {
  local real_home candidate
  real_home="${MMS_REAL_HOME:-${REAL_HOME:-${ORIGINAL_HOME:-$HOME}}}"
  for candidate in \
    "${MMS_XMEM_BIN:-}" \
    "${XMEM_BIN:-}" \
    "${real_home:-}/.local/bin/xmem" \
    "${real_home:-}/auto-skills/CtriXin-repo/xmem/bin/xmem"
  do
    [ -n "${candidate:-}" ] || continue
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  command -v xmem 2>/dev/null || true
}

XMEM_BIN="$(resolve_xmem)"
[ -n "${XMEM_BIN:-}" ] || exit 0

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
[ -n "${repo_root:-}" ] || exit 0

"$XMEM_BIN" hook start --path "$repo_root" >/dev/null 2>&1 || true
