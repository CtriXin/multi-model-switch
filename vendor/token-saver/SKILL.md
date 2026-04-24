---
name: token-saver
description: Session behavior pack for automatic token-saving decisions. Use when handling large tool output, structured data for another model, repeated handoff/status context, long logs, or when the user asks to save tokens/context. Prefer this unified pack over remembering separate TOON or context commands.
allowed-tools: Bash(mms-context:*), Bash($MMS_CONTEXT_BIN:*), Bash(mms-toon:*), Bash($MMS_TOON_BIN:*)
---

# Token Saver

Token Saver is the unified MMS session behavior for saving context.

Do not make the user remember helper commands. Use the rules automatically when they fit.

## Auto Rules

Use `mms-context` when:

- tool output is long
- logs contain many repeated lines
- test/build output is too large to paste
- a handoff/status packet would be noisy inline
- the user asks to keep context small

Default pattern:

```bash
some-command 2>&1 | mms-context put --kind tool-output --title "short title"
```

Then respond with:

- `mmsctx://...` ref
- short snippet
- conclusion / next action

Use `mms-context search` and `mms-context show` only when the stored output is needed again.

Use `mms-toon` when:

- structured JSON is agent-facing context
- rows are flat/repetitive
- the payload is for model-to-model handoff, status, counters, or compact metadata

Default pattern:

```bash
mms-toon --auto payload.json
```

## Do Not Convert

- command-required exact JSON
- API request bodies
- source files
- code patches
- raw stack traces that must remain exact
- secrets, tokens, cookies, auth headers, private keys
- short prose where a helper adds more overhead than it saves

If exact JSON is required by a command, keep it exact and optionally create a separate Token Saver summary.

## User-Facing Contract

The user should only need to say normal task words like:

- "跑测试"
- "看日志"
- "分析这个 JSON"
- "省点 context"
- `/token-saver`

When Token Saver is active, do not ask the user to remember `mms-context`, `mms-toon`, or `mmsctx://` mechanics.
