# OpenCode Hook-Fit Spike Phase 1 Result

Date: 2026-06-14
Status: `partial_blocked`
OpenCode version: `1.15.13`

## Verdict

Phase 1 did not pass as written.

Kill-switch A is `partial`: OpenCode can load a session-local plugin and legacy summarize can trigger `experimental.session.compacting`, but this run did not prove that a returned restore packet survives real compaction and remains usable afterward. The v2 compact endpoint exposed by OpenAPI returned 503 `V2 session compact is not available yet`.

Kill-switch B was not run because the fail-fast gate stopped after kill-switch A produced a major partial/blocking result.

## Decision

Do not start `opencode-reference-adapter-mvp` yet.

Before adapter work, choose one path:

1. rerun kill-switch A against an OpenCode version/path where v2 compact is available and can prove post-compaction restore packet survival;
2. narrow the continuity requirement so compaction restore is an optional optimization, while canonical continuity uses external session-close/pickup artifacts outside OpenCode compaction;
3. revise `docs/OPENCODE_RUNNER_CAPABILITY_DIRECTION_2026-06-14.md` to mark compaction restore as experimental/partial rather than MVP-blocking truth.

## Evidence

Primary evidence file:

- `opencode-local/spikes/opencode-hook-fit/PHASE1_EVIDENCE.md`

Local raw artifacts are under ignored paths:

- `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-compact/`
- `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-summarize-provider/`

Key observations:

- `opencode run` and `opencode serve` respected isolated `HOME`/`XDG_*`/`OPENCODE_CONFIG` paths under spike artifacts.
- session-local plugins under `OPENCODE_CONFIG_DIR/plugins/` load successfully.
- `/api/session/{sessionID}/compact` exists in OpenAPI but returned 503 in this runtime.
- `/session/{sessionID}/summarize` with a local fake OpenAI-compatible provider triggered `experimental.session.compacting`.
- hook input shape observed during summarize was only `{"sessionID":"ses_..."}`.
- hook return string was not proven to persist into the compacted context or post-compaction messages.

## Next Step

Recommended: revise the direction memo and spike README to split continuity into:

- required: external close/pickup artifact controlled by `opencode-local`/MMF adapter;
- optional: OpenCode compaction hook restore injection, gated by future proof.
