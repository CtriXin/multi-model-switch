#!/usr/bin/env bash
set -euo pipefail

# --- SPARKRING CINEMATIC V3 BRAND ASSETS GENERATOR ---
# 唯一事实来源 (SSOT): public/logo-v5-app.png
# 使用说明: 修改 logo 后运行 sh scripts/generate-brand-assets.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# 定义唯一源文件
SOURCE_PNG="$ROOT_DIR/public/logo-v5-app.png"
# 定义双端镜像文件 (供 UI 使用)
LIGHT_SOURCE="$ROOT_DIR/public/logos/logo-v5-light.png"
DARK_SOURCE="$ROOT_DIR/public/logos/logo-v5-dark.png"

TAURI_ICON_DIR="$ROOT_DIR/src-tauri/icons"
IOS_APPICON_SET="$ROOT_DIR/ios/App/App/Assets.xcassets/AppIcon.appiconset"
RELEASE_DIR="$ROOT_DIR/public/release-icons"

echo "🚀 开始分发品牌资产..."

if [ ! -f "$SOURCE_PNG" ]; then
    echo "❌ 错误: 未找到源文件 $SOURCE_PNG"
    exit 1
fi

echo "[1/4] 更新 Web 核心资产 (Favicon/UI)..."
cp "$SOURCE_PNG" "$ROOT_DIR/public/favicon.png"
# 确保 UI 内部使用的 Dark 版本也同步
cp "$SOURCE_PNG" "$DARK_SOURCE"

echo "[2/4] 生成 Tauri 图标 (macOS/Windows/PNG Rails)..."
# 使用 tauri icon 命令处理 PNG 源
npx tauri icon "$SOURCE_PNG" --output "$TAURI_ICON_DIR" >/dev/null

echo "[3/4] 准备 iOS 图标导出 (1024x1024)..."
mkdir -p "$RELEASE_DIR/ios" "$RELEASE_DIR/web" "$RELEASE_DIR/mac"
cp "$SOURCE_PNG" "$RELEASE_DIR/app-icon-1024.png"

# 同步到 Xcode Asset Catalog (iOS 打包实际读取的位置)
# Apple 要求 app icon 不能有 alpha 通道，用 sips 去除
if [ -d "$IOS_APPICON_SET" ]; then
  cp "$TAURI_ICON_DIR/ios/AppIcon-512@2x.png" "$IOS_APPICON_SET/AppIcon-512@2x.png"
  sips -s format png --setProperty formatOptions 0 "$IOS_APPICON_SET/AppIcon-512@2x.png" >/dev/null 2>&1 || true
  # 用 python 移除 alpha 通道（sips 不能直接去 alpha，用 CoreImage 兜底）
  python3 -c "
from PIL import Image
img = Image.open('$IOS_APPICON_SET/AppIcon-512@2x.png').convert('RGBA')
bg = Image.new('RGBA', img.size, (255, 255, 255, 255))
bg.paste(img, mask=img.split()[3])
bg.convert('RGB').save('$IOS_APPICON_SET/AppIcon-512@2x.png')
" 2>/dev/null || {
    # Fallback: 用 sips 转 JPEG 再转回 PNG（粗暴但有效）
    sips -s format jpeg "$IOS_APPICON_SET/AppIcon-512@2x.png" --out "$IOS_APPICON_SET/_tmp.jpg" >/dev/null 2>&1
    sips -s format png "$IOS_APPICON_SET/_tmp.jpg" --out "$IOS_APPICON_SET/AppIcon-512@2x.png" >/dev/null 2>&1
    rm -f "$IOS_APPICON_SET/_tmp.jpg"
  }
  echo "   ✅ 已同步到 iOS Asset Catalog (alpha 已移除)"
fi

echo "[4/4] 裁切全套 AppIcon 尺寸 (SIPS)..."
# 生成 iOS 全套
for size in 20 29 40 58 60 76 80 87 120 152 167 180 1024; do
  sips -z "$size" "$size" "$SOURCE_PNG" --out "$RELEASE_DIR/ios/icon-${size}.png" >/dev/null
done

# 生成 Web 全套
for size in 16 32 48 64 128 180 192 256 512; do
  sips -z "$size" "$size" "$SOURCE_PNG" --out "$RELEASE_DIR/web/icon-${size}.png" >/dev/null
done

echo "✅ 完成！"
echo "--- 关键更新点 ---"
echo "- Web Favicon: public/favicon.png"
echo "- Tauri (macOS/Win): src-tauri/icons/icon.icns / .ico"
echo "- UI Dark Version: public/logos/logo-v5-dark.png"
echo "- 上架产物: public/release-icons/"
echo "💡 提示: 如果你改了白色版，请手动同步到 $LIGHT_SOURCE"
