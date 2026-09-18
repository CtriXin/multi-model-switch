# Multi-Model Switch（MMS）

[English](./README.en.md) · [![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**MMS 让你在自己的电脑上，用自己的模型服务，跑各家 AI coding 工具。**

它管的是启动之前那件麻烦事：你有好几个 provider、一堆 API Key、几十个模型名、`claude` 和 `codex` 和 `opencode` 各自一套配置，还要担心某次失败会不会偷偷用了你的真实全局账号。MMS 把这些收到一个地方，让你在启动前看清楚"这次用谁、走哪条路、花谁的额度"。

装好以后有两个入口：**MMS Pilot**（浏览器里的工作台，日常都在这里）和 **`mms` 命令行**（启动 Claude / Codex / OpenCode 这些原生 CLI）。两边读同一份配置。

![MMS 启动器树结构](docs/images/mms-launcher-tree-cn.svg)

---

## 装它

macOS / Linux，一条命令：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```

装完会问一句要不要打开 Pilot。回车就好，浏览器会自己弹出来，服务在后台跑，安装进程退出。

**Windows** 是 Native Preview，步骤不一样，从零开始的完整流程见 [`docs/install/WINDOWS.md`](docs/install/WINDOWS.md)。

安装过程不问任何会影响安装内容的问题：默认 stable 通道、中文界面（要英文加 `--lang en`）、把 `~/.local/bin` 写进 shell PATH。`pi` 是必装的（Pilot 依赖它），缺失的 `claude` / `codex` / `opencode` 会自动补，已经装了的不动。

**升级就是重新粘贴同一条命令。** 但如果 Pilot 正在跑，安装器会停下来拒绝，不会替你关掉它：先在 Pilot 页面里点更新，或者 `mms web stop`（本机有多个实例用 `--all`），然后再跑安装命令。

其它安装方式（预览线、固定版本、CI 用的静默安装）见 [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md)。

## 第一次打开做什么

1. Pilot 会引导你加第一个通道：填服务地址和 API Key。
2. 点拉取模型。拉不到但你确认能用的，手填补上。
3. 勾选你真的会用的模型，保存前会给你一份脱敏的预览。
4. 回到主界面，选个文件夹、选个模型，开始说话。

跑起来之后，值得顺手做的两件事：在模型页把每个模型的**上下文长度**和**能不能读图**核对一遍（值来自哪里界面上有标注，和目录不一致时有一键填回），以及在设置里挑个主题和字体。

## 它替你管什么

**一个入口启动多个 CLI。** `mms` 进 TUI 选，或者直接 `mms claude` / `mms codex` / `mms opencode`。

**模型来源在启动前就看得见。** provider、account、路由、fallback、thinking、识图、cache 敏感的传输协议，都在选择界面上，不是启动之后才发现不对。

**隔离但能恢复。** Claude / Codex 的会话跑在 MMS 管的 HOME 和 config seed 里，少污染你的真实全局配置，同时 resume 照样能用。失败的时候它会在当前 runtime 里停下来报错，**不会**偷偷掉回你的全局 OAuth 账号。

**能力包按会话注入。** CodeGraph、TOON、grill-me、Weber（Web 自动化）这些默认是 session-local 的，不改你的全局 hook。

**先诊断再怀疑模型。** 报错的时候先看路由、协议、请求路径、Key 和 runtime 暴露面，`mms doctor` / `mms exposure` / `mms logs` 都是给这件事用的。

## 三个入口，什么时候用哪个

| | 怎么开 | 干什么 |
|---|---|---|
| **MMS Pilot** | `mms web --open` | 日常干活，以及绝大部分配置：开会话、加通道、拉模型、改能力开关、管工作文件夹、更新 |
| **`mms` 命令行** | `mms` 或 `mms claude` | 启动 Claude / Codex / OpenCode / Pi / agy 这些原生 CLI |
| **配置 Web UI**（已降级） | `mmf config web` | 只剩 Pilot 还没覆盖的部分：账号、偏好、Skill / MCP、迁移和需要人工确认的动作。教程见 [`docs/WEB_UI_QUICKSTART.md`](docs/WEB_UI_QUICKSTART.md) |

Pilot 保存通道和模型之后，终端读到的就是同一份，不需要再去配置页确认一遍。

Pilot 里跑会话用的 harness 目前是 **Pi**。Claude / Codex / OpenCode / agy 仍然只能从命令行启动，还没进 Pilot 的统一会话视图。

常用命令：

```bash
mms web --open              # 打开 Pilot
mms                         # 交互式启动器
mms claude                  # 启动 Claude
mms codex                   # 启动 Codex
mms opencode --profile review
mms --provider <id> codex   # 指定通道
mms --account <id> claude   # 指定账号
mms --export codex          # 只导出环境变量，不启动
mms doctor full             # 体检
mms logs                    # 看日志
```

## Pilot 现在能做什么

会话方面：连续对话、恢复、停止、分叉、归档、导出，会话内换模型和通道且保留上下文，工作中追加的消息进队列，刷新和进程重启之后接着原来的上下文。

看得见过程：流式回复、上游真给的 Thinking、工具参数和结果、工具图片、原生的确认/选择/输入交互。上下文占比、Token 和缓存都在同一处。

文件：应用内逐级浏览目录、文本 / Markdown / 图片预览、Git 文本差异、`@` 引用文件。引用本地文件是直接用原路径，不复制不上传，没有大小门槛。

模型能力：按模型设置默认 effort、上下文长度和能不能读图，每一项都标明当前值来自哪里，跟目录不一致时可以一键填回。**识图这个开关是全局真值**：在这里给某个模型打开，它在任何 harness 里都自己读图；关掉就由别的模型中转。

手机或另一台电脑访问：显式打开之后给你地址和二维码，带 token。默认只监听本机。

完整清单和边界见 [`docs/mms-web/FEATURES.md`](docs/mms-web/FEATURES.md)。

**几条边界值得先知道**：只监听本机地址，没有远程多用户认证；配置隔离不是文件系统 sandbox；只读规划模式是在工具调用层拦截，不是操作系统级 sandbox；文件浏览和 diff 是只读的，没有编辑、提交或发布按钮。想给别人用，让对方在自己机器上装一份、用自己的模型服务。

## 两条发布线

从 2026-09-16 起，`main` 和 `dev` 是两条**长期并行**的线，不是"稳定分支和开发分支"。

| 线 | 版本 | 安装参数 | 适合谁 | 里面有什么 |
|---|---|---|---|---|
| 稳定线 | 4.23.x | `--channel stable`（默认） | 把它当日常工具用的人 | 已经坐稳的功能，只收修复和验证过的能力 |
| 预览线 | 5.1.x | `--channel dev` | 愿意试新东西、能接受波动的人 | 稳定线的**全部内容**，外加还在打磨的 Bot 工作台 |

`main` 上的每一处改动都默认进 `dev`，所以预览线永远是稳定线的超集，不存在"用了 5.x 就丢掉 4.x 的某个修复"。

**5.x 多出来的是 Bot 工作台**：你交代一个目标，一个有名字、有记忆、能定时唤醒、能分发协作、能顺手问几家模型意见的执行者去做完再回报你。Pilot 普通会话是"我现在自己做这件事"，Bot 是"我交代目标，你去做完"。详见 [`docs/mms-web/BOTS.md`](https://github.com/CtriXin/multi-model-switch/blob/dev/docs/mms-web/BOTS.md)（这份文档只在 `dev` 分支上）。

两条线在同一台机器上**不能共存**，装了一条就是那一条。换线重跑安装器带对应的 `--channel`；配置、通道和会话历史都在同一个 config root 里，换线不会清空它们。

> **注意一个方向性差异。** Pilot 的「版本与更新」里可以选 4.x 稳定版或 5.x 预览版两个通道。4.x → 5.x 在 Pilot 里点几下就能完成；但**已经装了 5.x 之后，只把通道选回 stable 不会降回 4.x**——Pilot 只会推荐比当前更高的版本。要回稳定线必须重跑安装器带 `--channel stable`，配置和历史保留。

## 配置放在哪

唯一的 config root 是 `~/.config/mms-next`。`mms` / `mmf` / `mmg` 和 Pilot 网页都落在它上面，所以一处改动在命令行和网页都生效。legacy `~/.config/mms` 已经退出配置来源，**不再被任何入口读取**，那里只剩 `*-gateway/` 这类会话运行时目录。

配置的写入只有一条路径：**写入预览 DB + 发布**。本地修改优先走 Registry v2，TUI / `mms config` / WebUI 先创建 DB candidate，审阅通过后发布成 `generated/model-registry.latest-approved.json`，它引用的 generated Profile 就是 runtime boundary。终端和 Pilot 读的是同一份发布结果，所以两边看到的通道、模型和能力一致。没有第二条绕开审阅的写入路径。

其它位置：安装目录在 `~/.mms`（含自带的 `.venv`）；Pilot 的会话、更新缓存和成果在 `~/.local/share/mms-web`；安装元数据（版本、通道、界面语言）记在 `~/.config/mms-next/version.json`。

## 出问题先看哪

```bash
mms doctor            # 体检：Python、CLI 发现、配置根、通道
mms models            # 当前能看到哪些模型
mms routes            # 路由解析结果
mms exposure          # runtime 暴露面
mms logs              # 日志
mms test --provider <provider-id> --cli claude    # 真实冒烟
```

几个常见症状：

**"模型列表拉不到，但我确定这个模型能用"** —— 用手填补到当前通道。远端 `/models` 不返回不代表模型不可用；隐藏、能力标记和 fallback 都是本地 policy，不该因为一次拉取缺失就删掉。

**"Thinking 到底是哪个勾"** —— 模型表里的 `reason` / reasoning 是**能力 metadata**，不是启动开关。真正启动时开不开，取决于 provider/model 的 compatibility profile（`thinking.supported` / `default_enabled`）、effort 配置和 runtime 的 `thinking_mode`。

**"某个模型在一条路径上 403，另一条正常"** —— 正常。`Anthropic /v1/messages` 和 `OpenAI /v1/chat/completions` 不是等价传输，有的 provider 只在 Claude 兼容路径上开放某些模型。MMS 在路由支持时默认优先走 `/v1/messages`。

**"点了检查更新没反应"** —— 看 `~/.local/share/mms-web/updates/check.json` 在不在。

**Windows 上遇到自己机器特有的问题**：可以在 Pilot 里让本地 AI 先做诊断，然后按 [`docs/mms-web/WINDOWS-CONTRIBUTING.md`](docs/mms-web/WINDOWS-CONTRIBUTING.md) 提报告或 PR。**不要**把 API Key、`credentials.sh`、整个配置目录或没脱敏的会话发出来。

## 安全上的几条底线

- 真实 `HOME` 和全局 OAuth 状态是保护面，不是 fallback 池。provider / account 失败时在当前 runtime 里 fail closed，不静默切到另一个全局账号。
- 路由支持时 Claude 语义优先走 `Anthropic /v1/messages`；`chat/completions` 是 fallback，不是等价默认值。
- 写配置之前先出预览、diff、备份和审阅记录。
- legacy `~/.config/mms/**`（尤其 Claude 相关字段）仍然是 human-gated，Pilot 不写它。

## 文档

- [`docs/AI-ONBOARDING.md`](docs/AI-ONBOARDING.md) —— **给 AI / 新接手的人**：项目全貌、代码地图、门禁、踩过的坑
- [`docs/mms-web/GETTING-STARTED.md`](docs/mms-web/GETTING-STARTED.md) —— Pilot 安装与使用
- [`docs/mms-web/FEATURES.md`](docs/mms-web/FEATURES.md) —— Pilot 功能与边界
- [`docs/mms-web/CHANGELOG.md`](docs/mms-web/CHANGELOG.md) —— 每个版本实际改了什么
- [`docs/mms-web/API.md`](docs/mms-web/API.md) —— Pilot 本地 API v1
- [`docs/install/WINDOWS.md`](docs/install/WINDOWS.md) —— Windows Native Preview 完整流程
- [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md) —— 通道契约与安装参数
- [`docs/BUNDLED_PACKS.md`](docs/BUNDLED_PACKS.md) —— 内建能力包，以及已退休的安装项
- [`docs/MMS_USER_PREFERENCES.md`](docs/MMS_USER_PREFERENCES.md) —— `preferences.toml` 能写什么
- [`docs/MODEL_CONFIG_CONTRACT.md`](docs/MODEL_CONFIG_CONTRACT.md) · [`docs/AGENT_GUARDRAILS.md`](docs/AGENT_GUARDRAILS.md) —— 配置契约与高风险面约束
- [`docs/MAINTAINERS.md`](docs/MAINTAINERS.md) —— 维护者开发入口、worktree 流程、发版清单
