# Multi-Model Switch (MMS)

[English README](./README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 一个 launcher-first 的本地 AI Coding CLI 运行时管理器：用一个入口选择模型、provider、session 能力包和隔离的 Claude/Codex HOME，同时避免把真实全局账号状态当成 fallback 池。

![MMS 启动器树结构](docs/images/mms-launcher-tree-cn.svg)

## MMS 是什么

MMS 不是新的 chat 客户端。它是 `claude`、`codex`、`qwen`、`kimi`、`gemini` 等本地 AI coding CLI 前面的控制面。

它解决这些问题：

- 用一个 TUI 或命令启动不同 CLI
- 显式选择 provider、OAuth/account profile 和模型
- 让 Claude/Codex 的 session 隔离且可 resume
- 在兼容模型源上做 bridge，同时保留协议语义
- 按 session 注入 skills/hooks，而不是污染全局配置
- 在怀疑模型前，先诊断 provider、route、cache 和实际暴露的 runtime state

## 当前版本

最新 release：`v1.20.0`

这一代的重点：

- provider profiles 覆盖 OpenAI、Qwen/DashScope、MiMo、MiniMax、DeepSeek、Kimi Code、GLM/Z.ai
- bridge / launcher / chat / discuss / router 共享 profile-driven auth/body/thinking/effort patch
- Claude 通过 `.claude/projects` 恢复项目级 resume
- Codex 在隔离的 MMS-managed launch 之间做 bounded resume write-back
- 启动确认页按 provider profile 显示 Thinking/Effort 与默认值
- OMC/ECC Claude agent pack 变成互斥选择
- session surface 覆盖 `token-saver`、`TOON`、`web-access`、`weber`、`agent-browser`、`Pilot`、`auto-github-contributor`

## 安装 / 升级

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s --
```

默认行为：

- 安装最新 semver tag
- 在 `~/.mms` 创建隔离 MMS runtime
- 把 `mms` 和 `ccs` 链接到 `~/.local/bin`
- 安装可选包或缺失 CLI 前会询问
- 不会静默改写真实 provider/account 配置

安装时指定 UI 语言：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --lang zh
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --lang en
```

需要固定版本时，直接 pin release tag：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/v1.20.0/install.sh | bash -s --
```

安装后自检：

```bash
bash install.sh --check
mms doctor
mms test --provider <id> --cli claude
mms test --provider <id> --cli codex
```

## 快速使用

进入交互式启动器：

```bash
mms
```

直接启动某个 CLI：

```bash
mms claude
mms codex
mms --provider <provider-id> codex
mms --account <account-id> claude
```

只导出环境变量，不启动 CLI：

```bash
mms --export codex
mms --export claude --apply
```

看 route 和健康状态：

```bash
mms models
mms routes
mms doctor
mms test --provider <id> --cli claude
mms exposure
mms logs
```

## 心智模型

```text
MMS
├── 入口层
│   ├── mms TUI
│   ├── mms claude / mms codex
│   └── export / presets
├── 决策层
│   ├── provider profiles
│   ├── role + priority routing
│   └── doctor / test / trace diagnostics
├── 运行时隔离
│   ├── Claude: session HOME + .claude/projects resume
│   ├── Codex: bounded .codex seed + write-back
│   └── bridge: 需要时启动本地协议适配
└── Session 能力包
    ├── token-saver / TOON
    ├── web-access / weber / agent-browser
    └── Caveman / OMC / ECC / Pilot
```

图的源文件：

- `docs/images/mms-launcher-tree.mmd`
- `docs/images/mms-launcher-tree-outline.md`
- `docs/images/mms-launcher-tree.html`

## 运行时安全原则

MMS 的默认策略是：在当前选择的 runtime 内 fail closed。

- 真实 `HOME` 和全局 OAuth 状态是保护面，不是 fallback 池。
- provider/account 失败时，不应静默切到另一个全局账号。
- Claude 语义在 route 支持时优先走 `Anthropic /v1/messages`。
- `OpenAI /v1/chat/completions` 是 fallback transport，不是等价默认值。
- session pack 注入到隔离 session，不是全局默认 hook。
- resume 数据有边界、有 scope，避免 startup 膨胀和账号串线。

进一步文档：

- [Provider profiles](./docs/PROVIDER_PROFILES.md)
- [Claude cache / protocol runbook](./docs/SERVER_CLAUDE_CACHE_RUNBOOK.md)
- [Agent guardrails](./docs/AGENT_GUARDRAILS.md)
- [CLI/provider compatibility QA](./docs/CLI_PROVIDER_COMPAT_QA.md)

## Provider Profiles

厂商差异应该沉淀成数据，而不是继续在 launcher 里堆分支。

`config/provider-profiles.json` 记录：

- OpenAI-compatible / Anthropic-compatible endpoint
- auth header 规则
- Thinking / Effort 请求字段
- provider-specific body patch
- context window metadata
- 便于后续核验的官方 reference URL

用户自己的 overlay 可以作为只读 profile 输入放在 MMS config 目录。MMS 不应该因为一次 probe 就自动改写真实 `config.toml`。

## Session 能力包

MMS 可以按 session 暴露这些能力：

| Pack | 用途 |
| --- | --- |
| `token-saver` / `TOON` | 压缩长输出和结构化 handoff |
| `web-access` / `weber` / `agent-browser` | 浏览器和 web 任务路由指导 |
| `Caveman` | 低 token 沟通模式 |
| `OMC` / `ECC` | Claude workflow / orchestration agent pack |
| `Pilot` / `auto-github-contributor` | 规划和开源贡献入口 |

启动确认页会展示这些 surface；支持时也可以按当前 session 关闭某个 MCP / skill / hook。

## 可选安装包

只有当你希望能力在 MMS 管理之外也全局可用时，才需要安装这些包：

```bash
bash install.sh --install-token-saver
bash install.sh --install-rtk
bash install.sh --install-mindkeeper-context
bash install.sh --install-map
bash install.sh --install-read-once
bash install.sh --install-ops-env-safe
```

大多数日常 MMS session 不需要改全局 hook；launcher 可以直接注入 repo-owned session assets。

## 清理和重装

脏安装清理先跑 dry-run：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/cleanup_dirty_install.sh | bash
```

确认输出路径没问题，再 apply：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/cleanup_dirty_install.sh | bash -s -- --apply
```

彻底清 MMS-owned 面，也先 dry-run：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/reset_mms_install.sh | bash
```

再 apply：

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/reset_mms_install.sh | bash -s -- --apply
```

reset 默认只清 MMS 自己的安装/config surface；不会默认碰共享 `~/.claude`、共享 `~/.codex` 或全局 OAuth 登录态。

## 开发者说明

改 launcher/session 之后至少跑：

```bash
python3 -m py_compile mms_core.py mms_launchers.py mms_tui.py
PYTHONPATH=. python3 -m pytest -q tests/test_codex_history_growth.py
PYTHONPATH=. python3 -m pytest -q tests/test_claude_hardening_regressions.py -k 'resume or routing or bridge'
git diff --check
```

发版 checklist：

1. 保持 working tree clean
2. 选择下一个 semver tag
3. 创建 annotated tag
4. push branch 和 tag
5. 创建 GitHub Release，并写清安装/升级注意事项

## License

MIT
