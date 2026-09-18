# OpenCode Side Runner Pilot RFC

Date: 2026-06-14
Owner: Codex
CLI: codex
Model: GPT-5
Status: draft for committee review

## Executive Summary

This RFC records a proposed MMF/MMS pilot for an OpenCode side-runner: a thin, project-local workflow that lets slow OpenCode work continue in a managed background session while the user's main OpenCode session keeps moving.

The proposal is a compromise. It does not claim to implement a true native OpenCode `side` or `btw` thread. It uses documented OpenCode plugin, command, and server APIs to create and manage side sessions with aliases, status, abort, and later queue/merge support.

## User Intent

The user wants OpenCode work to stop getting blocked by one slow or noisy subagent when the rest of the work already has enough signal.

Desired experience:

- A slow review, deep check, or research lane can keep running without holding the main conversation hostage.
- The user can continue the main OpenCode session immediately after dispatching side work.
- The side lane is not just one prompt; it can be a continuing conversation that preserves its own context.
- The user can resume, ask follow-up questions, inspect status, and abort the side lane.
- The side lane should feel similar in spirit to Codex side lanes or Claude `btw`, but without patching OpenCode core.

Examples of intended commands:

```text
/side new review "Slowly inspect the current diff for regressions."
/side ask review "Also check whether this affects OpenCode profile session storage."
/side status
/side abort review
```

Non-goals:

- Do not change OpenCode core in the first pilot.
- Do not pretend this is a true in-session side thread if it is actually a managed OpenCode session.
- Do not bind this experiment to MMS/MMF business logic unless committee decides it should become a repo feature.
- Do not make OpenCode's built-in Task join semantics appear fixed; they remain unchanged.

## Current Pain Points

OpenCode can run subagents in parallel, but slow subagent work can still be frustrating when the parent session waits for the final lane to finish.

Observed pain:

- Some subagents enter a long read/check loop, such as repeatedly reading the same files.
- The slow lane may not be wrong; it may be a slow channel, a careful check, or a broader validation pass.
- Killing the slow lane too early loses potentially useful evidence.
- Waiting for it blocks the user from moving forward when 3 out of 4 lanes are already enough for a provisional conclusion.
- The user wants a way to continue the main work while a slow lane remains alive in the background.

Related bug already filed:

- GitHub issue #8: OpenCode profile cannot switch sessions; session list is empty.

This bug matters because a side-runner should not depend only on OpenCode's session list search. It should maintain its own alias-to-session index.

## Current State

OpenCode official surfaces relevant to this proposal:

- Plugins load from `.opencode/plugins/` or `~/.config/opencode/plugins/`.
- Commands load from `.opencode/commands/` or the global config command directory.
- Server API provides session creation/list/status, `prompt_async`, and abort endpoints.
- Commands can run as subtask with `subtask: true`, but that alone is not a true background side lane.
- Subagents create child sessions that can be navigated in the TUI, but parent Task behavior may still wait for joins.

Local decision so far:

- Track the idea in GitHub issue #10 for committee review.
- Record this local RFC in `docs/RFC_OPENCODE_SIDE_RUNNER_PILOT_2026-06-14.md`.
- Prefer project-local pilot first; promote to global OpenCode configuration only after review.

## Boundaries

What the pilot owns:

- Project-local OpenCode command files for side workflow entry points.
- A project-local OpenCode plugin or lightweight helper that records side aliases and dispatches prompts asynchronously.
- A side index mapping names like `review` to OpenCode session IDs.
- Status and abort commands for tracked side sessions.

What it does not own:

- OpenCode core source changes.
- OpenCode TUI internals.
- The built-in Task tool's blocking/join behavior.
- Automatic conversion of an already-running Task subagent into a side lane.
- Deep UI integration such as a native side panel or live side queue rendering.

## Proposed Compromise

Use managed OpenCode sessions as side lanes.

This is intentionally transparent:

```text
/side new review ...
= create or record an OpenCode session
+ send prompt with prompt_async
+ remember name -> sessionID
+ notify/status/abort through official APIs
```

This is "managed new session", not a true native side thread. The compromise is acceptable for a pilot because it solves the core pain: slow work no longer blocks the main session.

The user-facing model should be:

- Side lane is long-lived.
- Side lane has its own context.
- Side lane can receive follow-up messages.
- Main lane does not wait for side lane.
- Side lane can be resumed by alias even if OpenCode session search is unreliable.

## Proposed V1

Project-local files:

```text
.opencode/plugins/side-runner.js
.opencode/commands/side.md
.opencode/commands/side-status.md
.opencode/commands/side-abort.md
```

State file:

```text
.opencode/side-runner/state.json
```

V1 commands:

```text
/side new <name> <prompt>
/side ask <name> <prompt>
/side status
/side abort <name>
```

V1 behavior:

