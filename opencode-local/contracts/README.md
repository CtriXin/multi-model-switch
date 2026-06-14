# Runner-Neutral Contracts

This folder owns the stable contract that a concrete runner adapter must implement.

The contract should describe behavior, payloads, and compliance checks without depending on OpenCode internals, MMS implementation modules, or historical `mobius-*` agent names.

## Contract Surfaces

### Lifecycle

Required adapter lifecycle events:

- `session_start`
- `before_user_turn`
- `subagent_dispatch`
- `subagent_return`
- `finish_request`
- `abort_timeout`
- `session_close`
- `session_restore`

These are semantic events. A host adapter may map them to plugin events, hooks, wrappers, or tool calls.

### State Bridge

Allowed operations:

- `hydrate`
- `read`
- `report`
- `advance_done`
- `advance_blocked`

Adapters must call the owning state bridge. They must not write canonical task-state files or databases directly.

### Context Projection

Required projection modes:

- `thin_summary`
- `budgeted_projection`
- `contract_ref_only`
- `blocker_summary`

Subagents should receive the narrowest useful projection. Full state injection is a compliance failure by default.

### Continuity

Required artifacts:

- pickup pointer
- session close artifact
- compaction-safe restore payload

Continuity artifacts are restore hints, not authoritative task-state.

### Compliance

Minimum checks:

- no direct canonical task-state writes
- no done-gate bypass
- no full-state subagent injection by default
- no credential or real-home auth copying
- no runner ownership drift
