#!/usr/bin/env bash

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

INPUT="$(cat)"
URL="$(printf '%s' "$INPUT" | jq -r '.tool_input.url // empty')"

if [ -z "$URL" ]; then
  exit 0
fi

if ! printf '%s' "$URL" | grep -Eq 'https?://[^ ]*(feishu\.cn|larksuite\.com)/'; then
  exit 0
fi

if ! printf '%s' "$URL" | grep -Eq '/(wiki|docx|docs|sheet|sheets|base|bitable)/'; then
  exit 0
fi

if ! command -v lark-cli >/dev/null 2>&1; then
  exit 0
fi

REAL_HOME="${MMS_REAL_HOME:-${REAL_HOME:-${ORIGINAL_HOME:-$HOME}}}"
LARK_BIN="$(command -v lark-cli)"
REASON="Private Feishu/Lark URLs should be read with local lark-cli instead of WebFetch."
CONTEXT="$(cat <<EOF
This Feishu/Lark URL is private and WebFetch usually gets redirected to login. Use Bash with lark-cli under the real user home instead, for example:
HOME="$REAL_HOME" "$LARK_BIN" docs +fetch --doc "$URL" --format json
Then continue from the fetched content without asking the user to paste the document unless lark-cli also fails.
EOF
)"

jq -n \
  --arg reason "$REASON" \
  --arg context "$CONTEXT" \
  '{
    "hookSpecificOutput": {
      "hookEventName": "PreToolUse",
      "permissionDecision": "deny",
      "permissionDecisionReason": $reason,
      "additionalContext": $context
    }
  }'
