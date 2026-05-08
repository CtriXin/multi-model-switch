# Host Context Contract

MMS uses a two-layer contract for isolated agent sessions that need stable host paths or host capabilities without inheriting the real user environment.

## Layers

### Static Host Capability Template

Tracked source:

- `config/ops-env-safe.template.toml`

Optional real-user install target:

- `~/.config/mms/ops-env-safe.toml`

The real target is human-owned MMS config. Agents may read it when present, but must not auto-write it. Changes to the real target require the MMS config human gate: plan, backup, human confirmation, write, and post-write check.

Use this layer for stable path-only or localhost capability hints, for example:

- real host home as a path hint, not as `HOME`
- WebAccess proxy URL and Chrome debug port
- Chrome extension ID
- WebAccess `check-deps` script path
- Codex / Claude skills roots
- npm npx cache path
- Playwright browser cache path
- host wrapper tools such as `gh`, `lark-cli`, and `rh`

Do not put secrets here:

- API keys
- OAuth tokens
- Keychain material
- real `HOME` / `XDG_*` exports
- cookies, localStorage, session tokens, or account fingerprints

### Dynamic Session Context

Generated per MMS-launched session:

- `$MMS_HOST_CONTEXT_JSON`
- usually `SESSION_HOME/.mms/context/host-context.json`

Producer:

- `mms_host_context.py`
- called from `mms_launchers.py`

Use this layer for launch-specific data:

- current `cwd`
- current `repo_root`
- selected `model`
- current `session_home`
- selected CLI (`claude`, `codex`, etc.)
- resolved host capability hints from the static template
- host-wrapper tool paths for the current session

This file is session-local and can be regenerated. It is the preferred source for isolated agents because it combines stable host hints with the current workspace.

## Agent Read Order

When a tool or skill needs host capability hints:

1. Read `$MMS_HOST_CONTEXT_JSON` if present.
2. Read `$MMS_OPS_ENV_SAFE_CONFIG` if present.
3. Read `~/.config/mms/ops-env-safe.toml` only as path-only config.
4. Fall back to conservative built-in defaults only for non-auth paths.

For logged-in browser work, `web-access` is the required route. Do not fall back to Playwright, agent-browser, Camofox, or another isolated backend just because the sandboxed `HOME` cannot see the real Chrome profile.

## Environment Boundary

Allowed env hints:

- `MMS_HOST_CONTEXT_JSON`
- `MMS_HOST_CAPABILITIES_JSON`
- `MMS_OPS_ENV_SAFE_CONFIG`
- `WEB_ACCESS_HOST_HOME`
- `HOST_HOME`
- `MMS_WEB_ACCESS_PROXY`
- `MMS_WEB_ACCESS_PROXY_URL`
- `MMS_WEB_ACCESS_CHECK_DEPS`
- `MMS_CHROME_DEBUG_PORT`
- `MMS_CHROME_EXTENSION_ID`

Protected env values that must not be injected from the real host:

- real `HOME`
- real `XDG_CONFIG_HOME`
- real `XDG_CACHE_HOME`
- real `XDG_DATA_HOME`
- real `XDG_STATE_HOME`
- token or auth env such as `GH_TOKEN`, `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`, Lark tokens, or provider credentials

Host-auth tools should be exposed through session wrappers or a future host-exec capability, not by copying credential files into the isolated session.

## Where To Record Future Entries

Use this rule of thumb:

| Need | Record in |
| --- | --- |
| Stable path or localhost capability used by many sessions | `config/ops-env-safe.template.toml` |
| Per-session runtime metadata | `mms_host_context.py` generated context |
| Agent-facing behavior or read order | this doc and the relevant skill doc |
| A new isolated-session tool wrapper | `_SESSION_REAL_HOME_WRAPPER_COMMANDS` in `mms_launchers.py` plus this doc |
| User-specific installed value | human-owned `~/.config/mms/ops-env-safe.toml` |

If a new entry affects browser login state, OAuth, provider credentials, model routing, or Claude config, stop and apply the relevant human-gate or guardrail before writing anything.
