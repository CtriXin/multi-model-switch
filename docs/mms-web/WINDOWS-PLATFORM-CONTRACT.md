# Windows Native Preview 平台合同

当前状态：`Preview`，不是 `Stable`。本合同描述实现与能力边界，不把 macOS/Linux 通过推导成 Windows 通过。

## 平台字段

Pilot bootstrap 返回 `platform`：`os=win32`、`pathStyle=windows`、`shell=powershell.exe`、`processControl=windows-process-group`、`filePicker=html`。默认 config root 由 `mms_state_io.resolve_mms_config_dir()` 解析（通常为 `<home>\.config\mms-next`），state root 为 `%LOCALAPPDATA%\MMS\mms-web`；`MMS_CONFIG_ROOT`、`MMS_STATE_ROOT` 可显式覆盖，未发生静默迁移或复制旧 config。

`platform.configRoot` 复用 `mms_state_io.resolve_mms_config_dir()` 的实际解析结果；无显式覆盖时为 `<home>\.config\mms-next`，`MMS_CONFIG_ROOT` 可显式覆盖。descriptor 不会创建、迁移或写入真实配置。

## Browser capability

Windows 默认优先 `web-access` 的 Edge/Chrome CDP。CDP `loggedIn` 在未连接真实浏览器前保持 `unknown`，不会把未知登录态写成已登录；`requireLoggedInChrome` 会在调用方显式开启时阻止降级（默认行为见下）。无登录态任务可使用 `playwright` 或 `agent-browser`；Ego 返回 `supported=false` 和 Windows runtime 不可用原因。

`mms_platform.browser_capabilities()` 只描述路由，不连接浏览器。Windows 的 Webber discovery 已覆盖 Windows path separators、`pi-gateway` isolated-home 形态和 Edge/Chrome profile paths；固定端口候选在 proxy 建立连接后用 `Browser.getVersion` 校验并 pin 首次成功的 browser，切换浏览器不会静默发生。Windows 仍不能由 session 里的 POSIX `mms-chrome-host` 自动启动宿主浏览器，用户需要在 Edge/Chrome 中开启 remote debugging；这部分需要真实 desktop CDP 验收。

Pilot bootstrap、Settings 页面和 session diagnostics 都返回/展示 `browser` 与 `platform`；unsupported backend 会带原因，CDP 登录态在未连接真实浏览器前保持 `unknown`。

## 文件与停止语义

前端路径识别覆盖 drive path、UNC、引号、换行和 `file://`（drive URL、`file://localhost/C:/` 与 `file://server/share` UNC URL 都归一化为本地路径形式）。后端附件导入在 Windows 拒绝 symlink/junction（reparse point）目录重定向，写入使用同目录临时文件 + 原子 rename，失败或中断不残留半成品附件。锁使用 `msvcrt` 等价实现：非阻塞语义与 `fcntl` 一致；阻塞锁以重试循环等待（`msvcrt.LK_LOCK` 自带的 ~10 秒放弃不会冒泡给调用方）；`LOCK_SH` 在 Windows 降级为独占锁（fail-closed）；空 lock file 先补一个字节再锁。Unix 仍使用 `fcntl`。Pilot service 使用 `netstat` 端口发现与 PowerShell process query；stop 先请求 graceful window close，超时只报告未退出，不强制 `taskkill /F`。

## 验证边界

已通过 GitHub Actions Windows Server 2022/2025 acceptance matrix（PowerShell 5.1/7、Python 3.11–3.13、Node 18–22；包含 Pi discoverability、安装 dry-run、路径/UNC/junction、生命周期和更新负向路径）。Windows 10/11 桌面、真实 Edge/Chrome 登录态 CDP、Pi native model bootstrap 仍为 `unverified`，因此本合同继续标记 `Preview`。已知残余风险：Windows 附件目录检查与写入之间存在 TOCTOU 窗口；本次 release 不把它宣传为 Stable。Webber 的 Windows 路由边界见 `tests/test_mms_web_browser_capability.py`。
