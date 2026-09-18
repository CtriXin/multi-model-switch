#!/bin/bash
set -euo pipefail

# Package the committed source tree, including lib/ and all installer assets.
# Untracked files, local config, and work-in-progress edits are not included.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
PKG_NAME="MMS-Package"
ZIP_PATH="$DIST_DIR/${PKG_NAME}.zip"
mkdir -p "$DIST_DIR"
TMP_ZIP="$(mktemp "$DIST_DIR/.mms-package.XXXXXX")"
trap 'rm -f "$TMP_ZIP"' EXIT

git -C "$REPO_ROOT" archive --format=zip --prefix="${PKG_NAME}/" --output="$TMP_ZIP" HEAD
mv "$TMP_ZIP" "$ZIP_PATH"
echo "已生成已提交源码包：$ZIP_PATH"
