#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="${1:-$(node -p "require('./package.json').version")}"
PRODUCT_NAME="${PRODUCT_NAME:-$(node -e "const c=require('./src-tauri/tauri.conf.json');process.stdout.write(c.productName||'App')")}"
DEV_ID_APP_IDENTITY="${DEV_ID_APP_IDENTITY:-Developer ID Application: xin song (2HJP9YYL3H)}"
DEV_ID_INSTALLER_IDENTITY="${DEV_ID_INSTALLER_IDENTITY:-Developer ID Installer: xin song (2HJP9YYL3H)}"
NOTARY_PROFILE="${NOTARY_PROFILE:-AC_NOTARY}"
TARGET_DIR="$ROOT_DIR/src-tauri/target/direct"
TIMESTAMP="$(date +%Y%m%d-%H%M)"
PKG_NAME="${PKG_NAME:-${PRODUCT_NAME}-direct-${VERSION}-${TIMESTAMP}.pkg}"
PKG_PATH="$ROOT_DIR/$PKG_NAME"

echo "[1/7] 检查证书 identity..."
if ! security find-identity -v -p basic | grep -F "$DEV_ID_APP_IDENTITY" >/dev/null; then
  echo "未找到证书: $DEV_ID_APP_IDENTITY"
  exit 1
fi
if ! security find-identity -v -p basic | grep -F "$DEV_ID_INSTALLER_IDENTITY" >/dev/null; then
  echo "未找到证书: $DEV_ID_INSTALLER_IDENTITY"
  exit 1
fi

echo "[2/7] 检查 notary 凭据 profile..."
if ! xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" >/dev/null 2>&1; then
  echo "未找到可用 notary profile: $NOTARY_PROFILE"
  echo "请先执行:"
  echo "xcrun notarytool store-credentials \"$NOTARY_PROFILE\" --apple-id \"<邮箱>\" --team-id \"2HJP9YYL3H\" --password \"<app-specific-password>\""
  exit 1
fi

echo "[3/7] 构建 macOS App..."
CARGO_TARGET_DIR="$TARGET_DIR" npm run tauri build -- --bundles app

APP_PATH="$TARGET_DIR/release/bundle/macos/${PRODUCT_NAME}.app"
if [[ ! -d "$APP_PATH" ]]; then
  APP_PATH="$(find "$TARGET_DIR/release/bundle/macos" -maxdepth 1 -type d -name '*.app' | head -n 1 || true)"
fi
if [[ -z "${APP_PATH:-}" || ! -d "$APP_PATH" ]]; then
  echo "未找到 .app 产物，请检查构建日志。"
  exit 1
fi

echo "[4/7] 用 Developer ID Application 重签 App..."
codesign --force --deep --options runtime --timestamp \
  --sign "$DEV_ID_APP_IDENTITY" \
  "$APP_PATH"

echo "[5/7] 生成 Developer ID Installer pkg..."
xcrun productbuild \
  --sign "$DEV_ID_INSTALLER_IDENTITY" \
  --component "$APP_PATH" \
  /Applications \
  "$PKG_PATH"

echo "[6/7] 提交 Apple Notary 并等待通过..."
xcrun notarytool submit "$PKG_PATH" --keychain-profile "$NOTARY_PROFILE" --wait

echo "[7/7] 装订票据并验证..."
xcrun stapler staple "$PKG_PATH"
spctl -a -vv --type install "$PKG_PATH"
pkgutil --check-signature "$PKG_PATH" | sed -n '1,40p'
shasum -a 256 "$PKG_PATH"

echo
echo "完成: $PKG_PATH"
echo "该包已签名+公证+staple，可用于面对面分发。"

