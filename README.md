# Multi-Model Switch（MMS）

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[English](./README.en.md) · [中文镜像（旧链接）](./README.zh-CN.md)

**MMS 是一个 launcher-first 的本地 AI coding 运行时管理器。** 它把 `claude`、`codex`、`opencode`、`agy` 放到同一个入口里, 在启动前想清楚"用哪个模型、走哪条通道、花谁的额度", 而不是让某次失败悄悄掉回你的真实全局账号。

> **你是 AI, 或者刚接手这个项目?** 先读 [`docs/AI-ONBOARDING.md`](docs/AI-ONBOARDING.md)。
> 那份文档是这个仓库的交接书: 产品三层结构、`main` 4.x 与 `dev` 5.x 两条发布线以及怎么判断改动属于哪条、代码地图、门禁怎么跑, 以及这个项目已经踩过的十类坑。**不要跳过第八节** —— 那些坑每一条都已经真实发生过至少一次。

---

## 30 秒版（TL;DR）

| 你想知道的 | 看这里 |
|---|---|
| 这是什么 / 解决什么问题 | [§1 这是什么](#1-这是什么) |
| 我现在该装哪个版本 | [§2 装哪个版本](#2-装哪个版本-30-秒决策) |
| 怎么装、怎么开始用 | [§3 5 分钟上手](#3-5-分钟上手) |
| Pilot / Bot 工作台能做什么 | [§4 Pilot 现在能做什么](#4-pilot-现在能做什么) / [§5 Bot 工作台（仅 5.x）](#5-bot-工作台仅-5x) |
| 命令找不到 | [§6 命令参考](#6-命令参考)（折叠） |
| 出问题 | [§9 出问题先看哪](#9-出问题先看哪) |
| 常见疑问 | [§10 FAQ](#10-faq)（折叠, 8+ 条） |
| 安全 / 边界 | [§11 安全底线](#11-安全底线) |
| 完整文档地图 | [§13 文档地图](#13-文档地图) |

如果你只有 30 秒: 装 stable（`bash install.sh`）→ 浏览器打开 → 加第一个通道 → 跑起来。如果你不知道 stable 是什么意思, 看 [§2 装哪个版本](#2-装哪个版本-30-秒决策)。

---

## 目录

- [0. 30 秒版（TL;DR）](#30-秒版tldr)
- [1. 这是什么](#1-这是什么)
- [2. 装哪个版本（30 秒决策）](#2-装哪个版本-30-秒决策)
- [3. 5 分钟上手](#3-5-分钟上手)
- [4. Pilot 现在能做什么](#4-pilot-现在能做什么)
- [5. Bot 工作台（仅 5.x）](#5-bot-工作台仅-5x)
- [6. 命令参考](#6-命令参考)
- [7. 内建能力包](#7-内建能力包)
- [8. 配置放在哪](#8-配置放在哪)
- [9. 出问题先看哪](#9-出问题先看哪)
- [10. FAQ](#10-faq)
- [11. 安全底线](#11-安全底线)
- [12. 版本历史（v3 → v4 → v5 关键节点）](#12-版本历史v3--v4--v5-关键节点)
- [13. 文档地图](#13-文档地图)
- [14. Release checklist（维护者）](#14-release-checklist维护者)

---

## 1. 这是什么

### 1.1 一句话

把多个 AI coding CLI（Claude Code / Codex / OpenCode / Pi / agy）放一个入口, 在启动前选模型、通道、账号、能力包和隔离 HOME。

### 1.2 三层架构

| 层 | 是什么 | 入口 |
|---|---|---|
| **MMS launcher** | 启动 CLI 之前的"想清楚"层: 模型、通道、账号、能力包、隔离 HOME | `mms`（TUI）、`mms claude`、`mms codex`... |
| **MMS Pilot** | launcher 的本地 Web 客户端。开会话、加通道、拉模型、改能力、管工作文件夹都在这里。会话由本机 Pi 执行 | `mms web --open` |
| **MMS Bot**（5.x 才有） | Pilot 的执行层升级。一个有身份、有记忆、能定时唤醒、能分发协作的执行者去完成你交代的目标 | Pilot 里的 Bot 工作台 |

一句话区分 Pilot 会话和 Bot: **Pilot 是"我现在自己做这件事", Bot 是"我交代目标, 你去做完回报我"**。

### 1.3 跟"裸装 claude/codex"的区别

如果你同时使用 Claude Code、Codex、OpenCode、New API / OpenAI-compatible 平台、国产模型和多个 provider, MMS 负责把"启动前应该想清楚的事"集中起来:

- **一个入口启动多个 CLI**: `mms` 进入 TUI, 或直接 `mms claude` / `mms codex` / `mms opencode`。
- **一个地方管理模型来源**: provider、account、route、fallback、thinking、vision、cache-sensitive transport 都在启动前可见。
- **隔离但可恢复**: Claude/Codex session 使用 MMS 管理的 HOME / config seed, 减少污染真实全局配置, 同时保留 resume。
- **按 session 注入能力包**: CodeGraph、TOON、grill-me、Web automation bundle 等能力默认是 session-local, 不改你的全局 hook。
- **诊断优先**: 在怀疑模型之前, 先看 route、协议、cache、API Key、请求路径和 runtime exposure。

`chat`、`discuss` 和高上下文 helper 现在只作为 maintenance-only 表面; 主线是把本地 coding CLI 启动、路由、隔离和诊断做好。

---

## 2. 装哪个版本（30 秒决策）

> **TL;DR**: 默认装 **stable（4.23.x）**。想试 Bot 工作台装 **dev（5.1.x）**。Canary 已停更, 不要用。

| 你是谁 | 安装命令 | 装完之后 |
|---|---|---|
| 普通用户 / 把它当工具用的人 | `bash install.sh`（默认 stable, 4.23.x） | 长期不动 |
| 想试 Bot 工作台、能接受小幅波动 | `bash install.sh --channel dev`（5.1.x） | 见下面"升 5.x 之后" |
| 维护者 / 贡献者 | 两条线都要装 | 各自独立 worktree |

<details>
<summary><b>稳定线 vs 预览线: 长期并行的两条线（点开看完整说明）</b></summary>

从 2026-09-16 起, `main` 和 `dev` 是**两条长期并行**的发布线, 不是"稳定分支和开发分支"。

| 线 | 分支 | 版本 | 安装参数 | 里面有什么 |
|---|---|---|---|---|
| 稳定线 | `main` | 4.23.x | `--channel stable`（默认） | 已经坐稳的功能, 只收修复和验证过的能力 |
| 预览线 | `dev` | 5.1.x | `--channel dev` | 稳定线的**全部内容**, 外加 Bot 工作台 |
| Canary | `canary` | 停更 | `--channel canary` | 2026-06 起停更的旧实验线, 不要用它承载任何东西 |

`main` 上的每一处改动都默认进 `dev`, 所以预览线永远是稳定线的超集, 不存在"装了 5.x 就丢掉 4.x 的某个修复"。

**两条线在同一台机器上不能共存。** 换线要重跑安装器带对应 `--channel`; 配置、通道和会话历史都在同一个 config root 里, 换线不清空它们。

历史背景: v3.x 时代是三通道（Stable 3.4.z / Dev 3.5.z / Canary 3.6.z）。v4.0.0 重新规划为"双线 + Pilot", Canary 已在 2026-06 停更。详见 [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md)。

</details>

> **⚠️ 警告: 升 5.x 后不能从 Pilot 里点回 4.x**
>
> Pilot 的"版本与更新"里可以选 4.x 稳定版或 5.x 预览版两个通道。4.x → 5.x 在 Pilot 里点几下就能完成; 但**已经装了 5.x 之后, 只把通道选回 stable 不会降回 4.x** —— Pilot 只会推荐比当前更高的版本。要回稳定线必须重跑安装器带 `--channel stable`, 配置和历史保留。
>
> 历史原因（`mms_web/updates.py`）: `available = remote > current`, `4.23.x < 5.1.x`, 所以 4.x 永远不会被当成"可用更新"。这是设计, 不是 bug。任何文案都不许说"随时可逆"。

---

## 3. 5 分钟上手

### 3.1 安装（一行命令）

**macOS / Linux**:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```

装完会问一句要不要打开 Pilot。回车即可, 浏览器自动弹出, 服务在后台运行, 安装进程退出。

**Windows**: 步骤不一样（Native Preview, 从零开始 6 步）, 完整流程见 [`docs/install/WINDOWS.md`](docs/install/WINDOWS.md)。

<details>
<summary><b>其他安装方式（dev / canary / pin / 静默）</b></summary>

```bash
# 需要最新修复 / 想试 Bot 工作台
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel dev

# 固定到某个 release（CI、家里工作机同步）
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref v4.21.14

# CI / 脚本: 不打开 Web 端, 不改 shell 配置
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --no-launch-web --no-shell-rc

# 装完直接打开, 不询问
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --launch-web

# 精确控制安装哪些 CLI（默认会自动补 claude/codex/opencode）
bash install.sh --install-cli claude,codex
```

</details>

### 3.2 安装器默认会做什么

- 安装到 `~/.mms`, 并把 `mms`、`mmf`、`mmslogs` 链接到 `~/.local/bin`。
- 创建 `~/.mms/.venv`; 系统 Python 不够新时用 MMS-managed Python 兜底。
- 发现 PATH、Homebrew、NVM 下的 `claude` / `codex` / `opencode` / `agy`; 缺失的自动补, 已装的保持不动。**`pi` 是必装项**（Pilot 依赖它）。
- 安装内建 session assets, **不**静默改写真实 provider/account 配置。
- 写入 `~/.config/mms-next/version.json`, 记录安装 ref、channel 和界面语言。

### 3.3 安装后立刻跑一遍

```bash
mms doctor            # 体检: Python、CLI 发现、配置根、通道
mms models            # 当前能看到哪些模型
mms routes            # 路由解析结果
mms exposure          # runtime 暴露面
mms logs              # 日志
mms test --provider <id> --cli claude    # 真实冒烟
mms test --provider <id> --cli codex
```

### 3.4 第一次打开做什么

1. Pilot 引导你加第一个通道: 填服务地址和 API Key。
2. 点拉取模型。拉不到但你确认能用的, 手填补上。
3. 勾选你真的会用的模型, 保存前会给你一份脱敏的预览。
4. 回到主界面, 选个文件夹、选个模型, 开始说话。

跑起来之后, 值得顺手做的两件事: 在模型页把每个模型的**上下文长度**和**能不能读图**核对一遍（值来自哪里界面上有标注, 和目录不一致时有一键填回）, 以及在设置里挑个主题和字体。

### 3.5 三个入口, 什么时候用哪个

| 入口 | 怎么开 | 用来做什么 |
|---|---|---|
| **MMS Pilot** | `mms web --open` | 日常干活 + 绝大部分配置: 开会话、加通道、拉模型、改能力开关、管工作文件夹、更新 |
| **`mms` 命令行** | `mms` 或 `mms claude` | 启动 Claude / Codex / OpenCode / Pi / agy 这些原生 CLI |
| **配置 Web UI**（已降级） | `mmf config web` | 只剩 Pilot 还没覆盖的部分: 账号、偏好、Skill / MCP、迁移和需要人工确认的动作。教程见 [`docs/WEB_UI_QUICKSTART.md`](docs/WEB_UI_QUICKSTART.md) |

Pilot 保存通道和模型之后, 终端读到的就是同一份, 不需要再去配置页确认一遍。

**Pilot 当前唯一的 harness 是 Pi。** Claude / Codex / OpenCode / agy 仍然只能从命令行启动, 还没进 Pilot 的统一会话视图。

---

## 4. Pilot 现在能做什么

> **TL;DR**: Pilot 是一个本地 Web 工作台, 装好之后日常都在这里。会话、模型、文件、配置、更新全在一个页面里。

### 4.1 会话

连续对话、恢复、停止、分叉、归档、导出; 会话内切换模型与通道且保留上下文; 工作中追加消息进队列, 刷新和进程重启后接着原来的上下文。

### 4.2 模型与通道

按模型设置默认 effort、上下文长度和能否读图, 每一项都标明当前值来自哪里, 与目录不一致时可以一键填回目录值。**识图这个开关是全局真值**: 在这里给某个模型打开, 它在任何 harness 里都自己读图; 关掉就由别的模型中转。

### 4.3 文件与资料

应用内逐级浏览目录、文本 / Markdown / 图片预览、Git 文本 diff、`@` 引用文件。引用本地文件是直接用原路径, 不复制不上传, 没有大小门槛。`@` 引用文件夹里的内容, 折叠卡跟消息一起送进 Pi。

<details>
<summary><b>v4.18.0 起: 文件夹拖入定位</b></summary>

直接把文件夹拖到侧栏, 自动定位到对应 workspace 并展开。之前的版本只能从文件系统选择器一层层点, 拖入会落到错的目录。

</details>

### 4.4 终端会话进 Pilot（v4.12.0 起）

用 `mms` / `mmf` 在终端里开的 Pi 会话, 会以**只读**方式出现在 Pilot 的会话列表里; 选择「接入并继续」会把 transcript 复制到新的 runtime 后继续对话, 终端里的原文件一个字节不动。

如果不想在 Pilot 里看到, 在设置「使用」里关闭即可。

### 4.5 `/btw` 旁问（v4.22.0 起）

主任务继续跑的同时, 开一个**旁问**窗口。旁问读主上下文, 但 Q&A **不会**进入主任务的上下文 —— 适合"主线在干一件事, 我突然想问个不相关的事"。

```text
主任务: "帮我重构这个模块"
> /btw 9.11 和 9.9 哪个版本更适合 Claude?
[主任务继续, 旁问窗口弹出来, 问完关闭]
```

详见 [`docs/mms-web/HANDOFF-BTW.md`](docs/mms-web/HANDOFF-BTW.md)。v4.22.4 之后, 旁问卡的折叠状态会持久化, 不会每次刷新都展开。

### 4.6 任务模板（v4.10.0 起）

目标、示例、变量、Skills 与模型要求; 填写后载入草稿, 缺条件有明确提示, 发送前再次核验。三份即用模板: 整理产品需求、检查项目改动、分析一份数据。

分享出去之前, 自动清理已知凭据和本地路径, 并显示最终预览。

### 4.7 Pilot 服务管理命令（v4.14.0 起）

本机 Pilot 跑在后台, 装好后用这些命令管它:

```bash
mms web status         # 列出本机所有 Pilot（地址、版本、pid、state-root、config-root、来源目录）
mms web url            # 只打印当前实例地址
mms web start          # 已在跑就返回地址, 没跑就后台启动并打印地址（日志在 <state-root>/logs/mms-web.log）
mms web stop           # 只发 SIGTERM
mms web stop --all     # 停本机全部 Pilot
mms web restart        # 先停再起
mms web --open         # 前台启动并打开浏览器
```

`mmf web ...` 同样可用。

### 4.8 手机 / 远程访问

显式打开"让手机或另一台电脑访问"开关后, 给出地址和二维码, 带 token。默认只监听本机, 开关关了**不会清空 token**（v4.13.1 安全修复, 之前的版本关开关等于把门禁也关了）。

### 4.9 Pilot 的边界

- 只监听本机地址（开了远程访问除外）, 没有远程多用户认证。
- 配置隔离不等于文件系统 sandbox。
- 只读规划模式是在工具调用层拦截, 不是操作系统级 sandbox。
- 文件浏览和 diff 只读, 没有编辑、提交、发布按钮。
- Thinking 只展示上游真给的内容, 模型不给就不造。
- 用量来自 Pi, 不是供应商账单。

---

## 5. Bot 工作台（仅 5.x）

> **TL;DR**: Bot 工作台是 5.x 相对 4.x 的**唯一**增量。你交代目标, Bot 去做完回报你, 而不是你自己在 Pilot 里点点点。8 个对象: **Bot / Task / Plan / Fleet / Memory / Schedule / Mailbox / 浏览器能力**。详尽语义在 [`docs/mms-web/BOTS.md`](https://github.com/CtriXin/multi-model-switch/blob/dev/docs/mms-web/BOTS.md)（只在 `dev` 分支上）。

<details>
<summary><b>Bot 工作台 8 个对象（点开看完整说明）</b></summary>

**Bot** —— 有独立身份、头像、名字（用户自己起）、职责描述、默认模型和**独立持久记忆**的执行者。所有 Bot 默认用共享电脑的全局 `default` workspace, 不要求用户管目录。聊天窗口按 Bot 聚合历史任务, 是连续对话感, 不是控制台 Board。

**Task** —— 一次执行。状态 `queued` / `starting` / `running` / `waiting` / `completed` / `failed` / `interrupted` / `cancelled`。主聊天只呈现用户消息、Bot 回复、成果和等待提示; `bash`、`exit`、内部 `list`/`wait` 这类 CLI 诊断留在事件数据里不进主聊天。**取消要等 Pi 确认, 15 秒不停才结束该 Bot 自有进程, 只有实际停止才记 cancelled**（v5.0.3 修复了 "force-ended tool 优先于最新 turn" 的误判）。

**Plan（计划层）** —— 计划从提示词里拿出来, 变成落库、可见、可执行的对象。普通 `direct-first` 请求直接进持久会话, 不起 planner; 只有明确协作意图或显式 `plan-approve` 才调一次短 planner（20 秒预算）。计划有完整状态机（`proposed`/`auto`/`approved` → `running` → `merging` → `done`）, 步骤级 `pending → ready → running → done|failed|skipped`, 每步带 `onFailure`（`retry`/`skip`/`abort`）。分发链最多五层, 同一条链不能再次调用同一个 Bot。

**Fleet（同一个 Bot 的多模型评审）** —— 关键定位: **多模型评审是同一个 Bot 换几颗脑子, 不是让用户再雇一排永久同事。** 默认开、强度"听意见"、2 家便宜对照。Fleet worker 只能由 coordinator 内部创建, 是指定模型的一次性**只读** Pi session（只开 read/grep/find/ls, 禁用 skills、上下文文件加载）, 不改主 Bot 的模型/会话, 不把各家意见写进共享长期记忆。自动选择不足两家时走 direct 并**明确说明不是多方评审**; 显式选的家族或型号失效时停止并提示重选, **不换家族不换同名型号**（v5.0.5 修复了 Bot 复用 session 时 step model 被丢弃的 bug）。

**Memory（记忆）** —— 每个 Bot 独立, 在 `state_root/bots/memory/<botId>/memory.json`, 与 Pi 会话和 workspace 分开。最多 100 条事实 + 200 条任务摘要, 每条 2000 字。新任务按关键词检索相关内容注入, **当前用户指令优先, 记忆内容不增加权限**。整理阈值是软触发: Pi 回报的 context usage 到阈值后, 下一轮在安全 idle boundary 调 Pi 原生 `compact`。Pi 不回报 usage 时界面显示"未知", **不伪造硬上限**。

**Schedule（定时）** —— 独立实体, 不是 task 上的字段。带 `rule`（`once`/`interval`/`daily`/`weekly`）、必填 IANA `timezone`、单条 `enabled`、`overlapPolicy`（`skip`/`queue`）。到点**新建一个 task**, 所以每次运行有独立 transcript 和成果。几条容易做错的语义:
- 周期任务**不补课**: 停机错过超过一个周期就只把 `nextRunAt` 推到下一个未来时刻, 记 `lastSkip`, 不把积压全补跑; 恰好错过一次才立即补。
- `interval` 的下一次从**本该触发的时刻**算, 不被每次触发的延迟带偏。
- 「每天 9 点」在夏令时切换日仍是本地 9:00。
- **`once` 只有一次机会, 没跑就不消耗它**: 到点不能触发时这条 schedule 停在一旁（parked）, `nextRunAt` 保留那个过去的时间, 重新可用后的下一个 tick 补触发一次并在新 task 上写 system 消息说明是延后补触发。
- `wakeEnabled` 是 Bot 级总开关, 与单条 `enabled` 是两层, 任一 false 就不触发。

**Mailbox（Bot 间通信）** —— `dispatch` 用于有依赖的分工, `message`/`reply` 用于通知、澄清、追问, **不伪装成用户消息**。每条消息有 `queued`/`delivered`/`processed`/`waiting`/`failed` 回执; `reply` 只能回复发给当前 Bot 的消息; 连续自动往返超过 8 跳暂停, 避免 Bot 互相空转。

**浏览器能力** —— 由外部 `BrowserProvider` 提供, 不自研。macOS 装了 Ego 就交给 Ego; Windows/Linux 可由 Web Access 连用户明确授权的 Chrome/Edge CDP。Provider 不可用时显示明确的 capability unavailable, **不降级成一套自研的假浏览器**。

**明确不在范围**: 操作系统级 Computer Use、桌面窗口控制、通用 Connector 平台、云端 VM。

</details>

### 5.1 怎么开第一个 Bot

1. Pilot 里打开 Bot 工作台, 点新建 Bot, 起个名字和职责。
2. 选默认模型和 preset（preset 可以留空, 执行时解析当前可用默认 preset）。
3. 在对话窗口里交代目标, 或者写一个 Plan 让它分步做。
4. 想定时跑: 在 Bot 详情里加 Schedule, 选 `rule` 和时区。
5. 想让多个模型给意见: 直接说"走 Fleet"或者在设置里开启默认 Fleet。

---

## 6. 命令参考

<details>
<summary><b>完整命令参考（点开）</b></summary>

### 6.1 入口命令

```bash
mms web --open              # 打开 Pilot
mms web status              # 列出本机所有 Pilot
mms web start               # 后台启动 Pilot
mms web stop                # 停止当前 Pilot
mms web stop --all          # 停本机全部
mms web restart             # 先停再起

mms                         # 交互式启动器（TUI）
mms claude                  # 启动 Claude
mms codex                   # 启动 Codex
mms opencode                # 启动 OpenCode
mms opencode --profile review           # OpenCode 走 Review 预置
mms opencode --profile agent            # OpenCode 走 Agent 预置
mms --provider <id> codex   # 指定通道
mms --account <id> claude   # 指定账号
mms --export codex          # 只导出环境变量，不启动
mms --export claude --apply # 导出并应用到当前 shell
mms --export opencode
mms pi                      # 启动 Pi
mms agy                     # 启动 agy
```

### 6.2 本机命令矩阵（维护者）

```text
mms  -> public installed copy   # 只用于复现公开版本的问题
mmf  -> dev worktree            # 日常开发
mmg  -> canary worktree         # 已停更
```

由 `scripts/link_local_channel_commands.sh` 生成到 `~/.local/bin`。`mmd` / `mmm` 已退休（v4.13.0 撤销）, 这个脚本会删掉它写过的这两个包装器。普通用户不需要这些, 用安装器的 `--channel` 参数就行。

启动更新提醒默认只提醒、手动确认更新: `mmg` 每次启动检查, `mmf` 每日检查, `mms` 每日只提示 public installed copy。

### 6.3 诊断与配置

```bash
mms doctor            # 体检: Python、CLI 发现、配置根、通道
mms doctor full       # 更深体检
mms models            # 当前能看到哪些模型
mms routes            # 路由解析结果
mms exposure          # runtime 暴露面
mms logs              # 日志
mms config preferences.help    # preferences 配置帮助
mms test --provider <id> --cli claude    # 真实冒烟
mms test --provider <id> --cli codex

mmf config web        # 配置 Web UI（已降级）
mms web status --json # JSON 输出状态
```

### 6.4 升级与安装

```bash
bash install.sh                           # 升级（stable）
bash install.sh --channel dev             # 升级到 dev
bash install.sh --ref v4.21.14            # pin 到指定版本
bash install.sh --no-launch-web           # 不打开 Web
bash install.sh --no-shell-rc             # 不改 shell 配置
bash install.sh --install-cli claude,codex   # 精确控制安装哪些 CLI
bash install.sh --cleanup-retired-packs   # 清理已退休的 MMS 条目
bash install.sh --check                   # 仅检查, 不装
bash install.sh --dry-run                 # 仅打印计划, 不写文件
```

</details>

---

## 7. 内建能力包

MMS 的能力包默认是 **session-local**: 按会话注入, 不改你的全局 hook 和 skill 目录。

| Pack | 状态 | 用途 |
|---|---|---|
| CodeGraph | 内建 passive skill | 优先用 symbol graph 做代码定位、callers/callees、影响面分析 |
| TOON | 内建 | 压缩 agent-facing 的 JSON / status / handoff |
| grill-me | 内建 | 逐题澄清目标、约束和验收 |
| Weber（Web automation bundle） | 内建 | 只暴露 `weber` router; `web-access` 和 `agent-browser` 作为内部 backend |
| NSR | 显式 `/nsr` 手动循环 | 沿用原 task 推进; 不注册 Stop/compact hook, 不跨 session 续跑 |
| ECC / OMC | 可选 | Claude agent pack, 在启动确认页显式选择 |
| Figma / Pilot MCP | 检测到也默认关闭 | 需 `MMS_ENABLE_MCP_FIGMA=1` / `MMS_ENABLE_MCP_PILOT=1` 显式开启 |

**优先级**: 全局的赢。同名的全局 hook / skill 优先, MMS 的动态版本只在缺失时作为 fallback。`xmem` 是 global-only, MMS 不再 bundle / 安装 / 注入。

**已退役**: Caveman（压缩模式）、全局 token-saver、全局 TOON、RTK、BrainKeeper、Map auto-index、CodeGraph auto-index —— 这些以前是内建或可选安装, 现在全部下线。Caveman 的设置字段仍能读但被忽略。

**自动 hook 已退出默认路径**: NSR 的 Stop / compact hook、Map / CodeGraph auto-index 都已退休。旧 wrapper 保留为 no-op, 不读不删现有 marker。显式 `/nsr` 和 CLI 仍然可用。

完整包清单与清理计划见 [`docs/BUNDLED_PACKS.md`](docs/BUNDLED_PACKS.md)。

---

## 8. 配置放在哪

| 路径 | 是什么 |
|---|---|
| `~/.config/mms-next` | **唯一的 config root。** `mms` / `mmf` / `mmg` 和 Pilot 网页都落在它上面 |
| `~/.config/mms-next/version.json` | 安装元数据: `installed_version`、`install_channel`、`release_track*`、`installed_at`、`source`, 外加**用户偏好 `preferred_language`** |
| `~/.mms` | 安装目录（代码副本）, `~/.mms/.venv` 是它自己的 Python |
| `~/.local/share/mms-web` | Pilot 的 state root: 会话、更新缓存、Bot 数据、成果 |
| `<state>/updates/settings.json` | `channel` —— "我想检查哪条线" |
| `~/.config/mms` | **legacy, 已退出配置来源。** 不自动导入、不回退, 只剩 `*-gateway/` 这类运行时会话目录还在 |

**两条 channel 字段不要混**: `updates/settings.json` 的 `channel` 是"我想检查哪条线", `version.json` 的 `install_channel` 是"我实际装的是哪条线"。它们不是一回事。用户切到 preview、检查了、但没确认升级 —— 此时 channel 是 preview 而实际安装还是 stable, 这个状态是合法的。

**配置的写入只有一条路径**: 写入预览 DB + 发布。本地修改优先走 Registry v2, TUI / `mms config` / WebUI 先创建 DB candidate, 审阅通过后发布成 `generated/model-registry.latest-approved.json`, 它引用的 generated Profile 就是 runtime boundary。终端和 Pilot 读的是同一份发布结果。

`~/.config/mms/preferences.toml` 是用户偏好 allowlist 覆盖层, **agent 不能自动写真实文件**。可以读、解释、生成 TOML snippet 给用户, 写入走 human gate。

---

## 9. 出问题先看哪

```bash
mms doctor            # 第一步: 体检
mms models            # 模型列表是否正常
mms routes            # 路由解析
mms exposure          # runtime 暴露面
mms logs              # 看日志
```

<details>
<summary><b>几个常见症状的快速定位</b></summary>

**"模型列表拉不到, 但我确定这个模型能用"**
拉不到不等于不可用。用手填补到当前通道。远端 `/models` 不返回不代表模型不可用; 隐藏、能力标记和 fallback 都是本地 policy, 不该因为一次拉取缺失就删掉。

**"Thinking 到底是哪个勾"**
模型表里的 `reason` / reasoning 是**能力 metadata**, 不是启动开关。真正启动时开不开, 取决于 provider/model 的 compatibility profile（`thinking.supported` / `default_enabled`）、effort 配置和 runtime 的 `thinking_mode`。如果你在 Pilot 里看到一个存储档位, 但实际请求不带 thinking —— 检查这个模型在当前通道上是否真的支持该档位, 不要相信 UI。

**"某个模型在一条路径上 403, 另一条正常"**
正常。`Anthropic /v1/messages` 和 `OpenAI /v1/chat/completions` 不是等价传输, 有的 provider 只在 Claude 兼容路径上开放某些模型（如 `kimi-for-coding` 在 chat/completions 上 403 但 anthropic 路径正常）。MMS 在路由支持时默认优先走 `/v1/messages`。

**"点了检查更新没反应"**
看 `~/.local/share/mms-web/updates/check.json` 在不在, 有没有权限问题。

**"拖文件夹卡了几秒才到目标目录"**
v4.18.0 之前会卡, 因为全局写锁里跑文件搜索。v4.18.0+ 已修。

**"Pilot 启动的时候跑了几秒变卡"**
早期版本会在 launcher 启动热路径上跑同步网络 probe, 4 秒启动。现在是文件缓存 + 后台并行预热, 应该 < 1s。如果还慢, 跑 `mms doctor` 看哪条卡。

</details>

**Windows 上遇到自己机器特有的问题**: 可以在 Pilot 里让本地 AI 先诊断当前电脑; 诊断完再决定怎么提: 有 GitHub 账号就 fork 加 PR, 没有就生成脱敏的 Markdown 报告和 `.patch` 文件由维护者代提。详见 [`docs/mms-web/WINDOWS-CONTRIBUTING.md`](docs/mms-web/WINDOWS-CONTRIBUTING.md)。**不要**把 API Key、`credentials.sh`、整个配置目录或没脱敏的会话发出去。

---

## 10. FAQ

<details>
<summary><b>Q: 我只有一个 New API 平台, 模型很多, MMS 能用吗?</b></summary>

能。把 New API 当成 provider: 填 base URL / key / models endpoint, 然后让 Web UI 拉模型; 拉不到但真实可用的模型放到 extra/manual 模型。隐藏、能力标记和 fallback 属于本地 policy, 不应因为一次远端拉取缺失就盲删。

</details>

<details>
<summary><b>Q: Thinking 是 Web UI 里的哪个勾?</b></summary>

Web UI 模型表里的 `reason` / reasoning 是**模型能力 metadata**。真正启动时是否开 Thinking, 取决于 provider/model compatibility profile 的 `thinking.supported` / `default_enabled`、effort 配置, 以及 runtime 的 `thinking_mode`。

</details>

<details>
<summary><b>Q: Caveman 怎么没了? 以前启动页能选 Off/Light/Standard/Full</b></summary>

Caveman（压缩沟通模式）已全局下线, 不再随 MMS 安装、显示或注入, 旧配置字段会被忽略。如果你习惯轻量沟通, 用 TOON 把 agent-facing 的 JSON / status 压缩掉, 效果类似但不影响 provider 真实响应。

</details>

<details>
<summary><b>Q: 多台电脑应该装什么?</b></summary>

多台机器保持一致: 装同一条 channel, 必要时用 `--ref <commit-or-tag>` 固定到同一版本。Stable（默认）适合日常使用; Dev 适合想用 Bot 工作台的人。MMS 默认装在 `~/.mms`, **不要让两条 channel 同时覆盖同一个 `~/.mms`**; 真要并存, 用 VM、独立用户或明确安装前缀。

家里工作机想跟白天电脑对齐: 同样准备 worktree 后跑 `scripts/link_local_channel_commands.sh`, 三个命令会写到 `~/.local/bin`。普通用户不需要这个脚本。

</details>

<details>
<summary><b>Q: Pi 是必装吗?</b></summary>

对, **Pi 是必装的**（Pilot 依赖它）。安装器如果检测不到会拒绝继续, 而不是装一个残废版本。其它 CLI（claude / codex / opencode / agy）缺失会自动补装, 已装的保持不动。

Windows 上 Pi 要单独装: `npm.cmd install --global @earendil-works/pi-coding-agent`, 然后 `pi.cmd --version` 验证。

</details>

<details>
<summary><b>Q: 装了 5.x 之后想退回 4.x 怎么办?</b></summary>

在 Pilot 里选回 stable 不会降级。必须重跑安装器: `bash install.sh --channel stable`。配置和会话历史保留。

</details>

<details>
<summary><b>Q: 我装了 5.x, Bot 工作台在哪?</b></summary>

Pilot 主界面里点 Bot 工作台图标（在会话列表附近）。首次打开会让你建第一个 Bot。

</details>

<details>
<summary><b>Q: 远程访问开了之后, 关掉会不会把 token 也清掉?</b></summary>

不会（v4.13.1 修复）。`--listen all` 模式下, 关掉"让手机访问"开关不再清空 token 门禁。之前的版本关开关等于把门禁也关了, 网络上任何人不带 token 就能进。默认的回环模式和设置里打开的局域网模式不受影响。

</details>

<details>
<summary><b>Q: 我能让终端里 `mmf` 跑的会话同步到 Pilot 里吗?</b></summary>

v4.12.0 起可以。终端里 `mms` / `mmf` 开的 Pi 会话会以**只读**方式出现在 Pilot 会话列表里; 选"接入并继续"会把 transcript 复制到新 runtime 后继续对话, 终端里的原文件一个字节不动。如果不想在 Pilot 看到, 设置"使用"里关闭。

</details>

<details>
<summary><b>Q: 我启动的时候 TUI 跳了几秒才出来, 是不是坏了?</b></summary>

不是, 但也不应该是几秒。早期版本因为 launcher 启动热路径上跑同步网络 probe, 4 秒启动。现在是文件缓存 + 后台并行预热, < 1s。如果还慢, 跑 `mms doctor` 看哪条卡。CLI_NAMES 里塞了不再维护的 qwen/kimi 也会拖慢启动, 这种是已知性能坑, 修了。

</details>

<details>
<summary><b>Q: 任务模板里的 Skills 是什么? 我填了好像没生效</b></summary>

Skills 是按当前 workspace 搜索多选, `/skill:name` 补全, 内容随消息送入 Pi。Skills 加载/调用记录不保证模型遵循指引; 间接工具读取无法可靠归因时会明确无证据, 不伪造。

</details>

<details>
<summary><b>Q: 我跑了几次, Pilot 里的会话文件越来越大, 怎么清理?</b></summary>

归档 / 删除在会话菜单里; 归档的会话可以从归档列表恢复。`.pilot/attachments` 30 天无引用的导入副本会自动清理（v4.12.0 起）。Pilot 的 state root 在 `~/.local/share/mms-web`, 想完全清空可以停 Pilot 后删这个目录, 但**配置和 Bot 数据都在这里**, 不要只删一半。

</details>

---

## 11. 安全底线

- **真实 `HOME` 和全局 OAuth 状态是保护面, 不是 fallback 池。** provider / account 失败时在当前 runtime 里 fail closed, **不**静默切到另一个全局账号。
- 路由支持时 Claude 语义优先走 `Anthropic /v1/messages`; `OpenAI /v1/chat/completions` 是 fallback, 不是等价默认值。
- 写配置之前先出预览、diff、备份和审阅记录; **没有第二条绕开审阅的写入路径**。
- legacy `~/.config/mms/**`（尤其 Claude 相关字段）仍然是 human-gated, Pilot 不写它。
- 终端会话进 Pilot 是**只读**复制 transcript, 不会动终端里的原文件。
- 远程访问必须带 token, 关掉开关不会再清 token（v4.13.1）。

---

## 12. 版本历史（v3 → v4 → v5 关键节点）

<details>
<summary><b>v3.x → v4.0.0（2026-09-09）: Pilot 首版</b></summary>

MMS Pilot（本地 Web 客户端）的第一个大版本。从 v3 时代的"纯 TUI + 命令行"扩展为"launcher + Pilot + 内建 session assets"三层架构。4.x 期间快速迭代到 v4.23.x。

**v4.0.0 关键能力**: Pi RPC 会话、持续对话、恢复/停止/分支/归档/导出; 按模型合并通道选择、收藏、effort; 模型拉取与差异确认; Skills 与命令提示; 工作文件夹展开与本地文件原路径引用; 每轮过程折叠; 会话内切换模型/通道保留上下文。

</details>

<details>
<summary><b>v4.x 主要特性里程碑</b></summary>

| 版本 | 日期 | 关键能力 |
|---|---|---|
| v4.1.0 | 09-09 | 产物预览、选择、版本对比 |
| v4.2.0 | 09-09 | 项目材料与每消息来源记录 |
| v4.3.0 | 09-09 | 新手悬浮引导与功能帮助 |
| v4.4.0 | 09-09 | 设置弹窗、主题色板、字体 |
| v4.5.0 | 09-09 | 内联文件、项目搜索、能力审查 |
| v4.6.0 | 09-09 | 先连接服务再开始新手教程 |
| v4.7.x | 09-09 | 开箱即用的任务 skills 与文件夹引用 |
| v4.8.x | 09-09 | 快速模型选择 |
| v4.10.0 | 09-10 | 连接悬浮引导、任务模板 v2、3 份即用模板 |
| v4.11.0 | 09-10 | 统一配置根 `~/.config/mms-next`, 跨入口一致 |
| v4.12.0 | 09-10 | 终端会话进 Pilot、老机器自动收拢配置、K3 上下文窗口策略、Pilot 体验收口、LAN 写操作 |
| v4.13.0 | 09-10 | 唯一配置根（`mmd`/`mmm` 退休）、安装不再多起 Pilot |
| v4.13.1 | 09-11 | `--listen all` 下关闭开关不再清空 token |
| v4.14.0 | 09-11 | `mms web status/url/start/stop/restart` 服务管理 |
| v4.16.0 | 09-12 | CI pytest gate、k3-single-truth、ctrl-c cleanup |
| v4.17.0 | 09-12 | 视觉 relay, 完成 legacy root 退休 |
| v4.18.0 | 09-12 | 文件夹拖入定位 |
| v4.20.0 | 09-13 | **Windows Native Preview** |
| v4.21.x | 09-13~14 | Windows-only 修复线（v4.21.0 ~ v4.21.14） |
| v4.22.0 | 09-15 | **`/btw` 旁问**（终端 Pi 与 Pilot 都有）|
| v4.22.x | 09-16 | 远程访问保持登录、4.x↔5.x 通道切换门、blocked reasons、workspace 对话框 autofocus |
| v4.23.0~4 | 09-17~18 | T8g 配置/发现移出 mutation lock、T8h 5.x 装 stable 的通道 line 真相、Stable 焦点反馈、文件夹真路径回归 |

完整变更见 [`docs/mms-web/CHANGELOG.md`](docs/mms-web/CHANGELOG.md) 和每个版本的 `docs/mms-web/RELEASE-v*.md`。

</details>

<details>
<summary><b>v5.0.0（2026-09-16）: Bot 工作台</b></summary>

5.x 的**唯一**增量是 Bot 工作台。其它 4.x 的所有能力 5.x 都有。从 5.0.0 起到 5.1.7 的小版本:

| 版本 | 日期 | 关键能力 |
|---|---|---|
| v5.0.0 | 09-16 | Bot 工作台首发: T1~T4 UI + 协调器 + 计划层 |
| v5.0.1 | 09-16 | 设置滚动条遮挡与 Bot 交互/弹窗样式修复 |
| v5.0.2 | 09-16 | Bot T5/T6/T7 packets, grok TUI launcher |
| v5.0.3 | 09-17 | T7e 中途打断 turn 不再留空白 |
| v5.0.4 | 09-17 | T5a/T5b/T5c Bot 周期唤醒 |
| v5.0.5 | 09-17 | T5d plan step model 真正生效 |
| v5.0.6 | 09-17 | thinking-effort picker 移到 composer bar |
| v5.1.0 | 09-17 | 大批 verified stable fixes 进入 Preview; 侧栏 double-click rename |
| v5.1.1 | 09-17 | rename 对话框打开时焦点修复 |
| v5.1.2 | 09-17 | Fleet composer 可达 + rename 输入保留 |
| v5.1.3 | 09-17 | 侧栏版本号打开更新对话框 |
| v5.1.4 | 09-17 | 确认更新是独立步骤 |
| v5.1.5 | 09-17 | 移动端 popover 停靠底部 sheet |
| v5.1.6 | 09-17 | 交互修复 |
| v5.1.7 | 09-18 | T8i 实际接线回归与双线门禁 |

</details>

<details>
<summary><b>Canary 已停更, 不要用</b></summary>

Canary（`mmg` / `canary` 分支）2026-06 起停更。`mmg` 仍能在本机命令矩阵里用, 但对应的 worktree 路径可能已被清理（参见 `docs/RELEASE_CHANNELS.md` 的现状说明）。新功能不再进入这条线; 维护者也不再保留 canary 通道。

</details>

---

## 13. 文档地图

| 文档 | 什么时候用 | 备注 |
|---|---|---|
| [`docs/AI-ONBOARDING.md`](docs/AI-ONBOARDING.md) | **AI / 新接手项目的人**: 项目全貌、代码地图、门禁、踩过的坑 | 384 行, 含 10 条真实事故 |
| [`docs/mms-web/GETTING-STARTED.md`](docs/mms-web/GETTING-STARTED.md) | Pilot 安装与使用详细流程 | |
| [`docs/mms-web/FEATURES.md`](docs/mms-web/FEATURES.md) | Pilot 功能清单 | **顶部还写着"尚未公开发布", 已过期**, 实际功能清单本身基本可信 |
| [`docs/mms-web/CHANGELOG.md`](docs/mms-web/CHANGELOG.md) + [`docs/mms-web/RELEASE-v*.md`](docs/mms-web/) | 每个版本实际改了什么 | 比任何总结都准 |
| [`docs/mms-web/API.md`](docs/mms-web/API.md) | Pilot 本地 API v1 | |
| [`docs/mms-web/HANDOFF-BTW.md`](docs/mms-web/HANDOFF-BTW.md) | `/btw` 旁问的实现细节 | |
| [`docs/install/WINDOWS.md`](docs/install/WINDOWS.md) | Windows 从零开始的 6 步教程 | Native Preview |
| [`docs/mms-web/WINDOWS-CONTRIBUTING.md`](docs/mms-web/WINDOWS-CONTRIBUTING.md) | Windows 用户机器特有问题的报告与贡献流程 | |
| [`docs/WEB_UI_QUICKSTART.md`](docs/WEB_UI_QUICKSTART.md) | 配置 Web UI 教程 | |
| [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md) | 通道契约与安装参数 | **版本轨道表 `3.4/3.5/3.6` 已过期**, 通道定义和安装命令仍有效 |
| [`docs/BUNDLED_PACKS.md`](docs/BUNDLED_PACKS.md) | 内建能力包与已退休的安装项 | |
| [`docs/MMS_USER_PREFERENCES.md`](docs/MMS_USER_PREFERENCES.md) | `preferences.toml` 能写什么 | |
| [`docs/MODEL_CONFIG_CONTRACT.md`](docs/MODEL_CONFIG_CONTRACT.md) | 配置契约（model-routes/lineup/profile/policy） | |
| [`docs/AGENT_GUARDRAILS.md`](docs/AGENT_GUARDRAILS.md) | 高风险面的详细约束 | **AI 必读** |
| [`docs/MAINTAINERS.md`](docs/MAINTAINERS.md) | 维护者开发入口、worktree 流程、发版清单 | 普通用户不用看 |
| [`docs/mms-web/BOTS.md`](https://github.com/CtriXin/multi-model-switch/blob/dev/docs/mms-web/BOTS.md) | Bot 工作台详细语义 | **只在 `dev` 分支上**, 5.x 用户必读 |
| [`docs/mms-web/bot-work/`](docs/mms-web/bot-work/) | Bot 工作台的工作包（T1~T8i） | |
| [`docs/legacy/`](docs/legacy/) | 历史追溯 | |

**写代码前请核对**: 任何文档里的版本号、分支关系和"当前状态", 都以 `mms_version.py`、`git log` 和最近的 `RELEASE-v*.md` 为准。

---

## 14. Release checklist（维护者）

<details>
<summary><b>发版流程（点开）</b></summary>

1. 从 `dev` 挑选已验证变更进入 Stable 候选; 同步窗口结束后 `main` 本身就是 Stable/default。
2. 运行 `bash install.sh --check`、`mmf config check --json`、关键 launcher smoke、Web UI save-plan smoke。
3. 更新本 README 的版本历史节（§12）和对应 `docs/mms-web/RELEASE-v*.md`。
4. 更新版本号: **一个合并的 PR = 一个 patch 版本**, 纯文档包不 bump。**作者不碰版本文件**, 合并方在合并时盖版本号。release note 和 bump 放在一个单独的 commit 里, 别混进对方的改动, 保住对方的 authorship。
5. 打 tag, 推送 GitHub Release: `gh release create v<版本> --verify-tag --notes-file docs/mms-web/RELEASE-v<版本>.md --latest`（4.x）/`--prerelease`（5.x）。
6. 对家里工作机这类同步使用场景, 记录推荐 pinned commit。

详细流程见 [`docs/MAINTAINERS.md`](docs/MAINTAINERS.md) 的"版本号与发版"节。

</details>

---

## License

Apache-2.0
