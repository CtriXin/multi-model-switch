# Multi-Model Switch (MMS)

[简体中文 README](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> A launcher-first runtime manager for local AI coding CLIs. Use one entrypoint to choose models, providers, session packs, and isolated Claude/Codex homes without turning your real global account state into a fallback pool.

![MMS launcher tree](docs/images/mms-launcher-tree-en.svg)

## What MMS Does

MMS is not another chat client. It is the local control plane in front of tools such as `claude`, `codex`, `opencode`, and `gemini`; Qwen/Kimi remain provider models, not standalone CLI launchers.

Scope note: MMS is intentionally launcher-first. Legacy or helper surfaces such as `chat`, `discuss`, and high-context review helpers are maintenance-only unless they directly support launcher/session validation. Long-running planning, execution, compaction policy, and run authority should live in Moebius, Pilot, Ant, or addons instead of expanding MMS.

It helps you:

- start the right CLI from one TUI or command line
- choose providers and OAuth/account profiles explicitly
- keep Claude/Codex session state isolated and resumable
- bridge compatible model providers while preserving protocol semantics
- inject session-scoped skills and hooks without editing global config
- diagnose provider, route, cache, and exposed runtime state before blaming a model

## Current Version

Current tagged version: `v2.5.1`

Key changes in this generation:

- provider profiles for OpenAI, Qwen/DashScope, MiMo, MiniMax, DeepSeek, Kimi Code, and GLM/Z.ai
- profile-driven auth/body/thinking/effort patching across bridge and dispatch paths
- Claude resume persistence through `.claude/projects`
- Codex resume write-back across isolated MMS-managed launches
- OpenCode profiles: `Orchestrated`, `Roster`, and `Raw` with repo-local health feedback
- OpenCode Lite Pro mixed routes: GPT via OpenAI-compatible Responses/Chat, domestic models via Anthropic `/v1/messages`
- model fallback order: same-model second channel, same-role peer, then stable GPT fallback
- runtime discovery across PATH, Homebrew, and all NVM Node versions without changing default Node
- installer-managed Python virtualenv plus MMS-managed Python fallback when system Python is missing or too old
- bundled lightweight session assets for `Caveman`, `token-saver`, `TOON`, `web-access`, `weber`, and `agent-browser`
- optional MMS-managed ECC/OMC Claude agent-pack installer flow

## Install Or Upgrade

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s --
```

Default behavior:

- installs the latest semver tag
- creates an isolated MMS runtime under `~/.mms`
- links `mms` into `~/.local/bin`
- creates `~/.mms/.venv` and uses Python 3.11+ without replacing the user's system Python
- if Python 3.11+ is missing, prepares an MMS-managed Python via `uv` under `~/.mms`
- discovers installed `claude` / `codex` across PATH, Homebrew, and NVM versions
- keeps the legacy `ccs` shim installable with `--install-legacy-ccs`, but no longer exposes it by default
- asks before installing optional packs or missing frontend CLIs
- does not silently rewrite your real provider/account configuration

Fresh-machine install with optional CLI bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --install-cli claude,codex --write-shell-rc
```

Shell support:

- Bash/Zsh: `--write-shell-rc` writes `~/.local/bin` into the active shell rc.
- Fish: `--write-shell-rc` writes `~/.config/fish/conf.d/mms.fish`.
- Ghostty/iTerm/Terminal: reopen the tab after install, or run `exec $SHELL -l`.
- If you do not write shell rc, run `~/.local/bin/mms` immediately; direct `mms` works after PATH is loaded.

Set the UI language during install:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --lang en
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --lang zh
```

Pin a release when you need an exact version:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/v2.5.1/install.sh | bash -s --
```

Verify the install:

```bash
bash install.sh --check
mms doctor
mms test --provider <id> --cli claude
mms test --provider <id> --cli codex
```

## Quick Start

Interactive launch:

```bash
mms
```

Direct CLI launch:

```bash
mms claude
mms codex
mms opencode
mms --provider <provider-id> codex
mms --provider <provider-id> opencode
mms --account <account-id> claude
```

Export environment variables instead of launching:

```bash
mms --export codex
mms --export opencode
mms --export claude --apply
```

Inspect routes and health:

```bash
mms models
mms routes
mms doctor
mms test --provider <id> --cli claude
mms exposure
mms logs
```

## Mental Model

```text
MMS
├── Entry
│   ├── mms TUI
│   ├── mms claude / mms codex / mms opencode
│   └── export / presets
├── Decision
│   ├── provider profiles
│   ├── role + priority routing
│   └── doctor / test / trace diagnostics
├── Runtime Isolation
│   ├── Claude: session HOME + .claude/projects resume
│   ├── Codex: bounded .codex seed + write-back
│   ├── OpenCode: session HOME + inline OpenAI-compatible config
│   └── bridge: local protocol adapters when needed
└── Session Packs
    ├── token-saver / TOON
    ├── web-access / weber / agent-browser
    └── Caveman / OMC / ECC / Pilot
```

The diagram source lives in:

- `docs/images/mms-launcher-tree.mmd`
- `docs/images/mms-launcher-tree-outline.md`
- `docs/images/mms-launcher-tree.html`

## Runtime Safety Rules

MMS tries to fail closed inside the selected runtime.

- Real `HOME` and global OAuth state are protected surfaces, not fallback pools.
- A failed provider/account should not silently become another global account.
- Claude semantics prefer `Anthropic /v1/messages` when a route supports it.
- `OpenAI /v1/chat/completions` is fallback transport, not an invisible equivalent.
- Session packs are injected into the isolated session; they are not global default hooks.
- Resume data is bounded and scoped so startup stays usable and account state stays isolated.

Operational details:

- [Provider profiles](./docs/PROVIDER_PROFILES.md)
- [Claude cache / protocol runbook](./docs/SERVER_CLAUDE_CACHE_RUNBOOK.md)
- [Agent guardrails](./docs/AGENT_GUARDRAILS.md)
- [CLI/provider compatibility QA](./docs/CLI_PROVIDER_COMPAT_QA.md)

## Provider Profiles

Provider-specific behavior belongs in data, not in one-off launcher branches.

`config/provider-profiles.json` records:

- OpenAI-compatible and Anthropic-compatible endpoints
- auth header expectations
- Thinking / Effort request fields
- provider-specific body patches
- context window metadata
- reference URLs for future verification

User overlays can live in the MMS config directory as read-only profile inputs. MMS should not mutate your real `config.toml` just because a model was probed.

## Session Packs

MMS can expose capabilities per session without writing global hooks/config.

| Pack | Install state | Purpose |
| --- | --- | --- |
| `token-saver` / `TOON` | bundled | compact long outputs and structured handoffs |
| `web-access` / `weber` / `agent-browser` | bundled | browser and web-task routing guidance |
| `Caveman` | bundled | compact communication mode |
| `ECC` | optional MMS-managed pack | Claude engineering workflow / rules / quality hooks |
| `OMC` | optional MMS-managed pack | Claude orchestration runtime / team / verify loop |
| `Pilot` / `auto-github-contributor` | detected when installed | planning and contribution surfaces |

These surfaces are previewed before launch and can be disabled per session when supported by the confirmation UI. ECC and OMC stay disabled until selected from the Claude launch confirmation screen.

## Optional Installer Packs

Install global optional packs only when you want them available outside MMS-managed sessions:

```bash
bash install.sh --install-rtk
bash install.sh --install-brainkeeper-context
bash install.sh --install-map
bash install.sh --install-read-once
bash install.sh --install-token-saver
bash install.sh --install-ops-env-safe
```

Legacy `--install-mindkeeper-context` and `--mindkeeper-ref` still work as deprecated aliases for BrainKeeper installs.

Install MMS-managed Claude agent packs without touching global Claude config:

```bash
bash install.sh --install-ecc
bash install.sh --install-omc
bash install.sh --install-agent-packs
```

Most day-to-day MMS sessions do not need global hook installation; the launcher can inject bundled or MMS-managed session assets directly.

## Cleanup And Reset

Dry-run dirty-install cleanup:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/cleanup_dirty_install.sh | bash
```

Apply only after checking the printed paths:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/cleanup_dirty_install.sh | bash -s -- --apply
```

Full MMS-owned reset, dry-run first:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/reset_mms_install.sh | bash
```

Then apply:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/scripts/reset_mms_install.sh | bash -s -- --apply
```

Reset targets MMS-owned install/config surfaces. It intentionally avoids shared `~/.claude`, shared `~/.codex`, and global OAuth state unless an explicit flag says otherwise.

## Developer Notes

Run focused checks before publishing launcher/session changes:

```bash
python3 -m py_compile mms_core.py mms_launchers.py mms_tui.py
PYTHONPATH=. python3 -m pytest -q tests/test_codex_history_growth.py
PYTHONPATH=. python3 -m pytest -q tests/test_claude_hardening_regressions.py -k 'resume or routing or bridge'
git diff --check
```

Release checklist:

1. keep the working tree clean
2. choose the next semver tag
3. create an annotated tag
4. push branch and tag
5. create a GitHub Release with install/upgrade notes

## License

MIT
