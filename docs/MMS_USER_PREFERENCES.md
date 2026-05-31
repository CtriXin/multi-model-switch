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
[launch]
disabled_clis = []            # e.g. ["pi", "agy"]

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

[assets]
managed_enabled = true
managed_root = "~/.local/share/mms/assets"

[assets.roots]
web_access = "~/my-skills/web-access"
weber = "~/my-skills/weber"
agent_browser = "~/my-skills/agent-browser"
codegraph = "~/my-skills/codegraph"
token_saver = "~/my-skills/token-saver"
toon = "~/my-skills/toon"
xmem = "~/my-skills/xmem"
caveman = "~/my-packs/caveman"
nsr = "~/my-packs/non-stop-run"
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
claude, codex, opencode, pi, agy
```

`[session_surfaces.disabled]` accepts:

```toml
skills = []
mcp = []
hooks = []
```

`skills` accepts MMS dynamic skill names such as `web-access`, and CLI-scoped Global Skill filters such as `claude:frontend-design` or `codex:bugfix`. Scoped Global Skill filters only affect MMS-launched sessions; they do not delete or edit `~/.claude/skills` or `~/.codex/skills`.

`[launch] disabled_clis` accepts MMS launch targets such as:

```text
claude, codex, opencode, pi, agy
```

关闭后，该 CLI 会从 MMS 启动选择里隐藏；直接执行 `mms <cli>` / preset 指向该 CLI 时也会被阻止。它只影响 MMS，不会卸载或修改原生 CLI。

`[assets]` accepts:

| Key | Values | Effect |
| --- | --- | --- |
| `managed_enabled` | `true` / `false` | Whether launcher reads the user managed assets root before bundled assets |
| `managed_root` | path | User override root for MMS-only optional skills, MCP servers, packs, and hooks; default `~/.local/share/mms/assets` |

Managed assets root layout:

```text
~/.local/share/mms/assets/
  skills/<skill-name>/SKILL.md
  mcp/<mcp-name>/...
  packs/<pack-name>/...
  hooks/<hook-name>/...
  packages/<asset-name>/...
```

Put symlinks here when possible. Launcher resolves this user override root first, then the current MMS package `assets/session-assets`, and only falls back to legacy `vendor/` paths when bundled assets are missing.

`[assets.roots]` accepts:

```text
web_access, weber, agent_browser, codegraph, token_saver, toon, xmem, caveman, nsr, ecc, omc, auto_github_contributor
```

Env vars like `MMS_WEB_ACCESS_ROOT`, `MMS_ECC_ROOT`, and `MMS_MANAGED_ASSETS_ROOT` still take priority over `preferences.toml`.

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
4. Do not write real `~/.config/mms/**` automatically. Propose a TOML snippet/diff, or use the WebUI preferences writer only after the human explicitly confirms.
5. If the requested change touches credentials, accounts, provider routes, proxy, OAuth, real `HOME`, or Claude config, treat it as a human-gate change and do not auto-apply.

## Lazy Session Assets

MMS 自带动态 assets 随当前包放在 `assets/session-assets`；安装版会复制到 `~/.mms/assets/session-assets`。`~/.local/share/mms/assets` 是用户覆盖根，优先级高于包内 assets。Launchers 只在 session 启动时把最终解析到的来源 symlink 到隔离 HOME。

Common roots:

```text
~/.mms/assets/session-assets/packs/caveman
~/.mms/assets/session-assets/skills/web-access
~/.mms/assets/session-assets/skills/weber
~/.mms/assets/session-assets/skills/agent-browser
~/.mms/assets/session-assets/skills/token-saver
~/.mms/assets/session-assets/skills/toon
~/.mms/assets/session-assets/skills/xmem
~/.mms/hooks/nsr-builtin-hook.py
~/.mms/agent-packs/everything-claude-code
~/.mms/agent-packs/oh-my-claudecode
```

Passive assets are available naturally in MMS-launched sessions. NSR is also enabled by default for MMS-managed Claude/Codex sessions, but its default hooks are limited to tool/compact/closeout events and can be disabled per launch or via `nsr_mode = "disable"`. Heavier agent packs such as `ECC` and `OMC` remain opt-in.

This keeps global Claude/Codex/OpenCode/Antigravity config clean while still giving each MMS session the selected skills, hooks, and MCP surfaces.

## WebUI 能力目录

`mms config web` 提供 **Skill / MCP 管理**。它复用 TUI 启动确认页的 launch preview catalog，但按普通用户更容易理解的方式分组：

- `MMS 动态注入`：MMS 在 session 启动时临时注入的技能、MCP 服务、hooks 和 OpenCode 插件；Pi 目前只生成 provider/models/settings/retry extension，不注入 Skill/MCP/Hook；
- `全局继承`：用户自己已有的 Claude/Codex/OpenCode 配置或插件，MMS 可以看到，但 WebUI 不会静默编辑；
- `其它检测项`：启动预览能看到、但需要保守检查路径的条目。

面板默认用卡片展示用途、来源、CLI、类型和默认状态；路径、触发、`disable_key` 和原始说明折叠在“高级信息”里。Global Skill 数量较多时会按组折叠，例如 `lark-*` 会进入 Lark CLI 技能组，并能整组加入默认关闭草稿。默认关闭仍属于 `preferences.toml`；WebUI 只有在本次草稿相对当前 preferences 有变化时才显示底部保存栏，点击“保存并应用”会单独保存 Skill/MCP/Hook 偏好，创建 backup + audit，不混入模型/provider 保存。
