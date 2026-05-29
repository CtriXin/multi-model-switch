# handover

Shared continuity skill for Claude, Codex, OpenCode, Hive workers, cheaper
models, and local scripts.

It standardizes compact local handoff files so work can continue across models,
windows, machines, and fresh sessions without copy-pasting chat history.

## Core Surfaces

Default generic layout is `agent continuity v1`:

- `.agent.local/continuity/active.json` - current pointer only
- `.agent.local/continuity/pickup.json` - generated machine pickup view
- `.agent.local/continuity/pickup.md` - generated human/LM pickup view
- `.agent.local/continuity/checkpoints/<task-id>/<stamp>-<session-id>.json` - append-only source of truth
- `.agent.local/continuity/sessions/<session-id>.jsonl` - session-owned event stream
- `.agent.local/continuity/lifeboat/*.md,json` - lightweight fallback capsule
- `.agent.local/continuity/indexes/*.json` - rebuildable caches

Legacy `.ai/plan/current.md`, `.ai/plan/handoff.md`, and `.ai/plan/packet.json`
remain available only for repos that explicitly opt into `--layout legacy-ai-plan`.

## Install

### Global Skill Aliases

Preferred one-time/idempotent installer:

```bash
python3 <handover-root>/scripts/install_global_commands.py
```

`<handover-root>` is this directory, for example the bundled
`$MMS_HOME/vendor/handover` in public MMS installs.

It installs symlinks for:

- `handover` skill
- `offduty` / `onduty` skill aliases, so Codex can use `$offduty` / `$onduty`
- cleanup of old managed `/offduty` and `/onduty` command symlinks, so the same entry does not appear twice

Targets:

- `~/.agents`
- `~/.claude`
- `~/.codex`
- `~/.config/opencode`
- `~/.opencode`

The installer removes old managed command symlinks and keeps unmanaged command
files untouched. If a non-symlink skill already exists, it is skipped instead of
replaced.

The `mobius` skill runs this installer as trigger preflight, so after any
Mobius invocation `$offduty` / `$onduty` skill aliases should be available in
fresh sessions.

### Claude

```bash
ln -s <handover-root> ~/.claude/skills/handover
```

### Codex

```bash
ln -s <handover-root> ~/.codex/skills/handover
```

## Main Rule

Do not use old chat as the source of truth.

For generic projects:

- write append-only checkpoints under `.agent.local/continuity/checkpoints/`
- write session events under `.agent.local/continuity/sessions/`
- let only main/supervisor checkpoints update `active.json`
- treat `pickup.md` and `pickup.json` as generated views
- keep `.agent.local/` private or private-synced, not public

For legacy `.ai/plan/current.md` projects, `current.md` is not concurrency-safe:

- top-level owner may write `current.md`
- side sessions write task-local state
- meaningful shift boundaries prepend `handoff.md`
- all entries include agent / CLI / model / task id / status / next action

## Runtime Guard

Use only for the legacy `.ai/plan/current.md` layout:

```bash
python3 <handover-root>/scripts/handover_current.py status --root .
python3 <handover-root>/scripts/handover_current.py claim --root . --task-id <id> --owner <agent> --cli <cli> --model <model> --next-action "<next>"
python3 <handover-root>/scripts/handover_current.py audit --root .
```

## Offduty / Onduty

Use this at an intentional shift boundary: feature slice complete, iteration
complete, machine switch, context pressure, or major direction reversal.

Default usage:

```bash
/offduty
/onduty
$offduty
$onduty
<offduty-skill-dir>/offduty
<onduty-skill-dir>/onduty
```

The installed `offduty` / `onduty` alias directories include same-name wrapper
scripts that resolve `../../scripts/*` relative to the alias target, so public
installs do not depend on a developer checkout path.

Agents should infer task id, type, summary, risk, validation, and next action
from chat, docs, git status, and diff. Extra flags are overrides for scripts or
automation, not required user input.

Agents must also infer actual work roots. If a session started in repo A but did
work in repo B or C, `offduty` writes to B/C with `--root`, not to A. Multiple
touched roots mean multiple repo-local checkpoints. Each checkpoint records the
actual work cwd, resolved root, session id, session hash, checkpoint hash, and
model name/family and commit email hint when known.

When an agent creates a git commit, it must use the same identity: command-scoped
`<modelName>@<familyName>.com` author/committer, trailers `Agent-Model`,
`Agent-Family`, `Agent-Session`, optional `Agent-Run`, and `Agent-Step: x.y.z`
when the project has no stronger branch or milestone inheritance rule.

Task ids are capped and hash-suffixed when needed, so long summaries do not
become huge path names.

`offduty` writes bounded continuation state under `.agent.local/continuity/` by
default. It updates `active.json` / `pickup.*` only when the command owns the
main scope. It also writes a lifeboat capsule and best-effort BKC pack so stale
native resume or missing session cache does not lose the current truth.

`onduty` prints the fresh-session read order plus active pointer, pickup view,
recent checkpoints, lifeboat/BKC backup refs, and git status/diff evidence. It
is lite by default and does not replay native resume unless the user asks.

## Status Vocabulary

- `pending`
- `running`
- `waiting`
- `queued_retry`
- `fallback`
- `blocked`
- `request_human`
- `failed`
- `done`

## Durable Narrative Docs

Use compact files for immediate continuation.

Use durable narrative docs for long-term project intent, architecture,
boundaries, HumanGate rules, proof strategy, and future roadmap.

See:

- `references/document-writing-style.md`
- `references/durable-doc-template.md`
