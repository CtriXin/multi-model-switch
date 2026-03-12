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
    "CCS Installer.command"
    "MMS Installer.command"
    "mms"
    "README.md"
    "ccs"
    "ccs_core.py"
    "ccs_installer.py"
    "ccs_launchers.py"
    "ccs_tui.py"
    "config.example.toml"
    "install.sh"
)

for file in "${FILES[@]}"; do
    cp "$SCRIPT_DIR/$file" "$PKG_DIR/$file"
done

rm -f "$ZIP_PATH"
(
    cd "$TMP_DIR"
    zip -rq "$ZIP_PATH" "$PKG_NAME"
)

rm -rf "$TMP_DIR"

echo "已生成：$ZIP_PATH"
