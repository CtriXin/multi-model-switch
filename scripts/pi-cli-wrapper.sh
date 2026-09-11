#!/bin/sh
set -eu

export NPM_CONFIG_UPDATE_NOTIFIER=false

if [ -n "${MMS_PI_EXECUTABLE:-}" ]; then
  exec "$MMS_PI_EXECUTABLE" "$@"
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
SELF_PATH="$SCRIPT_DIR/$(basename "$0")"

absolute_path() {
  [ -n "${1:-}" ] || return 1
  dir=$(CDPATH= cd -- "$(dirname "$1")" 2>/dev/null && pwd) || return 1
  printf '%s/%s\n' "$dir" "$(basename "$1")"
}

# An installed Pi, whether or not its bin directory is on this PATH. MMS
# normally passes MMS_PI_EXECUTABLE, but the installer calls this script
# directly, and npm's global bin is often outside a non-interactive PATH.
# Without this the cache below is the only option, and npx refuses to fill it
# while a global copy exists — which left "warmup did not produce an
# executable" on machines whose terminal ran pi perfectly well.
installed_pi_path() {
  candidate=$(command -v pi 2>/dev/null) || candidate=""
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then
    resolved=$(absolute_path "$candidate" || printf '%s' "$candidate")
    # Never exec ourselves: `pi` on PATH can be this very wrapper.
    if [ "$resolved" != "$SELF_PATH" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi
  prefix=$(npm prefix -g 2>/dev/null) || prefix=""
  if [ -n "$prefix" ] && [ -x "$prefix/bin/pi" ]; then
    resolved=$(absolute_path "$prefix/bin/pi" || printf '%s' "$prefix/bin/pi")
    if [ "$resolved" != "$SELF_PATH" ]; then
      printf '%s\n' "$prefix/bin/pi"
      return 0
    fi
  fi
  return 1
}

if INSTALLED_PI=$(installed_pi_path); then
  exec "$INSTALLED_PI" "$@"
fi

ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
CACHE_DIR=${MMS_PI_NPX_CACHE:-"$ROOT_DIR/.ai/cache/pi-npx"}
LOCK_DIR="$CACHE_DIR/.mms-pi-npx-install.lock"
LOCK_TIMEOUT=${MMS_PI_NPX_INSTALL_LOCK_TIMEOUT:-300}
LOCK_HELD=0

mkdir -p "$CACHE_DIR"
export NPM_CONFIG_CACHE="$CACHE_DIR"
export npm_config_cache="$CACHE_DIR"

cached_pi_path() {
  for cached_pi in "$CACHE_DIR"/_npx/*/node_modules/.bin/pi "$CACHE_DIR"/_npx/*/node_modules/@earendil-works/pi-coding-agent/dist/cli.js; do
    case "$cached_pi" in
      */node_modules/.bin/pi) cached_manifest="${cached_pi%/.bin/pi}/@earendil-works/pi-coding-agent/package.json" ;;
      */@earendil-works/pi-coding-agent/dist/cli.js) cached_manifest="${cached_pi%/dist/cli.js}/package.json" ;;
      *) continue ;;
    esac
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
  if ! CACHED_PI=$(cached_pi_path); then
    # npx exits 0 without filling the cache when the package is already
    # installed globally, so look once more for that copy before giving up.
    if INSTALLED_PI=$(installed_pi_path); then
      release_lock
      trap - EXIT INT TERM HUP
      exec "$INSTALLED_PI" "$@"
    fi
    echo "MMS Pi cache warmup did not produce an executable, and no installed pi was found on PATH or under npm's global prefix" >&2
    exit 1
  fi
fi
release_lock
trap - EXIT INT TERM HUP
exec "$CACHED_PI" "$@"
