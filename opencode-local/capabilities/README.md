# Capabilities

Capabilities are reusable policies that sit between the neutral contract and a runner adapter.

They should be portable across OpenCode, Codex, Claude, and future hosts. A capability may know about contract concepts, but should not require OpenCode-specific files or MMF-specific profile names.

## Initial Capability Set

| Capability | Responsibility | Non-goal |
| --- | --- | --- |
| `context-projection` | Produce thin/budgeted/contract-ref payloads for primary and subagents. | Owning task-state. |
| `subagent-discipline` | Enforce slot-scoped payloads, permission shape, and return evidence. | Replacing the runner scheduler. |
| `closeout-bridge` | Convert runner finish intent into `report` plus done-gate request. | Declaring done without state-core. |
| `continuity-bridge` | Emit pickup and restore packets for long sessions/compaction. | Creating a second memory database. |
| `recorder-evidence` | Attach run evidence for review/release/debug. | Becoming the canonical issue tracker. |

## Packaging Rule

Each capability should expose:

- `inputs`
- `outputs`
- `allowed side effects`
- `forbidden side effects`
- `adapter responsibilities`
- `MVP validation`
