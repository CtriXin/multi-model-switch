# Multi-Model Switch (MMS)

[简体中文 README](./README.md)

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

> A launcher-first runtime manager for local AI coding CLIs. Use one entrypoint to choose models, providers, session packs, and isolated Claude/Codex homes without turning your real global account state into a fallback pool.

![MMS launcher tree](docs/images/mms-launcher-tree-en.svg)

## What MMS Does

MMS is not another chat client. It is the local control plane in front of tools such as `claude`, `codex`, `opencode`, and `agy`; Qwen/Kimi/Gemini remain provider models, not standalone CLI launchers.

Scope note: MMS is intentionally launcher-first. Legacy or helper surfaces such as `chat`, `discuss`, and high-context review helpers are maintenance-only unless they directly support launcher/session validation. Long-running planning, execution, compaction policy, and run authority should live in Moebius, Pilot, Ant, or addons instead of expanding MMS.

It helps you:

- start the right CLI from one TUI or command line
- choose providers and OAuth/account profiles explicitly
- keep Claude/Codex session state isolated and resumable
- bridge compatible model providers while preserving protocol semantics
- inject session-scoped skills and hooks without editing global config
- diagnose provider, route, cache, and exposed runtime state before blaming a model

## Current Version

Current branch release tracks:

- Stable / `main`: `3.4.z` (current stable branch tag: `v3.4.0`)
- Dev / `mmf`: `3.5.z`
- Canary / `mmg`: `3.6.z`

Patch `z` is channel-local. A single-commit release increments `z` once; a composite release covering multiple validated commits also increments `z` once.

Stable target branch: `main` after the current catch-up window.

Daily development branch: `dev`.

## Maintainer Development Entry

Maintainers should enter MMS from the repository root, and that root checkout should be on `dev`, clean, and current. `.worktrees/*` is reserved for isolated issue/PR work; `.worktrees/dev` must not be used as the shared default development entry.

Standard loop:

1. Enter the repository root and confirm the branch is `dev`.
2. Run `git pull --ff-only` so `dev` is current and clean.
3. Open an issue first, and record the plan in the issue or a linked plan document.
4. Create an isolated worktree/branch from current `dev`, for example `.worktrees/issue-14-redline-gate`.
5. Develop, validate, commit, and push inside that isolated worktree.
6. Open a PR targeting `dev` for committee review.
7. Merge only after committee/human approval, then fast-forward the root `dev` checkout before the next task.

Unless the human explicitly asks for direct edits in the shared `dev` entry, agents must not stack substantive work or leave untracked files there. Docs-only plan/report changes may be committed by default when the user asks to record, submit, or produce the document, but the commit must stage only the target document and no unrelated dirty files.

Key changes in this generation:

- Codex primary/rescue fallback now retries prompt-cache-sensitive GLM/DeepSeek/Qwen-compatible routes over Anthropic `/v1/messages` when a gateway rejects `/v1/chat/completions`
- provider profiles for OpenAI, Qwen/DashScope, MiMo, MiniMax, DeepSeek, Kimi Code, and GLM/Z.ai
- profile-driven auth/body/thinking/effort patching across bridge and dispatch paths
- Claude resume persistence through `.claude/projects`
- Claude-on-MMS vision sidecar: text-only domestic models fail closed or delegate screenshots/images to a configured Kimi/MiMo/Qwen-compatible sidecar instead of stalling
- Codex resume write-back across isolated MMS-managed launches
- OpenCode modes: `Agent`, `Review`, `OMO`, and `Raw` with repo-local health feedback
- OpenCode Agent contract lane: `mobius-spec-writer` writes an OpenSpec/SpecBridge-style task contract, and `mobius-spec-compliance-reviewer` checks diff + validation against it before release-gate review
- OpenCode Agent work split: GPT handles coordination, specs, implementation/fix work, and final review; DeepSeek/MiMo/Qwen/GLM/Kimi default to lightweight read-only exploration, bug-hunt, vision, and context checks
- OpenCode Agent mixed routes: GPT via OpenAI-compatible Responses/Chat, direct MiMo via OpenAI-compatible `/v1`, other domestic models via Anthropic `/v1/messages`
- OpenCode bypass is enabled by default through permission `allow`; subagent `ask` permissions are auto-approved while explicit `deny` boundaries stay intact, and optional `opencode run` preflight uses `--dangerously-skip-permissions`
- model fallback order: same-model second channel, same-role peer, then stable GPT fallback
- runtime discovery across PATH, Homebrew, and all NVM Node versions without changing default Node
- real-home compatibility wrappers for Keychain/Chrome/global CLIs inside isolated sessions
- installer-managed Python virtualenv plus MMS-managed Python fallback when system Python is missing or too old
- bundled lightweight session assets for `Caveman`, `token-saver`, `TOON`, and the Web automation bundle (`weber` router + `web-access` logged-in Chrome + `agent-browser` headless); Claude/Codex/OpenCode/Antigravity injection stays session-local
- Caveman now defaults to `lite`, keeping full sentences while still removing filler; `/caveman full` remains available for stronger compression
- quiet hook policy: MMS-managed Claude/Codex sessions avoid default SessionStart/UserPrompt probes; remaining hooks are guard, closeout, or explicitly enabled pack hooks
- session MCP hardening resolves inherited Claude MCP commands to real-HOME absolute CLIs or drops missing ones, and also surfaces URL-based MCP servers from installed Claude plugins (for example Figma); for Codex, app-backed integrations already enabled in real `~/.codex/config.toml` win over duplicate inherited URL MCP entries so MMS does not create a second broken OAuth path; Codex Caveman preserves trusted hook order where possible
- optional BrainKeeper context pack installs MCP, Claude commands/hooks, and `bk` / `brainkeeper` wrappers without requiring Xcode/git
- optional MMS-managed ECC/OMC Claude agent-pack installer flow

