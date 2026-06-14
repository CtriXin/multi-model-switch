# OpenCode Hook-Fit Spike

Date: 2026-06-15
Status: phase-1 partial_blocked
Owner: Codex

Phase 1 only runs the two kill-switch checks; all other surfaces remain `not_run` until Phase 1 passes.

Phase 1 result: `partial_blocked`. Do not expand into Phase 2 or adapter MVP until the compaction continuity requirement is narrowed or re-proven. See `PHASE1_EVIDENCE.md` and `RESULT.md`.

## Purpose

This spike exists to answer one narrow question before any adapter MVP work starts:

Can official OpenCode extension surfaces provide the timing, payload shape, and boundary controls required by our runner-neutral capability direction?

This spike is not an implementation phase.
It is a proof phase that must pass before:

- `runner-neutral-contract` drafting becomes implementation-shaped;
- `opencode-reference-adapter-mvp` drafting becomes more than a placeholder;
- any MMS integration work touches `mms_opencode_*` modules.

## Source Direction

This spike is downstream of:

- `docs/OPENCODE_RUNNER_CAPABILITY_DIRECTION_2026-06-14.md`

That memo is the frozen direction source.
If this spike fails, the next step is to revise the memo or narrow the target, not to force-fit an adapter.

## Non-Goals

This spike must not:

- patch OpenCode core;
- draft the full adapter;
- create a new public MMS mode;
- introduce `mommy` or `state-core` semantics into OpenCode core;
- directly write canonical state;
- settle upstream RFC scope.

## Questions To Prove

The spike must produce evidence for these questions.

### 1. Event Observation Fit

Can OpenCode's observable event surface provide enough signal for runner lifecycle observation?

Target observations:

- `session.created`
- `session.compacted`
- `session.error`
- `session.idle`
- `todo.updated`

Required proof:

- how the event is observed;
- what payload shape is actually available;
- whether the timing is good enough for our lifecycle surface;
- whether any critical field is missing.

### 2. Direct Hook Fit

Can OpenCode's documented direct hook keys support the interception points we care about?

Target hook keys:

- `tool.execute.before`
- `tool.execute.after`
- `shell.env`
- `experimental.session.compacting`

Required proof:

- exact trigger timing;
- input/output mutation surface;
- whether the hook is reliable enough for boundary enforcement or context injection;
- whether the hook is official/stable or experimental.

### 3. Custom Tool Bridge Fit

Can one or more `state-core` operations be safely exposed as OpenCode custom tools without violating canonical state boundaries?

Minimum target:

- one read path, such as `hydrate` or `read`
- one write-like gated path, such as `report` or `advance`

Required proof:

- tool shape;
- args schema;
- adapter-only access path;
- no direct canonical state file access.

### 4. Permission And Subagent Fit

Can OpenCode's agent and permission model enforce bounded subagent dispatch?

Minimum target:

- bounded subagent dispatch using `contract_ref` or budgeted projection;
- negative proof that full-state dispatch is rejected by policy or test harness.

Required proof:

- permission configuration used;
- what the subagent actually receives;
- what is intentionally withheld.

### 5. Compaction Restore Fit

Can OpenCode's compaction hook preserve a minimal restore packet across long sessions?

Minimum target restore packet fields:

- task pointer
- current phase
- blockers
- next action or equivalent restore hint
- contract refs or bounded slot context

Required proof:

- pre-compaction packet shape;
- post-compaction result;
- whether the packet remains usable in the next turn.

## Deliverables

This spike should produce the following files under this directory or a sibling evidence directory.

### Required outputs

- `README.md` — this outline
- `EVIDENCE_TEMPLATE.md` — phase-1 pass/fail evidence template for the two kill checks

### Optional outputs

- `examples/` — minimal plugin/tool samples
- `artifacts/` — logs, screenshots, captured outputs, or structured traces
- `RESULT.md` — do not create in advance; add only after a real phase-1 run completes

## Pass / Fail Rules

### Pass

Phase 1 passes only if all of the following are true:

1. A compaction restore packet can be injected through `experimental.session.compacting`, survives a real compaction cycle, and remains usable after compaction.
2. A bounded subagent negative test shows that full-state dispatch is rejected, blocked, or fail-closed.
3. A custom-tool boundary negative test shows that the tool path does not require direct canonical-state file access.
4. No step requires OpenCode core patching.

### Fail

Phase 1 fails if any of the following is true:

1. compaction cannot preserve a usable restore packet;
2. subagent full-state dispatch cannot be bounded tightly enough;
3. the custom-tool path depends on direct canonical-state access;
4. the only path forward requires OpenCode core patching before local proof.

## Suggested Test Order

Use a fail-fast, two-kill-switch execution order instead of a flat checklist.

### Two kill-switches

1. `experimental.session.compacting` restore packet viability
2. bounded subagent + custom-tool boundary negative tests

### Execution order

1. run `experimental.session.compacting` restore-packet validation
2. in parallel, run bounded subagent dispatch negative tests plus custom-tool boundary negative tests
3. if either kill-switch hard-fails, stop and record the failure before continuing
4. do not expand into non-kill-switch surfaces during phase 1
5. only after a phase-1 pass should later surfaces be scheduled

## Success Exit

If the spike passes:

- record the phase-1 evidence
- decide whether to open phase-2 surface validation
- keep `RESULT.md` deferred until a real run result exists

If the spike fails:

- stop adapter drafting;
- record the failing surfaces;
- revise the direction memo or narrow the target.

## Host Reminder

The output we want is not "OpenCode can do many things".
The output we want is:

- which official surfaces are truly usable,
- which are usable only with caveats,
- and which are not sufficient for our boundaries.

The spike is complete only when that distinction is evidence-backed.
