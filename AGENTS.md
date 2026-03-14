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
- Treat `ccs_core.py`, `ccs_launchers.py`, `ccs_tui.py`, `ccs_bridge.py`, `ccs_account_state.py`, `ccs_session.py`, `ccs_adapter_registry.py`, `mms`, and `ccs` as protected surfaces.
- Do not silently change default launch behavior, model/source resolution order, config schema, account isolation semantics, or bridge fallback rules without an explicit note in the task and targeted validation.
- If a task would alter a protected surface beyond the user's stated scope, stop and narrow the change or ask for confirmation.
