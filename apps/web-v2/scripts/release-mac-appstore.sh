#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="${1:-$(node -p "require('./package.json').version")}"
PRODUCT_NAME="${PRODUCT_NAME:-$(node -e "const c=require('./src-tauri/tauri.conf.json');process.stdout.write(c.productName||'App')")}"
APPSTORE_CONFIG="${APPSTORE_CONFIG:-src-tauri/tauri.appstore.conf.json}"
APPSTORE_INSTALLER_IDENTITY="${APPSTORE_INSTALLER_IDENTITY:-3rd Party Mac Developer Installer: xin song (2HJP9YYL3H)}"
TARGET_DIR="$ROOT_DIR/src-tauri/target/appstore"
TIMESTAMP="$(date +%Y%m%d-%H%M)"
PKG_NAME="${PKG_NAME:-${PRODUCT_NAME}-mac-appstore-${VERSION}-${TIMESTAMP}.pkg}"
PKG_PATH="$ROOT_DIR/$PKG_NAME"

echo "[1/4] 检查证书 identity..."
if ! security find-identity -v -p basic | grep -F "$APPSTORE_INSTALLER_IDENTITY" >/dev/null; then
  echo "未找到证书: $APPSTORE_INSTALLER_IDENTITY"
  echo "请先在钥匙串安装 3rd Party Mac Developer Installer 证书。"
  exit 1
fi

echo "[2/4] 构建 macOS App (App Store 配置)..."
CARGO_TARGET_DIR="$TARGET_DIR" npm run tauri build -- --bundles app --config "$APPSTORE_CONFIG"

APP_PATH="$TARGET_DIR/release/bundle/macos/${PRODUCT_NAME}.app"
if [[ ! -d "$APP_PATH" ]]; then
  APP_PATH="$(find "$TARGET_DIR/release/bundle/macos" -maxdepth 1 -type d -name '*.app' | head -n 1 || true)"
fi
if [[ -z "${APP_PATH:-}" || ! -d "$APP_PATH" ]]; then
  echo "未找到 .app 产物，请检查构建日志。"
  exit 1
fi

echo "[3/4] 打 App Store 上传 pkg..."
xcrun productbuild \
  --sign "$APPSTORE_INSTALLER_IDENTITY" \
  --component "$APP_PATH" \
  /Applications \
  "$PKG_PATH"

echo "[4/4] 本地校验关键信息..."
if [[ -f "$APP_PATH/Contents/Info.plist" ]]; then
  MIN_OS="$(/usr/libexec/PlistBuddy -c 'Print :LSMinimumSystemVersion' "$APP_PATH/Contents/Info.plist" 2>/dev/null || true)"
  if [[ -n "$MIN_OS" ]]; then
    echo "LSMinimumSystemVersion: $MIN_OS"
  fi
fi
pkgutil --check-signature "$PKG_PATH" | sed -n '1,20p'
echo
echo "完成: $PKG_PATH"
echo "下一步: 打开 Transporter 上传该 pkg。"

