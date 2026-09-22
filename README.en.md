# Multi-Model Switch (MMS)

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[简体中文](./README.md) · [中文镜像（旧链接）](./README.zh-CN.md)

**MMS is a launcher-first local AI coding runtime manager.** It puts `claude`, `codex`, `opencode`, and `agy` behind one entry point, so before launching you pick the model, route, account, session pack, and isolated HOME — instead of one failure silently dropping you back to your real global account.

> **Are you an AI agent, or new to this project?** Read [`docs/AI-ONBOARDING.md`](docs/AI-ONBOARDING.md) first.
> That document is the repository's handover: the three product layers, the `main` 4.x and `dev` 5.x release lines and how to tell which one your change belongs to, the code map, how to run the gates, and the ten classes of mistake this project has already made. **Do not skip section eight** — every item there has really happened at least once.

---

## 30-second version (TL;DR)

| You want to know | Jump to |
|---|---|
| What this is / what problem it solves | [§1 What it is](#1-what-it-is) |
| Which version to install | [§2 Which version to install](#2-which-version-to-install-30-second-decision) |
| How to install and start using it | [§3 5-minute quickstart](#3-5-minute-quickstart) |
| What Pilot / Bot workbench can do | [§4 What Pilot can do](#4-what-pilot-can-do) / [§5 Bot workbench (5.x only)](#5-bot-workbench-5x-only) |
| A command I can't find | [§6 Command reference](#6-command-reference) (collapsed) |
| Something is broken | [§9 Troubleshooting](#9-troubleshooting) |
| Common questions | [§10 FAQ](#10-faq) (collapsed, 12+ items) |
| Safety / boundaries | [§11 Safety baseline](#11-safety-baseline) |
| Full doc map | [§13 Doc map](#13-doc-map) |

If you only have 30 seconds: install stable (`bash install.sh`) → browser opens → add your first channel → start using. If you don't know what "stable" means, see [§2 Which version to install](#2-which-version-to-install-30-second-decision).

---

## Table of contents

- [0. 30-second version (TL;DR)](#30-second-version-tldr)
- [1. What it is](#1-what-it-is)
- [2. Which version to install (30-second decision)](#2-which-version-to-install-30-second-decision)
- [3. 5-minute quickstart](#3-5-minute-quickstart)
- [4. What Pilot can do](#4-what-pilot-can-do)
- [5. Bot workbench (5.x only)](#5-bot-workbench-5x-only)
- [6. Command reference](#6-command-reference)
- [7. Bundled packs](#7-bundled-packs)
- [8. Where config lives](#8-where-config-lives)
- [9. Troubleshooting](#9-troubleshooting)
- [10. FAQ](#10-faq)
- [11. Safety baseline](#11-safety-baseline)
- [12. Version history (v3 → v4 → v5 milestones)](#12-version-history-v3--v4--v5-milestones)
- [13. Doc map](#13-doc-map)
- [14. Release checklist (maintainers)](#14-release-checklist-maintainers)

---

## 1. What it is

### 1.1 One sentence

A single entry point for multiple AI coding CLIs (Claude Code / Codex / OpenCode / Pi / agy) that lets you pick the model, route, account, session pack, and isolated HOME before launching anything.

### 1.2 Three layers

| Layer | What | Entry |
|---|---|---|
| **MMS launcher** | The "think first" layer before launching: model, route, account, session pack, isolated HOME | `mms` (TUI), `mms claude`, `mms codex`... |
| **MMS Pilot** | Local web client for the launcher. Sessions, channels, models, capability edits, workspace management — all in the browser. Sessions are executed by the local Pi | `mms web --open` |
| **MMS Bot** (5.x only) | Pilot's execution upgrade. Hand a Bot a goal and an identity with memory, scheduled wake-ups, and the ability to dispatch work — it executes and reports back | Bot workbench in Pilot |

One sentence to tell Pilot sessions and Bots apart: **Pilot is "I'm doing this myself now", Bot is "I gave you a goal, you go do it and report back"**.

### 1.3 How it differs from "naked claude/codex"

If you use Claude Code, Codex, OpenCode, New API / OpenAI-compatible platforms, and Chinese-language models across multiple providers, MMS centralizes "what you should think about before launching":

- **One entry, multiple CLIs**: `mms` enters the TUI, or go direct with `mms claude` / `mms codex` / `mms opencode`.
- **Model sources in one place**: provider, account, route, fallback, thinking, vision, cache-sensitive transport — all visible before launch.
- **Isolated but recoverable**: Claude/Codex sessions run in an MMS-managed HOME / config seed, so they pollute your real global config less while still allowing resume.
- **Session-scoped pack injection**: CodeGraph, TOON, grill-me, Web automation bundle etc. are session-local by default; they don't modify your global hooks.
- **Diagnose first, suspect the model second**: before doubting the model, check route, protocol, cache, API key, request path, and runtime exposure.

`chat`, `discuss`, and high-context helpers are now maintenance-only surfaces; the main line is making local coding CLI launch, routing, isolation, and diagnostics solid.

---

## 2. Which version to install (30-second decision)

> **TL;DR**: Default: install **stable (4.23.x)**. Want the Bot workbench: install **dev (5.1.x)**. Canary is deprecated, don't use it.

| Who you are | Install command | After install |
|---|---|---|
| Normal user / use it as a tool | `bash install.sh` (default stable, 4.23.x) | Leave it alone for a long time |
| Want Bot workbench, can tolerate small bumps | `bash install.sh --channel dev` (5.1.x) | See "after upgrading to 5.x" below |
| Maintainer / contributor | Install both lines | Separate worktrees for each |

<details>
<summary><b>Stable vs preview: two long-running parallel lines (click for full)</b></summary>

Since 2026-09-16, `main` and `dev` are **two long-running parallel release lines**, not "stable branch and dev branch".

| Line | Branch | Version | Install flag | What's in it |
|---|---|---|---|---|
| Stable | `main` | 4.23.x | `--channel stable` (default) | Battle-tested features; only fixes and validated capabilities |
| Preview | `dev` | 5.1.x | `--channel dev` | Stable capabilities, Bot workbench, and other preview changes |
| Canary | `canary` | deprecated | `--channel canary` | Old experimental line, deprecated since 2026-06; do not use |

Stable fixes should be ported to `dev`, but synchronization requires an actual merge and is not automatic. Check each branch's Git history and Releases to confirm whether a fix is included.

**One public install directory, `~/.mms`, holds one release line at a time.** Switch by re-running the installer with the matching `--channel`; config, channels, and session history remain in the same config root. Developers can keep isolated worktrees for both lines, with care around shared config and service ports.

Historical background: in the v3.x era there were three channels (Stable 3.4.z / Dev 3.5.z / Canary 3.6.z). v4.0.0 re-planned as "two lines + Pilot", and Canary was deprecated in 2026-06. See [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md).

</details>

> **⚠️ Warning: after upgrading to 5.x you cannot downgrade to 4.x from inside Pilot**
>
> Pilot's "version & update" panel lets you pick between 4.x stable and 5.x preview. Going 4.x → 5.x takes a few clicks. But **after 5.x is installed, switching the channel back to stable in Pilot does not downgrade to 4.x** — Pilot only recommends versions higher than current. To return to the stable line you must re-run the installer with `--channel stable`; config and history are preserved.
>
> Reason (in `mms_web/updates.py`): `available = remote > current`, and `4.23.x < 5.1.x`, so 4.x will never be offered as "an available update". This is by design, not a bug. No documentation should ever claim "fully reversible".

---

## 3. 5-minute quickstart

> **T9a layout migration (4.23.8):** To move a flat installation into `lib/`, finish running tasks, exit Pilot, and rerun the installer. An old Pilot updater cannot perform this migration. Use an old tag's own installer when installing that tag.

### 3.1 Install (one command)

**macOS / Linux**:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```

When done it asks whether to open Pilot. Press Enter; the browser opens, the service runs in the background, the installer exits.

**Windows**: Different flow (Native Preview, 6 steps from scratch). Full guide at [`docs/install/WINDOWS.md`](docs/install/WINDOWS.md).

<details>
<summary><b>Other install modes (dev / canary / pin / silent)</b></summary>

```bash
# Want the latest fixes / Bot workbench
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --channel dev

# Pin to a specific release (CI, multi-machine sync)
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --ref v4.23.9

# CI / scripts: don't open Web, don't touch shell config
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --no-launch-web --no-shell-rc

# Open immediately, no prompt
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --launch-web

# Control exactly which CLIs get installed (default auto-installs claude/codex/opencode)
bash install.sh --install-cli claude,codex
```

</details>

### 3.2 What the installer does by default

- Installs to `~/.mms`, symlinks `mms`, `mmf`, `mmslogs` into `~/.local/bin`.
- Creates `~/.mms/.venv`; falls back to an MMS-managed Python if the system Python is too old.
- Discovers `claude` / `codex` / `opencode` in PATH, Homebrew, and NVM; auto-installs missing ones, leaves existing ones alone. Install `agy` separately. **`pi` is mandatory** (Pilot depends on it).
- Installs built-in session assets; does **not** silently overwrite your real provider/account config.
- Writes `~/.config/mms-next/version.json` recording install ref, channel, and UI language.

### 3.3 Right after install, run

```bash
mms doctor            # checkup: Python, CLI discovery, config root, channels
mms models            # what models are visible right now
mms routes            # route resolution
mms exposure          # runtime exposure surface
mms logs              # logs
mms test --provider <id> --cli claude    # real smoke
mms test --provider <id> --cli codex
```

### 3.4 First-run flow

1. Pilot walks you through adding your first channel: service URL and API key.
2. Click "fetch models". Anything the endpoint doesn't return but you know works, fill in by hand.
3. Tick the models you'll actually use. You'll see a redacted preview before saving.
4. Back to the main screen, pick a folder, pick a model, start talking.

Two things worth doing right after: on the models page verify each model's **context length** and **whether it can read images** (the UI labels where each value came from, and offers a one-click fill-back when it disagrees with the catalog), and pick a theme and font in settings.

### 3.5 Three entries, when to use which

| Entry | How to open | What for |
|---|---|---|
| **MMS Pilot** | `mms web --open` | Day-to-day + most configuration: sessions, channels, models, capability toggles, workspace management, updates |
| **`mms` CLI** | `mms` or `mms claude` | Launch native CLIs: Claude / Codex / OpenCode / Pi / agy |
| **Config Web UI** (downgraded) | `mmf config web` | Only what Pilot doesn't cover yet: accounts, preferences, Skill / MCP, migrations, and human-confirm actions. See [`docs/WEB_UI_QUICKSTART.md`](docs/WEB_UI_QUICKSTART.md) |

Once Pilot saves a channel and models, the terminal reads the same data; no need to re-confirm in the config page.

**Pilot's only harness right now is Pi.** Claude / Codex / OpenCode / agy are still CLI-only; they are not yet in Pilot's unified session view.

---

## 4. What Pilot can do

> **TL;DR**: Pilot is a local web workbench; after install, day-to-day work lives here. Sessions, models, files, config, and updates are all in one page.

### 4.1 Sessions

Continuous conversation, resume, stop, fork, archive, export. Switch model and route mid-session while preserving context. Append messages to a queue while a turn is running; refresh and process restart resume the original context.

### 4.2 Models and channels

Set per-model default effort, context length, and image-reading capability. Each value is labeled with its source, and you can one-click fill back from the catalog when it disagrees. **Image-reading is a global truth**: turn it on for a model here, it reads images itself in any harness; turn it off, another model relays.

### 4.3 Files and project materials

Browse directories level-by-level in-app; preview text / Markdown / images; view Git text diffs; reference files with `@`. Local file references use the original path — no copy, no upload, no size cap. Folder references fold cards that are sent to Pi alongside the message.

<details>
<summary><b>Folder references and workspace selection</b></summary>

Drop a folder into the message composer to reference its local path. Use the workspace picker when creating a session. Dropping a folder onto the sidebar does not switch workspaces.

</details>

### 4.4 Terminal sessions enter Pilot (since v4.12.0)

Pi sessions opened via `mms` / `mmf` in the terminal appear **read-only** in Pilot's session list. Choosing "adopt and continue" copies the transcript into a new runtime and continues the conversation; the original terminal file is not touched at the byte level.

If you don't want them visible in Pilot, turn it off under Settings → Usage.

### 4.5 `/btw` side questions (since v4.22.0)

While the main task keeps running, open a **side question** window. The side question reads main context, but its Q&A **does not enter** the main task's context — perfect for "main task is doing one thing, I suddenly want to ask something unrelated".

```text
Main task: "Refactor this module for me"
> /btw Which version, 9.11 or 9.9, suits Claude better?
[Main task keeps running, side question window pops up; close when done]
```

See [`docs/mms-web/HANDOFF-BTW.md`](docs/mms-web/HANDOFF-BTW.md). From v4.22.4 on, the side-question card's fold state persists across refreshes.

### 4.6 Task templates (since v4.10.0)

Goal, examples, variables, Skills, and model requirements. Loading a template fills a draft, the missing pieces are flagged, and it's re-checked before send. Three ready-made templates: organize product requirements, review project changes, analyze a dataset.

Before sharing, known credentials and local paths are scrubbed and a final preview is shown.

### 4.7 Pilot service management commands (since v4.14.0)

Pilot runs in the background; once installed, manage it with:

```bash
mms web status         # list every Pilot on this machine (URL, version, pid, state-root, config-root, source dir)
mms web url            # print the current instance URL only
mms web start          # already running → return URL; not running → start in background and print URL (logs at <state-root>/logs/mms-web.log)
mms web stop           # send SIGTERM only
mms web stop --all     # stop every Pilot on this machine
mms web restart        # stop then start
mms web --open         # foreground start + open browser
```

`mmf web ...` works the same way.

### 4.8 Phone / remote access

Explicitly turning on "let phone / another computer access" exposes a URL and QR code with a token. By default Pilot only listens on localhost, and turning the switch off **does not clear the token** (v4.13.1 security fix — earlier versions cleared the gate when you turned off the switch).

### 4.9 Pilot boundaries

- Listens on localhost only (unless remote access is on); no multi-user auth.
- Config isolation ≠ filesystem sandbox.
- Read-only planning mode is a tool-call layer interception, not an OS-level sandbox.
- File browsing and diff are read-only; no edit / commit / publish buttons.
- Thinking shows only what the upstream actually returns; models don't get content if they don't send it.
- Usage numbers come from Pi, not from vendor billing.

---

## 5. Bot workbench (5.x only)

> **TL;DR**: The Bot workbench is a main addition in 5.x, alongside other preview interactions and changes. You give a goal, the Bot does it and reports back, instead of you clicking around in Pilot yourself. Eight objects: **Bot / Task / Plan / Fleet / Memory / Schedule / Mailbox / Browser capability**. Full semantics in [`docs/mms-web/BOTS.md`](https://github.com/CtriXin/multi-model-switch/blob/dev/docs/mms-web/BOTS.md) (only on the `dev` branch).

<details>
<summary><b>Eight Bot-workbench objects (click for full semantics)</b></summary>

**Bot** — A worker with its own identity, avatar, name (user-chosen), responsibility description, default model (`presetId` can be empty; resolved at execution from the current default preset), and **independent persistent memory**. All Bots default to the shared machine-global `default` workspace, with no per-user directory management. The chat window aggregates past tasks per Bot — it's continuous conversation feel, not a control panel Board.

**Task** — One execution. States: `queued` / `starting` / `running` / `waiting` / `completed` / `failed` / `interrupted` / `cancelled`. The main chat shows only user messages, Bot replies, deliverables, and waiting prompts; CLI diagnostics like `bash`, `exit`, internal `list`/`wait` stay in event data. **Cancel waits for Pi confirmation, ends the Bot's own process after 15 seconds of non-response, and only counts as cancelled if it actually stopped** (v5.0.3 fixed the false positive where `isTurnInterrupted` checked a force-ended tool before checking whether the turn was the latest one).

**Plan** — Plans are extracted from the prompt into persisted, visible, executable objects. Plain `direct-first` requests go straight into persistent sessions without calling a planner; only clear collaboration intent or an explicit `plan-approve` triggers a short planner (20s budget). Plans have a full state machine (`proposed`/`auto`/`approved` → `running` → `merging` → `done`), and steps have per-step state (`pending → ready → running → done|failed|skipped`) with `onFailure` (`retry`/`skip`/`abort`). Dispatch chains cap at five layers; a chain cannot invoke the same Bot twice.

**Fleet (multi-model review under one Bot)** — Key positioning: **multi-model review is one Bot borrowing several brains, not hiring a permanent row of new coworkers**. Default-on, "listen to opinions" intensity, 2 cheap comparisons. Fleet workers can only be created internally by the coordinator; they're throwaway read-only Pi sessions with the chosen model (read/grep/find/ls only, skills and context-file loading disabled). They don't change the main Bot's model or session, and don't write opinions to shared long-term memory. If fewer than 2 models can be auto-selected, fall back to direct and **explicitly say it isn't multi-party review**; if explicitly chosen family or model fails, stop and ask for re-selection — **do not switch family or rename to the same model** (v5.0.5 fixed the bug where Bot session reuse dropped the step model).

**Memory** — Per-Bot, in `state_root/bots/memory/<botId>/memory.json`, separate from Pi sessions and workspaces. At most 100 facts + 200 task summaries, 2000 chars each. New tasks retrieve relevant entries by keyword; **the current user instruction has priority, memory content does not grant extra permissions**. Compaction is soft-triggered: when Pi reports context usage hits the threshold, the next turn calls Pi-native `compact` at a safe idle boundary. When Pi doesn't report usage, the UI shows "unknown" — **no fake hard caps**.

**Schedule** — Independent entity, not a field on task. Has `rule` (`once`/`interval`/`daily`/`weekly`), required IANA `timezone`, single `enabled`, `overlapPolicy` (`skip`/`queue`). On trigger a **new task is created**, so each run has its own transcript and deliverable. Subtle semantics worth getting right:
- Periodic tasks **don't backfill**: if missed by more than one cycle during downtime, only push `nextRunAt` to the next future tick, log `lastSkip`, don't replay the whole backlog; exactly-one-miss triggers immediate catch-up.
- `interval` next time is computed from **the moment it should have fired** (`previous + everySeconds`), not delayed by per-trigger lag.
- "Every day at 9" is still local 9:00 across DST switches.
- **`once` only has one shot — if it didn't run, it isn't consumed**: when the trigger moment can't fire, the schedule parks; `nextRunAt` keeps the past time, and the next tick after it becomes available catches up once and writes a system message on the new task marking it as a delayed catch-up.
- `wakeEnabled` is the Bot-level master switch, layered with per-schedule `enabled`; either being false suppresses trigger.

**Mailbox (Bot-to-Bot communication)** — `dispatch` for dependency-bearing split work; `message`/`reply` for notifications, clarification, follow-up questions; **never impersonates user messages**. Each message has `queued`/`delivered`/`processed`/`waiting`/`failed` receipts; `reply` can only reply to messages addressed to the current Bot; auto back-and-forth exceeding 8 hops pauses to avoid Bots spinning each other.

**Browser capability** — Provided by an external `BrowserProvider`, not built in-house. macOS with Ego installed → hand to Ego; Windows/Linux can use Web Access against a user-explicitly-authorized Chrome/Edge CDP. When no provider is available, show explicit "capability unavailable"; **never silently fall back to a fake in-house browser**.

**Explicitly out of scope**: OS-level Computer Use, desktop window control, generic Connector platform, cloud VM.

</details>

### 5.1 How to start your first Bot

1. Open Bot workbench in Pilot, click "new Bot", give it a name and responsibility.
2. Pick a default model and preset (preset can be empty; resolved at execution from the current default preset).
3. Hand it a goal in the chat window, or write a Plan for it to step through.
4. Want it to run on a schedule: in Bot details, add a Schedule with `rule` and timezone.
5. Want multiple model opinions: just say "use Fleet", or enable the default Fleet in settings.

---

## 6. Command reference

<details>
<summary><b>Full command reference (click to open)</b></summary>

### 6.1 Entry commands

```bash
mms web --open              # open Pilot
mms web status              # list every Pilot on this machine
mms web start               # start Pilot in background
mms web stop                # stop current Pilot
mms web stop --all          # stop all
mms web restart             # stop then start

mms                         # interactive launcher (TUI)
mms claude                  # launch Claude
mms codex                   # launch Codex
mms opencode                # launch OpenCode
mms opencode --profile review           # OpenCode with Review preset
mms opencode --profile agent            # OpenCode with Agent preset
mms --provider <id> codex   # specify channel
mms --account <id> claude   # specify account
mms --export codex          # export env vars only, don't launch
mms --export claude --apply # write env/claude.sh under the config root; source it separately
mms --export opencode
mms pi                      # launch Pi
mms agy                     # launch agy
```

### 6.2 Local command matrix (maintainers)

```text
mms  -> public installed copy   # only for reproducing public-version issues
mmf  -> dev worktree            # daily development
mmg  -> canary worktree         # deprecated
```

Generated by `scripts/link_local_channel_commands.sh` into `~/.local/bin`. `mmd` / `mmm` are retired (v4.13.0); the script removes any wrappers it had previously written. Normal users don't need these; use the installer `--channel` flag.

Startup update reminders default to "remind only, manual confirm": `mmg` checks every launch, `mmf` checks daily, `mms` only reminds daily for the public installed copy.

### 6.3 Diagnostics and config

```bash
mms doctor            # checkup: Python, CLI discovery, config root, channels
mms doctor full       # deeper checkup
mms models            # what models are visible
mms routes            # route resolution
mms exposure          # runtime exposure surface
mms logs              # logs
mms config preferences.help    # preferences help
mms test --provider <id> --cli claude    # real smoke
mms test --provider <id> --cli codex

mmf config web        # config Web UI (downgraded)
mms web status --json # JSON status
```

### 6.4 Upgrade and install

```bash
bash install.sh                           # upgrade (stable)
bash install.sh --channel dev             # upgrade to dev
bash install.sh --ref v4.23.9            # pin to a specific version
bash install.sh --no-launch-web           # don't open Web
bash install.sh --no-shell-rc             # don't touch shell config
bash install.sh --install-cli claude,codex   # control which CLIs get installed
bash install.sh --cleanup-retired-packs   # clean up retired MMS entries
bash install.sh --check                   # check only, don't install
bash install.sh --dry-run                 # print plan only, no file writes
```

</details>

---

## 7. Bundled packs

MMS packs are **session-local** by default: injected per-session, not modifying your global hooks and skill directories.

| Pack | Status | Purpose |
|---|---|---|
| CodeGraph | Built-in passive skill | Prefer symbol graph for code locating, callers/callees, impact analysis |
| TOON | Built-in | Compress agent-facing JSON / status / handoff |
| grill-me | Built-in | Question-by-question clarification of goals, constraints, and acceptance |
| Weber (Web automation bundle) | Built-in | Only exposes the `weber` router; `web-access` and `agent-browser` are internal backends |
| NSR | Explicit `/nsr` manual loop | Drives the original task forward; doesn't register Stop/compact hooks, doesn't run across sessions |
| ECC / OMC | Optional | Claude agent pack; chosen explicitly on the launch confirmation page |
| Figma / Pilot MCP | Detected but off by default | Require explicit `MMS_ENABLE_MCP_FIGMA=1` / `MMS_ENABLE_MCP_PILOT=1` |

**Priority**: global wins. Same-named global hooks / skills take priority; MMS's dynamic version only fills in when missing. `xmem` is global-only — MMS no longer bundles / installs / injects it.

**Retired**: Caveman (compression mode), global token-saver, global TOON, RTK, BrainKeeper, Map auto-index, CodeGraph auto-index — all formerly built-in or optional, now all gone. Caveman's settings field still reads but is ignored.

**Auto-hooks have left the default path**: NSR's Stop / compact hooks, Map / CodeGraph auto-index are all retired. Old wrappers stay as no-op; they don't read or delete existing markers. Explicit `/nsr` and the CLIs still work.

Full pack list and cleanup plan at [`docs/BUNDLED_PACKS.md`](docs/BUNDLED_PACKS.md).

---

## 8. Where config lives

| Path | What |
|---|---|
| `~/.config/mms-next` | **The only config root.** `mms` / `mmf` / `mmg` and Pilot web all land here |
| `~/.config/mms-next/version.json` | Install metadata: `installed_version`, `install_channel`, `release_track*`, `installed_at`, `source`, plus **user preference `preferred_language`** |
| `~/.mms` | Install directory (code copy); `~/.mms/.venv` is its own Python |
| `~/.local/share/mms-web` | Pilot state root: sessions, update cache, Bot data, deliverables |
| `<state>/updates/settings.json` | `channel` — "which line I want to check" |
| `~/.config/mms` | **Legacy, no longer a config source.** Not auto-imported, not fallen back to; only `*-gateway/` runtime session dirs remain |

No entry reads configuration from legacy `~/.config/mms`; retained gateway session directories are not a configuration source.

**Don't mix the two `channel` fields**: `updates/settings.json`'s `channel` means "which line I want to check", `version.json`'s `install_channel` means "which line I'm actually installed on". They are not the same thing. The user switched to preview, checked, but didn't confirm upgrade — `channel` is preview while actual install is still stable; this state is legal.

**Only one write path for config**: write preview DB + publish. Local edits prefer Registry v2: TUI / `mms config` / WebUI first create a DB candidate, on review it's published as `generated/model-registry.latest-approved.json`, and the generated Profile it references is the runtime boundary. Terminal and Pilot read the same published result.

`~/.config/mms-next/preferences.toml` is the user preference allowlist overlay; **agents must not auto-write the real file**. Read, explain, and generate TOML snippets for the user — actual writes go through the human gate.

---

## 9. Troubleshooting

```bash
mms doctor            # first step: checkup
mms models            # is the model list OK
mms routes            # route resolution
mms exposure          # runtime exposure surface
mms logs              # logs
```

<details>
<summary><b>Quick triage for common symptoms</b></summary>

**"Can't fetch the model list, but I know the model works"**
Can't fetch ≠ doesn't work. Fill it in by hand into the current channel. A remote `/models` returning empty doesn't mean the model is broken; hide / capability / fallback are local policy and shouldn't be deleted because of one missing fetch.

**"Which toggle is Thinking?"**
The `reason` / reasoning column in the model table is **capability metadata**, not a launch switch. Whether thinking actually turns on at launch depends on the provider/model compatibility profile (`thinking.supported` / `default_enabled`), effort config, and runtime `thinking_mode`. If you see a stored level in Pilot but the actual request doesn't carry thinking — check whether the model on this channel actually supports that level; don't trust the UI.

**"Model returns 403 on one path but works on another"**
That's normal. `Anthropic /v1/messages` and `OpenAI /v1/chat/completions` are not equivalent transports; some providers only expose certain models on the Claude-compatible path (e.g. `kimi-for-coding` returns 403 on chat/completions but is fine on the Anthropic path). MMS prefers `/v1/messages` by default when the route supports it.

**"Clicked 'check for updates' and nothing happens"**
Check whether `~/.local/share/mms-web/updates/check.json` exists, and whether there are permission issues.

**"Dragging a folder hangs for seconds before arriving at the target directory"**
This happened before v4.18.0, because folder search ran inside the global write lock. Fixed in v4.18.0+.

**"Pilot startup takes a few seconds and stutters"**
Early versions ran synchronous network probes on the launcher startup hot path — 4 seconds to launch. Now it's file cache + parallel background prewarm, should be < 1s. If it's still slow, run `mms doctor` to see what's blocking.

</details>

**Windows-specific machine issues**: you can have the local AI in Pilot diagnose this machine first; then decide how to file: if you have a GitHub account, fork and PR; if not, generate a redacted Markdown report and a `.patch` file and have a maintainer file it for you. See [`docs/mms-web/WINDOWS-CONTRIBUTING.md`](docs/mms-web/WINDOWS-CONTRIBUTING.md). **Don't** send API keys, `credentials.sh`, the whole config directory, or unredacted sessions.

---

## 10. FAQ

<details>
<summary><b>Q: I only have one New API platform with many models — can MMS handle it?</b></summary>

Yes. Treat New API as a provider: fill in base URL / key / models endpoint, then have the Web UI fetch models. Models the endpoint doesn't return but you know work, add as extra/manual. Hide / capability / fallback are local policy; don't blindly delete them just because one remote fetch was missing.

</details>

<details>
<summary><b>Q: Which toggle in the Web UI is Thinking?</b></summary>

The `reason` / reasoning column is **model capability metadata**. Whether Thinking is actually turned on at launch depends on the provider/model compatibility profile (`thinking.supported` / `default_enabled`), effort config, and runtime `thinking_mode`.

</details>

<details>
<summary><b>Q: Where did Caveman go? I used to pick Off/Light/Standard/Full on the launch page.</b></summary>

Caveman (compressed communication mode) has been globally retired; it is no longer installed, displayed, or injected by MMS, and old config fields are ignored. If you like lightweight communication, use TOON to compress agent-facing JSON / status; the effect is similar without affecting the provider's actual response.

</details>

<details>
<summary><b>Q: What should I install on multiple machines?</b></summary>

To keep multiple machines aligned, install the same channel; pin to the same version with `--ref <commit-or-tag>` when needed. Stable (default) suits daily use; Dev suits users who want the Bot workbench. MMS defaults to `~/.mms`; **don't let two channels cover the same `~/.mms`** — if you really want them side by side, use a VM, separate users, or an explicit install prefix.

To sync your home machine with your work machine: prepare worktrees and run `scripts/link_local_channel_commands.sh`; it writes the three commands into `~/.local/bin`. Normal users don't need this script.

</details>

<details>
<summary><b>Q: Is Pi mandatory?</b></summary>

Yes — **Pi is mandatory** (Pilot depends on it). The installer refuses to continue if it can't detect Pi, rather than installing a crippled version. Other CLIs (claude / codex / opencode) auto-install when missing; existing ones stay untouched. Install agy separately.

On Windows, install Pi separately: `npm.cmd install --global @earendil-works/pi-coding-agent`, then `pi.cmd --version` to verify.

</details>

<details>
<summary><b>Q: I installed 5.x — how do I downgrade to 4.x?</b></summary>

Switching back to stable in Pilot doesn't downgrade. You must re-run the installer: `bash install.sh --channel stable`. Config and session history are preserved.

</details>

<details>
<summary><b>Q: I installed 5.x — where is the Bot workbench?</b></summary>

Click the Bot workbench icon in the Pilot main UI (near the session list). First time open will walk you through creating your first Bot.

</details>

<details>
<summary><b>Q: After turning on remote access, will turning it off clear the token?</b></summary>

No (v4.13.1 fix). Under `--listen all`, turning off the "let phone access" switch no longer clears the token gate. Earlier versions cleared the gate when you turned off the switch — anyone on the network could come in without a token. The default loopback mode and the LAN mode turned on in settings are unaffected.

</details>

<details>
<summary><b>Q: Can I sync a `mmf` session from the terminal into Pilot?</b></summary>

Since v4.12.0, yes. Pi sessions opened via `mms` / `mmf` in the terminal appear **read-only** in Pilot's session list. Choosing "adopt and continue" copies the transcript into a new runtime and continues the conversation; the original terminal file is not touched at the byte level. If you don't want to see them in Pilot, turn it off under Settings → Usage.

</details>

<details>
<summary><b>Q: When I launch the TUI it takes a few seconds to appear — is it broken?</b></summary>

No, but it shouldn't take seconds. Early versions ran synchronous network probes on the launcher startup hot path — 4 seconds. Now it's file cache + parallel background prewarm, < 1s. If it's still slow, run `mms doctor` to see what's blocking. Stuffing qwen/kimi into `CLI_NAMES` when they're no longer maintained also slows launch — that's a known perf trap, fixed.

</details>

<details>
<summary><b>Q: What are Skills in task templates? I filled them in but they don't seem to work.</b></summary>

Skills are multi-selected by searching the current workspace, `/skill:name` completes, and the content is sent to Pi with the message. Skills loading/call records don't guarantee the model follows instructions; when indirect tool reads can't be reliably attributed, the UI says "no evidence" — it doesn't fabricate.

</details>

<details>
<summary><b>Q: Pilot session files keep growing — how do I clean up?</b></summary>

Archive / delete in the session menu; archived sessions can be restored from the archive list. `.pilot/attachments` import copies unused for 30 days are auto-cleaned (since v4.12.0). Pilot's default state root is `~/.local/share/mms-web`, containing session and Bot runtime data; model and channel configuration lives in `~/.config/mms-next`. Prefer session management in the UI. Before disk cleanup, stop Pilot, confirm the actual state root, and back it up. Removing the state root does not reset model configuration.

</details>

---

## 11. Safety baseline

- **Real `HOME` and global OAuth state are protected surfaces, not fallback pools.** When provider / account fails, fail closed in the current runtime — do **not** silently switch to another global account.
- When the route supports it, Claude semantics prefer `Anthropic /v1/messages`; `OpenAI /v1/chat/completions` is a fallback, not an equivalent default.
- Before writing config, produce preview / diff / backup / audit evidence; **no second write path that bypasses review**.
- Legacy `~/.config/mms/**` (especially Claude-related fields) remains human-gated; Pilot does not write to it.
- Terminal sessions entering Pilot are **read-only** transcript copies; the terminal's original file is not modified.
- Remote access requires a token, and turning off the switch no longer clears the token (v4.13.1).

---

## 12. Version history (v3 → v4 → v5 milestones)

<details>
<summary><b>v3.x → v4.0.0 (2026-09-09): Pilot first release</b></summary>

The first major version of MMS Pilot (the local web client). The v3-era "pure TUI + CLI" expanded to a "launcher + Pilot + built-in session assets" three-layer architecture. Through v4.x to v4.23.x the line iterated rapidly.

**v4.0.0 key capabilities**: Pi RPC sessions, continuous conversation, resume/stop/fork/archive/export; per-model combined channel selection, favorites, effort; model fetch and diff confirmation; Skills and command hints; workspace folder expansion and local file original-path reference; per-turn process folding; in-session model/route switch with context preserved.

</details>

<details>
<summary><b>v4.x main feature milestones</b></summary>

| Version | Date | Key capability |
|---|---|---|
| v4.1.0 | 09-09 | Deliverable preview, selection, version comparison |
| v4.2.0 | 09-09 | Project materials and per-message source records |
| v4.3.0 | 09-09 | New-user hover guidance and feature help |
| v4.4.0 | 09-09 | Settings popup, theme palette, fonts |
| v4.5.0 | 09-09 | Inline files, project search, capability review |
| v4.6.0 | 09-09 | Connect service before onboarding tutorial starts |
| v4.7.x | 09-09 | Out-of-the-box task Skills and folder references |
| v4.8.x | 09-09 | Quick model selection |
| v4.10.0 | 09-10 | Connect-flow hover guidance, task templates v2, three ready-made templates |
| v4.11.0 | 09-10 | Unified config root `~/.config/mms-next`, consistent across entries |
| v4.12.0 | 09-10 | Terminal sessions enter Pilot, automatic config consolidation on legacy machines, K3 context window policy, Pilot UX closure, LAN write operations |
| v4.13.0 | 09-10 | Single config root (`mmd`/`mmm` retired), installer no longer spawns a duplicate Pilot |
| v4.13.1 | 09-11 | `--listen all` switch-off no longer clears the token |
| v4.14.0 | 09-11 | `mms web status/url/start/stop/restart` service management |
| v4.16.0 | 09-12 | CI pytest gate, k3-single-truth, ctrl-c cleanup |
| v4.17.0 | 09-12 | Vision relay, finish legacy root retirement |
| v4.18.0 | 09-12 | Drag-folder-to-locate |
| v4.20.0 | 09-13 | **Windows Native Preview** |
| v4.21.x | 09-13~14 | Windows-only fix line (v4.21.0 ~ v4.21.14) |
| v4.22.0 | 09-15 | **`/btw` side questions** (terminal Pi and Pilot) |
| v4.22.x | 09-16 | Remote access preserves login, 4.x↔5.x channel switch gate, blocked reasons, workspace dialog autofocus |
| v4.23.0~4 | 09-17~18 | T8g config/discovery out of mutation lock, T8h 5.x-on-stable channel line truth, Stable focus feedback, folder real-path regression |

Full changes at [`docs/mms-web/CHANGELOG.md`](docs/mms-web/CHANGELOG.md) and per-version `docs/mms-web/RELEASE-v*.md`.

</details>

<details>
<summary><b>v5.0.0 (2026-09-16): Bot workbench</b></summary>

The Bot workbench is a main addition in 5.x, alongside other preview changes. Check Git history and Releases to confirm shared fixes. From v5.0.0 through v5.1.7:

| Version | Date | Key capability |
|---|---|---|
| v5.0.0 | 09-16 | Bot workbench first release: T1~T4 UI + coordinator + plan layer |
| v5.0.1 | 09-16 | Fix settings scrollbar occlusion and Bot interaction/popover styles |
| v5.0.2 | 09-16 | Bot T5/T6/T7 packets, grok TUI launcher |
| v5.0.3 | 09-17 | T7e interrupted-turn no longer leaves blank turns |
| v5.0.4 | 09-17 | T5a/T5b/T5c Bot periodic wake-up |
| v5.0.5 | 09-17 | T5d plan-step model actually applied |
| v5.0.6 | 09-17 | thinking-effort picker moved to composer bar |
| v5.1.0 | 09-17 | Many verified-stable fixes into Preview; sidebar double-click rename |
| v5.1.1 | 09-17 | Rename dialog opens with focus |
| v5.1.2 | 09-17 | Fleet composer reachable + rename input preserved |
| v5.1.3 | 09-17 | Sidebar version number opens update dialog |
| v5.1.4 | 09-17 | Confirm update is its own step |
| v5.1.5 | 09-17 | Mobile popover docks as bottom sheet |
| v5.1.6 | 09-17 | Interaction fixes |
| v5.1.7 | 09-18 | T8i real-wiring regression and dual-line gate |

</details>

<details>
<summary><b>Canary is deprecated — don't use it</b></summary>

Canary (`mmg` / `canary` branch) has been deprecated since 2026-06. `mmg` is still usable in the local command matrix, but the corresponding worktree path may have been cleaned up (see `docs/RELEASE_CHANNELS.md` current state). New features no longer enter this line; maintainers no longer keep the canary channel alive.

</details>

---

## 13. Doc map

| Document | When to use | Notes |
|---|---|---|
| [`docs/AI-ONBOARDING.md`](docs/AI-ONBOARDING.md) | **AI / new contributor**: project overview, code map, gates, mistakes already made | 384 lines, 10 real-incident entries |
| [`docs/mms-web/GETTING-STARTED.md`](docs/mms-web/GETTING-STARTED.md) | Pilot install and usage detailed walkthrough | |
| [`docs/mms-web/FEATURES.md`](docs/mms-web/FEATURES.md) | Pilot feature list | **Top still says "not yet publicly released" — outdated**, but the feature inventory itself is mostly reliable |
| [`docs/mms-web/CHANGELOG.md`](docs/mms-web/CHANGELOG.md) + [`docs/mms-web/RELEASE-v*.md`](docs/mms-web/) | What each version actually changed | More accurate than any summary |
| [`docs/mms-web/API.md`](docs/mms-web/API.md) | Pilot local API v1 | |
| [`docs/mms-web/HANDOFF-BTW.md`](docs/mms-web/HANDOFF-BTW.md) | `/btw` side-question implementation details | |
| [`docs/install/WINDOWS.md`](docs/install/WINDOWS.md) | Windows from-scratch 6-step guide | Native Preview |
| [`docs/mms-web/WINDOWS-CONTRIBUTING.md`](docs/mms-web/WINDOWS-CONTRIBUTING.md) | Reporting and contributing flow for Windows machine-specific issues | |
| [`docs/WEB_UI_QUICKSTART.md`](docs/WEB_UI_QUICKSTART.md) | Config Web UI walkthrough | |
| [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md) | Channel contract and install flags | **Version-track table `3.4/3.5/3.6` is outdated**; channel definitions and install commands still valid |
| [`docs/BUNDLED_PACKS.md`](docs/BUNDLED_PACKS.md) | Built-in packs and retired install entries | |
| [`docs/MMS_USER_PREFERENCES.md`](docs/MMS_USER_PREFERENCES.md) | What can go in `preferences.toml` | |
| [`docs/MODEL_CONFIG_CONTRACT.md`](docs/MODEL_CONFIG_CONTRACT.md) | Config contract (model-routes / lineup / profile / policy) | |
| [`docs/AGENT_GUARDRAILS.md`](docs/AGENT_GUARDRAILS.md) | High-risk-surface constraints | **Required reading for AI** |
| [`docs/MAINTAINERS.md`](docs/MAINTAINERS.md) | Maintainer entry, worktree flow, release checklist | Normal users don't need this |
| [`docs/mms-web/BOTS.md`](https://github.com/CtriXin/multi-model-switch/blob/dev/docs/mms-web/BOTS.md) | Bot workbench full semantics | **Only on `dev` branch**, required reading for 5.x users |
| [`docs/mms-web/bot-work/`](docs/mms-web/bot-work/) | Bot workbench work packets (T1~T8i) | |
| [`docs/legacy/`](docs/legacy/) | Historical archive | |

**Before writing code, verify**: any version number, branch relationship, or "current state" claim in any document should be cross-checked against `lib/mms_version.py`, `git log`, and the most recent `RELEASE-v*.md`.

---

## 14. Release checklist (maintainers)

<details>
<summary><b>Release flow (click to open)</b></summary>

1. Pick verified changes from `dev` to enter the Stable candidate; once the sync window ends, `main` itself is Stable/default.
2. Run `bash install.sh --check`, `mmf config check --json`, key launcher smokes, Web UI save-plan smoke.
3. Update this README's version-history section (§12) and the matching `docs/mms-web/RELEASE-v*.md`.
4. Bump version: **one merged PR = one patch version**; pure-doc packages don't bump. **Authors don't touch the version file**; the merger overwrites it at merge time. Release notes and the version bump go in a separate commit; don't mix them with the author's changes — preserve their authorship.
5. Tag, push GitHub Release: `gh release create v<version> --verify-tag --notes-file docs/mms-web/RELEASE-v<version>.md --latest` (4.x) / `--prerelease` (5.x).
6. For multi-machine sync (home/work), record the recommended pinned commit.

Detailed flow at [`docs/MAINTAINERS.md`](docs/MAINTAINERS.md) → "Versioning and release" section.

</details>

---

## License

Apache-2.0
