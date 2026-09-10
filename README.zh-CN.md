# Multi-Model Switch（MMS）

> **MMS Pilot 是 MMS 的本地 Web 客户端，从 v4 起随安装包分发。** 安装后运行 `mms web --open` 打开。会话仍通过原有 MMS 启动链交给本机 Pi 执行，浏览器只是交互入口。[安装与使用](docs/mms-web/GETTING-STARTED.md) · [功能与边界](docs/mms-web/FEATURES.md) · [首版说明](docs/mms-web/RELEASE-v4.0.0.md) · [产品方向](docs/mms-web/NEXT-PHASE.md)。已有 CLI 启动能力全部保留。


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
- **按 session 注入能力包**：CodeGraph、TOON、grill-me、Web automation bundle 等能力默认是 session-local，不改你的全局 hook；已移除 Caveman 与 token-saver 的内建安装。
- **诊断优先**：在怀疑模型之前，先看 route、协议、cache、API Key、请求路径和 runtime exposure。

MMS Pilot 是原 launcher 的可视交互入口。`chat`、`discuss` 和高上下文 helper 现在只作为 maintenance-only 表面；主线是把本地 coding CLI 启动、路由、隔离和诊断做好。

## MMS Pilot：本地 Web 客户端

**产品名固定为 MMS Pilot。** 命令入口不变，仍然是 `mms web`、独立的 `mms-web`，macOS 上还有 `~/.mms/MMS Pilot.command`。旧的 `MMS Web.command` 会在升级时被移除，避免 `~/.mms` 里留下两个一样的启动器。

Pilot 和 `mmf config web` 是两个不同的页面，不要混：

| | 打开方式 | 用来做什么 |
|---|---|---|
| MMS Pilot | `mms web --open` | 日常干活：开会话、选模型和通道、管工作文件夹、看执行过程和产出 |
| 配置 Web UI | `mmf config web` | 配置：加通道、拉模型列表、隐藏噪音模型、生成保存预览并发布 |

Pilot 当前的 harness 是 Pi。Claude、Codex、OpenCode、agy 仍从 MMS CLI 启动，尚未接入 Pilot 的统一会话。

v4 各版累积下来的能力：

- **会话**：连续对话、恢复、停止、分叉、归档、导出，会话内切换模型与通道且保留上下文。
- **模型能力**：按模型设置默认 effort、上下文长度和能否读图，每一项都标明当前值来自哪里，与 MMF 目录不一致时可以一键填回目录值。
- **工作区**：侧栏管理工作文件夹的排序、重命名和移除，会话行支持复制 ID、重命名、分叉、导出与归档。
- **成果与资料**：预览和比较记录下来的产出，管理项目资料并记录每轮实际提交的上下文来源。
- **外观**：设置是弹窗；主题可跟随系统，主题色、界面/等宽/中文字体和字号都能实时改，只列出本机真的装了的字体。

边界：只监听本机地址，没有远程多用户认证，配置隔离不等于文件系统 sandbox。要给别人用，让对方在自己机器上安装并使用自己的模型服务。

## 版本通道：Stable / Dev / Canary

我们采用类似 Chrome 的三通道策略，并把 branch / channel / 入口语义固定下来：

| 通道 | 固定关系 | 安装命令 | 适合谁 | 更新节奏 | 质量预期 |
|---|---|---|---|---|---|
| Stable | `Stable == main` | `--channel stable` | 普通用户、主力生产环境 | 慢，最终固定到 `main` | 纯稳定上线版本，完整 smoke 后推进 |
| Dev | `Dev == dev branch == MMF/mmf` | `--channel dev` | 作者自己的日常工作机、需要最新修复的人 | 快，跟随 `dev` 分支 | 开发中稳定，targeted tests 通过 |
| Canary | `Canary == canary branch == MMG/mmg` | `--channel canary` | 每天测试的实验机器 / session | 最快，可每日同步 | 小步高频 commit，允许短期破，但必须方便回滚 |

