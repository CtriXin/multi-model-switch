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

当前面板叫 **Skill / MCP 管理**，默认按“操作入口”组织，而不是先解释来源：

- 顶部先显示当前管理范围、待应用关闭项，以及三个操作入口：在这里开/关、添加到 MMS 动态、添加到 Global；
- 然后进入来源/CLI/类型筛选和能力卡片，**当前加载来源 / 路径诊断** 放在卡片区之后并默认折叠；
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
- **应用默认关闭** 是 preferences.toml 的单独保存区，仍保留复制片段作为 fallback；**Global 添加位置** 只显示最常用落点，已检测到的其它全局/plugin 位置默认折叠；
- Claude / Codex 自己全局目录下的 Skill 可以加入“默认关闭草稿”；MMS 启动时会在 session-local merge 阶段过滤这些名字，不会删除真实全局目录。
- 宿主级共享候选和 Codex plugin cache 仍是只读展示，避免 WebUI 承诺 launcher 当前不能保证的继承过滤。
- 全局 Skill 量很大时按技能组折叠展示，例如 `lark-*` 会进入 **Lark CLI 技能组**，并支持把可过滤的同组项一次性加入/移出“默认关闭草稿”。

这一版不会把 Skill/MCP/Hook 偏好混进模型/provider 保存。`应用默认关闭` 会走独立 preferences writer：确认后只写 `preferences.toml`，并创建 backup + audit；复制片段仍作为 fallback。

## 安装版 / 开发版位置

MMS 动态 skill/MCP/hook 现在有一个固定的用户级安装根：

```text
~/.local/share/mms/assets/
  skills/<skill-name>/SKILL.md
  mcp/<mcp-name>/...
  packs/<pack-name>/...
  hooks/<hook-name>/...
  packages/<asset-name>/...   # 兼容兜底
```

推荐把真实包软链到这个目录，而不是复制完整目录。launcher 的读取顺序是：

1. 显式 env，例如 `MMS_WEB_ACCESS_ROOT`；
2. `preferences.toml` 的 `[assets.roots]` 单项覆盖；
3. 固定 managed assets root：`~/.local/share/mms/assets` 或 `[assets].managed_root`；
4. 开发版 / 安装版内置的 `vendor/`、`agent-packs/` 和历史兼容路径。

运行时仍然会把最终解析到的来源软链到本次 session 的隔离 HOME，不会把包复制进每个隔离环境：

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
- `[assets].managed_root` 是固定 managed assets 安装根；默认是 `~/.local/share/mms/assets`。
- `[assets].managed_enabled = false` 可以关闭固定根读取；env 显式 root 仍可用于调试。
- `config.toml` / registry DB 继续作为 model/provider/routing 真源，不承载 per-session 能力开关。
- 全局 Claude/Codex/OpenCode 配置保持只读，除非用户明确进入全局安装或配置流程。
- `session_surfaces.disabled.skills` 支持 `claude:<skill>` / `codex:<skill>` 这种 CLI-scoped Global Skill 过滤；不带前缀的名字仍可用于 MMS 动态 skill 或手动全局过滤。

因此，未来保存支持应该是独立的 audited preferences writer，而不是模型/通道保存流程的副作用。

## 固定展示位置与固定安装位置

当前已完成的是 WebUI 固定管理入口：`Skill / MCP 管理`。首屏用于筛选、开关和保存偏好；**当前加载来源 / 路径诊断** 会按实际 resolver 展示安装版/开发版当前选中的根，但默认折叠，避免抢占主要管理区。

当前也已经有固定安装根：`~/.local/share/mms/assets`。现有持久配置入口包括 `[assets].managed_root` 和 `[assets.roots]`；前者是统一根，后者是单个能力的覆盖。任何写入 `~/.config/mms/preferences.toml` 仍必须走 human gate。

## 交互参考

这一版更接近 MCP Inspector / Smithery 这类管理中心的信息层级：先显示可筛选能力和状态，把来源路径、协议细节或 CLI 细节折叠起来。
