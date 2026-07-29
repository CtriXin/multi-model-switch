#!/bin/sh
set -eu

export NPM_CONFIG_UPDATE_NOTIFIER=false
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
CACHE_DIR=${MMS_PI_NPX_CACHE:-"$ROOT_DIR/.ai/cache/pi-npx"}

mkdir -p "$CACHE_DIR"
export NPM_CONFIG_CACHE="$CACHE_DIR"
export npm_config_cache="$CACHE_DIR"

for CACHED_PI in "$CACHE_DIR"/_npx/*/node_modules/.bin/pi; do
  CACHED_MANIFEST="${CACHED_PI%/.bin/pi}/@earendil-works/pi-coding-agent/package.json"
  if [ -x "$CACHED_PI" ] && [ -f "$CACHED_MANIFEST" ]; then
    exec "$CACHED_PI" "$@"
  fi
done

exec npx -y --cache "$CACHE_DIR" @earendil-works/pi-coding-agent "$@"
