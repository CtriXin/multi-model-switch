# Multi-Model Switch（MMS）

[主 README](./README.md) · [English README](./README.en.md)

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

> MMS 是一个 launcher-first 的本地 AI Coding CLI 运行时管理器。它把 `claude`、`codex`、`opencode`、`agy` 放到同一个入口里，让你选择模型、通道、账号、session 能力包和隔离 HOME，而不是让失败路径偷偷掉回真实全局账号。

![MMS 启动器树结构](docs/images/mms-launcher-tree-cn.svg)

## 先说人话：它解决什么问题？

如果你同时使用 Claude Code、Codex、OpenCode、New API / OpenAI-compatible 平台、国产模型和多个 provider，MMS 负责把“启动前应该想清楚的事”集中起来：

- **一个入口启动多个 CLI**：`mms` 进入 TUI，或直接 `mms claude` / `mms codex` / `mms opencode`。
- **一个地方管理模型来源**：provider、account、route、fallback、thinking、vision、cache-sensitive transport 都在启动前可见。
- **隔离但可恢复**：Claude/Codex session 使用 MMS 管理的 HOME / config seed，减少污染真实全局配置，同时保留 resume。
- **Web UI 配配置**：不想手写 TOML 时，用 `mmf config web` 添加通道、拉模型、隐藏噪音模型、预览保存计划。
- **按 session 注入能力包**：Caveman、CodeGraph、token-saver、TOON、xmem、Web automation bundle 等能力默认是 session-local，不改你的全局 hook。
- **诊断优先**：在怀疑模型之前，先看 route、协议、cache、API Key、请求路径和 runtime exposure。

MMS 不是新的 chat 客户端。`chat`、`discuss` 和高上下文 helper 现在只作为 maintenance-only 表面；主线是把本地 coding CLI 启动、路由、隔离和诊断做好。

## 版本通道：Stable / Dev / Canary

我们采用类似 Chrome 的三通道策略，避免 `main` 同时承担“稳定版”和“日常开发版”的语义。

| 通道 | 安装命令 | 适合谁 | 更新节奏 | 质量预期 |
|---|---|---|---|---|
| Stable | `--channel stable` | 普通用户、主力生产环境 | 慢，跟随 GitHub Release / stable 分支 | 完整 smoke 后推进 |
| Dev | `--channel dev` | 作者自己的日常工作机、需要最新修复的人 | 快，当前过渡期跟随 `main`；分支切好后跟随 `dev` | targeted tests 通过 |
| Canary | `--channel canary` | 专门试新功能/回归验证的机器 | 最快，可每日同步 | 允许短期破，但必须可回滚 |

分支约定见 [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md)。当前过渡期建议：`main` 暂不停止迭代；`dev` 和 `canary` 先从当前 `main` 切出；等 `release/stable-*` 追上后，再把稳定发布节奏固定下来。

## 安装 / 升级

> 默认 UI 语言是中文；如果要英文，加 `--lang en`。

### Stable：推荐给普通用户

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel stable --write-shell-rc
```

### Dev：推荐给你的两台工作机保持同状态

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel dev --write-shell-rc
```

### Canary：只给测试机或专门试新功能的 session

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel canary --write-shell-rc
```

### 固定到某个 release 或分支

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref v3.3.1
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref main
```

