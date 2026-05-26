# Agent Continuity Checkpoint

Use this shape for the human-readable meaning of a checkpoint. The machine form
is `.agent.local/continuity/checkpoints/<task-id>/<stamp>-<session-id>.json`.

## Identity

- Task ID: task-example-001
- Run ID: run-example-001
- Session ID: session-example
- Agent: Codex
- CLI: codex
- Model: gpt-5.4
- Status: active

## Current Truth

- Summary: <main result/current truth>
- Next action: <exact next action>
- Scope: <main or side>
- Work type: <work type>

## Evidence

- Changed files: <paths>
- Validation: <commands and results>
- Risks: <risks>
- Refs: <artifact paths>

## Writeback

- write future checkpoints under `.agent.local/continuity/checkpoints/<task-id>/`
- write session events under `.agent.local/continuity/sessions/<session-id>.jsonl`
- update `active.json` only from main/supervisor/offduty scope