分支约定见 [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md)。除非人类明确要求改 release/channel contract，否则不要再重命名、重映射或混用这些关系。当前过渡期：`main` 会和 `dev` 同步一段时间；等 Stable 追到当前能力后，`main` 固定为 Stable/default，不再当日常 Dev 使用。开发过程中发现的 bug 会先修复，再进入 Stable。

v4.0.0 是 MMS Pilot 的首个大版本，之后 4.x 沿 Dev 继续推进。下列 3.x 轨道为此前分支发布历史，不代表 v4 已晋级各分支：Stable/Main `3.4.z`、Dev `3.5.z`、Canary `3.6.z`。`z` 是各 channel 内的 release 计数：单 commit release 就 `z+1`，复合多个已验证 commits 的 release 也只 bump 一次；未 tag 的日常小步 commit 继续用 git hash 追踪。

当前本机维护者命令已固定：`mms` 是 public installed copy，只用于公开版本复现；`mmf` 指 dev worktree；`mmg` 指 canary worktree。`mmd` / `mmm` 已退休。唯一的 config root 是 `~/.config/mms-next`，`mms` / `mmf` / `mmg` 和 Pilot 网页都落在它上面；legacy `~/.config/mms` 不再被任何入口读取。重新生成本机命令用 `scripts/link_local_channel_commands.sh`。

## 维护者开发入口

维护者默认从仓库根目录进入 MMS，且根目录应 checkout `dev` 并保持干净、最新。`.worktrees/*` 只用于具体 issue/PR 的隔离施工，不再把 `.worktrees/dev` 当作多人共享的默认开发入口。

标准循环：

1. 进入仓库根目录，确认当前分支是 `dev`。
2. 执行 `git pull --ff-only`，保持 `dev` 最新且干净。
3. 先开 issue，并把计划写进 issue 或对应计划文档。
4. 从最新 `dev` 创建独立 worktree/branch，例如 `.worktrees/issue-14-redline-gate`。
5. 在独立 worktree 中开发、验证、commit、push。
6. 提 PR 到 `dev`，由 committee 审核。
7. committee/human 同意后 merge；根目录 `dev` 再 fast-forward 到最新，进入下一轮。

除非人类明确要求直接在 `dev` 根入口编辑，否则 agent 不得在共享 `dev` 入口叠加实质性改动或留下未跟踪文件。docs-only 计划/报告类改动在用户要求“记录/提交/产出文档”时可以默认 commit，但必须只 stage 目标文档，不能带入任何无关脏文件。

## 安装 / 升级

在新电脑上打开终端，粘贴这一条：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```

装完会问一句要不要打开 MMS Web。回车即可，浏览器自动弹出，服务在后台运行，安装进程随即退出。在页面里添加 provider 和 API Key 就能开始对话。

安装过程不问任何会影响安装内容的问题，默认走 stable 通道并把 `~/.local/bin` 写进 shell PATH。默认 UI 语言是中文，要英文加 `--lang en`。

<details>
<summary>其他安装方式</summary>

```bash
# 需要最新修复的开发用户
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel dev

# 只给测试机
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel canary

# 固定到某个 release 或分支
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref v4.2.1
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref main

# 不打开 Web 端，也不改 shell 配置（CI、脚本）
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --no-launch-web --no-shell-rc

