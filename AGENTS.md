# AGENTS.md - multi-model-switch Bootstrap

> This file is the bootstrap entry for local agents.
> Treat it as the startup map, not the full rule source.

This file applies to both `Codex` and `Claude`.

## Startup Order

1. Read the primary rule file in this order:
   - `AGENT.md`
   - `CLAUDE.md`
   - `AGENT_RULES.md`
2. Read `.ai/manifest.json` if present
3. Read `.ai/plan/current.md` if present
4. Read `.ai/workflow.md` if present
5. Read `AI_BOOTSTRAP.md` if present

## Conflict Rules

- Project-specific rules win over shared defaults.
- If multiple rule files exist, prefer `AGENT.md`, then `CLAUDE.md`, then `AGENT_RULES.md`.
- `.ai/plan/current.md` is the current task source of truth when present.

## TODO Management

- On plan phase or new task, list TODOs in **four-quadrant format** (Urgent+Important / Important+Not Urgent / Urgent+Not Important / Neither) in `.ai/plan/TODO.md`.
- Each item: `- [ ] description (source: @agent, created: YYYY-MM-DD)`
- On completion: `- [x] description (source: @agent, created: ..., completed: YYYY-MM-DD)`
- At plan start, archive `[x]` items to `docs/archive/todo-archive-YYYY-MM.md` (append-only, never delete).

## Release Handoff

- After each completed iteration stage, append a record to `./.ai/agent-release-notes.md`.
- Keep that file ignored in `.gitignore`; it is local release-prep context.
- Each record should include:
  - timestamp
  - agent name
  - landed commit/tag/release, if any
  - changed file scope
  - concise landed summary
  - reusable release-note bullets
  - validation run and result
- Before preparing a version bump, tag, or GitHub release, `Codex` should read this file first.

## Iteration Commit Gate

- After each completed iteration stage, ask the user whether to create a commit before starting the next substantial change.
- Do not assume "not asking" means "continue uncommitted".
- Do not auto-commit without explicit user confirmation.
- If the user declines, continue only for the current requested scope and keep the final note explicit that the work remains uncommitted.

## Operational Guardrails

- Before changing launcher, routing, bridge, config, account, or TUI selection logic, read `docs/AGENT_GUARDRAILS.md`.
- `Claude` must also read `CLAUDE.md` before making any repo changes; when `CLAUDE.md` and a task conflict, Claude should stop and ask the user to confirm scope.
- Treat `mms_core.py`, `mms_launchers.py`, `mms_tui.py`, `mms_bridge.py`, `mms_account_state.py`, `mms_session.py`, `mms_adapter_registry.py`, `mms`, and `ccs` as protected surfaces.
- Do not silently change default launch behavior, model/source resolution order, config schema, account isolation semantics, or bridge fallback rules without an explicit note in the task and targeted validation.
- If a task would alter a protected surface beyond the user's stated scope, stop and narrow the change or ask for confirmation.

## Stability Window

- The following chain is now under a stability window and must be treated as a protected integration surface:
  - `MMS -> private(/claude) -> CRS`
  - `MMS -> privateopenai(/openai) -> CRS`
  - `MMS -> xin/newapi(4001) -> CRS`
- Any person or agent touching any of the following must explicitly confirm whether the change can affect the above chain before proceeding:
  - provider `models_endpoint`
  - `extra_models` / `hidden_models`
  - model probe logic / cache logic
  - `channel_affinity`
  - `Codex` / `Claude` header passthrough
  - CRS-facing `/claude` or `/openai` route assumptions
- Minimum pre-change checklist for that chain:
  - Does this change alter model visibility, aliasing, or fallback behavior?
  - Does this change alter whether `/models` is probed, skipped, or cached?
  - Does this change alter client identity headers or sticky-session key sources?
  - Can this break `private`, `privateopenai`, or `xin/newapi` even if the local unit test still passes?
- Any change on that chain must update:
  - `docs/CLI_PROVIDER_COMPAT_QA.md`
  - `docs/PRIVATE_CRS_SMOKETEST_RUNBOOK.md`
- Any change on that chain must run at least one matching smoke test from:
  - `docs/PRIVATE_CRS_SMOKETEST_RUNBOOK.md`
