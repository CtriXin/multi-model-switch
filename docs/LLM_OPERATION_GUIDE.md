# MMS LLM Operation Guide

> Purpose: give any third-party or user-owned LLM a safe operating boundary before it edits MMS.
> Read this before changing `multi-model-switch`, generated install files, or any real `~/.config/mms/**` state.

## One-Line Rule

MMS is a launcher/session/runtime manager. Prefer docs, tests, declarative profiles, and user overlays; do not casually change launcher, routing, bridge, account, config, or real-home auth behavior.

## First Prompt To Give Your LLM

```text
You are modifying MMS. First read docs/LLM_OPERATION_GUIDE.md, docs/AGENT_GUARDRAILS.md, docs/MMS_USER_PREFERENCES.md, docs/PROVIDER_PROFILES.md, and docs/MODEL_CONFIG_CONTRACT.md. Do not write ~/.config/mms/** automatically. If a change touches launcher/routing/bridge/account/config/Claude/OAuth/real HOME/provider fallback behavior, stop and explain the blast radius before editing.
```

After install, the copied guide usually lives at:

```text
~/.mms/docs/LLM_OPERATION_GUIDE.md
```

## Safe-To-Edit By Default

These areas are usually safe when the requested scope is clear and the LLM keeps changes small:

| Area | Examples | Required check |
| --- | --- | --- |
| Docs | `docs/*.md`, README links, install notes | no secrets; keep public/private boundaries clear |
| Tests | `tests/*.py` for existing behavior | run targeted tests |
| Local regression notes | `.ai/regression-reports/*.md` | keep local-only if ignored |
| Declarative built-in provider profiles | `config/provider-profiles.json` | update `docs/PROVIDER_PROFILES.md`; run profile tests |
| Non-behavioral comments | comments near complex code | do not hide behavior changes in comments |
| Session asset docs | `vendor/*/README.md`, skill docs | do not copy secrets or real host paths |

Even in safe areas, never mix unrelated dirty files into a commit.

## Prefer Overlay Instead Of Code

Use overlays when the request is about preferences, visibility, local provider quirks, or user-specific paths.

| Need | Preferred surface | LLM action |
| --- | --- | --- |
| Daily launch preferences | `~/.config/mms/preferences.toml` allowlist | generate snippet; ask human before writing |
| Thinking / effort / Caveman / bypass / agent pack defaults | `preferences.toml` | generate snippet; do not edit code |
| Disable selected session skills/MCP/hooks | `[session_surfaces.disabled]` in `preferences.toml` | generate snippet; ask human to apply |
| Override session asset roots | `[assets.roots]` in `preferences.toml` | generate snippet; no secret paths in public docs |
| Provider-specific request schema differences | `config/provider-profiles.json` for built-in behavior; `~/.config/mms/provider-profiles.json` for human local overlay | built-in changes need tests/docs; real overlay is human-gated |
| Model visibility / favorite / project policy | `model-policy.json` | preserve human policy; do not overwrite blindly |
| Team/power-user full runtime override | `override.toml` | human-gated; explain risk and backup path |

`preferences.toml` intentionally ignores credentials, provider routes, account identity, proxy, OAuth, real `HOME`, real `XDG_*`, and Claude config fields.

## Human Gate: Never Auto-Write

The real MMS config tree is human-only:

```text
~/.config/mms/config.toml
~/.config/mms/override.toml
~/.config/mms/preferences.toml
~/.config/mms/credentials.sh
~/.config/mms/usage.json
~/.config/mms/accounts/**
~/.config/mms/env/**
~/.config/mms/provider-profiles.json
~/.config/mms/model-profiles.json
```

LLMs may read, compare, explain, and produce a manual diff or TOML snippet. They must not persist changes without explicit human confirmation.

Required flow for any real config write:

```text
plan -> backup -> human double check -> audited write -> post-write human double check
```

For Claude-related MMS config, the rule is stricter: do not auto-write even if the LLM thinks the fix is obvious. Stop and hand the exact path, fields, old value, new value, and risk to the human.

## Stop And Ask Before Editing

Stop before editing when the change can affect any of these surfaces:

| Surface | Why it is risky |
| --- | --- |
| `mms_core.py` | source/config/model selection and route export semantics |
| `mms_launchers.py` | actual CLI launch env, HOME/XDG isolation, session assets, bridge choice |
| `mms_tui.py` | selection result shape and user confirmation semantics |
| `mms_bridge.py` | protocol translation, auth headers, provider fallback, error semantics |
| `mms_account_state.py` | account status, auth state, Permission denied paths |
| `mms_session.py` / `mms_session_index.py` | session restore and isolation state |
| `mms_adapter_registry.py` | CLI/provider capability mapping |
| `mms` entrypoint | user-facing launcher behavior |
| retired `ccs` / `mmc` cleanup logic | must not reintroduce legacy entrypoints or `~/.config/ccs` fallback |

