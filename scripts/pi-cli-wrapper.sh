#!/bin/sh
set -eu

export NPM_CONFIG_UPDATE_NOTIFIER=false
exec npx -y @earendil-works/pi-coding-agent "$@"