xmem is global-only: MMS / MMF no longer bundles, installs, or injects xmem skills, hooks, or OpenCode plugins. If a global agent skill or hook provides xmem, that global version wins so dev-channel copies cannot shadow it with an older bundled copy.

## Install Or Upgrade

The main README is Chinese-first. English users can still install with the same three explicit channels. The channel contract is frozen unless a human explicitly changes the release/channel policy:

- `Stable == main == MMD/mmd`
- `Dev == dev branch == MMF/mmf`
- `Canary == canary branch == MMG/mmg`

### Stable: recommended for normal users

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel stable --write-shell-rc
```

### Dev: recommended for the maintainer's own work machines

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel dev --write-shell-rc
```

### Canary: only for test machines or experimental sessions

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel canary --write-shell-rc
```

Exact pin when needed:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref v3.4.0
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref main
```

Channel behavior:

- `stable` is the pure stable channel; after the catch-up window, `main` is Stable/default.
- `dev` follows the `dev` branch for daily work and should remain development-stable.
- `canary` follows the `canary` branch for daily experiments; use frequent small commits so rollback stays easy.
- Maintainer-local commands are generated by `scripts/link_local_channel_commands.sh`: `mms` is the public installed copy for public-version repro only; `mmd` points to the stable worktree; `mmf` points to the dev worktree; `mmg` points to the canary worktree; `mmm` points to the main worktree. `mmf` and `mmg` both force the `~/.config/mms-next` preview DB root. Update reminders are notify-first: `mmg` checks every launch, `mmf` / `mmm` daily, `mmd` weekly, and `mms` only reminds about the public installed copy; manual `update` only allows clean fast-forward worktrees.

Fresh-machine install with optional CLI bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel dev --install-cli claude,codex,opencode --write-shell-rc --lang en
```

After install:

```bash
mms doctor
mms models
mmf config web
```

Note: `mmf` and `mmg` are preview DB entrypoints. Use `mmf config web` or `mmg config web` for `Write preview DB + publish`; `mms config web` intentionally shows the public installed stable/current legacy save path.

See also: [Release channels](docs/RELEASE_CHANNELS.md) and [Web UI quickstart](docs/WEB_UI_QUICKSTART.md).

## Config V2 Preview Root

Config v2 is available as a preview path before it becomes the stable default. Maintainer-local command semantics are:

```text
mms -> public installed copy, default ~/.config/mms
mmd -> Stable worktree, default ~/.config/mms
mmf -> Dev worktree, forced ~/.config/mms-next
mmg -> Canary worktree, forced ~/.config/mms-next
mmm -> Main worktree, default ~/.config/mms
```

Recommended preview flow:

```bash
mmf config root --json
mmf preview doctor --json
mmf preview prepare --from ~/.config/mms --json
mmf preview prepare --from ~/.config/mms --include-secrets --json
mmf config check --json
mmf config bundle --json
mmf config web
```

In preview mode, the human-facing entrypoints are TUI / `mms config` / WebUI.
Those surfaces write DB candidates, the preview secret backend, and a verified
`generated/model-registry.latest-approved.json` bundle; they do not make
`config.toml`, `credentials.sh`, route, policy, profile, or lineup files compete
as separate truth sources.

Stable promotion is still human-gated and read-only:

```bash
mmf promote --json
mms migrate config-v2 --json
mms config release-readiness --json
```

Even with `--apply`, `mms migrate config-v2` currently reports
`apply_enabled=false` and stops at `stable_root_human_only` /
`promotion_apply_not_implemented`. There is no silent fallback from the preview
root into stable credentials, OAuth state, or Claude config. The release
readiness audit can return `READY_FOR_4_0_HUMAN_GATE`, but it still reports
`release_complete=false` until the human-gated stable promotion and post-promotion
smoke are done.

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
mms opencode --profile agent
mms opencode --profile review
mms opencode --profile omo
mms opencode --profile raw
mms --provider <provider-id> codex
mms --provider <provider-id> opencode
mms --account <account-id> claude
```

