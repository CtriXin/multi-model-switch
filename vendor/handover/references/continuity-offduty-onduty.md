# Continuity Offduty / Onduty

Status: active
Owner: handover
Schema: agent.continuity.v1

## Conclusion

Use `offduty` and `onduty` as explicit shift boundaries, not as always-on hooks.
The default contract is `agent continuity v1` under `.agent.local/continuity/`.
It works for ordinary repos even when Moebius is not enabled.

Legacy `.ai/plan/current.md` / `handoff.md` / `packet.json` is still supported
only when a repo explicitly asks for `--layout legacy-ai-plan`.

## Command Surface

Default human-facing commands after global install:

```text
$offduty
$onduty
/offduty
/onduty
```

Direct script commands:

```bash
/Users/xin/auto-skills/shared-skills/handover/scripts/offduty
/Users/xin/auto-skills/shared-skills/handover/scripts/onduty
```

Global skill alias install is idempotent:

```bash
python3 /Users/xin/auto-skills/shared-skills/handover/scripts/install_global_commands.py
```

Mobius runs that installer as trigger preflight, so invoking Mobius should make
the continuity package available to future Claude/Codex/Agents/OpenCode
sessions. Codex should prefer `$offduty` / `$onduty`; slash-command hosts may
use `/offduty` / `/onduty`.

When a user says `$offduty` or `/offduty`, the LLM should infer classification
and content. The user should not need to provide `task-id`, `scope`, `lane`, or
type.

Machine/script overrides remain available:

```bash
/Users/xin/auto-skills/shared-skills/handover/scripts/offduty --task-id <task-id> --summary "<current truth>" --next-action "<next>"
```

Useful options:

- `--layout agent-local`: default write target, `.agent.local/continuity/`.
- `--layout legacy-ai-plan`: old `.ai/plan` contract for explicit legacy repos.
- `--work-type`: internal override only; otherwise inferred from context/branch.
- `--scope main`: update `active.json` and regenerate `pickup.*`.
- `--scope side`: write checkpoint/session state without taking active pointer.
- `--diff-mode stat`: record git status and diff stat only; default.
- `--diff-mode patch`: also write `.agent.local/continuity/diffs/<stamp>-<task>-<session>.patch`.
- `--attempt`, `--attempt-result`, `--keep`: record failed/revisited attempts without polluting pickup.
- `--validation`, `--risk`, `--decision`, `--ref`: add execution evidence.
- `--bkc auto|off|required`: best-effort BrainKeeper dual-write by default; `required` records continuity then returns non-zero if BKC fails.
- `--bkc-preset standard`: fidelity for BKC file output.
- `--no-lifeboat`: skip the extra lightweight markdown/json capsule.

## Root Attribution

The source of truth is the actual touched repo/root, not the folder where the
session was launched.

Before writing offduty, infer touched roots from:

- tool `workdir`
- edited file paths
- `git -C` / `cd` commands
- explicit repo paths in chat
- dirty git status and branch evidence

Resolve each candidate with:

```bash
git -C "<candidate>" rev-parse --show-toplevel
```

If one session started in repo A but worked on repo B and repo C, run:

```bash
/Users/xin/auto-skills/shared-skills/handover/scripts/offduty --root "<repo-B-root>"
/Users/xin/auto-skills/shared-skills/handover/scripts/offduty --root "<repo-C-root>"
```

Do not write to repo A unless A was actually touched. If no actual root can be
inferred, fallback to cwd and explicitly report that fallback.

Record actual work cwd separately from root. If the command runs from a helper
directory, pass:

```bash
/Users/xin/auto-skills/shared-skills/handover/scripts/offduty --root "<actual-repo-root>" --cwd "<actual-work-cwd>"
```

Each checkpoint records cwd, root, session id, session hash, checkpoint hash,
model name/family, and commit email hint. Task ids use a capped slug with a short hash suffix when the
inferred name is too long.

Commit identity must line up with continuity identity. Use command-scoped
`<modelName>@<familyName>.com` author/committer identity plus `Agent-Model`,
`Agent-Family`, `Agent-Session`, optional `Agent-Run`, and `Agent-Step: x.y.z`
trailers when the repo has no stronger branch/milestone inheritance rule.

## File Contract

Default write set:

- `.agent.local/continuity/active.json`: current recommended continuation pointer.
- `.agent.local/continuity/pickup.json`: generated machine-readable pickup view.
- `.agent.local/continuity/pickup.md`: generated human/LM pickup view.
- `.agent.local/continuity/checkpoints/<task-id>/<stamp>-<session-id>.json`: append-only checkpoint.
- `.agent.local/continuity/sessions/<session-id>.jsonl`: append-only session journal.
- `.agent.local/continuity/lifeboat/<stamp>-<task-id>-<session-id>.md`: lightweight human/LM recovery capsule.
- `.agent.local/continuity/lifeboat/<stamp>-<task-id>-<session-id>.json`: machine-readable copy of that capsule.
- `.agent.local/continuity/diffs/`: optional patch snapshots when `--diff-mode patch` is used.
- `.agent.local/continuity/archive/`: optional old generated/index material.
- `.ai/continuity/*.md`: optional BKC/BrainKeeper pack when the local session can be resolved; added to local git exclude by the helper.

Source-of-truth order:

1. checkpoint JSON files;
2. session JSONL files;
3. git state and referenced artifacts;
4. lifeboat and BKC backup packs for stale/missing resume paths;
5. generated `active.json` / `pickup.*` views.

## Multi-Session Rule

Do not let every plan/review/executor session overwrite a global truth file.

- Planner/reviewer sessions write their own artifacts and optional checkpoints.
- Executor sessions write result artifacts and optional checkpoints.
- Side sessions use `offduty --scope side` or checkpoint-only state.
- Supervisor/offduty uses `--scope main` or `--scope auto` when it owns the task.
- Hooks may write session-local events, but should not mutate active pointers.
- `active.json` is a pointer; losing it is recoverable from checkpoints.

## Attempt Log Policy

Record the path that got you there, not only the final answer.

Use `Keep?` values:

- `yes`: needed for the current continuation.
- `revisit`: previous conclusion may be invalid; future agent should know.
- `no`: dead end; keep one-line reason only.
- `archive`: preserved for provenance but not default context.

Example:

```text
scheme 2 failed keep=revisit note=network outage made result unreliable
scheme 4 partial keep=no note=proved business logic was not root cause
return to scheme 2 keep=yes note=network recovered; path viable
```

## Fresh Session Read Rule

`onduty` should make a new session productive without reading old chat:

1. read project rules (`AGENTS.md`, `README.md`, `CLAUDE.md` when present),
2. read `.agent.local/continuity/pickup.md`,
3. read `.agent.local/continuity/active.json`,
4. read the Lifeboat / BKC Backup section when present,
5. open only the active checkpoint or matching task checkpoints,
6. inspect `git status` / `git diff` before editing if dirty.

Archive is opt-in. Open it only to debug old decisions.
Native resume and full BKC transcript replay are opt-in; default `onduty` stays
lightweight and uses file refs instead of replaying the session.

## Moebius Slot Boundary

This is a continuity addon/slot, not a new executor.

- Moebius owns mainline, HumanGate, trace, and final judgment.
- Looop owns live session hooks and compaction recovery.
- Handover owns file shape and offduty/onduty fold/unfold.
- Pilot/Hive/Ant output artifacts feed references back into the continuity packet;
  they do not become the continuity source of truth.
- Moebius internal `.ai/plan/*` may be referenced as artifacts, but generic
  offduty/onduty does not write there unless `--layout legacy-ai-plan` is used.
