#!/bin/sh
set -eu

export NPM_CONFIG_UPDATE_NOTIFIER=false

if [ -n "${MMS_PI_EXECUTABLE:-}" ]; then
  exec "$MMS_PI_EXECUTABLE" "$@"
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
CACHE_DIR=${MMS_PI_NPX_CACHE:-"$ROOT_DIR/.ai/cache/pi-npx"}
LOCK_DIR="$CACHE_DIR/.mms-pi-npx-install.lock"
LOCK_TIMEOUT=${MMS_PI_NPX_INSTALL_LOCK_TIMEOUT:-300}
LOCK_HELD=0

mkdir -p "$CACHE_DIR"
export NPM_CONFIG_CACHE="$CACHE_DIR"
export npm_config_cache="$CACHE_DIR"

cached_pi_path() {
  for cached_pi in "$CACHE_DIR"/_npx/*/node_modules/.bin/pi; do
    cached_manifest="${cached_pi%/.bin/pi}/@earendil-works/pi-coding-agent/package.json"
    if [ -x "$cached_pi" ] && [ -f "$cached_manifest" ]; then
      printf '%s\n' "$cached_pi"
      return 0
    fi
  done
  return 1
}

release_lock() {
  if [ "$LOCK_HELD" = "1" ] && [ -f "$LOCK_DIR/pid" ]; then
    lock_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
    if [ "$lock_pid" = "$$" ]; then
      rm -rf "$LOCK_DIR"
    fi
  fi
  LOCK_HELD=0
}

acquire_lock() {
  start_time=$(date +%s)
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    if [ -f "$LOCK_DIR/pid" ]; then
      lock_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
      if [ -n "$lock_pid" ] && ! kill -0 "$lock_pid" 2>/dev/null; then
        rm -rf "$LOCK_DIR"
        continue
      fi
    fi
    now=$(date +%s)
    if [ $((now - start_time)) -ge "$LOCK_TIMEOUT" ]; then
      echo "MMS Pi npx install lock timeout after ${LOCK_TIMEOUT}s: $LOCK_DIR" >&2
      exit 124
    fi
    sleep 1
  done
  printf '%s\n' "$$" > "$LOCK_DIR/pid"
  LOCK_HELD=1
  trap release_lock EXIT INT TERM HUP
}

if CACHED_PI=$(cached_pi_path); then
  exec "$CACHED_PI" "$@"
fi

acquire_lock
if ! CACHED_PI=$(cached_pi_path); then
  npx -y --cache "$CACHE_DIR" @earendil-works/pi-coding-agent --version >/dev/null
  CACHED_PI=$(cached_pi_path) || {
    echo "MMS Pi cache warmup did not produce an executable" >&2
    exit 1
  }
fi
release_lock
trap - EXIT INT TERM HUP
exec "$CACHED_PI" "$@"
