#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARK_SVG="$ROOT_DIR/src/assets/brand/logo-mark.svg"
APP_ICON_SVG="$ROOT_DIR/src/assets/brand/app-icon.svg"
TAURI_ICON_DIR="$ROOT_DIR/src-tauri/icons"
IOS_APPICON="$ROOT_DIR/ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png"
RELEASE_DIR="$ROOT_DIR/public/release-icons"
TMP_JPG="$(mktemp /tmp/sparkring-icon.XXXXXX.jpg)"
TMP_PNG="$(mktemp /tmp/sparkring-icon.XXXXXX.png)"
trap 'rm -f "$TMP_JPG" "$TMP_PNG"' EXIT

echo "[1/5] 生成 Tauri 图标（ico/icns/png）..."
npx tauri icon "$APP_ICON_SVG" --output "$TAURI_ICON_DIR" >/dev/null

echo "[2/5] 生成 iOS 1024 图标..."
sips -s format jpeg -s formatOptions best "$APP_ICON_SVG" --out "$TMP_JPG" >/dev/null
sips -s format png "$TMP_JPG" --out "$TMP_PNG" >/dev/null
cp "$TMP_PNG" "$IOS_APPICON"

echo "[3/5] 生成 Web favicon 源..."
cp "$MARK_SVG" "$ROOT_DIR/public/favicon.svg"

echo "[4/5] 导出上架常用尺寸..."
mkdir -p "$RELEASE_DIR/ios" "$RELEASE_DIR/web" "$RELEASE_DIR/mac"
cp "$TMP_PNG" "$RELEASE_DIR/app-icon-1024.png"
sips -s format png "$MARK_SVG" --out "$RELEASE_DIR/logo-mark-128.png" >/dev/null

for size in 20 29 40 58 60 76 80 87 120 152 167 180 1024; do
  sips -z "$size" "$size" "$RELEASE_DIR/app-icon-1024.png" --out "$RELEASE_DIR/ios/icon-${size}.png" >/dev/null
done

for size in 16 32 48 64 128 180 192 256 512; do
  sips -z "$size" "$size" "$RELEASE_DIR/app-icon-1024.png" --out "$RELEASE_DIR/web/icon-${size}.png" >/dev/null
done

for size in 16 32 64 128 256 512 1024; do
  sips -z "$size" "$size" "$RELEASE_DIR/app-icon-1024.png" --out "$RELEASE_DIR/mac/icon-${size}.png" >/dev/null
done

echo "[5/5] 完成。关键产物："
echo "- $TAURI_ICON_DIR/icon.ico"
echo "- $TAURI_ICON_DIR/icon.icns"
echo "- $IOS_APPICON"
echo "- $RELEASE_DIR"
