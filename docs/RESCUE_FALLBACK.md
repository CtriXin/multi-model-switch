# MMS Rescue Fallback

Status: L3 file-only foundation with thin bridge hook, TUI rescue viewer, and safe fallback handover generation.

## Current Scope

- Writes deterministic rescue artifacts before any future continuation model call.
- Hooks terminal bridge failures for blocking classes: 429/quota, 403/401 permission/auth, context overflow, model not found, timeout, 5xx, and unsupported capability/parameter.
- Keeps automatic continuation fallback disabled.
- Keeps global OAuth fallback disabled.
- Keeps private/public boundary crossing disabled.
- Exposes recent rescue packets through `MMS -> Settings -> Interrupted / Rescue`.
- When no packets exist, the TUI can create a safe demo rescue packet for local verification; it makes no upstream/model request.
- For an existing packet, the TUI can generate `fallback-handover.md/json` for an explicitly selected fallback model; it still makes no model call.

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
```

Global metadata index:

```text
<real-home>/.config/mms/rescue/index.jsonl
```

The global index stores metadata and pointers only. Raw upstream bodies are redacted before write, and auth-bearing raw paths such as `.codex/auth.json`, `.claude.json`, `.gemini`, `config.toml`, credentials files, key files, and account folders are skipped.

## Real Home Resolution

Rescue metadata resolves the real MMS config root through:

```text
MMS_REAL_HOME -> REAL_HOME -> ORIGINAL_HOME -> stripped MMS gateway session HOME -> HOME
```

It must not write rescue metadata under an isolated session HOME such as `.config/mms/codex-gateway/s/*`.

## Not Implemented Yet

- No full continuation fallback.
- No automatic fallback model call; fallback handover generation is file-only and explicit.
- No automatic session resume; the TUI viewer is read-only recovery metadata + packet display.
- No registry DB persistence beyond the file-only metadata/index shape.
