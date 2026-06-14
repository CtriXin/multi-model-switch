# OpenCode Hook-Fit Spike Evidence Template

Use this template for phase 1 only.

Phase 1 is intentionally narrow and covers only the two kill checks:

1. `experimental.session.compacting` restore packet
2. boundary negative tests:
   - full-state subagent reject
   - custom tool does not directly touch canonical state

Do not use this template to pre-write `RESULT.md`.
Use it only to collect evidence for the first fail-fast gate.

## Run Metadata

- date:
- operator:
- repo root:
- branch:
- OpenCode version:
- MMS context used:
- spike scope version:
- overall run status: in_progress|completed|blocked

## Kill-Switch Status

- kill-switch A: `experimental.session.compacting` restore packet -> not_run|pass|partial|fail
- kill-switch B: bounded subagent + custom-tool boundary negative tests -> not_run|pass|partial|fail
- fail-fast stop triggered: yes|no
- stop reason:
- proceed to non-kill-switch surfaces: yes|no

## Phase-1 Summary Table

Fill this table first, then complete the detailed sections.

| Check | Official mechanism | Goal | Verdict | Kill-switch | Blocking issue | Evidence path |
| --- | --- | --- | --- | --- | --- | --- |
| restore packet | `experimental.session.compacting` | compaction restore viability | pass\|partial\|fail | A | yes\|no |  |
| subagent negative | permissions/subagent dispatch | reject full-state payload | pass\|partial\|fail | B | yes\|no |  |
| custom-tool negative | custom tool bridge | no direct canonical-state access | pass\|partial\|fail | B | yes\|no |  |

## Evidence Section Template

Copy this section once per tested surface.

```md
## <surface name>

- goal:
- official mechanism tested:
- why this mechanism matters to the lifecycle surface:
- setup:
- config or code path under test:
- observed trigger timing:
- observed payload shape:
- mutation/control surface available:
- fits current need: yes|partial|no
- blocker level: none|minor|major
- kill-switch relevance: A|B
- hard-stop touched: yes|no
- hard-stop detail:
- boundary concerns:
- evidence paths:
- verdict: pass|partial|fail
- follow-up:
```

## Hard-Stop Log

Use this section whenever a test touches or attempts to cross a forbidden boundary.

```md
### Hard-stop incident <n>

- surface:
- attempted action:
- forbidden boundary touched:
- was the action blocked: yes|no
- evidence paths:
- impact on spike verdict:
- follow-up:
```

## Required Phase-1 Records

Phase 1 must include exactly these records.

### 1. `experimental.session.compacting`

Must answer:

- Can it inject a minimal restore packet?
- Does the packet survive a real compaction cycle?
- Is the mechanism too fragile/experimental for MVP, or acceptable with caveats?

### 2. Subagent Full-State Negative Test

Must answer:

- Can a deliberately oversized or full-state payload be rejected, blocked, or fail-closed?
- Is the rejection mechanism policy-based, permission-based, adapter-based, or only advisory?
- If it is only advisory, is that already a blocker for phase 1?

### 3. Custom Tool Boundary Negative Test

Must answer:

- Does the tool path avoid direct canonical-state file access?
- Is adapter-only access actually enforced, or only conventionally intended?
- If the agent tries the direct path anyway, is the boundary blocked or only documented?

## Phase-1 Gate Decision

Fill this section after the three required records above are complete.

- phase-1 verdict: pass|partial|fail
- kill-switch A final verdict: pass|partial|fail
- kill-switch B final verdict: pass|partial|fail
- fail-fast stop triggered: yes|no
- if yes, at which check:
- blocking findings:
  -
- acceptable caveats:
  -
- recommended next step:
  - proceed to later spike surfaces
  - rerun one kill check with narrower setup
  - revise frozen memo before continuing

## Filing Guidance

- Use durable relative paths under `opencode-local/spikes/opencode-hook-fit/` whenever possible.
- If code snippets or temporary plugin/tool files are created, record their exact path.
- If a result depends on an experimental OpenCode surface, say so explicitly.
- If a boundary is only partially proven, do not upgrade it to `pass`.
- If a test was skipped, say why it was skipped and what would be required to run it.
- Do not create `RESULT.md` during phase 1 planning; create it only after a real phase-1 execution finishes.
