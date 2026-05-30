# MMS User Preferences

`preferences.toml` 是用户自己的安全偏好覆盖层，用来改 launch 默认值和 session surface 开关；安装和升级不会覆盖它。

## Path

默认路径：

```text
~/.config/mms/preferences.toml
```

辅助入口：

```bash
mms config preferences.help
mms config preferences.path
mms config preferences.example
mms config human-gate
```

## Overlay Order

运行时合并顺序：

```text
config.toml -> override.toml -> preferences.toml allowlist -> confirm screen changes -> launcher
```

- `override.toml` 仍是 power-user / team runtime overlay，可以完整覆盖运行时配置。
- `preferences.toml` 只接受 allowlist 字段，适合用户日常偏好。
- TUI confirmation screen 上本次手动切换的值优先级最高，但不会写回真实配置。

## Example

```toml
[launch.defaults]
thinking_mode = "enable"      # enable | disable
reasoning_effort = "high"     # low | medium | high | xhigh
caveman_mode = "enable"       # enable | disable
caveman_level = "light"       # light | standard | full
nsr_mode = "enable"           # enable | disable
agent_pack = "none"           # none | ecc | omc
bypass = true                 # true | false

[launch.cli.codex]
reasoning_effort = "high"

[launch.cli.claude]
agent_pack = "ecc"

[launch.cli.agy]
caveman_mode = "enable"
caveman_level = "light"

[session_surfaces.disabled]
skills = ["agent-browser"]
mcp = ["pilot"]
hooks = []

[assets.roots]
web_access = "~/my-skills/web-access"
weber = "~/my-skills/weber"
agent_browser = "~/my-skills/agent-browser"
token_saver = "~/vendor/token-saver"
toon = "~/vendor/toon"
xmem = "~/vendor/xmem"
caveman = "~/vendor/caveman"
nsr = "~/vendor/non-stop-run"
ecc = "~/.mms/agent-packs/everything-claude-code"
omc = "~/.mms/agent-packs/oh-my-claudecode"
```

## Allowed Keys

`[launch.defaults]` and `[launch.cli.<name>]` accept:

| Key | Values | Effect |
| --- | --- | --- |
| `thinking_mode` | `enable` / `disable` | Default Thinking toggle for supported `Claude` / `Codex` routes |
| `reasoning_effort` | `low` / `medium` / `high` / `xhigh` | Default effort when the selected model profile supports it |
| `caveman_mode` | `enable` / `disable` | Default session-local Caveman overlay |
| `caveman_level` | `light` / `standard` / `full` | Default Caveman intensity when enabled |
| `nsr_mode` | `enable` / `disable` | Default session-local NSR hook injection for Claude/Codex; default is `enable`, without startup/prompt hooks |
| `agent_pack` | `none` / `ecc` / `omc` | Default Claude agent pack toggle |
| `bypass` | `true` / `false` | Default launch approval bypass toggle |
| `disabled_session_surfaces` | table with `skills` / `mcp` / `hooks` arrays | Per-launch disabled surface overlay |

Supported CLI names:

```text
claude, codex, opencode, agy
```

`[session_surfaces.disabled]` accepts:

```toml
skills = []
mcp = []
hooks = []
```

`[assets.roots]` accepts:

```text
web_access, weber, agent_browser, token_saver, toon, xmem, caveman, nsr, ecc, omc, auto_github_contributor
```

Env vars like `MMS_WEB_ACCESS_ROOT` and `MMS_ECC_ROOT` still take priority over `preferences.toml`.

## Denied / Ignored Keys

`preferences.toml` intentionally ignores anything outside the allowlist, including:

- `api_key`, `base_url`, `anthropic_base_url`, `openai_base_url`
- `proxy`, `no_proxy`, `timezone`, `home_dir`
- provider/account priority, routing, fallback, bridge, and model-list fields
- OAuth tokens, Keychain state, account identity, owner fingerprint
- Claude config, real `HOME`, real `XDG_*`, global auth caches

Use `override.toml` only when you intentionally need full runtime overlay power. Agents must still treat both files as real user config.

## Human Gate

`~/.config/mms/**` is `human-only` for agents.

Allowed without writing:

- read current values
- explain what to change
- print `mms config preferences.example`
- generate a manual diff or exact TOML snippet

Blocked unless the human explicitly confirms the write:

- writing `preferences.toml`
- writing `config.toml`, `override.toml`, `credentials.sh`
- writing `accounts/**`, `env/**`, `usage.json`, or account state
- changing Claude config or Claude-related MMS config fields

Required write flow for real config:

```text
plan -> backup -> human double check -> audited write -> post-write human double check
```

## LLM / Agent Instructions

When a user asks "MMS 该改哪个配置":

1. Run or cite `mms config preferences.help`.
2. Read this document.
3. Prefer `preferences.toml` for daily preferences like `thinking_mode`, `reasoning_effort`, `bypass`, `nsr_mode`, `agent_pack`, and disabled session surfaces.
4. Do not write real `~/.config/mms/**` automatically. Propose a TOML snippet or diff and ask the human to apply/confirm.
5. If the requested change touches credentials, accounts, provider routes, proxy, OAuth, real `HOME`, or Claude config, treat it as a human-gate change and do not auto-apply.

## Lazy Session Assets

MMS-installed assets are copied under `~/.mms/vendor/` during install. Launchers then symlink them into each isolated session only when that session starts.

Common roots:

```text
~/.mms/vendor/caveman
~/.mms/vendor/web-access
~/.mms/vendor/weber
~/.mms/vendor/agent-browser
~/.mms/vendor/token-saver
~/.mms/vendor/toon
~/.mms/vendor/xmem
~/.mms/hooks/nsr-builtin-hook.py
~/.mms/agent-packs/everything-claude-code
~/.mms/agent-packs/oh-my-claudecode
```

Passive assets are available naturally in MMS-launched sessions. NSR is also enabled by default for MMS-managed Claude/Codex sessions, but its default hooks are limited to tool/compact/closeout events and can be disabled per launch or via `nsr_mode = "disable"`. Heavier agent packs such as `ECC` and `OMC` remain opt-in.

This keeps global Claude/Codex/OpenCode/Antigravity config clean while still giving each MMS session the selected skills, hooks, and MCP surfaces.
