# AI_BOOTSTRAP.md - Cross-AI Entry

## Applies To

- Claude
- Codex
- Gemini
- Other AI tools that do not auto-load local project rules

## Mandatory Read Order

1. Read the primary rule file: `AGENT.md` or `CLAUDE.md` or `AGENT_RULES.md`
2. Read `.ai/manifest.json` if present
3. Read `.ai/plan/current.md` if present
4. Read `.ai/workflow.md` if present
5. Read `docs/AGENT_GUARDRAILS.md`

## Execution Rules

- State planned file impact before non-trivial edits.
- Do not change the main launch chain casually: `TUI -> core -> launcher -> bridge`.
- If behavior changes, update the corresponding docs in the same pass.
- After each completed iteration stage, ask the user whether to commit before proceeding to the next substantial change.
- Do not rely on session memory for task state; persist key context in files.

## Commit Hygiene

- Multi-agent work should prefer short, isolated iterations.
- A finished iteration should either be committed, explicitly deferred by the user, or clearly marked as still uncommitted in the handoff.
- Never start stacking unrelated follow-up changes on top of an unconfirmed iteration by default.

## Delivery Format

1. Changed files and behavior
2. Validation status
3. Commit status
4. Remaining risks or skipped items
