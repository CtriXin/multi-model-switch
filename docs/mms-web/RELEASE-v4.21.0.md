# v4.21.0 · Windows Native Preview 修复版

## 升级须知

本版本基于 `v4.20.0`，只收口 Windows Native Preview 的启动与对话阻塞。Windows 仍是 Preview，不等同于 Stable 支持；后续 `dev` 功能不在本版本范围内。

## Windows 修复

- Windows 下优先解析可执行的 `pi.cmd` / `pi.exe`，跳过 npm 生成的 extensionless shim。
- Windows installer 和运行环境补齐 `tzdata`，避免 `ZoneInfo` 初始化失败。
- 增加 Windows resolver、runtime、Pilot lifecycle 和 Pi RPC smoke 覆盖。

## 验证边界

Windows Server 2022/2025、PowerShell 5.1/7、Python 3.11–3.13、Node 18–22 的 Acceptance 矩阵用于平台证据。真实 Windows 机器上的 Pilot 启动、Pi RPC 和模型对话由用户完成验证。

Windows 10/11 桌面、真实 Edge/Chrome 登录态 CDP、Pi native model bootstrap、Job Object 和真实升级恢复仍属于后续 Preview 边界。

## 安装

Windows 不使用公开 npm installer 的 `npx @ctrixin/mms` 路径。请从本 Release 下载 `packages/mms-install/bin/install.ps1`，或在 PowerShell 中执行：

```powershell
$script = Join-Path $env:TEMP 'mms-install-v4.21.0.ps1'
Invoke-WebRequest https://raw.githubusercontent.com/CtriXin/multi-model-switch/v4.21.0/packages/mms-install/bin/install.ps1 -OutFile $script
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -Ref v4.21.0
```

要求：PowerShell 5.1 或 7、Python 3.11+、Node 18.17+。安装器会使用独立版本目录并保留已有 config、session 和 OAuth。

## 回滚

Windows 安装保留版本目录。出现问题时可停止 Pilot 并选择先前版本目录；不要删除包含会话和 runtime 的 state 目录。
