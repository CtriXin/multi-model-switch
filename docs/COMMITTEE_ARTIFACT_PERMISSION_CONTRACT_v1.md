# OpenCode Committee Artifact and Permission Contract v1

Status: draft implementation contract
Issue: https://github.com/CtriXin/multi-model-switch/issues/15
Profile: `committee`

## Purpose

This document defines how the OpenCode `committee` profile handles file writes,
formal vote artifacts, checker runs, and permissions. It complements
`docs/COMMITTEE_MODE_POLICY_v1.md`.

The default committee posture is advisory and non-formal. Durable writes, formal
votes, `decision.md`, ratification markers, merges, approvals, and deploy gates
require explicit user or project authorization.

## Artifact Modes

### `chat_only`

Default for simple advisory, estimate, and review work.

Rules:

- Members respond in chat.
- No member writes files.
- Host does not create or update decision artifacts.
- Host may mention suggested artifact paths for a future authorized run.

### `artifact_advisory`

Use for long reports, audits, or multi-section outputs that should be durable
but not formal votes.

Suggested layout:

```text
.ai/committee/<thread-id>/
  brief.md
  state.json
  members/
    <agent-id>.md
  synthesis.md
```

Rules:

- Host assigns each member an exact output path.
- A member may write only its assigned path.
- Chat reply should contain path, compact summary, and blocked/missing sections.
- Advisory artifacts must not be presented as quorum votes or approval records.

### `formal_vote_files`

Use only when the user or project governance explicitly asks for formal durable
ballots.

Suggested layout is project-defined. If no project rule exists, prefer:

```text
votes/<model-or-agent>.vote.md
```

Rules:

- Host assigns each member exactly one vote-file path.
- A member may write only its own assigned vote file.
- Members must not edit `decision.md`, ratification markers, or other members'
  vote files.
- Host must preserve provenance and must not claim a member wrote a file it did
  not write.

### `decision_file`

Use only when explicitly authorized after formal vote collection or project
checker output.

Rules:

- Host may update only the assigned decision artifact.
- Host must cite vote files, checker output, or explicit user instructions.
- Host must not ratify, merge, deploy, approve a PR, or mark final acceptance
  unless that action is explicitly requested and permitted by local rules.

### `checker_only`

Use when the project supplies a quorum checker, release gate, governance checker,
or CI/security runbook.

Rules:

- Host calls the provided checker instead of reimplementing project-specific
  rules.
- Checker command, exit code, and relevant output are deterministic evidence.
- Model votes must not override deterministic checker failure without an explicit
  human decision.

## Permission Profiles

### `readonly`

Allowed surfaces:

- read/list/glob/grep
- safe repository inspection commands such as `pwd`, `ls`, `rg`, `git status`,
  `git diff`, and `git log`

Denied by default:

- edits
- task delegation by members
- external directory writes
- formal artifact writes

### `artifact_write`

Extends `readonly` with scoped artifact writes.

Rules:

- Write permission is limited by prompt contract to assigned artifact paths.
- Members still cannot call other agents.
- Members still cannot update decision files unless assigned that exact role by
  user/project rules.

### `checker_run`

Extends `readonly` with selected validation/checker commands.

Examples:

- governance/quorum checker
- `git diff --check`
- relevant test or lint command when the task explicitly requires validation

Rules:

- Prefer project-provided checkers over invented rules.
- Record command and exit status in the final synthesis.
- Deterministic failures are not settled by majority vote.

### `implementation_ask`

Use only when the committee is asked to prepare or perform implementation.

Rules:

- Committee may prepare an execution packet by default.
- Actual edits require explicit user authority or an implementation profile.
- If edits are allowed, keep them narrow and preserve assigned ownership.

## Bypass Behavior

When MMS/OpenCode bypass converts `ask` permissions to `allow`, deny boundaries
must remain deny boundaries. A bypassed committee run still may not treat
unauthorized formal writes, merges, approvals, ratification, or external writes
as permitted.

## Host Safety Rules

The host must:

- declare artifact mode and permission profile before dispatch;
- assign exact file paths for any write;
- keep advisory artifacts separate from formal vote files;
- call provided checkers instead of reimplementing local governance;
- never promote chat/advisory ballots into formal quorum votes;
- never claim a file was written by a model or member unless it was actually
  written by that assigned agent.

## Member Safety Rules

A member must:

- read only what is needed;
- not call other agents;
- write only the assigned artifact path, if any;
- include provenance for evidence and inspected files;
- report blocked/missing sections instead of fabricating completion.

## Backward Compatibility

If no explicit artifact mode is configured, `committee` behaves as `chat_only`
for short outputs and `artifact_advisory` only when the host assigns scoped
paths for long outputs. Formal vote and decision-file behavior remains
opt-in only.
