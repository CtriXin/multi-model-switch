# v4.21.14

## 升级须知

本版本继续提供 Windows Native Preview。Windows 启动与 Pi 生命周期路径已修复，Pilot 的会话、工作目录和历史记录会在更新或回滚时保留。安装器与 Pilot 文档补充了 Windows 的安装、排查和贡献说明。

本次升级不会导入、覆盖或回退已有的 config、credentials 或 session 目录。

## 变更

- 修复 Windows 下 Pi 启动、进程发现和会话清理的兼容性问题。
- 增加 Windows Native Preview 的自检、故障报告和贡献修复路径。
- 更新 Pilot Web 的发布与安全切换说明。
