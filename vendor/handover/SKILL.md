---
name: handover
description: Create and maintain compact, durable handoff docs for Claude/Codex/Hive/cheap-model collaboration; supports bare offduty/onduty fresh-session continuity, execution handoff identity, current-owner safety, progress files, packet refs, and multi-session write rules.
---

# Handover

Use this skill to turn agent work into durable, low-token handoff files.

This skill applies to all execution-related work, not only Hive.

## Goal

Avoid copy-paste handoff between:

- Claude planner
- Codex executor
- Hive workers
- cheaper LLM workers
- local scripts
- future sessions after compaction or restart

The handoff surface should be readable by:

- another model
- the human
- future you after compaction or session loss

## Core Files

Default working set for generic projects is `agent continuity v1`:

- `./.agent.local/continuity/active.json`
- `./.agent.local/continuity/pickup.json`
- `./.agent.local/continuity/pickup.md`
- `./.agent.local/continuity/checkpoints/<task-id>/<timestamp>-<session-id>.json`
- `./.agent.local/continuity/sessions/<session-id>.jsonl`
- `./.agent.local/continuity/lifeboat/<timestamp>-<task-id>-<session-id>.{md,json}`
- `./.agent.local/continuity/indexes/*.json`

`.agent.local/` is private local state. It may be private-synced between a
user's machines, but it should not be published to a public repo.

Legacy Moebius-governed projects may explicitly opt into:

- `./.ai/plan/current.md`
- `./.ai/plan/handoff.md`
- `./.ai/plan/packet.json`
- `./.ai/plan/progress/<id>.md`
- `./.ai/plan/current-owner.json`
- `./.ai/plan/current-audit.jsonl`

Only use the legacy `.ai/plan` layout when project rules require it or a command
passes `--layout legacy-ai-plan`.

## Required Identity

Every handoff/progress/packet entry must record:

- timestamp
- owner or agent
- CLI, for example `codex`, `claude-code`, `hive`, `script`
- model and model family when known
- session id / session hash / checkpoint hash when available
- commit email hint when available
- task id or run id
- status
- next action

If this metadata is missing, the handoff is incomplete.

## File Roles

### `active.json`

Use as the latest continuation pointer only.

Rules:

- atomic overwrite is allowed
- no long history
- points to the active checkpoint and pickup view
- can be rebuilt from `checkpoints/` and `sessions/`
- not the source of truth

### `pickup.json` / `pickup.md`

Use as generated fresh-session views.

Rules:

- overwrite is allowed
- optimized for quick resume
- reference-based
- no transcript dump
- old decisions stay in checkpoint refs, not in the pickup surface

### `checkpoints/<task-id>/<stamp>-<session-id>.json`

Use as the durable source of truth for an explicit shift boundary.

Rules:

- append-only by filename
- one checkpoint per offduty fold
- include identity, scope, git evidence, validation, risks, decisions, and next action
- safe for parallel sessions because each write gets a unique path

### `sessions/<session-id>.jsonl`

Use for session-owned event streams.

Rules:

- append-only
- each process writes only its own session file
- useful for rebuilding indexes and active pointers

### `lifeboat/*.md` / `lifeboat/*.json`

Use as the lightweight "last resort" continuity capsule.

Rules:

- written by default on every agent-local `offduty`
- small enough to read before native resume or full `bkc`
- contains current truth, next action, risks, validation, git evidence, and refs
- may point to a `bkc`/BrainKeeper pack when local transcript capture succeeds
- never replaces checkpoint JSON as the source of truth

### Legacy `.ai/plan/current.md`

Use only for repos that explicitly require the old Moebius current/packet/handoff
contract. It is not the generic default because it is single-owner and not
concurrency-safe.

## Multi-Session Rule

`active.json` is only a pointer. The durable state is append-only checkpoint and
session files.

Therefore:

1. Each session writes only its own `sessions/<session-id>.jsonl`.
2. Each offduty fold writes a new checkpoint file.
3. Main/supervisor folds may update `active.json` and regenerate `pickup.*`.
4. Side sessions may checkpoint their own work without becoming active.
5. If `active.json` is stale or wrong, rebuild it from recent checkpoints.

For legacy `.ai/plan/current.md` projects, use the runtime guard below.

## Runtime Guard

From any repo root, only when using the legacy `.ai/plan/current.md` contract:

```bash
python3 /Users/xin/auto-skills/shared-skills/handover/scripts/handover_current.py status --root .
python3 /Users/xin/auto-skills/shared-skills/handover/scripts/handover_current.py claim --root . --task-id <id> --owner <agent> --cli <cli> --model <model> --next-action "<next>"
python3 /Users/xin/auto-skills/shared-skills/handover/scripts/handover_current.py audit --root .
```

If the project has its own guard script, use the project-local one.

## Default Workflow

### 1. Choose Handoff Shape

- top-level active work -> checkpoint + `active.json` + `pickup.json` + `pickup.md`
- side task / parallel session -> checkpoint + session event, without taking active pointer
- model-to-model transfer -> `pickup.json` or task checkpoint ref
- landed iteration -> `agent-release-notes.md`
- shift boundary / fresh restart -> `continuity.py offduty` then `continuity.py onduty`