# 装完直接打开，不询问
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --launch-web
```

</details>

安装器默认会：

- 安装到 `~/.mms`，并把 `mms`、`mmf`、`mmslogs` 链接到 `~/.local/bin`。
- 创建 `~/.mms/.venv`；系统 Python 不够新时，用 MMS-managed Python 兜底。
- 发现 PATH、Homebrew、NVM 下的 `claude` / `codex` / `opencode` / `agy`。
- 安装内建 session assets，但不会静默改写真实 provider/account 配置。
- 写入 `~/.config/mms-next/version.json`，记录安装 ref、channel 和语言；旧版本写在 `~/.config/mms` 的记录仍可读。

安装后检查：

```bash
mms doctor
mms models
mms routes
mms test --provider <provider-id> --cli claude
mms test --provider <provider-id> --cli codex
```

## 通道入口和当前配置 root

长期固定语义是：

```text
mms -> public installed copy  # 只用于公开版本复现
mmf -> Dev worktree           # preview DB root，固定 ~/.config/mms-next
mmg -> Canary worktree        # preview DB root，固定 ~/.config/mms-next
```

当前本机用 `scripts/link_local_channel_commands.sh` 把 5 个命令写到 `~/.local/bin`。另一台家里工作机如果要和白天电脑保持一致，建议同样准备 dev/canary/stable/main worktree 后运行这个脚本；如果只是普通用户安装，仍使用公开 `mms` 安装命令。

启动更新提醒默认只提醒、手动确认更新：`mmg` 每次启动检查，`mmf` 每日检查，`mms` 每日只提示 public installed copy。手动运行 `mmf update` / `mmg update` 时只允许 clean worktree fast-forward；dirty 或分叉会拒绝。

## 配置 Web UI 教程：从通道到模型可见性

这一节讲的是 `mmf config web` 的配置页面，不是 MMS Pilot。配置 Web UI 是现在最适合做教程的入口，比 TUI 更容易截图和解释。注意：`mmf` / `mmg` 都是 preview DB 入口，所以预览 DB 保存跟 `~/.config/mms-next` workflow 绑定；`mms` 也落在同一个 preview DB root 上，所以保存同样走 `写入预览 DB + 发布`；legacy root 与 `mmd` / `mmm` 已退休，不再有 legacy audited save 入口。等价入口：

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
mms web --open              # 打开 MMS Pilot
mms                         # 交互式启动器
mms claude                  # 启动 Claude
mms codex                   # 启动 Codex
mms opencode --profile agent
mms opencode --profile review
mms --provider <id> codex
mms --account <id> claude
```

OpenCode Review 推荐直接走 `mms` TUI：选 `OpenCode` -> `Review`，在 reviewer 模型页用 Space 勾选、Enter 启动；这次选择会自动写入 `[opencode.review].models`，下次自动预选。`--review-models` 仍保留给脚本/高级用户。

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
| TOON | 内建 | 压缩 agent-facing JSON / status / handoff |
| grill-me | 内建 | 逐题澄清目标、约束和验收，直接可用 |
| Web automation bundle | 内建 | 只暴露 `weber` router；`web-access` 与 `agent-browser` 作为内部 backend |
| NSR | 显式 `/nsr` 手动工作循环 | 沿用原 task 推进；不注册 Stop/compact hook、不跨 session 续跑 |
| ECC / OMC | 可选安装 | Claude agent pack；启动确认页显式选择 |
| Figma / Pilot MCP | 检测到也默认关闭 | 需要时用 `MMS_ENABLE_MCP_FIGMA=1` / `MMS_ENABLE_MCP_PILOT=1` 显式开启 |

xmem 改为 global-only：MMS / MMF 不再 bundle、安装或注入 xmem skill/hook/plugin；如果全局 agent 目录里有 xmem，就由全局版本自己生效，避免 dev channel 复制出低版本。

NSR、Map、CodeGraph 的自动 hook 已退出默认路径。旧 `nsr-*-hook`、`nsr-stop-wrapper.py`、Map/CodeGraph auto-index wrapper 保留为 no-op，不读取或删除现有 marker，不同步索引。显式 `/nsr`、`nsrctl`、Map 与 CodeGraph CLI 仍可使用。MMS 在合并旧 managed hooks 后也过滤自有退休入口；旧 runtime 的 NSR toggle 不会恢复自动 hook。

安装器只提供全局注册的只读清理计划。需要清理已存在注册时，使用 [`mms_hook_retirement.py`](mms_hook_retirement.py) 明确指定 `--file`；默认只输出 locator/hash。`--apply` 另要求审阅时 SHA256 和私有 backup 目录，且只删除精确自有入口。它不处理 MMS generated session/config；旧 session 可通过激活 shared no-op wrapper 停止自动行为。

