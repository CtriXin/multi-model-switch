---
name: toon
description: Convert structured JSON into compact TOON for short model-to-model handoff, launch/session packets, status summaries, or repeated tabular metadata. Use automatically when the user asks for TOON, compact context, token-saving structured payloads, or wants to pass structured state between Codex/Claude sessions.
allowed-tools: Bash(mms-toon:*), Bash($MMS_TOON_BIN:*)
---

# TOON

Use TOON only for structured data that benefits from compact representation:

- session metadata
- handoff packets
- progress/status summaries
- repeated rows with the same fields
- small JSON objects/lists passed between agents

Do not use TOON for prose, code, logs, secrets, credentials, or data that needs exact original formatting.

## Command

Prefer the command:

```bash
mms-toon data.json
```

If `mms-toon` is not on `PATH`, use the fallback env:

```bash
"$MMS_TOON_BIN" data.json
```

Read from stdin:

```bash
printf '%s\n' '{"task":"demo","next":"inspect"}' | mms-toon
```

Use JSON fallback when compactness is not guaranteed:

```bash
mms-toon --auto data.json
```

Show savings:

```bash
mms-toon --stats data.json
```

## Limits

This MMS TOON encoder supports:

- JSON objects with string keys
- primitive values: string, number, boolean, null
- primitive arrays
- arrays of objects with identical keys and primitive values

If conversion fails, keep JSON and continue.
