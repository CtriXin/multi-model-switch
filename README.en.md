# Multi-Model Switch (MMS)

[简体中文](./README.md) · [![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**MMS runs AI coding tools on your own machine, against your own model services.**

It handles the annoying part that happens before anything starts. You have several providers, a pile of API keys, dozens of model names, separate config for `claude` and `codex` and `opencode`, and a nagging worry that one failure will quietly fall back to your real global account. MMS puts all of that in one place so you can see, before launching, which model you are using, which route it takes, and whose quota it spends.

After installing you get two entry points: **MMS Pilot** (a workbench in your browser, where day-to-day work happens) and the **`mms` command line** (launching the native CLIs). Both read the same configuration.

![MMS launcher tree](docs/images/mms-launcher-tree-en.svg)

---

## Install

macOS / Linux, one command:

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash
```

It asks once whether to open Pilot. Press Enter; the browser opens, the service keeps running in the background, and the installer exits.

**Windows** is a Native Preview with a different procedure. The full from-scratch walkthrough is in [`docs/install/WINDOWS.md`](docs/install/WINDOWS.md).

The installer asks nothing that changes what gets installed: stable channel by default, Chinese UI (add `--lang en` for English), and `~/.local/bin` written into your shell PATH. `pi` is mandatory because Pilot depends on it; missing `claude` / `codex` / `opencode` are installed for you, and anything already present is left alone.

**Upgrading is the same command again.** But if Pilot is running, the installer stops and refuses rather than closing it for you: update from inside Pilot, or run `mms web stop` (`--all` if you have several instances), then re-run the install command.

Other install modes (preview line, pinned versions, silent install for CI) are in [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md).

## The first five minutes

1. Pilot walks you through your first channel: service URL and API key.
2. Fetch the model list. Anything the endpoint does not return but you know works, add by hand.
3. Select the models you will actually use. You get a redacted preview before saving.
4. Back on the main screen, pick a folder, pick a model, start talking.

Two things worth doing right after: check each model's **context length** and **whether it can read images** on the model page (the UI labels where each value came from, and offers a one-click fill-back when it disagrees with the catalog), and pick a theme and font in settings.

## What it manages for you

**One entry point for several CLIs.** `mms` opens the TUI, or go direct with `mms claude` / `mms codex` / `mms opencode`.

**Model sources are visible before launch.** Provider, account, route, fallback, thinking, vision, and cache-sensitive transport are all on the selection screen, not a surprise after startup.

**Isolated but resumable.** Claude and Codex sessions run in a MMS-managed HOME and config seed, which keeps your real global config cleaner while resume keeps working. On failure it fails closed inside the current runtime; it does **not** quietly fall back to your global OAuth account.

**Capability packs are per-session.** CodeGraph, TOON, grill-me, and Weber (web automation) are session-local by default and do not touch your global hooks.

**Diagnose before blaming the model.** When something errors, look at the route, protocol, request path, key, and runtime exposure first. `mms doctor`, `mms exposure`, and `mms logs` exist for exactly that.

## Three entry points, and when to use which

| | How to open | What for |
|---|---|---|
| **MMS Pilot** | `mms web --open` | Daily work, and nearly all configuration: sessions, channels, model lists, capability switches, work folders, updates |
| **`mms` CLI** | `mms` or `mms claude` | Launching the native CLIs: Claude, Codex, OpenCode, Pi, agy |
| **Config Web UI** (demoted) | `mmf config web` | Only what Pilot has not covered yet: accounts, preferences, Skill / MCP, migrations, human-gated actions. Walkthrough: [`docs/WEB_UI_QUICKSTART.md`](docs/WEB_UI_QUICKSTART.md) |

Once Pilot saves a channel or model, the terminal reads the same thing. You do not need to confirm it again in the config page.

Pilot's session harness is currently **Pi**. Claude, Codex, OpenCode, and agy still launch from the command line only; they are not in Pilot's unified session view yet.

Common commands:

```bash
mms web --open              # open Pilot
mms                         # interactive launcher
mms claude                  # launch Claude
mms codex                   # launch Codex
mms opencode --profile review
mms --provider <id> codex   # pick a channel
mms --account <id> claude   # pick an account
mms --export codex          # export env vars only, do not launch
mms doctor full
mms logs
```

## What Pilot can do today

Sessions: continuous conversation, resume, stop, fork, archive, export, switching model and channel mid-session while keeping context, a follow-up queue for messages sent while it is working, and the same context after a browser refresh or a process restart.

Visible process: streaming replies, the Thinking the provider actually returned, tool arguments and results, tool images, and native confirm / select / input interactions. Context share, tokens, and cache all live in one place.

Files: an in-app directory browser, text / Markdown / image preview, Git text diffs, and `@` references. Referencing a local file uses the original path directly, with no copying, no upload, and no size gate.

Model capabilities: per-model default effort, context length, and image reading. Every value is labelled with where it came from, and can be filled back from the catalog in one click. **The image switch is global truth**: turn it on for a model and it reads images itself in any harness; turn it off and another model relays for it.

Access from a phone or another computer: explicitly enabled, then you get an address and a QR code with a token. Local-only by default.

The complete inventory and its limits are in [`docs/mms-web/FEATURES.md`](docs/mms-web/FEATURES.md).

**Limits worth knowing up front**: it listens on local addresses only and has no remote multi-user authentication; config isolation is not a filesystem sandbox; read-only planning intercepts at the tool-call layer, not at the OS level; file browsing and diffs are read-only, with no edit, commit, or publish buttons. To give it to someone else, have them install it on their own machine with their own model services.

## Two release lines

Since 2026-09-16, `main` and `dev` are two **long-lived parallel** lines, not "a stable branch and a development branch".

| Line | Version | Install flag | Who for | What is in it |
|---|---|---|---|---|
| Stable | 4.23.x | `--channel stable` (default) | Anyone using this as a daily tool | Settled features; only fixes and verified capabilities |
| Preview | 5.1.x | `--channel dev` | People who want new things and can take some turbulence | **Everything** in stable, plus the Bot workbench still being polished |

Every change on `main` flows into `dev` by default, so the preview line is always a superset of stable. "I moved to 5.x and lost a 4.x fix" cannot happen.

**What 5.x adds is the Bot workbench**: you hand over a goal and an executor with a name, a memory, scheduled wake-ups, the ability to delegate, and the option to ask a few other models for a second opinion goes and finishes it. A normal Pilot session is "I am doing this now"; a Bot is "here is the goal, report back". See [`docs/mms-web/BOTS.md`](https://github.com/CtriXin/multi-model-switch/blob/dev/docs/mms-web/BOTS.md) (that document lives on the `dev` branch only).

The two lines **cannot coexist** on one machine. To switch, re-run the installer with the matching `--channel`; config, channels, and session history all live in the same config root and are not cleared.

> **One asymmetry to note.** Pilot's version-and-updates panel lets you pick the 4.x stable or 5.x preview channel. Going 4.x → 5.x completes inside Pilot. But **once 5.x is installed, selecting the stable channel alone will not take you back to 4.x** — Pilot only ever offers versions higher than the current one. Returning to stable requires re-running the installer with `--channel stable`; config and history are preserved.

## Where configuration lives

The single config root is `~/.config/mms-next`. `mms`, `mmf`, `mmg`, and the Pilot web page all land on it, so one change takes effect in both the terminal and the browser. The legacy `~/.config/mms` has left the config sources and is no longer read by any entry point; all that remains there are runtime session directories such as `*-gateway/`.

There is exactly one write path for configuration: **write a preview DB, then publish**. Local edits go through Registry v2: the TUI, `mms config`, or the WebUI first creates a DB candidate; once reviewed it is published as `generated/model-registry.latest-approved.json`, and the generated Profile it references is the runtime boundary. The terminal and Pilot read the same published result, so both see the same channels, models, and capabilities. There is no second write path that bypasses review.

Other locations: the install directory is `~/.mms` (with its own `.venv`); Pilot's sessions, update cache, and artifacts are under `~/.local/share/mms-web`; install metadata (version, channel, UI language) is recorded in `~/.config/mms-next/version.json`.

## When something breaks

```bash
mms doctor            # Python, CLI discovery, config root, channels
mms models            # which models are currently visible
mms routes            # route resolution
mms exposure          # runtime exposure surface
mms logs
mms test --provider <provider-id> --cli claude    # real smoke test
```

A few common symptoms:

**"The model list will not fetch, but I know this model works."** Add it by hand to the current channel. A `/models` endpoint that omits a model does not prove the model is unusable; hiding, capability flags, and fallback are local policy and should not be deleted because one fetch came back short.

**"Which checkbox is Thinking?"** The `reason` / reasoning column in the model table is **capability metadata**, not a launch switch. Whether Thinking is actually on at launch depends on the provider/model compatibility profile (`thinking.supported` / `default_enabled`), the effort configuration, and the runtime's `thinking_mode`.

**"This model 403s on one path and works on another."** Expected. `Anthropic /v1/messages` and `OpenAI /v1/chat/completions` are not equivalent transports, and some providers only expose certain models on the Claude-compatible path. MMS prefers `/v1/messages` when the route supports it.

**"I clicked check-for-updates and nothing happened."** Look for `~/.local/share/mms-web/updates/check.json`.

**A Windows-specific problem on your own machine**: you can ask the local AI inside Pilot to diagnose it first, then follow [`docs/mms-web/WINDOWS-CONTRIBUTING.md`](docs/mms-web/WINDOWS-CONTRIBUTING.md) to file a report or a PR. **Do not** send API keys, `credentials.sh`, your whole config directory, or un-redacted sessions.

## Security lines that do not move

- Your real `HOME` and global OAuth state are a protected surface, not a fallback pool. When a provider or account fails, MMS fails closed inside the current runtime rather than quietly switching to another global account.
- Claude semantics prefer `Anthropic /v1/messages` when the route supports it. `chat/completions` is a fallback, not an equivalent default.
- Writing configuration produces a preview, a diff, a backup, and an audit record first.
- The legacy `~/.config/mms/**`, especially Claude-related fields, stays human-gated. Pilot does not write it.

## Documentation

- [`docs/AI-ONBOARDING.md`](docs/AI-ONBOARDING.md) — **for AI agents and new maintainers**: the whole picture, code map, gates, and mistakes already made
- [`docs/mms-web/GETTING-STARTED.md`](docs/mms-web/GETTING-STARTED.md) — installing and using Pilot
- [`docs/mms-web/FEATURES.md`](docs/mms-web/FEATURES.md) — Pilot features and limits
- [`docs/mms-web/CHANGELOG.md`](docs/mms-web/CHANGELOG.md) — what each version actually changed
- [`docs/mms-web/API.md`](docs/mms-web/API.md) — Pilot local API v1
- [`docs/install/WINDOWS.md`](docs/install/WINDOWS.md) — Windows Native Preview walkthrough
- [`docs/RELEASE_CHANNELS.md`](docs/RELEASE_CHANNELS.md) — channel contract and install flags
- [`docs/BUNDLED_PACKS.md`](docs/BUNDLED_PACKS.md) — bundled capability packs and retired install paths
- [`docs/MMS_USER_PREFERENCES.md`](docs/MMS_USER_PREFERENCES.md) — what `preferences.toml` accepts
- [`docs/MODEL_CONFIG_CONTRACT.md`](docs/MODEL_CONFIG_CONTRACT.md) · [`docs/AGENT_GUARDRAILS.md`](docs/AGENT_GUARDRAILS.md) — config contract and high-risk surfaces
- [`docs/MAINTAINERS.md`](docs/MAINTAINERS.md) — maintainer entry point, worktree flow, release checklist
