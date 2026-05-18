#!/usr/bin/env bash
# rtk-hook-version: 3
# RTK Claude Code hook — rewrites commands to use rtk for token savings.
# Requires: rtk >= 0.23.0, jq
#
# This is a thin delegating hook: all rewrite logic lives in `rtk rewrite`,
# which is the single source of truth.

rtk_debug() {
  [ "${MMS_RTK_HOOK_DEBUG:-0}" = "1" ] || return 0
  printf '%s\n' "$*" >&2
}

if ! command -v jq &>/dev/null; then
  rtk_debug "[rtk] WARNING: jq is not installed. Hook cannot rewrite commands."
  exit 0
fi

if ! command -v rtk &>/dev/null; then
  rtk_debug "[rtk] WARNING: rtk is not installed or not in PATH. Hook cannot rewrite commands."
  exit 0
fi

RTK_VERSION=$(rtk --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -n "$RTK_VERSION" ]; then
  MAJOR=$(echo "$RTK_VERSION" | cut -d. -f1)
  MINOR=$(echo "$RTK_VERSION" | cut -d. -f2)
  if [ "$MAJOR" -eq 0 ] && [ "$MINOR" -lt 23 ]; then
    rtk_debug "[rtk] WARNING: rtk $RTK_VERSION is too old (need >= 0.23.0)."
    exit 0
  fi
fi

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [ -z "$CMD" ]; then
  exit 0
fi

REWRITTEN=$(rtk rewrite "$CMD" 2>/dev/null)
EXIT_CODE=$?

case $EXIT_CODE in
  0)
    [ "$CMD" = "$REWRITTEN" ] && exit 0
    ;;
  1)
    exit 0
    ;;
  2)
    exit 0
    ;;
  3)
    ;;
  *)
    exit 0
    ;;
esac

ORIGINAL_INPUT=$(echo "$INPUT" | jq -c '.tool_input')
UPDATED_INPUT=$(echo "$ORIGINAL_INPUT" | jq --arg cmd "$REWRITTEN" '.command = $cmd')

if [ "$EXIT_CODE" -eq 3 ]; then
  jq -n \
    --argjson updated "$UPDATED_INPUT" \
    '{
      "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "updatedInput": $updated
      }
    }'
else
  jq -n \
    --argjson updated "$UPDATED_INPUT" \
    '{
      "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": "RTK auto-rewrite",
        "updatedInput": $updated
      }
    }'
fi
