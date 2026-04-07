# Multi-Model Switch (MMS)

[简体中文 README](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> A local launcher that unifies `claude`, `codex`, and other AI coding CLIs behind one entrypoint.

![MMS - Before vs After](assets/cover.svg)

## Why MMS

**MMS** helps local developers manage multiple AI coding tools from one place:

- One TUI to browse model families and launch sessions
- One config system for gateway providers and OAuth accounts
- One way to export env vars or presets for scripts and automation
- One routing layer for provider priority, bridge compatibility, and diagnostics

## Install

### Quick install

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s --
```

By default, the installer pulls the latest semver tag.
When run in an interactive terminal, it asks for UI language first, then the optional RTK enhancement, and finally checks whether `Claude Code` / `Codex CLI` are already present before asking to install any missing ones.

### Default English UI on install

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --lang en
```

### Install with optional RTK rewrite enhancement

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-rtk
```

This optional path installs `jq` + `rtk`, wires the Claude `PreToolUse:Bash` hook, and when `Codex CLI` is already available (or gets installed in the same run) it also runs `rtk init --codex --global`.

### Install MMS plus selected CLIs

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-cli claude,codex
```

Supported names: `claude`, `codex`.

### Upgrade

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s --
```

### Install a specific version or branch

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref v1.3.5
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --main
```

## Language

MMS defaults to Chinese unless you choose English during install or override it explicitly.

Supported ways to switch UI language:

```bash
mms config set ui.language en
mms config set ui.language zh

MMS_LANG=en mms
mms --lang en
```

Priority order:

1. `--lang`
2. `MMS_LANG`
3. `ui.language` in config
4. install preference
5. fallback `zh`

## Quick start

### First-time setup

```bash
mms config connect
```

### Launch the TUI

```bash
mms
```

### Non-interactive examples

```bash
mms --preset coding
mms claude --provider openrouter
mms codex --account work
mms --trace --preset coding
```

## Core features

- Unified TUI for model-family-first navigation
- Gateway providers and OAuth accounts in one config surface
- Provider/account priority with bridge-aware routing
- Presets and load-balance profiles
- Usage tracking, route export, and diagnostics
- Per-account isolation for OAuth login state
- `doctor`, `test`, `warm`, `routes`, and `session` utilities

## Screenshots

### Claude tab
![Claude Tab](assets/mms-tui.png)

### Codex tab
![Codex Tab](assets/mms-tui-codex.png)

### Launch confirm
![Launch Confirm](assets/mms-launch-confirm.png)

## Supported CLIs

| CLI | Primary protocol | Notes |
|-----|------------------|------|
| `claude` | Anthropic Messages | Can bridge GPT / Gemini / domestic models |
| `codex` | OpenAI Responses | Falls back to chat-completions bridge when needed |
| `qwen` | OpenAI compatible | Direct launch |
| `kimi` | OpenAI compatible | Defaults to `kimi-k2.5` |
| `gemini` | Google AI | OAuth account support |

## Common commands

```bash
mms config connect
mms config provider.list
mms config account.add claude

mms ls
mms warm
mms routes
mms routes export

mms doctor
mms test --provider <id> --cli <name>

mms chat "explain recursion"
mms discuss "design a protocol"
```

## Config layout

```text
~/.config/mms/
├── config.toml
├── credentials.sh
├── usage.json
├── model-routes.json
├── env/
└── accounts/
```

Key docs:

- [Routing system](./docs/MMS_ROUTING_SYSTEM.md)
- [CLI/provider compatibility QA](./docs/CLI_PROVIDER_COMPAT_QA.md)
- [Agent guardrails](./docs/AGENT_GUARDRAILS.md)

## Notes

- `priority` is runtime-level, not per-model
- Higher numeric `priority` means higher precedence
- `role` still outranks `priority`: `primary > auto > fallback`
- `use_count` affects display/export ranking, not the main runtime routing decision

## License

MIT
