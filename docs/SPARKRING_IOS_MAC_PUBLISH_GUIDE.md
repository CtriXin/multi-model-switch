# SparkRing macOS / iOS 上架指南

> 版本：0.3.4 | 最后更新：2026-03-17

---

## 目录

1. [准备工作](#1-准备工作)
2. [macOS 上架（App Store）](#2-macos-上架app-store)
3. [macOS 上架（DMG/公证）](#3-macos-上架dmg公证)
4. [iOS 上架](#4-ios-上架)
5. [常见问题](#5-常见问题)

---

## 1. 准备工作

### 1.1 Apple 账号

| 类型 | 费用 | 分发方式 |
|------|------|----------|
| Apple Developer（个人/公司） | $99/年 | App Store + TestFlight |
| 免费 Apple ID | 免费 | 仅限 Xcode 真机调试 |

**推荐**：先注册免费 Apple ID 调试，最后再买付费账号正式上架。

### 1.2 必需工具

```bash
# 检查已安装
xcode-select -p    # Xcode
which altool       # App Store 工具
```

### 1.3 项目当前状态

- **Bundle ID**: `com.mms.sparkring`
- **App 名称**: SparkRing
- **版本**: 0.3.4
- **Tauri**: 2.10.1
- **iOS 项目**: 已通过 Capacitor 初始化

---

## 2. macOS 上架（App Store）

### Step 1：创建 App Store 记录

1. 登录 [App Store Connect](https://appstoreconnect.apple.com)
2. 我的 App → + → 新建 App
3. 填写：

| 字段 | 值 |
|------|-----|
| 平台 | macOS |
| 名称 | SparkRing |
| 主语言 | 简体中文 |
| Bundle ID | com.mms.sparkring |
| SKU | sparkring-mac |

### Step 2：生成 App 图标

尺寸要求：1024x1024 PNG

```bash
# 已有 icons 目录，检查是否完整
ls -la apps/web-v2/src-tauri/icons/
```

如需生成，使用 [App Icon Generator](https://appiconmaker.co/) 或：

```bash
# 安装 iconGen（可选）
npm install -g icon-gen
icon-gen -i icon.png -o icons/ --ico --ico-name icon --ico-sizes 16,32,64,128,256,512
```

### Step 3：准备截图

| 尺寸 | 用途 |
|------|------|
| 2880x1800 | macOS Retina 登录页 |
| 2880x1800 | macOS 主界面 |

**工具**：macOS 截图快捷键 `Cmd + Shift + 4`，或用 CleanShot X

### Step 4：配置 tauri.conf.json

```json
{
  "productName": "SparkRing",
  "version": "0.3.4",
  "identifier": "com.mms.sparkring",
  "build": {
    "frontendDist": "../dist",
    "devUrl": "http://localhost:5188",
    "beforeDevCommand": "npm run dev",
    "beforeBuildCommand": "npm run build"
  },
  "app": {
    "windows": [
      {
        "title": "SparkRing",
        "width": 1100,
        "height": 720,
        "minWidth": 800,
        "minHeight": 500
      }
    ]
  },
  "bundle": {
    "active": true,
    "targets": ["app", "dmg"],
    "category": "public.app-category.productivity",
    "shortDescription": "AI Model Switcher",
    "longDescription": "SparkRing - 多模型切换工具，支持 OpenRouter、Claude、GPT 等主流 AI 模型",
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ],
    "macOS": {
      "entitlements": null,
      "exceptionDomain": "",
      "frameworks": [],
      "providerShortName": null,
      "signingIdentity": "-"
    }
  }
}
```

### Step 5：构建 macOS App

```bash
cd apps/web-v2

# 确保依赖安装
npm install

# 构建（首次可能需要 5-10 分钟）
npm run tauri:build
```

产物位置：`apps/web-v2/src-tauri/target/release/bundle/mac/SparkRing.app`

### Step 6：创建证书

#### 方式 A：Xcode 自动（推荐）

1. 打开 Xcode → Settings → Accounts
2. 添加 Apple ID
3. 点击 "Manage Certificates" → + → "Apple Distribution"

#### 方式 B：手动创建

```bash
# 1. 创建证书签名请求
openssl req -new -nodes -out SigningRequest.certsigningrequest \
  -keyout private.key -newkey rsa:2048

# 2. 上传到 Apple Developer → Certificates
# 下载 .cer 文件

# 3. 转换为 .p12（需要密码）
openssl x509 -inform DER -in Certificates.cer -out Certificates.pem
openssl pkcs12 -export -in Certificates.pem -inkey private.key \
  -out Certificates.p12 -password pass:YOUR_PASSWORD
```

### Step 7：签名 + 上传

```bash
# 使用 Xcode 工具上传
xcodebuild -exportArchive \
  -archivePath SparkRing.xcarchive \
  -exportOptionsPlist ExportOptions.plist \
  -exportPath .

# 或使用 altool
altool --upload-app -f SparkRing.ipa -u YOUR_EMAIL -p APP_PASSWORD
```

**ExportOptions.plist 示例**：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>signingStyle</key>
    <string>automatic</string>
</dict>
</plist>
```

### Step 8：App Store Connect 提交

1. 登录 App Store Connect
2. 进入 SparkRing → 版本
3. 上传构建版本（等 10-30 分钟显示）
4. 填写：
   - 隐私政策 URL（必需）
   - App 预览截图
   - 版本说明
5. 点击"提交以供审核"

**审核时间**：通常 24-48 小时

---

## 3. macOS 上架（DMG/公证）

### 适用于：不想上 App Store，直接分发 .dmg

### Step 1：构建 DMG

```bash
cd apps/web-v2
npm run tauri:build
# 产物：src-tauri/target/release/bundle/dmg/SparkRing_0.3.4_aarch64.dmg
```

### Step 2：代码签名

```bash
# 签名
codesign --force --deep --sign "Developer ID Application: YOUR_NAME (TEAM_ID)" \
  SparkRing.app

# 验证
codesign --verify -vvvv SparkRing.app
```

### Step 3：公证（Notarization）

```bash
# 1. 创建 ZIP（公证不支持 .dmg）
zip -r SparkRing.zip SparkRing.app

# 2. 提交公证
xcrun notarytool submit SparkRing.zip \
  --apple-id YOUR_EMAIL \
  --password APP_PASSWORD \
  --team-id TEAM_ID

# 3. 等待完成（可查询状态）
xcrun notarytool wait SparkRing.zip --apple-id YOUR_EMAIL --password APP_PASSWORD --team-id TEAM_ID

# 4. 附加 Ticket
xcrun stapler staple SparkRing.app
```

### Step 4：创建 DMG

```bash
# 使用 create-dmg（推荐）
brew install create-dmg

create-dmg \
  --volname "SparkRing" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon SparkRing.app 150 185 \
  --app-drop-link 450 185 \
  SparkRing_0.3.4.dmg SparkRing.app/
```

---

## 4. iOS 上架

### Step 1：创建 App Store 记录

1. 登录 [App Store Connect](https://appstoreconnect.apple.com)
2. 我的 App → + → 新建 App
3. 填写：

| 字段 | 值 |
|------|-----|
| 平台 | iOS |
| 名称 | SparkRing |
| 主语言 | 简体中文 |
| Bundle ID | com.mms.sparkring |
| SKU | sparkring-ios |

### Step 2：准备 iOS 设备

```bash
# 检查连接的设备
xcrun simctl list devices available

# 或连接真机后
xcrun simctl list devices
```

### Step 3：生成 iOS 项目

```bash
cd apps/web-v2

# 首次生成 iOS 项目（已执行过）
npm run cap:sync

# 打开 Xcode（重要！）
npm run cap:open
```

### Step 4：Xcode 配置

打开后需要配置：

1. **Signing & Capabilities**
   - Team：选择你的 Apple ID
   - Bundle Identifier：`com.mms.sparkring`
   - 自动签名

2. **General**
   - Display Name：SparkRing
   - Version：0.3.4
   - Build：1

3. **Info.plist 添加**（若需要定位等权限）

### Step 5：构建 iOS

#### 方式 A：Xcode 图形界面

1. Product → Build（Cmd + B）
2. Product → Archive
3. Window → Organizer → 提交

#### 方式 B：命令行

```bash
# 开发构建（真机）
xcodebuild -workspace ios/App/App.xcworkspace \
  -scheme App \
  -configuration Debug \
  -destination 'platform=iOS Developer' \
  -allowProvisioningUpdates \
  build

# 发布构建（App Store）
xcodebuild -workspace ios/App/App.xcworkspace \
  -scheme App \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath SparkRing.xcarchive \
  archive

# 导出 IPA
xcodebuild -exportArchive \
  -archivePath SparkRing.xcarchive \
  -exportOptionsPlist ios/ExportOptions.plist \
  -exportPath ./dist
```

### Step 6：上传构建版本

```bash
# 使用 altool
xcrun altool --upload-app -f SparkRing.ipa \
  -u YOUR_EMAIL -p APP_PASSWORD

# 或使用 Transporter（推荐）
open /Applications/Transporter.app
```

### Step 7：提交审核

1. App Store Connect → 构建版本（等待 10-30 分钟）
2. 填写：
   - App 信息
   - 隐私政策 URL
   - iOS 截图（必需）
   - App 预览视频（可选）
3. 提交审核

---

## 5. 常见问题

### Q1: 证书找不到？

```bash
# 查看已安装证书
security find-identity -v -p codesigning
```

### Q2: 构建失败，签名错误？

```bash
# 清除缓存
rm -rf src-tauri/target

# 重新构建
npm run tauri:build -- --no-bundle
```

### Q3: App Store Connect 找不到构建版本？

- 等 15-30 分钟
- 检查邮件是否有错误
- 确认 Bundle ID 一致

### Q4: iOS 真机调试闪退？

```bash
# 检查设备 UUID
xcrun simctl list devices

# 重新注册设备
xcrun devicectl device pair
```

### Q5: Notarization 失败？

常见原因：
- 未签名就提交
- Hardened Runtime 未启用
-  entitlements 错误

```bash
# 检查错误详情
xcrun notarytool log SparkRing.zip
```

---

## 附录：快速检查清单

### 上架前必做

- [ ] Apple Developer 账号
- [ ] Bundle ID 已创建
- [ ] App 图标（1024x1024）
- [ ] 隐私政策 URL
- [ ] 截图（macOS: 2880x1800, iOS: 多种尺寸）
- [ ] 版本号已更新
- [ ] 测试通过

### macOS App Store

- [ ] 证书（Apple Distribution）
- [ ] 签名配置正确
- [ ] 构建成功

### macOS DMG/公证

- [ ] 证书（Developer ID Application）
- [ ] 已公证（stapled）
- [ ] DMG 打包完成

### iOS

- [ ] 证书（Apple Distribution）
- [ ] Provisioning Profile
- [ ] 真机测试通过
- [ ] 构建版本上传成功
