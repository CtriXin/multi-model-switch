#!/usr/bin/env bash
set -euo pipefail

# MMS-owned xmem gateway probe. Silent/fail-open by default.
# It lets launchers measure when xmem would inject without editing every skill.

resolve_xmem() {
  local real_home candidate
  real_home="${MMS_REAL_HOME:-${REAL_HOME:-${ORIGINAL_HOME:-${HOME:-}}}}"
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

extract_prompt() {
  python3 -c '
import json, sys
raw = sys.stdin.read()
if not raw.strip():
    raise SystemExit(0)
try:
    data = json.loads(raw)
except Exception:
    print(raw.strip())
    raise SystemExit(0)
for key in ("prompt", "user_prompt", "userPrompt", "message", "input"):
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        print(value.strip())
        raise SystemExit(0)
messages = data.get("messages")
if isinstance(messages, list):
    for item in reversed(messages):
        if isinstance(item, dict) and item.get("role") == "user":
            value = item.get("content")
            if isinstance(value, str) and value.strip():
                print(value.strip())
                raise SystemExit(0)
' 2>/dev/null || true
}

compact_json() {
  python3 -c '
import json, sys
try:
    print(json.dumps(json.load(sys.stdin), ensure_ascii=False, separators=(",", ":")))
except Exception:
    pass
' 2>/dev/null || true
}

payload="$(cat || true)"
prompt="$(printf '%s' "$payload" | extract_prompt)"
[ -n "${prompt:-}" ] || exit 0

XMEM_BIN="$(resolve_xmem)"
[ -n "${XMEM_BIN:-}" ] || exit 0

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
[ -n "${repo_root:-}" ] || exit 0

mode="${XMEM_GATEWAY_HOOK_MODE:-dry-run}"
args=(gateway "$prompt" --cwd "$repo_root" --event pre-task --format json)
if [ "$mode" != "inject" ]; then
  args+=(--dry-run)
fi

out="$("$XMEM_BIN" "${args[@]}" 2>/dev/null || true)"
[ -n "${out:-}" ] || exit 0

real_home="${MMS_REAL_HOME:-${REAL_HOME:-${ORIGINAL_HOME:-${HOME:-}}}}"
xmem_home="${XMEM_HOME:-${real_home:-$HOME}/.xmem}"
mkdir -p "$xmem_home" 2>/dev/null || exit 0
printf '%s' "$out" | compact_json >> "$xmem_home/gateway-hook.jsonl" || true

# Intentionally no stdout: this is dry-run telemetry until injection semantics are enabled.
exit 0
