# SparkRing 发布运行手册（iOS + macOS + 面对面直传）

最后更新：2026-03-18  
适用目录：`/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2`

## 0. 场景导航（先看这个）

1. 你要发 iPhone/iPad 测试包：走「第 2 章 iOS」。
2. 你要发 mac 的 TestFlight/App Store 包：走「第 3 章 macOS App Store」。
3. 你要把 mac 安装包面对面发给别人（不走 TestFlight）：走「第 4 章 macOS 直传」。

## 1. 通用规则（所有平台都适用）

### 1.1 版本号规则

1. 任何上传到 Apple 的新构建，`Build` 必须比上次大。
2. 建议统一版本策略：
   - `marketing version`（如 `0.3.5`）按功能阶段升级。
   - `build number`（如 `2 -> 3`）每次上传必加。
3. 遇到 `duplicate bundle version` 报错，优先检查 build 号。

### 1.2 Bundle ID 规则

1. 当前项目统一使用：`com.xin.lab`。
2. App Store Connect、Xcode、配置文件必须一致。
3. 一旦正式绑定上架记录，不要随意改 Bundle ID。

### 1.3 这套项目的已知配置

1. iOS 已设置：`ITSAppUsesNonExemptEncryption = NO`。
2. `apps/web-v2/capacitor.config.ts` 里的 `ios.contentInset` 必须保持 `never`，不要改成 `always`。
   - 改成 `always` 会让 iPhone 全面屏设备出现额外的底部 inset，表现为黑条或底部留白异常。
   - 如果以后有人误改，恢复成 `never` 后执行 `npm run cap:build`。
3. mac App Store 路线已设置：`minimumSystemVersion = 12.0`（arm64-only）。
4. mac 面对面直传路线使用 `Developer ID + Notarization + Staple`。

## 2. iOS 发布（Capacitor + Xcode）

### 2.1 一次迭代的标准流程

1. 前端改动后，先同步到 iOS 工程：

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2
npm run cap:build
```

2. 打开 Xcode：

```bash
npm run cap:open
```

3. 在 Xcode 检查：
   - `Targets -> App -> Signing & Capabilities`
   - `Team` 选你的团队
   - `Bundle Identifier = com.xin.lab`
   - `Automatically manage signing` 已开启
4. 在 `General -> Identity` 检查：
   - `Version`（可按需更新）
   - `Build`（每次上传必 +1）
5. 归档上传：
   - 顶部设备选 `Any iOS Device (arm64)`
   - `Product -> Archive`
   - Organizer -> `Distribute App`
   - 选 `App Store Connect` -> `Upload` -> 一路 Next

### 2.2 上传后去哪里看

1. App Store Connect -> `SparkRing` -> `TestFlight`。
2. 状态 `Processing` 后，等待可测试。
3. Internal 可立即分发，External 需 Beta 审核。

### 2.3 iOS 常见问题

1. `The bundle version must be higher than...`
   - 处理：Xcode 把 `Build` +1 后重传。
2. 签名失败或证书不匹配
   - 处理：检查 Team、Bundle ID、一键自动签名是否开启。
3. 加密合规弹窗
   - 项目有 Web Crypto 逻辑（AES-GCM/PBKDF2），按标准加密路径填写。

## 3. macOS App Store / TestFlight 发布（Tauri）

### 3.1 一键脚本（推荐）

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2
npm run release:mac:appstore
```

可指定版本号（仅影响输出文件名）：

```bash
bash scripts/release-mac-appstore.sh 0.3.6
```

脚本产物：`SparkRing-mac-appstore-<version>-<timestamp>.pkg`

### 3.2 脚本做了什么

1. 校验 `3rd Party Mac Developer Installer` identity。
2. 用 `src-tauri/tauri.appstore.conf.json` 构建 `.app`。
3. 用 `productbuild` 生成 App Store 上传用 `pkg`。
4. 输出基础签名信息，供上传前确认。

### 3.3 上传到 Apple

1. 打开 `Transporter`。
2. 拖入脚本生成的 `pkg`。
3. 点击 `Deliver`。
4. App Store Connect -> `SparkRing` -> `TestFlight` 看处理状态。

