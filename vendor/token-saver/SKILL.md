---
name: token-saver
description: Session behavior pack for automatic token-saving decisions. Use when handling large tool output, structured data for another model, repeated handoff/status context, long logs, or when the user asks to save tokens/context. Prefer this unified pack over remembering separate TOON or context commands.
allowed-tools: Bash(token-saver:*), Bash($TOKEN_SAVER_BIN:*), Bash($MMS_TOKEN_SAVER_BIN:*), Bash(mms-context:*), Bash($MMS_CONTEXT_BIN:*), Bash(mms-toon:*), Bash($MMS_TOON_BIN:*)
---

# Token Saver

Token Saver is the unified session behavior for saving context.

The user-facing contract comes first: do not make the user remember helper commands.

Use Token Saver automatically when it fits. Do not tell the user to run `token-saver`,
`mms-context`, or `mms-toon` unless they explicitly ask for the low-level command.

The only user-facing trigger worth mentioning is the simple `/token-saver` command. Normal
requests such as "跑测试", "看日志", "分析这个 JSON", or "省点 context" are enough.

## Agent Rules

For commands that may print long output, run the command through Token Saver yourself:

```bash
token-saver run --title "short title" -- some-command
```

It prints the command output directly when short. When long, it stores the full output and returns:

- `mmsctx://...` ref for agent reuse
- exit code
- short snippet

Use the same wrapper for tests, builds, log reads, search commands, and diagnostics where full output may be noisy.

Use `token-saver put` or `mms-context put` yourself when text already exists and should be stored:

- tool output is long
- logs contain many repeated lines
- test/build output is too large to paste
- a handoff/status packet would be noisy inline
- the user asks to keep context small

Stored-text pattern:

```bash
cat long-output.txt | token-saver put --kind tool-output --title "short title"
```

Then respond with:

- conclusion first
- `mmsctx://...` ref only if useful for follow-up
- short snippet
- next action

Use `mms-context search` and `mms-context show` only when the stored output is needed again.

Use `token-saver toon` or `mms-toon --auto` yourself when:

- structured JSON is agent-facing context
- rows are flat/repetitive
- the payload is for model-to-model handoff, status, counters, or compact metadata

Structured-data pattern:

```bash
token-saver toon payload.json
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

When Token Saver is active, do not ask the user to remember `token-saver run`, `mms-context`, `mms-toon`, or `mmsctx://` mechanics. Treat those as internal implementation details.
