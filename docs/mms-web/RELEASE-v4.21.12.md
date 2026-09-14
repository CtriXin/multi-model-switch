# v4.21.12 · Windows 修复累积版

## 升级须知

基于 `v4.21.1` 的纯修复线，汇总 v4.21.2 到 v4.21.12。不含新功能，Windows 仍是 Preview；macOS / Linux 行为不变。配置根仍是 `~/.config/mms-next`，无需迁移。本说明按各版本提交记录整理，细节以 `RELEASE-v4.21.0.md`、`RELEASE-v4.21.1.md` 与对应提交为准。

## Windows 修复

- Pi 启动：允许更慢的启动握手；RPC 管道在 launcher 中保持传递；Pi 的 bash 不可用时改用 PowerShell（v4.21.2、v4.21.3）。
- 会话历史：Pi 历史按 UTF-8 读取，GBK 系统不再出现乱码或轮询中断（v4.21.4）。
- 工作区：支持文件夹选择器，并保持选择器在长列表下可响应（v4.21.7）。
- Pi 生命周期：sink 出错后 RPC reader 继续存活，流式历史不再中断（v4.21.8、v4.21.9）。
- Pilot doctor：新增自检，可选模型 smoke（v4.21.10、v4.21.11）。
- 会话守护：用 Win32 API 查询守护进程 pid，不再依赖命令行工具输出的编码（v4.21.12）。