### 3.4 环境变量覆盖（可选）

```bash
APPSTORE_INSTALLER_IDENTITY="3rd Party Mac Developer Installer: xxx (TEAMID)" \
bash scripts/release-mac-appstore.sh
```

### 3.5 mac App Store 常见问题

1. `supports arm64 but not Intel...`
   - 处理：保持 `minimumSystemVersion >= 12.0`。
2. `application identifier missing`
   - 处理：检查 entitlements 与 profile 对齐。
3. `duplicate bundle version`
   - 处理：升级版本后重构建重传。

## 4. macOS 面对面直传（不报损坏的标准链路）

## 4.1 结论先说

1. 不能用 App Store 证书直传。
2. 必须使用：
   - `Developer ID Application`
   - `Developer ID Installer`
   - `Notarization`
   - `Staple`

### 4.2 一次性准备

1. 证书安装到钥匙串并可用：

```bash
security find-identity -v -p basic | rg "Developer ID Application|Developer ID Installer"
```

2. 配置 notarytool profile（只需一次）：

```bash
xcrun notarytool store-credentials "AC_NOTARY" \
  --apple-id "<AppleID邮箱>" \
  --team-id "2HJP9YYL3H" \
  --password "<app-specific-password>"
```

### 4.3 一键脚本（推荐）

```bash
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2
npm run release:mac:direct
```

可指定版本号：

```bash
bash scripts/release-mac-direct.sh 0.3.6
```

脚本会自动做：

1. Tauri build。
2. `Developer ID Application` 重签 `.app`。
3. `Developer ID Installer` 打 `.pkg`。
4. 提交 Apple notary 并等待 `Accepted`。
5. `stapler staple`。
6. `spctl/pkgutil/shasum` 验证。

### 4.4 脚本可配置参数（可选）

```bash
DEV_ID_APP_IDENTITY="Developer ID Application: xxx (TEAMID)" \
DEV_ID_INSTALLER_IDENTITY="Developer ID Installer: xxx (TEAMID)" \
NOTARY_PROFILE="AC_NOTARY" \
bash scripts/release-mac-direct.sh
```

### 4.5 给测试者的发送建议

1. 只发已 notarized + stapled 的 `pkg`。
2. 同时发送 SHA256 校验值。
3. 推荐传输方式：AirDrop / 网盘 / U 盘均可。
4. 若仍提示异常，先校验 SHA，再确认对方系统时间正常。

## 5. TestFlight 分发策略（减少手工）

### 5.1 Internal（内部测试）

1. 只在第一次需要把成员加进测试组。
2. 之后新 build 加入同一组，成员会自动收到更新通知。
3. 不需要每次重输邮箱。

### 5.2 External（外部测试）

1. 新 build 通常需要 Beta App Review。
2. 外部审核期间不要频繁替换正在审核的 build。
3. 审核通过后，优先使用 `Public Link`，避免逐个邮箱邀请。

### 5.3 你当前建议策略

1. 正在审核的外部 build 不动，先等结果。
2. 新改动先走 Internal 验证。
3. 稳定后再提下一次 External，减少排队次数。

## 6. 统一排错速查

1. 上传失败 + 版本重复
   - 改大 `Build`。
2. 签名相关
   - 检查证书 identity、Bundle ID、Team 是否一致。
3. mac 提示损坏
   - 检查是否已走 `Developer ID + Notary + Staple`。
4. Transporter 409 架构问题
   - arm64-only 时确保 `minimumSystemVersion >= 12.0`。
5. TestFlight 外部不让下载
   - 检查 build 是否 `Ready to Test`，组是否启用 `Public Link`。

## 7. 一页命令速查

```bash
# iOS（前端同步）
cd /Users/xin/auto-skills/CtriXin-repo/multi-model-switch/apps/web-v2
npm run cap:build
npm run cap:open

# mac App Store/TestFlight 包
npm run release:mac:appstore

# mac 面对面直传包（签名+公证+staple）
npm run release:mac:direct
```
