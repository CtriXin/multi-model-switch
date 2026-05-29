# MMS 会话能力中心

状态：WebUI 第一版只读目录 + 默认关闭草稿。

## 用户问题

模型和通道已经能在 WebUI 里看懂，但技能、MCP 服务、hooks 和能力包仍然容易混在一起：

- 哪些来自用户自己的全局 CLI 配置；
- 哪些是 MMS 启动 session 时临时注入；
- 哪个 CLI 会拿到它；
- 文件路径或触发点在哪里；
- 默认会带上、按能力包启用，还是应该默认关闭。

## 展示模型

WebUI 按三层解释，不把技术字段一口气摊开：

1. **MMS 动态注入**：启动 session 时临时加入的技能、MCP 服务、插件和 hooks；默认不污染全局 CLI。
2. **全局继承**：用户已有的 Claude/Codex/OpenCode 配置或插件；WebUI 只读展示，不静默编辑。
3. **其它检测项**：启动预览能看到但还未明确归类的条目，保守展示并把路径放进高级信息。

能力包如 Caveman、NSR、ECC、OMC 仍然是用户级开关；技能 / MCP / hooks 是能力包展开后的 surface。

## WebUI 第一版

当前面板叫 **会话能力中心**，默认用卡片而不是大表格：

- 按“来源 / CLI / 类型”筛选，并支持搜索名称、用途和路径；
- 卡片正面只显示用途、来源、CLI、类型和默认状态；
- 路径、触发、`disable_key`、原始说明折叠到“高级信息”；
- 勾选“默认关闭”只更新页面内草稿，并生成 `preferences.toml` 片段；
- 全局位置单独只读展示，避免用户误以为 WebUI 会改全局 CLI。

这一版不会写 `~/.config/mms/preferences.toml`。它只负责展示、解释、内存编辑和复制片段；后续如果要真实写入，仍要走 audited preferences writer 和 human gate。

## TUI 关系

TUI 启动确认页仍然负责单次启动覆盖：

- `Tab` 切换 bypass；
- `C` 切换 Caveman；
- `N` 在可用时切换 NSR；
- `X` 切换 Claude agent pack（`none` / `ecc` / `omc`）；
- MCP / Skills / Hooks 面板可以选择某个显示项，并在本次启动禁用。

WebUI 是发现、理解和默认偏好草稿；TUI 是最终单次启动确认面。

## 持久化边界

当前读写边界：

- `preferences.toml` 才是 `bypass`、`caveman_mode`、`nsr_mode`、`agent_pack` 和 disabled session surfaces 的持久偏好位置。
- `config.toml` / registry DB 继续作为 model/provider/routing 真源，不承载 per-session 能力开关。
- 全局 Claude/Codex/OpenCode 配置保持只读，除非用户明确进入全局安装或配置流程。

因此，未来保存支持应该是独立的 audited preferences writer，而不是模型/通道保存流程的副作用。
