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

## WebUI 当前版

当前面板叫 **Skill / MCP 管理**，默认用卡片而不是大表格：

- 顶部直接进入来源/CLI/类型筛选和能力卡片，**当前加载来源 / 路径诊断** 默认折叠；
- **当前加载来源 / 路径诊断** 只做 resolver 诊断，展开后显示全部 vendor / agent-pack / MCP 根，不再截断前几个；
- `全局继承` 会展开 Claude / Codex 的真实全局 Skill 清单，而不是只显示 TUI preview 抽样；
- Claude 和 Codex 分开统计：Claude 看 `~/.claude/skills`，Codex 看 `~/.codex/skills` + Codex plugin cache；`~/.agents/skills` 作为宿主级共享候选展示，不等于两者 launcher 都强制继承；
- **TUI 确认页对照** 和 Claude / Codex / OpenCode / Antigravity 的 CLI 总览卡放在可展开区域，避免一进页面像介绍文档；
- 每个 CLI 总览卡列出 MMS 动态、全局继承、其它检测、skill/MCP/hook 数量；
- 每个 CLI 总览卡列出 TUI 控制项、TUI 面板计数、全局来源和全局条目示例；
- 按“来源 / CLI / 类型”筛选，并支持搜索名称、用途和路径；
- 卡片正面只显示用途、来源、CLI、类型和默认状态；
- 路径、触发、`disable_key`、原始说明折叠到“高级信息”；
- 勾选“默认关闭”只更新页面内草稿，并生成 `preferences.toml` 片段；
- 全局位置单独只读展示，避免用户误以为 WebUI 会改全局 CLI。
- Claude / Codex 自己全局目录下的 Skill 可以加入“默认关闭草稿”；MMS 启动时会在 session-local merge 阶段过滤这些名字，不会删除真实全局目录。
- 宿主级共享候选和 Codex plugin cache 仍是只读展示，避免 WebUI 承诺 launcher 当前不能保证的继承过滤。
- 全局 Skill 量很大时按技能组折叠展示，例如 `lark-*` 会进入 **Lark CLI 技能组**，并支持把可过滤的同组项一次性加入/移出“默认关闭草稿”。

这一版不会写 `~/.config/mms/preferences.toml`。它只负责展示、解释、内存编辑和复制片段；后续如果要真实写入，仍要走 audited preferences writer 和 human gate。

## 安装版 / 开发版位置

MMS 动态 skill/MCP 不要求复制到某一个全局 skill 目录；运行时会按当前安装形态解析真实来源，再软链到本次 session 的隔离 HOME：

- 开发版通常来自当前 worktree 的 `vendor/` 或 `agent-packs/`；
- 安装版通常来自 MMS 安装包内部的 `vendor/` / `agent-packs/`；
- 用户显式覆盖或历史安装可能来自 `~/auto-skills/installed-skills`、`~/auto-skills/shared-skills`、`~/auto-skills/vendor`、`~/.agents/skills`、`~/.codex/skills` 等；
- WebUI 的 **当前加载来源 / 路径诊断** 按实际 resolver 结果全量展示，所以本地和安装版可能路径不同，但管理入口是同一个。

## TUI 关系

TUI 启动确认页仍然负责单次启动覆盖：

- `Enter` 按当前开关启动；
- `←/→` 在 `摘要 / MCP / 技能 / 钩子` 面板间切换；
- `↑/↓` 浏览 MCP / 技能 / 钩子条目，底部显示路径或命令；
- `D` 进入禁用选择，`Space` 切换本次启动禁用；
- `Tab` 切换 bypass；
- `M` 在支持的 Claude Opus/Sonnet 模型上切换 1M context；
- `C` 切换 Caveman；
- `N` 在可用时切换 NSR；
- `T / E` 在支持的 Claude/Codex 路径上切换 thinking / effort；
- `X` 切换 Claude agent pack（`none` / `ecc` / `omc`）；
- `B / Q` 返回或取消。

WebUI 是发现、理解和默认偏好草稿；TUI 是最终单次启动确认面。

## 持久化边界

当前读写边界：

- `preferences.toml` 才是 `bypass`、`caveman_mode`、`nsr_mode`、`agent_pack` 和 disabled session surfaces 的持久偏好位置。
- `config.toml` / registry DB 继续作为 model/provider/routing 真源，不承载 per-session 能力开关。
- 全局 Claude/Codex/OpenCode 配置保持只读，除非用户明确进入全局安装或配置流程。
- `session_surfaces.disabled.skills` 支持 `claude:<skill>` / `codex:<skill>` 这种 CLI-scoped Global Skill 过滤；不带前缀的名字仍可用于 MMS 动态 skill 或手动全局过滤。

因此，未来保存支持应该是独立的 audited preferences writer，而不是模型/通道保存流程的副作用。

## 固定展示位置 vs 真实安装位置

当前已完成的是 WebUI 固定展示入口：`Skill / MCP 管理` 里的 **当前加载来源 / 路径诊断**。它会按实际 resolver 展示安装版/开发版当前选中的根，但默认折叠，避免抢占主要管理区。

还没有完成“把所有动态 Skill/MCP 物理整合到一个真实文件夹再统一安装”。现有持久配置入口是 `[assets.roots]`，用户可以在 `preferences.toml` 指定某个动态 skill 的真实根，例如 `web_access = "~/my-skills/web-access"`；但任何写入 `~/.config/mms/preferences.toml` 都必须走 human gate。

## 交互参考

这一版更接近 MCP Inspector / Smithery 这类管理中心的信息层级：先显示可筛选能力和状态，把来源路径、协议细节或 CLI 细节折叠起来。
