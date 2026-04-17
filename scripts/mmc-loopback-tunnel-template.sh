#!/usr/bin/env bash
set -euo pipefail

# Client-side template only.
# It exposes a server-side loopback listener as a local loopback route for MMC/MMS.
#
# Required env:
#   SSH_TARGET=ubuntu@example-host
# Optional env:
#   LOCAL_PORT=31001
#   REMOTE_PORT=41001

SSH_TARGET="${SSH_TARGET:?set SSH_TARGET, for example ubuntu@example-host}"
LOCAL_PORT="${LOCAL_PORT:-31001}"
REMOTE_PORT="${REMOTE_PORT:-41001}"

exec ssh \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -N \
  -L "127.0.0.1:${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
  "${SSH_TARGET}"
