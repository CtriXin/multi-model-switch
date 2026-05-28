---
name: onduty
description: Codex `$onduty` / fresh-session resume entry. 开工、换机、fresh session 时，从 repo-local continuity 恢复可执行上下文。
---

# Onduty Alias

Use this alias when the user types `$onduty`, `/onduty`, or asks to resume from continuity.

## Required Behavior

1. From the current repo root, run:

```bash
/Users/xin/auto-skills/shared-skills/handover/scripts/onduty --root "<actual-repo-root>"
```

2. If the user launched from repo A but asks to continue work that belongs to repo B/C, switch to the actual repo/root and pass `--root`.
3. Read Start Here, Active Pointer, Pickup Snapshot, Recent Checkpoints, Git Status, and Diff Stat.
4. Also read the Lifeboat / BKC Backup section if present; it is the lightweight fallback when native resume or BrainKeeper session lookup is stale.
5. Give the user one conclusion first: where to continue now.
6. If several active checkpoints exist, present them as choices and recommend one when evidence is clear.
7. Do not ask for old chat. Old chat is not the source of truth.

## Rules

- Default input is `.agent.local/continuity/`; legacy `.ai/plan` requires `--layout legacy-ai-plan`.
- For Codex, `$onduty` is the preferred explicit trigger.
- For Claude/OpenCode, `/onduty` may route through the skill alias; legacy command symlinks are cleaned to avoid duplicate entries.
- Root ownership follows actual target repo/root, not the session launch folder.
- Open archive/checkpoint history only for old decision/debug provenance.
- If git is dirty, inspect diff before editing.
- Default `onduty` is lite: do not run native resume or full transcript replay unless the user explicitly asks.
- `--no-lifeboat` hides fallback refs only; it does not delete anything.
