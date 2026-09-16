# v4.19.4 · 四个 harness 统一 context window

- 所有 harness 通过同一个 context-window resolver 读取模型上下文窗口。
- 用户在 Pilot 设置的 context window 优先级最高，并在 Claude Code、Codex、Pi、OpenCode 之间保持一致。
- `k3`、MiMo `[1m]`、provider profile、远端 `/models` listing 和本地覆盖文件的来源顺序固定并可排查。
- 普通稳定版安装入口仍只提供公开的 `mms` 命令。

## 升级须知

普通用户照常执行公开安装命令即可。升级不会删除会话数据；正在执行的任务按 Pilot 的安全更新规则处理。

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```
