# 内建能力包，以及已退休的安装项

MMS 的能力包默认是 **session-local** 的：按会话注入，不改你的全局 hook 和 skill 目录。

## 现在随 MMS 提供的

| Pack | 状态 | 用途 |
|---|---|---|
| CodeGraph | 内建 passive skill | 优先用 symbol graph 做代码定位、callers/callees、影响面分析 |
| TOON | 内建 | 压缩 agent-facing 的 JSON / status / handoff |
| grill-me | 内建 | 逐题澄清目标、约束和验收 |
| Weber（Web automation bundle） | 内建 | 只暴露 `weber` router；`web-access` 和 `agent-browser` 只作为内部 backend |
| NSR | 显式 `/nsr` 手动循环 | 沿用原 task 推进；不注册 Stop/compact hook，不跨 session 续跑 |
| ECC / OMC | 可选 | Claude agent pack，在启动确认页显式选择 |
| Figma / Pilot MCP | 检测到也默认关闭 | 需要时用 `MMS_ENABLE_MCP_FIGMA=1` / `MMS_ENABLE_MCP_PILOT=1` 显式开启 |

## 优先级：全局的赢

MMS dev channel 的动态 session assets **不应该** shadow 你的全局 hook / skill。同名的全局版本优先，MMS 的动态版本只在缺失时作为 fallback。

`xmem` 是 global-only：MMS / MMF 不再 bundle、安装或注入 xmem 的 skill / hook / plugin。全局 agent 目录里有 xmem 就由全局版本生效，避免 dev channel 复制出一个低版本。

Figma 和 Pilot MCP 不默认注入，即使检测到已安装的 plugin / server，也要显式 opt-in（`MMS_ENABLE_MCP_FIGMA=1`、`MMS_ENABLE_FIGMA_MCP=1`、`MMS_ENABLE_MCP_PILOT=1`、`MMS_ENABLE_PILOT_MCP=1` 任一）。

## 自动 hook 已退出默认路径

NSR 的 Stop / compact hook、Map 的 auto-index、CodeGraph 的 auto-index 都已退休。旧的 `nsr-*-hook`、`nsr-stop-wrapper.py`、Map / CodeGraph auto-index wrapper 保留为 no-op：**不读取也不删除你现有的 marker，不同步索引**。显式的 `/nsr`、`nsrctl`、Map 和 CodeGraph CLI 仍然可用。

MMS 在合并旧的 managed hooks 之后也会过滤掉自己已退休的入口；旧 runtime 里的 NSR toggle 不会恢复自动 hook。

## 全局注册的清理

安装器只提供**只读**的清理计划。要清理已存在的注册，用 [`lib/mms_hook_retirement.py`](../lib/mms_hook_retirement.py) 明确指定 `--file`；默认只输出 locator 和 hash。`--apply` 另外要求审阅时的 SHA256 和一个私有 backup 目录，而且只删除精确匹配的自有入口。它不处理 MMS 生成的 session / config；旧 session 可以通过激活 shared no-op wrapper 来停止自动行为。

全局 Superset terminal 注册可以用 `hooks/owned-superset-notify.sh`：先检查原 app 已使用的 `SUPERSET_TAB_ID`，没有 owner 时不读 stdin、不通知；有 owner 时委托原 `~/.superset/hooks/notify.sh`，保留 app 自己的 Mastra 直连路径。这个 wrapper **不证明** app 上游模板已经改过；app 升级如果重建了全局注册，需要重新检查精确命令。

## 已移除的可选安装项

安装器不再提供可选包。RTK、BrainKeeper、Map、CodeGraph、全局 token-saver、全局 TOON、ops-env-safe、ECC 与 OMC 的**安装路径**已移除，对应的 `--install-*` 参数会打印一条提示后忽略。TOON、grill-me、weber 仍作为内建 session assets 随 MMS 提供。

Caveman 已全局下线，不再随 MMS 安装、显示或注入，旧配置字段会被忽略。

## 从旧版本升级时会动什么

只有这三类会被移入 `~/.mms/retired-backup.*`（**保留原文件供恢复**）：

1. 带 MMS 专属标记的 wrapper / 命令
2. 明确指向当前 MMS vendor 的 Skill 链接
3. 安装目录内的旧 agent packs

**不会自动修改**：同名的自定义 Skills、全局 hooks / MCP 设置、真实配置目录。也不会卸载任何第三方程序。

想单独整理 MMS 条目而不重装：

```bash
bash install.sh --cleanup-retired-packs
```

## 安装时的 CLI 选择

安装过程零交互：不问界面语言，也不逐项确认可选包。`pi` 是必装项（Pilot 依赖它）；缺失的 `claude` / `codex` / `opencode` 会自动补装，已安装的保持不动。需要精确控制时：

```bash
bash install.sh --install-cli claude,codex
```
