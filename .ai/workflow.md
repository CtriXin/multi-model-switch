# Workflow

## Default Flow

1. Read rule files and local state files.
2. Read `.ai/plan/TODO.md`.
3. Scope the current iteration narrowly.
4. Make the smallest coherent change.
5. Validate the change.
6. Update TODO / handoff files.
7. Ask the user whether to commit before starting the next substantial change.

## Protected Launch Chain

When a task touches the launch path, reason explicitly across:

`TUI -> core -> launcher -> bridge -> actual CLI`

Do not change one segment casually without checking the others.
