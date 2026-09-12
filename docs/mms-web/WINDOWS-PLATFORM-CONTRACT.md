# Windows Native Preview 平台合同

当前状态：`Preview`，不是 `Stable`。本合同描述实现与能力边界，不把 macOS/Linux 通过推导成 Windows 通过。

## 平台字段

Pilot bootstrap 返回 `platform`：`os=win32`、`pathStyle=windows`、`shell=powershell.exe`、`processControl=windows-process-group`、`filePicker=html-or-powershell`。默认目录为 `%APPDATA%\MMS\mms-next`（config）和 `%LOCALAPPDATA%\MMS\mms-web`（state）；`MMS_CONFIG_ROOT`、`MMS_STATE_ROOT` 可显式覆盖，未发生静默迁移或复制旧 config。

注意：`platform.configRoot` 只是描述性字段；Pilot 实际使用的 config root 仍由 `mms_state_io.resolve_mms_config_dir()` 解析（无显式覆盖时为 `<home>\.config\mms-next`）。两者在 Windows 上尚不一致，需要后续对齐，不能把 bootstrap 里的 `configRoot` 当作真实生效路径。

## Browser capability

Windows 默认优先 `web-access` 的 Edge/Chrome CDP。CDP `loggedIn` 在未连接真实浏览器前保持 `unknown`，不会把未知登录态写成已登录；`requireLoggedInChrome` 会在调用方显式开启时阻止降级（默认行为见下）。无登录态任务可使用 `playwright` 或 `agent-browser`；Ego 返回 `supported=false` 和 Windows runtime 不可用原因。

`mms_platform.browser_capabilities()` 只描述路由，不连接浏览器；以下边界是审查（2026-09-12）确认的当前实现状态，需要在 W1/W2 逐项验证并补齐：

- weber 的 unified adapter 只在调用方传入 `requireLoggedInChrome: true` 时才把 fallback 限制在 `web-access`；默认降级链（`web-access → playwright → agent-browser → camoufox`）在 CDP 运行中断线时会切到 isolated backend，只有 `console.warn`，用户不可见。
- `browser-discovery.mjs` 的 isolated HOME 判定只匹配 POSIX 分隔符和 `.mmf`/`.config/mms`/`gateway/s`/`sessions` 形态；实际 `pi-gateway/s/...` 布局与 Windows `\` 路径都不命中，CDP 会话必须依赖 MMS 注入的 `WEB_ACCESS_HOST_HOME` / `HOST_HOME`。
- session 的 `mms-chrome-host` wrapper 是 `/bin/sh` 脚本，只在 macOS/Linux 启动 Chrome；Windows Native 下 cdp-proxy 的“用 mms-chrome-host 重启宿主 Chrome”恢复指引不可用，只能由用户手动在 Edge/Chrome 打开 `edge://inspect` / `chrome://inspect` 允许远程调试。
- bundled `lib/adapters/agent-browser.ts` 用 `execFile('agent-browser')`；Windows 上 npm 生成的 `.cmd` shim 不能由 `execFile` 直接执行，能力探测（`shutil.which`）与适配器实际可用性会不一致。`playwright` 同理：registry 探测 CLI，adapter 用 npm module。
- 固定端口 9222/9229/9333 的 fallback 连接在 `browser.id === 'unknown'` 时不做 `Browser.getVersion` 产品校验；`check-deps` 也把 `unknown` 代理视为与任意期望浏览器兼容，存在错连到其他自动化 Chrome 的路径。

Pilot bootstrap 已返回 `browser` 列表和 `platform`，但 Pilot Web UI 和 session diagnostics 目前都没有渲染/导出这些字段，“页面和诊断中显示实际 backend、登录态要求及不可用原因”尚未完成。

## 文件与停止语义

前端路径识别覆盖 drive path、UNC、引号、换行和 `file://`（drive URL、`file://localhost/C:/` 与 `file://server/share` UNC URL 都归一化为本地路径形式）。后端附件导入在 Windows 拒绝 symlink/junction（reparse point）目录重定向，写入使用同目录临时文件 + 原子 rename，失败或中断不残留半成品附件。锁使用 `msvcrt` 等价实现：非阻塞语义与 `fcntl` 一致；阻塞锁以重试循环等待（`msvcrt.LK_LOCK` 自带的 ~10 秒放弃不会冒泡给调用方）；`LOCK_SH` 在 Windows 降级为独占锁（fail-closed）；空 lock file 先补一个字节再锁。Unix 仍使用 `fcntl`。Pilot service 使用 `netstat` 端口发现与 PowerShell process query；stop 先请求 graceful window close，超时只报告未退出，不强制 `taskkill /F`。

## 验证边界

当前环境为 macOS，已执行 descriptor、browser capability、lock/import（含 fake-msvcrt 单测与 Windows 分支 monkeypatch 测试）和 cross-platform negative tests；Windows 真实 install、PowerShell 新窗口 PATH、Edge/Chrome CDP、隔离 HOME 注入、mms-chrome-host、真实 junction/reparse 行为、真实 msvcrt 竞争、UNC 实际访问、路径大小写归一化、Job Object 和升级恢复仍为 `unverified`，需要 GitHub Actions Windows runner 或真实 Windows 机器验收。已知残余风险：Windows 附件目录检查与写入之间存在 TOCTOU 窗口（本地攻击者可在检查后替换目录），macOS/Linux 由 dir_fd + O_NOFOLLOW 消除该窗口。Webber 的 Windows 路由边界见 `tests/test_mms_web_browser_capability.py`。
