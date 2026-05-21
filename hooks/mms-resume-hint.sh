#!/usr/bin/env bash
set -euo pipefail

input="$(cat || true)"

session_id=""
if command -v jq >/dev/null 2>&1; then
  session_id="$(printf '%s' "$input" | jq -r '.session_id // .sessionId // empty' 2>/dev/null || true)"
fi
if [ -z "$session_id" ]; then
  session_id="$(printf '%s' "$input" | sed -nE 's/.*"session_id"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' | head -n 1)"
fi
if [ -z "$session_id" ]; then
  session_id="$(printf '%s' "$input" | sed -nE 's/.*"sessionId"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' | head -n 1)"
fi

case "$session_id" in
  ""|"None"|pid-*) exit 0 ;;
  *[!A-Za-z0-9._:-]*) exit 0 ;;
esac

command_name="${MMS_RESUME_COMMAND_NAME:-mms}"
case "$command_name" in
  mms|ccs) ;;
  *) command_name="mms" ;;
esac

printf '\n[MMS] resume: %s resume claude:%s\n' "$command_name" "$session_id"
