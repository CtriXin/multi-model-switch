# SparkRing iOS/macOS 构建、上传与面对面分发手册

最后更新：2026-03-18  
适用项目路径：`/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2`

## 1. 你要用的三条发布链路

1. `iOS`：`Capacitor + Xcode Archive + App Store Connect 上传`
2. `macOS App Store/TestFlight`：`Tauri + App Store pkg + Transporter 上传`
3. `macOS 面对面直传（不走 TestFlight）`：`Developer ID 签名 + Notarization + 发送 pkg`

## 2. iOS：每次迭代怎么 build + 上传

### 2.1 每次发布前检查

1. Bundle ID 一致：`com.xin.lab`
2. 版本号规则：
   - `Version (MARKETING_VERSION)`：可不每次改
   - `Build (CURRENT_PROJECT_VERSION)`：每次上传必须递增（例如 1 -> 2 -> 3）
3. `Signing & Capabilities`：
   - Team 选你的团队
   - `Automatically manage signing` 打开

### 2.2 命令（先同步前端到 iOS）

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2
npm run cap:build
npm run cap:open
```

### 2.3 Xcode 上传路径（逐步点击）

1. 打开 `ios/App/App.xcworkspace`
2. Target `App` -> `General` -> `Identity`
   - 确认 `Version/Build`
3. 顶部设备选择：`Any iOS Device (arm64)`
4. 菜单：`Product -> Archive`
5. Organizer 打开后选最新 Archive，点 `Distribute App`
6. 选择：`App Store Connect`
7. 选择：`Upload`
8. 后续默认下一步，直到 `Upload`

### 2.4 上传后去哪里看

1. App Store Connect -> `SparkRing` -> `TestFlight`
2. 等待 `Processing`
3. `Internal Testing` 可立即分发
4. `External Testing` 需要 Beta App Review

### 2.5 iOS 常见报错

1. `The bundle version must be higher...`
   - 处理：Xcode 把 `Build` +1，重新 Archive 上传
2. 签名失败
   - 处理：检查 Team、Bundle ID、自动签名是否开启
3. 加密合规弹窗
   - 你项目包含 Web Crypto（AES-GCM/PBKDF2）逻辑，按问卷选择“标准加密”路径
   - 已在 iOS `Info.plist` 添加 `ITSAppUsesNonExemptEncryption = NO`

## 3. macOS（App Store/TestFlight）：每次迭代怎么 build + 上传

### 3.1 每次发布前检查

1. 版本号一致：
   - `apps/web-v2/package.json`
   - `apps/web-v2/src-tauri/Cargo.toml`
   - `apps/web-v2/src-tauri/tauri.conf.json`
2. `cfBundleVersion` 必须递增（否则 Transporter 409）
3. 当前配置是 `arm64-only + minimumSystemVersion 12.0`

### 3.2 一键脚本（推荐）

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2
npm run release:mac:appstore
```

可选：指定版本号（影响输出文件名）

```bash
bash scripts/release-mac-appstore.sh 0.3.6
```

默认输出：`SparkRing-mac-appstore-<version>-<timestamp>.pkg`  
可通过环境变量覆盖证书名：

```bash
APPSTORE_INSTALLER_IDENTITY="3rd Party Mac Developer Installer: xxx (TEAMID)" \
bash scripts/release-mac-appstore.sh
```

### 3.3 手动命令（兜底）

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2
npm run tauri build -- --bundles app --config src-tauri/tauri.appstore.conf.json
```

产物：
- `src-tauri/target/release/bundle/macos/SparkRing.app`

### 3.4 打 App Store 上传用 pkg

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2
xcrun productbuild \
  --sign "3rd Party Mac Developer Installer: xin song (2HJP9YYL3H)" \
  --component "src-tauri/target/release/bundle/macos/SparkRing.app" \
  /Applications \
  "SparkRing-mac-appstore-<version>.pkg"
```

### 3.5 上传路径（Transporter）

1. 打开 `Transporter`
2. 拖入 `SparkRing-mac-appstore-<version>.pkg`
3. 点 `Deliver`
4. App Store Connect -> `SparkRing` -> `TestFlight` 查看 `Processing`