For OpenCode Review, prefer the `mms` TUI: choose `OpenCode` -> `Review`, Space-select reviewer models, then Enter to launch and remember the selection under `[opencode.review].models`. `--review-models` remains available for scripts and advanced users.

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
│   ├── mms claude / mms codex / mms opencode / mms agy
│   └── export / presets
├── Decision
│   ├── provider profiles
│   ├── role + priority routing
│   └── doctor / test / trace diagnostics
├── Runtime Isolation
│   ├── Claude: session HOME + .claude/projects resume
│   ├── Codex: bounded .codex seed + write-back
│   ├── OpenCode: real HOME + session-local XDG/config
│   └── bridge: local protocol adapters when needed
└── Session Packs
    ├── token-saver / TOON
    ├── Web automation bundle
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
- GUI/Keychain/browser launches from isolated sessions go through real-home wrappers; OpenCode keeps config/state session-local with real `HOME`.
- Background helpers do not read macOS Keychain unless `MMS_STATUSLINE_KEYCHAIN_USAGE=1`, `MMS_ALLOW_KEYCHAIN_READ=1`, or `mms usage --keychain` is explicitly used.
- Session packs are injected into the isolated session; they are not global default hooks.
- Resume data is bounded and scoped so startup stays usable and account state stays isolated.

Operational details:

- [Provider profiles](./docs/PROVIDER_PROFILES.md)
- [User preferences](./docs/MMS_USER_PREFERENCES.md)
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
- provider-specific parameter aliases
- context window metadata
- reference URLs for future verification

Registry v2 is the preferred path for local changes: TUI / `mms config` / WebUI
creates DB candidates, then publishes a verified
`generated/model-registry.latest-approved.json` bundle. When that manifest is
present, the generated Profile it references is the runtime boundary.

Legacy user overlays can still live in the MMS config directory as manual
import/export compatibility inputs. MMS should not mutate your real
`config.toml` just because a model was probed.

## User Preferences

Use `~/.config/mms/preferences.toml` for install-safe daily launch preferences:

- `thinking_mode` / `reasoning_effort`
- `bypass`, `caveman_mode`, `nsr_mode`, `agent_pack`
- disabled session `skills` / `mcp` / `hooks`
- custom bundled asset roots such as `web_access`, `token_saver`, `nsr`, `ecc`, `omc`

LLMs can discover the safe schema with `mms config preferences.help` or `mms config preferences.example`. This file is still real MMS config: agents may inspect and propose edits, but must not auto-write `~/.config/mms/**` without human confirmation.

## Session Packs

MMS can expose capabilities per session without writing global hooks/config.

| Pack | Install state | Purpose |
| --- | --- | --- |
| `token-saver` / `TOON` | bundled in `~/.mms/vendor` | compact long outputs and structured handoffs |
| Web automation bundle | bundled in `~/.mms/vendor` | `weber` routes the task, `web-access` connects logged-in Chrome, and `agent-browser` handles lightweight headless flows |
| `Caveman` | bundled in `~/.mms/vendor` | compact communication mode; only active when enabled by preference or launch confirmation |
| `NSR` | built-in channel payload, default hook injection | session-local Stop hook for Claude/Codex; installer also adds `/nsr` commands; `/nsr` enables the loop |
| `ECC` | optional MMS-managed pack | Claude engineering workflow / rules / quality hooks |
| `OMC` | optional MMS-managed pack | Claude orchestration runtime / team / verify loop |
| `Pilot` / `Figma` / `auto-github-contributor` | detected when installed | optional MCP/contribution surfaces; Pilot and Figma MCP stay disabled unless explicitly enabled with `MMS_ENABLE_MCP_PILOT=1` or `MMS_ENABLE_MCP_FIGMA=1` |