Before proceeding, answer:

1. Which layer changes: display, selection, runtime decision, launcher, bridge, config, or account state?
2. Does the default launch path change?
3. Does this change provider/account priority, fallback, or model visibility?
4. Does any failure path read real-home auth-bearing state?
5. What targeted smoke test proves the selected model/source is the one actually launched?

## Hard No Without Explicit Human Direction

Do not do these as a convenience fix:

- silently fallback to global OAuth or real-home auth after a provider/account failure
- read `~/.claude.json`, `~/.codex/auth.json`, Keychain OAuth, `~/.gemini`, or other auth-bearing state as retry input
- write Claude config, Claude account fields, `proxy`, `no_proxy`, `timezone`, `home_dir`, or default Claude source selection
- change provider/account priority or role semantics without a migration note and validation
- convert cache-sensitive Anthropic `/v1/messages` routes back to OpenAI `/v1/chat/completions` silently
- probe `/models` for sensitive relay/private providers that intentionally use manual model lists
- reintroduce `ccs`, `~/.config/ccs`, or `CCS_*` compatibility
- install global hooks or modify global shell/runtime config without telling the human first
- hide upstream auth/account failures behind generic errors; preserve useful provider/account/upstream context

## Provider And Protocol Changes

For vendor-specific behavior, prefer data over launcher branches:

- Add request body/header/model differences to `config/provider-profiles.json` when it is a built-in public behavior.
- Use `~/.config/mms/provider-profiles.json` or `~/.config/mms/model-profiles.json` only as human-managed local overlays.
- Update `docs/PROVIDER_PROFILES.md` and `docs/MODEL_CONFIG_CONTRACT.md` when the contract changes.
- Run provider-profile tests and at least one relevant route/bridge smoke if the behavior affects real requests.

Cache-sensitive dual-protocol rule:

- If a route supports `anthropic_messages`, keep Claude-style traffic on Anthropic `/v1/messages` by default.
- Treat OpenAI `/v1/chat/completions` as an audited fallback with a visible fallback reason, not a silent default.

## Error Message Changes

MMS errors should help the user identify the failing layer:

| Problem | Message should identify |
| --- | --- |
| Provider rejected key | provider id, selected account/source, upstream auth status when safe |
| Account missing/disabled | account id/source, selected CLI, no global OAuth fallback |
| Bridge translation failed | protocol, request path, model id, safe fallback reason |
| Permission denied | whether it is file permission, account permission, upstream 401/403, or CLI sandbox |
| Language preference | use MMS language setting for user-facing MMS messages; do not force Chinese globally |

Do not print secrets, full API keys, tokens, cookies, or raw auth headers.

## Minimum Validation Matrix

Pick the smallest set that matches the changed surface:

| Changed surface | Minimum validation |
| --- | --- |
| Docs only | `git diff --check`; verify links/paths exist |
| Install script | `bash -n install.sh`; targeted installer tests |
| Python code | `python3 -m py_compile <changed files>` |
| Provider profiles | `python3 -m pytest -q tests/test_provider_profiles.py` |
| Launcher/session hooks | hook render smoke + launcher/session tests |
| Bridge/protocol | bridge tests + one real/simulated request-path smoke |
| Config/account logic | config tests + prove no real `~/.config/mms/**` auto-write |
| High-risk files | targeted tests, then widened regression; write a regression report |

After substantive changes, write a local regression report under:

```text
.ai/regression-reports/YYYY-MM-DD-<short-slug>.md
```

## Commit Rules For LLMs

For every agent-created commit:

- keep the commit scoped to the requested change
- do not include unrelated dirty files
- use command-scoped identity, not global `git config`
- email format: `<modelName>@<familyName>.com`, for example `gpt-5@openai.com`
- add trailers: `Agent-Model`, `Agent-Family`, `Agent-Session`, and `Agent-Run` when available

Example:

```bash
git -c user.name="Codex" -c user.email="gpt-5@openai.com" commit
```

## Quick Decision Tree

```text
Can this be docs/tests/profile data only?
  yes -> do that, validate targeted tests.
  no  -> continue.

Is it user-specific preference or local provider behavior?
  yes -> generate overlay snippet; human applies real ~/.config/mms/** write.
  no  -> continue.

Does it touch launcher/routing/bridge/account/config/Claude/OAuth/real HOME?
  yes -> stop, explain blast radius, ask before editing.
  no  -> make minimal patch and validate.

Could a failure silently switch to another account/provider/global OAuth?
  yes -> redesign fail-closed; do not ship silent fallback.
  no  -> validate and record regression report.
```
