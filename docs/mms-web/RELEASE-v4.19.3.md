# v4.19.3 · 公共命令入口收口

- 普通 stable 安装默认只提供公开的 `mms` 命令，以及 `mms-web`、`mmslogs` 辅助入口。
- 安装器不再覆盖维护者本机的 `mmf`、`mmg` 等开发入口；显式安装 `dev` 或 `canary` 时仍可创建对应预览入口。
- `mmf`、`mmg`、`mmd`、`mmm` 的本机命令矩阵继续由 `scripts/link_local_channel_commands.sh` 管理。

## 升级须知

普通用户照常执行公开安装命令即可。已有本机开发入口不会被 stable 安装改写；旧的 MMS-owned `mmf` 链接会被移除，避免把公开副本误当成 dev 入口。

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```
