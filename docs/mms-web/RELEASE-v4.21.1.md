# v4.21.1 · Windows 对话链路 hotfix

## 升级须知

基于 `v4.21.0` 的纯 hotfix：只修复 Windows（尤其是中文/GBK 系统）下 `mms web` 生命周期与 Pilot 对话链路的编码崩溃。不含新功能；Windows 仍是 Preview。macOS / Linux 行为不变。

## Windows 修复

- `mms web start/status/stop/restart`：`netstat` 与 `powershell.exe`（CIM 进程查询）改为字节捕获，先严格 UTF-8、再按系统 ANSI 代码页（GBK 系统为 cp936）安全解码，兜底 `errors=replace`；不再因系统输出解码失败让整个生命周期命令崩溃。
- 发送消息后会话无法继续：catalog 与 model-settings 两个 worker 子进程的 JSON 契约固定为 UTF-8 字节（父进程发送 UTF-8 bytes、worker 端 `stdin` 按 UTF-8 读取、父进程按 UTF-8 `errors=replace` 解码），不再被 GBK locale 的 `text=True` 双向损坏。
- 新增 Windows 编码回归测试：GBK 字节下 netstat/CIM 解析、含中文路径的命令行拆分、worker UTF-8 roundtrip（GBK locale 模拟），并纳入 Windows Acceptance pytest 套件。

## 验证边界

Windows Server 2022/2025、PowerShell 5.1/7、Python 3.11–3.13、Node 18–22 的 Acceptance 矩阵用于平台证据；真实中文 Windows 桌面上的 Pilot 对话由用户完成验证。

## 安装与回滚

与 v4.21.0 相同：使用 Release 内的 `packages/mms-install/bin/install.ps1`，`-Ref v4.21.1`。安装器保留已有 config、session 与 OAuth；回滚时停止 Pilot 并选回先前版本目录，不要删除 state 目录。
