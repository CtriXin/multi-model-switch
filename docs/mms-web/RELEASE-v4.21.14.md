# v4.21.14 · Windows 修复累积版

## 升级须知

继续 `v4.21.1` 的纯修复线，在 `v4.21.12` 之上汇总 v4.21.13 与 v4.21.14。不含新功能，Windows 仍是 Native Preview；macOS / Linux 行为不变。配置根仍是 `~/.config/mms-next`，无需迁移。本说明按 `v4.21.12..v4.21.14` 的提交记录整理，更早的变更见 `RELEASE-v4.21.12.md`、`RELEASE-v4.21.1.md` 与 `RELEASE-v4.21.0.md`。

## Windows 修复

- Pi 共享 bin：Windows 上改用 junction（`os.junction`，缺失时回退 `_winapi.CreateJunction`）建立共享 agent bin 链接，不再依赖需要开发者模式或提权的符号链接。POSIX 仍走原有 `os.symlink` 路径并保留跨设备失败时的放弃逻辑。
- Pilot skills 读取：Windows 没有可用的符号链接 overlay，改为直接把 MMS 选中的 skill 条目按优先级传给 Pi；只加载选中的条目，避免扫描父目录把被覆盖的 skill 和无关的捆绑同级目录重新带回来。同时兼容 npm 全局安装布局解析 Pi 的 `core/skills.js`，子进程输出固定按 UTF-8 解码（`errors="replace"`），GBK 系统不再因解码失败读不到 skills。
- 成果预览：Windows 缺少 `O_DIRECTORY` / `dir_fd`，`read_output` 改为逐段做词法路径校验，对工作区根、每一级目录和目标文件都拒绝符号链接、junction 及其它 reparse point，并保留原有的大小上限与错误码，维持与 POSIX 一致的不跟随链接边界。
- 服务日志：未归类异常在返回通用 500 响应的同时，把 traceback 打到服务日志，Windows 专有故障可被定位；用户可见的响应文案不变。

## 文档

- README 新增 Windows Native Preview 的从零安装步骤（PowerShell、winget 安装 Python/Node、`npm.cmd` 全局装 Pi、按 tag 运行 `install.ps1`、`mms web start`，以及 Windows 暂无可依赖 TUI 时的 `mms pi` 启动方式），并说明用户发现自身独立问题时如何脱敏上报。
- 新增 `docs/mms-web/WINDOWS-CONTRIBUTING.md`：本地 AI 诊断提示词、PowerShell 取证命令、GitHub fork/PR 步骤与 PR 模板。`GETTING-STARTED.md` 增加指向该文档的入口。
- 新增 `docs/mms-web/WINDOWS-PI-FIX-HANDOFF.md` 记录本轮 Pi 修复的交接事实。
- `AGENT.md` 增加 “User-Machine Repairs And Contributions” 一节，约定机器特定 bug 的诊断、修复报告、公开提交流程与凭据不外传边界。

## 静态包

`mms_web_static/build.json` 随版本更新到 `4.21.14`。dev 4.21 稳定线保留已发布的静态产物，不在本线重建。