These surfaces are previewed before launch and can be disabled per session when supported by the confirmation UI. Figma and Pilot MCP servers are default-off even when detected; opt in with `MMS_ENABLE_MCP_FIGMA=1`, `MMS_ENABLE_FIGMA_MCP=1`, `MMS_ENABLE_MCP_PILOT=1`, or `MMS_ENABLE_PILOT_MCP=1`. Passive skills (`CodeGraph`, `token-saver`, `TOON`, `web-access`, `weber`, `agent-browser`) are available naturally in MMS-launched sessions. `NSR` is copied with the selected install channel into `~/.mms/hooks/`; MMS injects its lightweight Stop-hook wrapper by default, and `/nsr` opts the current repo into the rewritten loop. It can be disabled from the launch confirmation screen or with `nsr_mode = "disable"` in `preferences.toml`. Heavier active behavior packs (`ECC`, `OMC`) still require explicit selection. OpenCode receives session-local Caveman / CodeGraph / token-saver / TOON / web-access / weber skills plus the manual `/nsr` command, and RTK is added through the session-local plugin directory when `rtk` exists.

## Optional Installer Packs

Install global optional packs only when you want them available outside MMS-managed sessions:

```bash
bash install.sh --install-rtk
bash install.sh --install-brainkeeper-context
bash install.sh --install-map
bash install.sh --install-codegraph
bash install.sh --install-token-saver
bash install.sh --install-toon
bash install.sh --install-ops-env-safe
```

Add `--dry-run` to preview the install plan without writing files, for example `bash install.sh --install-codegraph --dry-run`.

`--install-brainkeeper-context` installs/updates the full BrainKeeper context pack: BrainKeeper MCP, Claude `/distill` / `/cz` / `/cr`, token hooks, and `~/.local/bin/bk` plus `~/.local/bin/brainkeeper`. The installed runtime lives at `~/.local/share/brainkeeper`; when a sibling BrainKeeper repo exists, the installer reuses its `install.sh`, but the active install still syncs into that directory. If Node/npm is missing, the installer prepares an nvm Node 22 runtime for this install without changing the user's default Node. If Xcode/git is unavailable, it falls back to a GitHub archive download.

`--install-map` installs the project-structure Map and enables the Claude SessionStart auto-index hook. It helps Claude orient in a repo faster by refreshing a lightweight directory/file map. This is a global Claude hook; use `--map-ref` to pin the version.

`--install-codegraph` installs the CodeGraph CLI/MCP via npm for symbol search, callers/callees, and code-context retrieval. MMS also injects a passive CodeGraph-first skill so agents prefer graph discovery before broad file reads. MMS no longer adds a default SessionStart auto-register hook for CodeGraph; run indexing explicitly when a repo needs it. Use `--codegraph-package` to override the npm package spec. To initialize everything immediately, ask an LLM: “Find every git repo under this workspace, run `codegraph init -i` when `.codegraph` is missing and `codegraph sync` when it exists, skip `node_modules/vendor/build`, and report failures.”

> `--install-read-once` **REMOVED 2026-06-12** — the optional Read token-saver pack (PreToolUse Read hook + PostCompact compact hook) was retired because a stale hook binary could leak control characters into the API payload and trigger 400 `invalid character` errors. See `installed-skills/AGENTS.md` → Removed Packs for the full audit trail. If you need Read token saving, use the `--install-token-saver` pack plus RTK's read interception.

`--install-token-saver` installs the shared Codex/Claude token-saver skill plus local commands for long logs, test output, broad `rg`, `git diff/show`, and noisy diagnostics as refs plus snippets. `token-gain` / `mms-gain` / `token-saver gain` show estimated saved chars and gain percentage for stored refs, and a normal shell falls back to the most recent non-empty MMS session store when the current repo store is empty. Agents use the low-level commands automatically; users can just say `/token-saver` or ask to save context.

`--install-toon` installs the shared Codex/Claude TOON skill plus the local `mms-toon` command for structured JSON/status/handoff compression in export-only sessions outside MMS. MMS-launched sessions still bundle TOON by default. Do not use TOON for prose, code, raw logs, secrets, or exact CLI/API JSON.

`--install-ops-env-safe` is an advanced-only path hint pack: it writes a Codex skill, Claude `/ops-env-safe`, and `~/.config/mms/ops-env-safe.toml` so export-only or special isolated sessions can inspect known host paths. Normal MMS sessions already receive real-HOME path hints and session host context, so most users do not need it. It does not set real `HOME`/`XDG_*` and does not export auth secrets.

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

Apache-2.0
