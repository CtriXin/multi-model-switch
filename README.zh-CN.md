# Multi-Model Switch (MMS)

[English README](./README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 一个让 `claude`、`codex` 等 AI 编程 CLI 统一接入的本地 launcher。

## 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s --
```

![MMS - Before vs After](assets/cover.svg)

**MMS** 是一个面向本地开发者的多模型 CLI 启动器。它让你用**一个入口**管理所有 AI 编程工具，告别繁琐的环境变量配置。

---

## ⚠️ 协议与缓存的重要结论

后续只要新增 dual-protocol provider，先记住这 4 条：

- `Anthropic /v1/messages` 和 `OpenAI /v1/chat/completions` 不是等价 transport
- 如果 provider 支持 `anthropic_messages`，`Claude` 语义默认应优先走 `messages`
- `chat/completions` 是 fallback，不是默认兜底
- `cache hit` 很低时，先查实际 request path，不要只看 model/vendor 名称

进一步的运维/排查规则见：

- `docs/SERVER_CLAUDE_CACHE_RUNBOOK.md`
- `docs/AGENT_GUARDRAILS.md`

---

## ✨ 核心特性

- 🎯 **统一 TUI**：方向键选模型，回车启动，无需记忆命令
- ⚡ **快速切换**：一行命令临时切换 provider 或账号
- 🔧 **环境导出**：一键生成 env 文件供脚本使用
- 🩺 **健康诊断**：内置 `doctor` 命令检测所有 provider 状态
- 🔍 **链路追踪**：`--trace` 模式查看选择逻辑
- 🏠 **账号隔离**：多 OAuth 账号独立目录，互不串号
- 📝 **预设系统**：保存常用配置，一键启动

---

<!-- repo-graphics:runtime-start -->
## 运行时流程

![MMS 运行时流程图](docs/images/architecture-mainline-cn.png)

这张图把当前 MMS 主链路压缩成一屏：先做配置与路由决策，再启动隔离 session，并导出 routes / diagnostics。
<!-- repo-graphics:runtime-end -->

## 📦 安装

### 一键安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s --
```

默认会安装最新发布的 semver tag。
如果在交互终端里执行，安装脚本现在会先询问 `中文 / English`，然后逐项询问是否安装 `RTK enhancement`、`MindKeeper context pack`、`Map auto-index`、`read-once`、`token-saver`、`ops-env-safe`，最后检查本机有没有 `Claude Code` / `Codex CLI`，只对缺失项逐个询问要不要安装。
安装包会同时带上 MMS 自己的 `statusline-command.sh`，不依赖用户已有的全局 `~/.claude/` 脚本。
通过 `install.sh` 安装的版本还会保留一个轻量版本标记；之后在交互终端里启动 `mms` 时，如果你已经落后 `3+` 个 tag，MMS 会给出升级提示，但不会每次启动都反复刷屏。

### 安装策略

- 正常安装 / 升级：用 `main/install.sh`
- 紧急 hotfix 已发 tag、但还没 merge 到 `main`：改用 `tag-pinned installer`

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/v1.16.3/install.sh | bash
```

原因很简单：

- 安装器修复落在 `install.sh` 本身
- 如果 `main/install.sh` 还没更新，即使新 tag 已经发了，旧安装器逻辑也可能漏掉 hotfix

### 安装后立刻自检

```bash
bash install.sh --check
mms doctor
mms test --provider <id> --cli claude
mms test --provider <id> --cli codex
```

含义：

- `--check`：看安装是不是落到正确路径
- `doctor`：看 route / auth / protocol 通不通
- `test`：看指定 provider / CLI 的真实消息链路通不通

### 清理之前装过的脏版本

如果之前装过有问题的 installer，怀疑它把文件写进了 gateway session home，先跑 `dry-run`：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/cleanup_dirty_install.sh | bash
```

确认输出路径没问题，再执行真正清理：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/cleanup_dirty_install.sh | bash -s -- --apply
```

这个脚本只会清明显属于脏安装残留的目标：

- `<session-home>/.mms`
- `<session-home>/.nvm`
- `<session-home>/.config/mms`
- `<session-home>/.local/bin/mms`
- `<session-home>/.local/bin/ccs`
- `~/.local/bin/mms` / `~/.local/bin/ccs` 里仍然指向 gateway session 路径的旧链接

如果你要在 `main` 更新前先拿某个 hotfix 版本的清理脚本，把上面的 `main` 换成对应 tag 即可，例如 `v1.16.3`。

### 彻底重装前先做 full reset

如果一台机器上积累了太多历史 MMS 状态，想彻底从头安装，先跑官方 full reset 脚本的 `dry-run`：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/reset_mms_install.sh | bash
```

确认输出路径没问题，再执行真正清理：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/reset_mms_install.sh | bash -s -- --apply
```

默认只会清 MMS 自己的安装面：

- `~/.mms`
- `~/.config/mms`
- `~/.local/bin/mms`
- `~/.local/bin/ccs`
- `~/.local/bin/mmslogs`

它不会默认碰共享的 `~/.claude`、共享的 `~/.codex`，也不会碰任何 global OAuth 登录态。

如果你以前用过 `install.sh --write-shell-rc`，还想顺手删掉 shell rc 里那段精确的 `# Added by MMS` PATH block，再加：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/reset_mms_install.sh | bash -s -- --apply --include-shell-rc
```

### 一键升级

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s --
```

### 安装时改成 English UI

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --lang en
```

### 安装时顺手加上 RTK rewrite 增强

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-rtk
```

这条可选路径会额外安装 `jq` + `rtk`，并把 Claude 的 `PreToolUse:Bash` hook 配好；之后通过 MMS 启动的 Claude session 会自动继承 RTK rewrite。若本机已经有 `Codex CLI`，或者本轮安装时顺手装上了 `Codex CLI`，安装器也会继续执行 `rtk init --codex --global`。

### 安装 MMS 时顺手加上 MindKeeper context pack

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-mindkeeper-context
```

这条可选路径会安装：

- `MindKeeper MCP`
- Claude 的 `/distill`
- Claude 的 `/cz`
- Claude 的 `UserPromptSubmit` token monitor hook
- Claude 的 `SessionStart` context restore hint hook

如果本机没有 `jq`，安装器也会尝试补装，因为 token monitor hook 依赖它。

默认会锁定到经过 MMS 验证的 `MindKeeper v2.2.0`。
如果你要覆盖版本，可以显式传 `--mindkeeper-ref`：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-mindkeeper-context --mindkeeper-ref v2.2.0
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-mindkeeper-context --mindkeeper-ref main
```

边界说明：

- 这是 `Claude` 优先的 context 可选包，不包含 Hive compact/restore
- 当前不会顺手给 `Codex` 写独立 slash command
- `Hive` 相关 hook / pack 仍保持独立，不进 MMS 默认安装

### 安装 MMS 时顺手加上 Map auto-index

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-map
```

这条可选路径会安装 `Map`，并把 Claude 的 `SessionStart` auto-index hook 配好。之后进入项目时，Claude 会自动建立或刷新项目结构索引。默认会锁定到经过 MMS 验证的 `Map v0.3.1`。

如果你要覆盖 Map 版本，可以显式传 `--map-ref`：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-map --map-ref main
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-map --map-ref v0.3.1
```

边界说明：

- 当前优先接入 `Claude` 的 `SessionStart` hook
- 默认优先复用本机已有的 `Node.js 18+`；如果没有合适版本，MMS 会跳过 `Map`，不会自动改你的默认 `Node`
- 只有你明确希望 MMS 准备一个 `Node 22` fallback 时，才建议额外加 `--ensure-node22`
- 如果 `Map` 构建产物不存在，安装器会跳过 hook 注入并给出提示

### 安装 MMS 时顺手加上 read-once

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-read-once
```

这条可选路径会安装 `read-once`，并把 Claude 的下面两类 hook 配好：

- `PreToolUse:Read` token saver hook
- `PostCompact` cache reset hook

效果是避免重复全文读取文件，并在文件变化后优先提供 diff。若本机没有 `jq`，安装器也会尝试补装；如果仍然缺失，hook 会保持 fail-open 静默模式，不阻塞 Claude 正常使用。

`MMC` 的 `OAuth Claude` 隔离路径也只会内建一组 repo-owned allowlist hooks：

- `PreToolUse:Bash -> rtk-rewrite.sh`
- `PreToolUse:Read -> read-once-hook.sh`
- `PostCompact -> read-once-compact.sh`

边界说明：

- 不继承 global/source `hooks`
- 不带 `Hive` / `Map` / `Feishu` / `agentim` hooks
- `top-level mcpServers` 仍保持隔离，不通过 `MMC` 自动回流

### 安装 MMS 时顺手加上 token-saver

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-token-saver
```

这条可选路径会给普通 export-only 会话安装共用 Token Saver：

- Codex skill：`~/.codex/skills/token-saver`
- Claude skill：`~/.claude/skills/token-saver`
- 本机命令：`token-saver`、`mms-context`、`mms-toon`

边界说明：

- 不写 `~/.config/mms`
- 不改模型、账号、proxy 或 reasoning 设置
- 让普通 Codex/Claude 会话也能靠 skill 自动用长输出 ref/snippet，不需要记底层命令

### 安装 MMS 时顺手加上 ops-env-safe

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-ops-env-safe
```

这条可选路径会安装一个给隔离会话用的 path-only host integration pack：

- Codex skill：`~/.codex/skills/ops-env-safe`
- Claude 命令：`~/.claude/commands/ops-env-safe.md`
- 本地路径映射模板：`~/.config/mms/ops-env-safe.toml`

边界说明：

- 它只提供 path hints，不会注入真实 `HOME/XDG`
- 不会导出 auth secret，也不会偷偷 bootstrap 成 host shell
- 安装后请按需编辑 `~/.config/mms/ops-env-safe.toml`，补你自己的稳定宿主路径
- 适合 `mms/mmc` 隔离 session 只需要“知道路径在哪”，但不想破坏隔离语义的场景

安装后用法：

- 在 Claude 里用 `/ops-env-safe <entry-name>`
- 在 Codex 里让 `ops-env-safe` skill 按路径查询需求自动触发

### 安装 MMS 时顺手补齐常用 CLI

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-cli claude,codex
```

支持的名字只保留：`claude`、`codex`。

公开版说明：

- 这里安装 `claude`，表示安装本地 `Claude Code` binary 作为前端 CLI。
- 公开版会保留 `claude` tab 和 `mms claude` 入口。
- 如果当前 route 支持，会同时展示原生 `claude-*` 模型，以及可经 `Claude CLI` bridge 的非 `claude-*` 模型。
- 公开文档不包含 `Claude OAuth account.add/login` 流程。

### 安装指定版本

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref v1.2.0
```

### 手动安装

```bash
git clone https://github.com/CtriXin/multi-model-switch.git
cd multi-model-switch
bash install.sh --write-shell-rc
```

---

## 🚀 快速开始

### 1. 首次配置

```bash
mms config connect    # 进入配置向导，添加第一个 provider
```

### 2. 启动 TUI

```bash
mms                   # 进入交互界面，选择模型启动
```

### 3. 快速启动（免交互）

```bash
mms --preset coding                    # 使用预设启动
mms claude --provider openrouter       # 临时指定 provider
mms codex --account work               # 临时切换账号
```

---

## 📸 界面预览

### Claude Tab
![Claude Tab](assets/mms-tui.png)

### Codex Tab
![Codex Tab](assets/mms-tui-codex.png)

### 启动确认页
![Launch Confirm](assets/mms-launch-confirm.png)
*启动前确认配置：模型、Provider、模式一目了然*

**操作说明**：
- `←/→`：切换 CLI Tab（claude / codex / qwen / kimi）
- `↑/↓`：选择模型族群 / 模型
- `Enter`：确认启动
- `A`：在当前模型族内按本地测速结果智能排序通道
- `P`：从 Provider 角度浏览
- `O`：接入新通道
- `Q/Esc`：退出

**启动确认页补充**：
- `←/→`：在 `摘要 / MCP / 技能 / 钩子` 面板之间循环切换
- `Tab`：切换 `Bypass`
- `C / T / E / X`：切换 `Caveman / Thinking / Effort / ECC`，右侧面板内容会随开关实时更新

---

## 🎯 使用场景

### 场景 1：日常开发

每天需要切换不同模型对比效果：

```bash
mms                              # 进入 TUI，方向键选择
# 或者直接用预设
mms --preset sonnet-for-coding   # 启动 Claude Sonnet
mms --preset gpt-for-review      # 启动 GPT 做 Code Review
```

### 场景 2：`claude` 作为 bridge 前端

如果你希望继续用 `Claude CLI` 的交互习惯，但实际模型走 GPT / Gemini / 兼容国产模型：

```bash
mms claude --provider openrouter
```

此时公开版会在 `claude` tab 里展示当前 route 支持的原生 `claude-*` 模型，也会展示可 bridge 的非 `claude-*` 模型。

### 场景 3：团队协作

团队共享配置，但密钥各自保管：

```bash
# 团队 leader 创建 override.toml
# 包含推荐的 provider 配置（不含密钥）
# 分发给团队成员

# 成员只需要填自己的 API Key
mms config provider.credentials my-provider
```

### 场景 4：CI/CD 集成

为脚本导出环境变量：

```bash
# 生成独立 env 文件
mms env my-preset --apply

# 在脚本中使用
source ~/.config/mms/env/my-preset.sh
claude
```

### 场景 5：问题诊断

Provider 连不上或模型异常：

```bash
# 快速诊断所有 provider
mms doctor

# 测试特定 provider
mms test --provider openrouter --cli claude

# 查看详细选择链路
mms --trace --preset coding
```

---

## 🛠️ 完整命令列表

### 配置管理

```bash
mms config connect                    # 统一接入向导
mms config migrate                    # 从旧版 ccs 迁移
mms config file                       # 查看配置文件路径

mms config provider.list              # 查看 provider 列表
mms config provider.add [template]    # 添加 provider（支持模板）
mms config provider.edit <id>         # 编辑 provider
mms config provider.remove <id>       # 删除 provider
mms config provider.credentials [id]  # 编辑密钥

mms config account.add <cli>          # 添加 OAuth 账号
mms config account.login <id>         # 登录账号
mms config account.status [id]        # 查看登录状态
```

现在 `mms config provider.add` 会直接进入“通用兼容网关”配置，不再弹出 Qwen / Kimi / GLM / MiniMax 等预设模板选择。

### 模型管理

```bash
mms ls                                # 列出所有模型（支持测速）
mms warm                              # 预热模型
mms cache                             # 查看/调整缓存策略
```

### 诊断工具

```bash
mms doctor                            # 默认 lite：诊断 route / auth / protocol
mms doctor full                       # 全量：额外包含真实 Claude CLI smoke
mms doctor --provider <id>            # 诊断指定 provider
mms test --provider <id> --cli <name> # 最小闭环测试，验证实际链路
```

### Broker 实验入口

```bash
mms broker ls                         # 查看 broker profiles
mms broker show <id>                  # 查看单个 broker profile
mms broker run <id>                   # 从 MMS 启动 broker session shell
mms broker run <id> --resume-last     # 续上当前项目最近一次 broker session
mms broker smoke <id>                 # 跑一条 official child attach smoke test
```

现在也可以直接：

- 运行 `mms`
- 切到 `claude` tab
- 按 `B`

如果配置了多个 broker profile，MMS 会先让你选一个；进入后默认先尝试 `resume-last`，当前项目还没有本地记忆 session 时会自动新建，不会直接报错退出。

现在 broker profile 也会出现在 `claude` 的正常“使用入口”列表里：

- 你可以像选 `官方` / `网关` 一样选它
- 选中后会直接走 `cc-official-broker`
- 如果 profile 的 `entry_mode = "official_proxy"`，MMS 会直接拉起本机真实 official `Claude` CLI，再通过本地 proxy 接到远端 official runtime，不需要再按 `B` 进 broker shell
- 如果你是 `mms claude` 这种直接启动，选中 broker 后仍然会先让你选模型；确认后直接进 remote official cc

当前按 `B` 进去后，如果你不知道该测什么，先记两条命令就够了：

- `/tool pwd`
  - 验证本地 runner / 本地文件现场这条线
- `/official`
  - 验证 broker 是否真的返回 `sdk_url + access_token`，并让真实 official child attach 上来

如果你连 broker shell 都不想看，只想“按 B 后直接像普通通道一样进 cc”，现在可以在对应 `broker_profile` 里加：

```toml
entry_mode = "official_proxy"
```

这样按 `B` 选中这个 profile 后，会直接调用 `cc-official-broker official:proxy`，不再先进 broker shell。

如果你之前已经配成 `entry_mode = "official_connect"`，但本机 public `Claude Code` 不支持 direct-connect，MMS 现在也会自动改走 `official:proxy`，不需要手动回 shell。

`broker_profiles` 现在也可以顺带声明远端 runtime service 目标，例如：

- `remote_service_label`
- `remote_service_base_url`
- `remote_service_endpoint`
- `remote_service_model`
- `remote_service_bearer_token_env`
- `remote_claude_ssh_target_env`
- `remote_claude_container_name_env`
- `remote_claude_credentials_path_env`
- `remote_claude_global_config_path_env`

这样一个 broker profile 就可以对应一个 server-side runtime / OAuth 池，便于后续做多 OAuth 测试，而不影响原有 provider/account 主路径。

如果你的部署已经固定到 host-path auth source，现在也可以直接由 MMS 帮你把这组 env 传给 `cc-official-broker`：

- `CC_BROKER_REMOTE_CLAUDE_SSH_TARGET=root@broker-runtime.example.com`
- `CC_BROKER_REMOTE_CLAUDE_CONTAINER_NAME=''`
- `CC_BROKER_REMOTE_CLAUDE_CREDENTIALS_PATH=/path/to/isolated-claude/.credentials.json`
- `CC_BROKER_REMOTE_CLAUDE_GLOBAL_CONFIG_PATH=/path/to/isolated-claude/.claude.json`

注意：

- `CC_BROKER_REMOTE_CLAUDE_CONTAINER_NAME=''` 这里的空字符串是“显式走 host-path auth source”，不是没配
- MMS 现在会保留这个空字符串传给 broker，不会再偷偷 fallback 回旧 container 名

当前 broker shell 还会把最近一次本地 session 记到 `~/.config/cc-official-broker/session-registry.json`，作用域按 `device/workspace/project_root` 区分，所以 `--resume-last` 只会续当前项目自己的那条会话，不会去串别的项目。

开源说明：

- 文档里只保留占位 host / path 示例
- 真实部署地址、SSH target、凭据路径请保存在你自己的本地运维文档里，不要直接写进仓库

如果你现在想先验证“这个 broker profile 能不能真的吐出 `sdk_url + access_token` 给 official child”，可以直接：

```bash
mms broker smoke official-broker-personal
```

它会复用 profile 里的 `broker_base_url + device_key`，然后内部调用 `cc-official-broker` 的 `official:attach`：

- 先做 `POST /auth/device`
- 再做 `POST /sessions`
- 再拉起本机真实 official `claude --print --sdk-url ...`

如果结果是：

- `protocol_ok_auth_missing`

就说明：

- MMS 侧 profile 接线是通的
- broker 已经返回了真实可消费的 `sdk_url + access_token`
- 当前机器只是 local Claude CLI 还没登录

### 聊天与讨论

```bash
mms chat "解释递归"                   # 多模型并排对话
mms discuss "设计 proto"              # 多模型摘要 + 综合裁定
mms session resume <id>               # 恢复会话
```

---

## 🏗️ 架构设计

### 核心原则

1. **单次注入**：环境变量只在本次启动生效，不写全局 shell 配置
2. **凭据隔离**：`config.toml` 只存元数据，密钥存 `credentials.sh` 或系统 keychain
3. **本地覆盖**：支持 `~/.config/mms/override.toml`，团队共享不泄露密钥
4. **账号隔离**：每个 OAuth 账号独立目录，登录态互不干扰

### 数据流

```
用户输入 → mms → 解析配置 → 选择 provider/account →
注入环境变量 → 启动目标 CLI → 清理环境
```

### 支持的 CLI

| CLI | 协议 | 特性 |
|-----|------|------|
| `claude` | Anthropic Messages | 公开版保留 `claude` tab 和 `mms claude`；当前 route 支持时，可同时展示原生 `claude-*` 与 bridge 非 `claude-*` 模型 |
| `codex` | OpenAI Responses | 自动降级到 Chat Completions |
| `qwen` | OpenAI compatible | 直接启动 |
| `kimi` | OpenAI compatible | 默认 kimi-k2.5 |
| `gemini` | Google AI | OAuth 账号支持 |

---

## 📁 配置文件

### 目录结构

```
~/.config/mms/
├── config.toml          # 模型源元数据
├── credentials.sh       # API Key（加密存储）
├── override.toml        # 本地/团队覆盖配置
├── usage.json           # 本地启动统计
├── model-routes.json    # Hive 读取的固定 latest export
├── model-routes.snapshots/ # 按 content hash 去重的历史快照
├── speed-stats.json     # 模型测速结果
└── accounts/            # 公开版支持的 OAuth 账号目录（不包含 Claude OAuth）
    ├── personal/
    └── work/
```

### Hive routes export

- 固定 latest 路径：`~/.config/mms/model-routes.json`
- snapshot 目录：`~/.config/mms/model-routes.snapshots/`
- 导出只保留最小契约：`version`、`generated_at`、每个 model 的 `primary` / `fallbacks`
- 每条 route 只包含 `provider_id`、`anthropic_base_url`、`openai_base_url`、`api_key`
- 去重 hash 基于 canonical `version + routes` 内容，`generated_at` 不参与 hash
- 如果 canonical 内容没变，就复用已有 snapshot，并把该 snapshot 内容回写到固定 latest 文件，而不是新建快照
- 现在每次启动 `mms` CLI 都会在命令分发前同步刷新一次 Hive routes，尽量保证 session 内 Hive 读到的是最新可用通道

### config.toml 示例

```toml
[provider]
default = "openrouter"

[[providers]]
id = "openrouter"
name = "OpenRouter"
protocols = ["anthropic_messages", "openai_chat_completions"]
supported_clis = ["claude", "codex"]
# proxy = "http://127.0.0.1:7890"   # 可选：通道级强制 proxy；预探测和实际启动都走它
# no_proxy = ""                     # 可选：传给 NO_PROXY
# timezone = "America/Los_Angeles"  # 可选：默认就是这个；只影响该次启动环境
# force_ipv4 = true                 # 可选：默认开启；MMS 预探测和子进程优先 IPv4

[[accounts]]
id = "personal"
cli = "claude"
home_dir = "~/.config/mms/accounts/personal"
# proxy = "http://127.0.0.1:7890"   # 可选：账号级强制 proxy，不通则不启动
# no_proxy = ""                     # 可选：传给 NO_PROXY
# timezone = "America/Los_Angeles"  # 可选：默认就是这个；只影响该次 Claude 进程
# force_ipv4 = true                 # 可选：默认开启；MMS 会话优先 IPv4
```

### dual-protocol provider 建议

- 如果某个 provider 同时支持 `anthropic_messages` 和 `openai_chat_completions`，推荐显式同时配置：
  - `anthropic_base_url`
  - `openai_base_url`
- `claude` 会优先走 `anthropic_base_url`
- `codex` / `qwen` / `kimi` 继续走 `openai_base_url`
- 如果是 `newapi/shared-root` 这类同 root 同时承载两种协议的 gateway，只配 `openai_base_url = https://gateway.example.com/v1` 也可以；`MMS` 会先尝试把它探测成 `https://gateway.example.com` 的 `Anthropic /v1/messages`
- 但如果厂商把两种协议放在不同路径，例如 `.../v1` 和 `.../apps/anthropic`，`MMS` 不能自动猜出第二条路径，仍然应该显式配置两条 URL

---

## 🚧 已知限制

- 首次启动需要配置至少一个 provider
- 部分国产模型需通过 gateway bridge 使用
- Windows 原生支持正在开发中（目前可用 WSL）

---

## 🗺️ 路线图

- [ ] **Phase 2**：负载模式（自动按任务复杂度选模型）
- [ ] GUI 配置界面
- [ ] 插件系统
- [ ] Windows 原生支持
- [ ] 云端配置同步

---

## 🤝 贡献

欢迎 Issue 和 PR！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing`)
5. 创建 Pull Request

---

## 📄 License

MIT © 2026 [CtriXin](https://github.com/CtriXin)

---

## 🙏 致谢

感谢所有测试和反馈的用户。特别感谢以下开源项目：
- [Claude Code](https://github.com/anthropics/claude-code)
- [Codex CLI](https://github.com/openai/codex)
- [Rich](https://github.com/Textualize/rich) - Python TUI 库