- `new` creates a managed OpenCode session or records a newly created one.
- `ask` sends a new prompt to the existing side session.
- Dispatch uses `prompt_async` so the main session does not wait.
- `status` lists alias, session ID, title, last state, start time, and last update time.
- `abort` calls the documented OpenCode abort endpoint for the tracked session.
- The plugin should avoid reading private OpenCode session databases.

## Proposed Later Iterations

V2:

- Per-side-lane queue: if a side lane is still running and the user sends another `ask`, enqueue it and dispatch after `session.idle`.
- Completion toast or notification when a side lane finishes.
- `ask-after` policy, such as warning after 180 seconds rather than killing automatically.

V3:

- `/side merge <name>` to summarize the side result and append it to the current prompt or produce a copyable merge block.
- `/side fork <name> <new-name>` to branch a side lane.
- Read-only default side agents for review/research lanes.

V4:

- Evaluate whether this should become a global OpenCode extension under `~/.config/opencode/`.
- Consider upstream feature request to OpenCode for true native side/btw support.

## HumanGate / Safety

The pilot should not silently kill long-running work.

Rules:

- Abort only on explicit user command in V1.
- A future `ask-after` timer may ask the user whether to continue or abort, but should not auto-abort by default.
- Side lanes that can edit files should be opt-in; read-only review/research lanes should be the safe default.
- If a side lane modifies files, the main session must be told that there may be concurrent workspace changes.
- If OpenCode server API or session status is unavailable, fail visibly and do not pretend the side work is running.

## Constraints And Limitations

Known constraints:

- This will not fix OpenCode's built-in Task join behavior.
- If the primary agent internally launches Task subagents, those may still block the parent.
- The best first-use pattern is explicit: use `/side` for slow review, deep check, long research, or non-blocking validation.
- The side runner may need OpenCode's server to be available from the current TUI/session environment.
- If the MMF OpenCode profile uses isolated config/data directories, state path and server discovery must be tested carefully.

Upgrade risk:

- Low-to-medium if the implementation only uses documented plugin directories, command files, and server endpoints.
- Higher if it depends on OpenCode internal TUI state, private data files, or unofficial hooks.

## Proof Strategy

Committee should ask for proof with a small local fixture before approving a broader rollout.

Minimum proof:

```text
/side new review "Wait briefly, then summarize this repo's OpenCode docs."
/side status
/side ask review "Now check whether session switching records are visible."
/side abort review
```

Pass criteria:

- Main OpenCode session remains usable immediately after `/side new`.
- Side session appears in side-runner state with a stable alias.
- `ask` continues the same side context rather than creating unrelated one-shot tasks.
- `status` reports enough information to identify stuck/running/done lanes.
- `abort` stops the tracked side session.
- No OpenCode source patch is required.

Additional proof after issue #8:

- Verify side-runner alias resume still works even when OpenCode's session switcher shows `No results found`.

## Roadmap

1. Committee review of this RFC and issue #10.
2. Decide pilot location: project-local `.opencode/` versus personal global `~/.config/opencode/`.
3. Implement V1 only: `new`, `ask`, `status`, `abort`.
4. Test with one read-only side lane and one long-running mock side lane.
5. Decide whether queue/notification belongs in V2.
6. If stable, decide whether to promote to global OpenCode or propose upstream.

## Open Questions For Committee

1. Should side lanes be read-only by default?
2. Should side lanes inherit the current primary agent, or use a dedicated side agent?
3. Should project-local state live under `.opencode/side-runner/`, or should local runtime state stay out of repo paths?
4. Should the pilot include notification in V1, or keep V1 strictly command-driven?
5. Should side-runner be documented as a personal workflow extension or as an MMS/MMF supported feature?

## Future LMs Must Not Forget

- The user's primary goal is not "more subagents"; it is less blocking during useful slow work.
- The proposed pilot is a compromise: managed OpenCode sessions, not a true native side thread.
- Do not claim this fixes built-in Task join behavior.
- Do not tie the concept unnecessarily to MMS internals.
- Start project-local for review; global install is a later promotion decision.
- Preserve human control over abort decisions.
- Prefer official OpenCode plugin/command/server APIs over private data or source patches.

## References

- GitHub issue #10: RFC: Pilot OpenCode side-runner for managed background sessions.
- GitHub issue #8: Bug: OpenCode profile cannot switch sessions; session list is empty.
  - **Status**: RFC approved with modifications (2026-06-15)
  - **RFC Document**: [`RFC_OPENCODE_SESSION_SWITCHING_FIX_2026-06-15.md`](RFC_OPENCODE_SESSION_SWITCHING_FIX_2026-06-15.md)
  - **Implementation Guide**: [`ISSUE_8_OPENCODE_SESSION_FIX_GUIDE.md`](ISSUE_8_OPENCODE_SESSION_FIX_GUIDE.md)
- OpenCode plugins: https://opencode.ai/docs/plugins/
- OpenCode commands: https://opencode.ai/docs/commands/
- OpenCode server API: https://opencode.ai/docs/server/