### 3.6 mac App Store 常见报错

1. `supports arm64 but not Intel... deployment target must be 12.0 or higher`
   - 处理：保持 `minimumSystemVersion >= 12.0`
2. `application identifier missing`
   - 处理：检查 `Entitlements.plist` 与 profile 里的 `com.apple.application-identifier` 一致
3. `duplicate bundle version`
   - 处理：把版本号升高后再构建上传

## 4. macOS 面对面直传（不走 TestFlight，且尽量不报“损坏”）

关键结论：  
`Apple Distribution / 3rd Party Installer` 是给 App Store 上传用的，不适合官网直装。  
面对面直传要用 `Developer ID Application + Developer ID Installer + Notarization`。

### 4.1 一次性准备

1. 在 Apple Developer 创建并安装证书：
   - `Developer ID Application`
   - `Developer ID Installer`
2. 准备 notarization 认证（推荐 keychain profile）：

```bash
xcrun notarytool store-credentials "AC_NOTARY" \
  --apple-id "<你的AppleID邮箱>" \
  --team-id "<TEAM_ID>" \
  --password "<app-specific-password>"
```

### 4.2 一键脚本（推荐）

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2
npm run release:mac:direct
```

可选：指定版本号

```bash
bash scripts/release-mac-direct.sh 0.3.6
```

默认输出：`SparkRing-direct-<version>-<timestamp>.pkg`  
可通过环境变量覆盖：

```bash
DEV_ID_APP_IDENTITY="Developer ID Application: xxx (TEAMID)" \
DEV_ID_INSTALLER_IDENTITY="Developer ID Installer: xxx (TEAMID)" \
NOTARY_PROFILE="AC_NOTARY" \
bash scripts/release-mac-direct.sh
```

### 4.3 手动命令（兜底）

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2

# 先构建 app（可用 tauri 默认配置，或你自己的 direct 配置）
npm run tauri build -- --bundles app

APP_PATH="src-tauri/target/release/bundle/macos/SparkRing.app"

# 用 Developer ID Application 重签
codesign --force --deep --options runtime --timestamp \
  --sign "Developer ID Application: <Your Name> (<TEAM_ID>)" \
  "$APP_PATH"
```

### 4.4 打直传 pkg + 公证 + 装订

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2

APP_PATH="src-tauri/target/release/bundle/macos/SparkRing.app"
PKG="SparkRing-direct-<version>.pkg"

xcrun productbuild \
  --sign "Developer ID Installer: <Your Name> (<TEAM_ID>)" \
  --component "$APP_PATH" /Applications "$PKG"

# 提交公证并等待结果
xcrun notarytool submit "$PKG" --keychain-profile "AC_NOTARY" --wait

# 装订票据（离线安装更稳）
xcrun stapler staple "$PKG"
```

### 4.5 本地验签（发给别人前必须跑）

```bash
pkgutil --check-signature "SparkRing-direct-<version>.pkg"
spctl -a -vv --type install "SparkRing-direct-<version>.pkg"
```

### 4.6 面对面传输建议

1. 优先传 `notarized + stapled` 的 `pkg`，不要直接传裸 `.app`
2. 传输方式：AirDrop/U 盘/网盘都可以
3. 建议附带校验值：

```bash
shasum -a 256 "SparkRing-direct-<version>.pkg"
```

4. 收件方安装仍异常时：
   - 先核对 SHA256
   - 再看系统是否拦截为未知开发者
   - 只有内部临时测试才考虑手动移除隔离属性（不建议对外）

## 5. 一页速查（你后续只看这段）

1. iOS：
   - `npm run cap:build` -> Xcode `Archive` -> `Distribute App -> Upload`
   - 每次只要改 `Build`（+1）
2. mac App Store：
   - `npm run tauri build -- --bundles app --config src-tauri/tauri.appstore.conf.json`
   - `productbuild` 打 `SparkRing-mac-appstore-<version>.pkg`
   - Transporter 上传
3. mac 面对面直传不报损坏：
   - 必须 `Developer ID + Notarization + Staple`
   - 发 `pkg`，发前跑 `spctl/pkgutil` 验签
