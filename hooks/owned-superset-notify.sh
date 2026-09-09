#!/bin/sh
# Global terminal registration only. The app's direct Mastra hook is unchanged.
# Generic session_id/resourceId is not terminal ownership. Check before stdin/IO.
[ -n "${SUPERSET_TAB_ID:-}" ] || exit 0

hook_owner_home="${MMS_REAL_HOME:-${REAL_HOME:-${ORIGINAL_HOME:-${HOME:-}}}}"
[ -n "$hook_owner_home" ] || exit 0
hook_notify="$hook_owner_home/.superset/hooks/notify.sh"
[ -f "$hook_notify" ] || exit 0
exec /bin/bash "$hook_notify" "$@"
