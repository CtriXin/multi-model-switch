# handover

Read this before using the handover skill.

## What This Skill Is

`handover` is a shared local continuity skill for Claude, Codex, OpenCode, Hive
workers, cheaper models, and local scripts.

Default durable surfaces use `agent continuity v1`:

- `.agent.local/continuity/active.json`
- `.agent.local/continuity/pickup.json`
- `.agent.local/continuity/pickup.md`
- `.agent.local/continuity/checkpoints/<task-id>/<stamp>-<session-id>.json`
- `.agent.local/continuity/sessions/<session-id>.jsonl`

Legacy `.ai/plan/current.md`, `.ai/plan/handoff.md`, and `.ai/plan/packet.json`
are supported only when a repo explicitly asks for `--layout legacy-ai-plan`.

## Mandatory Execution Rule

For execution-related work, do not rely on chat memory.
Write durable repo-local continuity files.

## Offduty / Onduty

Global `$offduty` / `$onduty` skill aliases are installed, and old managed
`/offduty` / `/onduty` command symlinks are cleaned, by:

```bash
python3 <handover-root>/scripts/install_global_commands.py
```

`<handover-root>` is the directory containing this file or the target of the
installed `handover` skill symlink. Do not use a developer-machine absolute
path in public installs.

Mobius runs this installer as trigger preflight. The installer is idempotent,
creates `handover`, `offduty`, and `onduty` skill symlinks for Agents, Claude,
Codex, and OpenCode, and does not overwrite unmanaged files.

For shift-boundary continuity, prefer bare commands:

```bash
$offduty
$onduty
/offduty
/onduty
<offduty-skill-dir>/offduty
<onduty-skill-dir>/onduty
```

The installed `offduty` / `onduty` alias directories include same-name wrapper
scripts that delegate to `../../scripts/*` relative to the alias target.

If the user says `$offduty` or `/offduty` with no parameters, do not ask them to
classify the work. Infer the task, work type, current truth, useful failed
attempts, risk, validation, and next action from the active chat plus cheap repo
evidence.

Do not assume the session launch folder is the root. Infer actual touched
repo/root from tool workdirs, edited paths, `git -C` / `cd` commands, and
explicit repo paths. If the session started in A but work happened in B/C, run
offduty with `--root` and `--cwd` for B/C and do not write to A unless A was
touched. Record cwd, root, session id/hash, checkpoint hash, model name/family, and
commit email hint when known. Keep task ids short; do not turn long summaries into path names.
When committing, use the same model/session identity via command-scoped
`<modelName>@<familyName>.com` author/committer plus `Agent-Model`,
`Agent-Family`, `Agent-Session`, optional `Agent-Run`, and `Agent-Step: x.y.z`
trailers when no stronger project rule exists.
Options such as `--task-id`, `--scope`, or `--diff-mode` are internal overrides,
not normal user-facing questions.

Use `--scope side` for plan/review/executor side sessions. Only supervisor or
explicit offduty mainline checkpoints should update `active.json` and
`pickup.*`. Keep failed attempts in checkpoint fields; keep old history in
archive or referenced artifacts, not default fresh-session context.

## Multi-Session Safety

Default continuity is append-only.

If you are not the active owner:

- write a new checkpoint and session event
- do not take the active pointer unless asked or clearly mainline
- do not edit legacy `current.md` unless the repo explicitly uses legacy layout

If a repo requires legacy current ownership:

```bash
python3 <handover-root>/scripts/handover_current.py claim --root . --task-id <id> --owner <agent> --cli <cli> --model <model> --next-action "<next>"
python3 <handover-root>/scripts/handover_current.py audit --root .
```

## Required Metadata

Every checkpoint should include:

- timestamp
- agent
- CLI
- model
- task id or run id
- status
- next action

## Do Not Do This

- do not use pickup files as transcript dumps
- do not use `agent-release-notes.md` as current truth
- do not omit identity fields in concurrent work
- do not overwrite legacy `current.md` from side sessions
- do not publish `.agent.local/` to a public repo

## Durable Narrative Docs

If the user gives long-term vision, architectural direction, or cross-project
execution rules, create a durable narrative doc instead of only updating compact
handoff.

Read:

- `references/document-writing-style.md`
- `references/durable-doc-template.md`

Do not let compact status files replace the project north star.
