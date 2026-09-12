# v4.20.0 · Windows Native Preview

## 升级须知

本版本在 `dev` track 发布 Windows Native Preview。macOS/Linux 的既有安装和 Pilot 会话继续沿用原有升级路径；Windows 是显式 Preview，不等同于 Stable 支持。

Windows GitHub-hosted acceptance 已覆盖 Windows Server 2022/2025、PowerShell 5.1/7、Python 3.11–3.13、Node 18–22。Windows 10/11 桌面、真实 Edge/Chrome 登录态 CDP 和 Pi native model bootstrap 尚未完成真实机器验收。

## Windows 安装

当前公开 npm installer `@ctrixin/mms@1.0.0` 的 `os` 元数据仍只有 `darwin`、`linux`，所以 Windows 不使用 `npx @ctrixin/mms`。请从本 Release 下载源码中的 `packages/mms-install/bin/install.ps1`，或在 PowerShell 中执行：

```powershell
$script = Join-Path $env:TEMP 'mms-install-v4.20.0.ps1'
Invoke-WebRequest https://raw.githubusercontent.com/CtriXin/multi-model-switch/v4.20.0/packages/mms-install/bin/install.ps1 -OutFile $script
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -Ref v4.20.0
```

要求：PowerShell 5.1 或 7、Python 3.11+、Node 18.17+。安装器会使用独立版本目录、创建 Python venv、安装 Pilot 运行所需依赖，并写入 `mms.cmd` / `mms.ps1`；已有 config、session 和 OAuth 不会被导入或覆盖。

## 变更

- 增加 Windows Native Preview 的 platform descriptor、路径识别、附件安全、锁和 service lifecycle。
- 增加 PowerShell bootstrap、PATH 入口、更新保护和 graceful stop。
- 增加 Windows acceptance workflow，覆盖 PowerShell、Python、Node、Pi discoverability、路径/UNC/junction、安装与生命周期负向路径。
- Webber 在 Windows 上优先使用 Edge/Chrome CDP；登录态未实际连接前保持 `unknown`，不把 isolated backend 冒充为登录态浏览器。
- Settings 和 session diagnostics 展示实际 platform/browser capability 及不可用原因。

## 已知边界

Windows Native 仍是 Preview。Windows 10/11 桌面行为、真实 Edge/Chrome logged-in CDP、Pi native model bootstrap、Job Object 和真实升级恢复需要后续桌面或 self-hosted Windows 验收。Windows 附件检查仍保留本地 TOCTOU 风险；本版本不宣称 Stable。

## 回滚

macOS/Linux 可回退到上一个正式 release。Windows 安装保留版本目录，出现问题时可停止 Pilot 并选择先前版本目录；不要删除包含会话和 runtime 的 state 目录。
