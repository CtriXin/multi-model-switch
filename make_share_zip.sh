#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
PKG_NAME="MMS-Package"
TMP_DIR="$(mktemp -d)"
PKG_DIR="$TMP_DIR/$PKG_NAME"
ZIP_PATH="$DIST_DIR/${PKG_NAME}.zip"

mkdir -p "$PKG_DIR" "$DIST_DIR"

FILES=(
    "MMS Installer.command"
    "mms"
    "README.md"
    "mms_core.py"
    "mms_installer.py"
    "mms_launchers.py"
    "mms_tui.py"
    "config.example.toml"
    "install.sh"
)

DIRS=(
    "hooks"
    "mms_opencode"
    "mms_codex"
    "mms_claude"
    "mms_agy"
)

for file in "${FILES[@]}"; do
    cp "$SCRIPT_DIR/$file" "$PKG_DIR/$file"
done

for dir in "${DIRS[@]}"; do
    cp -R "$SCRIPT_DIR/$dir" "$PKG_DIR/$dir"
done

rm -f "$ZIP_PATH"
(
    cd "$TMP_DIR"
    zip -rq "$ZIP_PATH" "$PKG_NAME"
)

rm -rf "$TMP_DIR"

echo "已生成：$ZIP_PATH"