### 2. Stamp Identity

Every new entry must include timestamp, agent, CLI, model, and task/run id.

### 3. Keep Current And History Separate

- `checkpoints/` = durable source of truth
- `sessions/` = session-owned event stream
- `active.json` = newest active pointer only
- `pickup.md` = generated fresh-session surface
- `agent-release-notes.md` = append-only local release history

### 4. Prefer Refs

Do not paste long transcripts or full plans. Use file refs and compact packets.

### 5. Validate Before Claiming Done

Record:

- validation commands and results
- changed files
- unresolved risks
- exact next action

## Guardrails

- do not dump raw transcripts into handoff files
- do not use `agent-release-notes.md` as the current truth panel
- do not omit timestamp / CLI / model in multi-agent work
- do not let `progress.md` become a second transcript
- do not create duplicate truth sources when one already exists
- do not overwrite legacy `current.md` from a side session
- do not treat generated `active.json` / `pickup.md` as append-only source of truth

## Durable Narrative Docs

Handover is not only compact status transfer.

When the user describes long-term intent, architecture direction, project boundaries, recurring pain, or rules that future agents must preserve, write a durable narrative doc.

Use:

- `references/document-writing-style.md`
- `references/durable-doc-template.md`

Durable docs preserve user intent, current pain points, unfinished work, module boundaries, HumanGate rules, limitations, proof strategy, roadmap, and what future LMs must not forget.

## Offduty / Onduty Continuity

Use this when the user wants a deliberate work-boundary checkpoint that can be
picked up by a fresh session or another machine.

Default `offduty` now writes three layers:

1. repo-local checkpoint/session/pickup under `.agent.local/continuity/`;
2. a `lifeboat` markdown/json capsule under `.agent.local/continuity/lifeboat/`;
3. best-effort `bkc`/BrainKeeper dual-write to `.ai/continuity/` when a supported
   local session selector is available.

Default `onduty` is intentionally lightweight: it reads `pickup.md`,
`active.json`, the active checkpoint, and lifeboat/BKC refs. It does not require
native resume or a full transcript replay.

## Global Slash Command Install

The managed global command installer is:

```bash
python3 /Users/xin/auto-skills/shared-skills/handover/scripts/install_global_commands.py
```

It creates or updates `handover` skill symlinks, `offduty` / `onduty` skill
alias symlinks for Codex `$offduty` / `$onduty`, and managed `/offduty` /
`/onduty` command-file symlinks for slash-command hosts. It is idempotent and
skips unmanaged existing files instead of overwriting them.

The `mobius` skill runs this installer on trigger, so a user who has invoked
Mobius should get the continuity package loaded globally without extra
parameters or manual setup.

Do not use always-on hooks to mutate repo-level handoff files. Hooks may keep
session-local traces; `offduty` is the explicit fold point.

Default user UX is bare:

```bash
/offduty
/onduty
$offduty
$onduty
/Users/xin/auto-skills/shared-skills/handover/scripts/offduty
/Users/xin/auto-skills/shared-skills/handover/scripts/onduty
```

When the user says `$offduty`, `/offduty`, or `offduty` with no parameters, do
not ask the user to classify the work. Infer task id, work type, summary,
attempts, risks, validation, and next action from the chat, docs, git status,
and diff. Pass those details to the helper only when they are known; otherwise
run bare.

### Root Attribution

Do not assume the session launch folder is the work root.

Before offduty/onduty, infer actual touched roots from:

- tool `workdir`
- edited file paths
- `git -C` / `cd` commands
- explicit repo paths in chat
- dirty git status and branch evidence

For each candidate, resolve the git root with:

```bash
git -C "<candidate>" rev-parse --show-toplevel
```

If the session started in repo A but actual work happened in B and C, run
offduty separately for B and C using `--root`; do not write to A unless A was
also touched. If root cannot be inferred, fallback to cwd and say it was a
fallback.

Record both the actual repo root and the actual work cwd. If the shell command
is launched from a different helper directory, pass `--cwd "<actual-work-cwd>"`
so future sessions know where to restart.

Task ids are short by design. Do not use a full summary as `--task-id`; use a
concrete task line, and let the helper cap long names with a short hash suffix.

Options are script overrides, not normal user-facing requirements:

```bash
/Users/xin/auto-skills/shared-skills/handover/scripts/offduty --root "<actual-repo-root>" --cwd "<actual-work-cwd>" --task-id <task-id> --summary "<current truth>" --next-action "<next>"
```

Rules:

- default writes go to `.agent.local/continuity/`
- supervisor/offduty may update `active.json` and regenerate `pickup.*`
- plan/review/executor side sessions write checkpoint/session-local state without taking active
- failed/revisited attempts belong in checkpoint `attempt` fields, not default pickup prose
- use `--diff-mode patch` only when a dirty patch snapshot is worth preserving
- use `--bkc off` only when local BrainKeeper capture should be skipped
- use `--no-lifeboat` only for tests or when another system already wrote the capsule
- use `--layout legacy-ai-plan` only when a repo explicitly requires `.ai/plan`

Read `references/continuity-offduty-onduty.md` for the full contract.