### 全新电脑顺手安装 CLI

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel dev --install-cli claude,codex,opencode --write-shell-rc
```

安装器默认会：

- 安装到 `~/.mms`，并把 `mms`、`mmf`、`mmslogs` 链接到 `~/.local/bin`。
- 创建 `~/.mms/.venv`；系统 Python 不够新时，用 MMS-managed Python 兜底。
- 发现 PATH、Homebrew、NVM 下的 `claude` / `codex` / `opencode` / `agy`。
- 安装内建 session assets，但不会静默改写真实 provider/account 配置。
- 写入 `~/.config/mms/version.json`，记录安装 ref、channel 和语言。

安装后检查：

```bash
mms doctor
mms models
mms routes
mms test --provider <provider-id> --cli claude
mms test --provider <provider-id> --cli codex
```

## MMS 和 MMF：不是两套程序，是两套配置 root

默认安装只有一套代码在 `~/.mms`，但会暴露两个入口：

```text
mms -> ~/.config/mms       # stable/current root，日常启动
mmf -> ~/.config/mms-next  # preview root，适合试 Config v2 / Web UI / registry DB
```

所以你现在看到的“本地两套”主要是 **MMS + MMF 两个 config root**，不是 Stable/Dev 两个安装目录。另一台家里工作机如果要和白天电脑保持一致，建议安装同一个 `Dev` channel / pinned commit，然后同步必要的 provider 配置；如果想同时试 Stable 和 Canary，当前建议通过 `mms` / `mmf` 的 root 隔离来做，不要让两个安装器互相覆盖 `~/.mms`。

## Web UI 教程：从通道到模型可见性

Web UI 是现在最适合做教程的入口，比 TUI 更容易截图和解释。启动：

```bash
mmf config web
```

常见流程：

1. **打开 Web UI**：先看首页的 Root / Registry DB / Latest Approved Bundle 状态。
2. **添加或选择通道**：填写内部 ID、显示名、OpenAI / Anthropic base URL、API Key、models endpoint、protocols、supported CLIs。
3. **拉取模型列表**：查看远端返回模型；如果远端不返回但你确认可用，用 extra/manual 模型补到当前通道。
4. **设置模型能力**：隐藏噪音模型，标记 vision / reasoning / cache-sensitive 等能力。注意 Web UI 的 `reason` 是能力 metadata，不是 launch-time Thinking 开关。
5. **生成保存预览**：先看 diff、risk、route publish guard 和 redacted plan JSON。
6. **保存/发布 preview bundle**：preview root 会写 DB candidate、secret backend 和 `generated/model-registry.latest-approved.json`。
7. **回到启动器验证**：用 `mmf config check --json`、`mmf config bundle --json`、`mmf doctor` 和一次真实 `mms test` 确认。

更完整的 Web UI 图文脚本见 [`docs/WEB_UI_QUICKSTART.md`](docs/WEB_UI_QUICKSTART.md)。后续要做截图时，用 Playwright 打开本地 Web UI 会比截 TUI 更稳定。

## 快速使用

```bash
mms                         # 交互式启动器
mms claude                  # 启动 Claude
mms codex                   # 启动 Codex
mms opencode --profile agent
mms --provider <id> codex
mms --account <id> claude
```

只导出环境变量，不立即启动：

```bash
mms --export codex
mms --export opencode
mms --export claude --apply
```

配置与诊断：

```bash
mms config preferences.help
mms exposure
mms logs
mms doctor full
mmf config web
```

## 常见问题

### 我只有一个 New API 平台，模型很多，MMS 能用吗？

能。把 New API 当成 provider：填 base URL / key / models endpoint，然后让 Web UI 拉模型；拉不到但真实可用的模型放到 extra/manual 模型。隐藏、能力标记和 fallback 属于本地 policy，不应因为一次远端拉取缺失就盲删。

### Thinking 是 Web UI 里的哪个勾？

Web UI 模型表里的 `reason` / reasoning 是模型能力 metadata。真正启动时是否开 Thinking，取决于 provider/model compatibility profile 的 `thinking.supported/default_enabled`、effort 配置，以及 runtime 的 `thinking_mode`。

### Caveman 现在怎么选？

启动确认页按 `C` 在 Off / Light / Standard / Full 之间循环。默认 Light。写偏好时用：

```toml
[launch.defaults]
caveman_mode = "enable"
caveman_level = "light" # light | standard | full
```

### 另一台电脑应该装什么？

如果那台是你的家里工作机，建议和白天机器一样安装 `Dev`，并尽量 pin 到同一个 commit / channel。Stable 更适合给别人或生产环境；Canary 更适合专门测试。

## 内建能力包

| Pack | 状态 | 用途 |
|---|---|---|
| Caveman | 内建 | 低 token 沟通模式；确认页选择 Off/Light/Standard/Full |
| CodeGraph | 内建 passive skill | 优先用 symbol graph 做代码定位、callers/callees、impact 分析 |
| token-saver | 内建 | 长日志/测试输出/diff 存 ref + snippet；`token-gain` / `mms-gain` 看节省估算 |
| TOON | 内建 | 压缩 agent-facing JSON / status / handoff |
| xmem | 内建 skill；可选全局 CLI | 跨项目 truth card / recall |
| Web automation bundle | 内建 | `weber` router + `web-access` 登录态 Chrome + `agent-browser` headless |
| NSR | 内建，默认开启 | MMS-managed Claude/Codex hook guard / closeout |
| ECC / OMC | 可选安装 | Claude agent pack；启动确认页显式选择 |

可选全局安装示例：

```bash
bash install.sh --install-codegraph
bash install.sh --install-token-saver
bash install.sh --install-toon
bash install.sh --install-xmem
```

CodeGraph 初始化提示：

```text
找出当前工作区下所有 git repo；没有 .codegraph 就执行 codegraph init -i，已有 .codegraph 就执行 codegraph sync；跳过 node_modules/vendor/build；最后汇总失败列表。
```

## 安全原则

- 真实 `HOME` 和全局 OAuth 状态是保护面，不是 fallback 池。
- provider/account 失败时，应在当前 runtime 内 fail closed，不静默切到另一个全局账号。
- Claude 语义在 route 支持时优先走 `Anthropic /v1/messages`。
- `OpenAI /v1/chat/completions` 是 fallback transport，不是等价默认值。
- Web UI / TUI 写配置前应先生成 preview / diff / backup / audit evidence。
- 真实 `~/.config/mms/**`，尤其 Claude 相关字段，仍然是 human-gated 配置。

## 更多文档

- [`docs/WEB_UI_QUICKSTART.md`](docs/WEB_UI_QUICKSTART.md)
- [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md)
- [`docs/MMS_USER_PREFERENCES.md`](docs/MMS_USER_PREFERENCES.md)
- [`docs/MODEL_CONFIG_CONTRACT.md`](docs/MODEL_CONFIG_CONTRACT.md)
- [`docs/AGENT_GUARDRAILS.md`](docs/AGENT_GUARDRAILS.md)

## Release checklist

1. 从 `dev` / `main` 挑选已验证变更进入 Stable 候选。
2. 运行 installer check、config check、关键 launcher smoke、Web UI save-plan smoke。
3. 更新 README / release notes，明确 Stable / Dev / Canary 安装命令。
4. 打 tag，推送 GitHub Release。
5. 对家里工作机这类同步使用场景，记录推荐 pinned commit。
