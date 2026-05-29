# MMS Rescue Fallback

Status: L3 file-first rescue with thin bridge hook, TUI rescue viewer, safe fallback handover generation, incident logging, and paused current-session hot fallback for Codex Responses bridge failures.

## Current Scope

- Writes deterministic rescue artifacts before any continuation model call.
- Hooks terminal bridge failures for blocking classes: 429/quota, 403/401 permission/auth, context overflow, model not found, timeout, 5xx, and unsupported capability/parameter.
- Global fallback is file-first behavior: bridge failures write the rescue packet and `fallback-handover.md/json`, but do not switch the active request to the fallback model automatically.
- Current-session hot fallback is paused pending redesign. `[rescue].hot_fallback_enabled = true` and `MMS_RESCUE_HOT_FALLBACK=1` are still parsed for compatibility, but the bridge keeps handoff-only behavior.
- Fallback route resolution checks `<config_root>/generated/model-registry.latest-approved.json` first. When the manifest exists, only the verified Router payload is used and invalid manifests fail closed; when it is missing, legacy generated/root `model-routes.json` files remain compatibility fallbacks.
- Blocking failures and cache-sensitive channel switches append redacted JSONL entries to `<resolved-mms-config>/logs/incidents.jsonl`.
- When a fallback model is configured, the bridge may generate `summary.md` asynchronously in the rescue artifact directory; this is a recovery summary only, not a same-request hot fallback.
- Keeps global OAuth fallback disabled.
- Keeps private/public boundary crossing disabled.
- Exposes recent rescue packets through `MMS -> Settings -> Interrupted / Rescue`.
- The same TUI page shows `Hot fallback` status and offers an explicit toggle after a global fallback model exists.
- When no packets exist, the TUI can create a safe demo rescue packet for local verification; it makes no upstream/model request.
- For an existing packet, the TUI can generate `fallback-handover.md/json` for an explicitly selected fallback model; the TUI viewer itself still makes no model call.

## Artifacts

Repo-local:

```text
<repo>/.mms/rescue/latest.json
<repo>/.mms/rescue/latest.md
<repo>/.mms/rescue/<timestamp>/rescue.json
<repo>/.mms/rescue/<timestamp>/rescue.md
<repo>/.mms/rescue/<timestamp>/raw/*
<repo>/.mms/rescue/<timestamp>/fallback-handover.json
<repo>/.mms/rescue/<timestamp>/fallback-handover.md
<repo>/.mms/rescue/latest-fallback-handover.json
<repo>/.mms/rescue/latest-fallback-handover.md
<repo>/.mms/rescue/<timestamp>/summary.md
```

Global metadata index:

```text
<real-home>/.config/mms/rescue/index.jsonl
<resolved-mms-config>/logs/incidents.jsonl
```

The global index and incident log store metadata and pointers only. Raw upstream bodies are redacted before write, auth-bearing raw paths such as `.codex/auth.json`, `.claude.json`, `.gemini`, `config.toml`, credentials files, key files, and account folders are skipped, and incident URLs/details are redacted before append.

## Real Home Resolution

Rescue metadata resolves the real MMS config root through:

```text
MMS_REAL_HOME -> REAL_HOME -> ORIGINAL_HOME -> stripped MMS gateway session HOME -> HOME
```

It must not write rescue metadata under an isolated session HOME such as `.config/mms/codex-gateway/s/*`.

## Current Limits

- Hot fallback execution is currently paused; only route resolution, rescue artifacts, incident logs, fallback handovers, and async summaries remain active.
- Context-heavy failures still rely on the rescue packet/context policy; MMS does not auto-compact before choosing a smaller fallback model.
- No automatic session resume; the TUI viewer is read-only recovery metadata + packet display.
- No registry DB persistence beyond the file-only metadata/index shape.