全局 Superset terminal 注册可使用 `hooks/owned-superset-notify.sh`：先检查原 app 已使用的 `SUPERSET_TAB_ID`，无 owner 时不读取 stdin、不通知；有 owner 时委托原 `~/.superset/hooks/notify.sh`，保留 app 的直接 Mastra 路径。此 wrapper 不证明 app 上游模板已修改；app 升级若重建全局注册，需要重新检查精确命令。

Figma 和 Pilot MCP 不再默认注入；即使检测到已安装 plugin/server，也需要用 `MMS_ENABLE_MCP_FIGMA=1`、`MMS_ENABLE_FIGMA_MCP=1`、`MMS_ENABLE_MCP_PILOT=1` 或 `MMS_ENABLE_PILOT_MCP=1` 显式 opt-in。

安装器不再提供可选包。RTK、BrainKeeper、Map、CodeGraph、全局 token-saver、全局 TOON、ops-env-safe、ECC 与 OMC 的安装路径已移除；对应的 `--install-*` 参数会打印一条提示后忽略。TOON、grill-me、weber 仍作为内建 session assets 随 MMS 提供；`web-access` 与 `agent-browser` 仅作为 Weber 内部 backend。

从旧版本升级时，仅将有 MMS 专属标记的 wrapper/命令、明确指向当前 MMS vendor 的 Skill 链接和安装目录内的旧 agent packs 移入 `~/.mms/retired-backup.*`，保留原文件供恢复。同名自定义 Skills、全局 hooks/MCP 设置及真实配置目录不自动修改，也不卸载第三方程序。全局退休 hook 可按上面的只读清理计划另行检查。想单独整理 MMS 条目而不重装：

```bash
bash install.sh --cleanup-retired-packs
```

安装过程零交互：不再询问 UI 语言，也不再逐项确认可选包。`pi` 是必装项，pilot web 端依赖它；缺失的 `claude` / `codex` / `opencode` 会自动补装，已安装的保持不动。需要精确控制时仍可用 `--install-cli`：

```bash
bash install.sh --install-cli claude,codex
```

## 安全原则

- 真实 `HOME` 和全局 OAuth 状态是保护面，不是 fallback 池。
- provider/account 失败时，应在当前 runtime 内 fail closed，不静默切到另一个全局账号。
- Claude 语义在 route 支持时优先走 `Anthropic /v1/messages`。
- `OpenAI /v1/chat/completions` 是 fallback transport，不是等价默认值。
- Web UI / TUI 写配置前应先生成 preview / diff / backup / audit evidence。
- legacy `~/.config/mms/**`，尤其 Claude 相关字段，仍然是 human-gated 配置：Web 不写它。默认根 `~/.config/mms-next` 的写入统一走 Registry 审阅计划。

## 更多文档

- [`docs/mms-web/GETTING-STARTED.md`](docs/mms-web/GETTING-STARTED.md) — MMS Pilot 安装与使用
- [`docs/mms-web/FEATURES.md`](docs/mms-web/FEATURES.md) — MMS Pilot 功能与交互边界
- [`docs/mms-web/API.md`](docs/mms-web/API.md) — MMS Pilot 本地 API v1
- [`docs/WEB_UI_QUICKSTART.md`](docs/WEB_UI_QUICKSTART.md) — 配置 Web UI
- [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md)
- [`docs/MMS_USER_PREFERENCES.md`](docs/MMS_USER_PREFERENCES.md)
- [`docs/MODEL_CONFIG_CONTRACT.md`](docs/MODEL_CONFIG_CONTRACT.md)
- [`docs/AGENT_GUARDRAILS.md`](docs/AGENT_GUARDRAILS.md)

## Release checklist

1. 从 `dev` 挑选已验证变更进入 Stable 候选；同步窗口结束后，`main` 本身就是 Stable/default。
2. 运行 installer check、config check、关键 launcher smoke、Web UI save-plan smoke。
3. 更新 README / release notes，明确 Stable / Dev / Canary 安装命令。
4. 打 tag，推送 GitHub Release。
5. 对家里工作机这类同步使用场景，记录推荐 pinned commit。
