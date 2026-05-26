# Handover Concurrency And Ownership

## Conclusion

Default `agent continuity v1` avoids shared mutable `current.md`.
The durable source of truth is append-only checkpoint files plus session JSONL.

Use legacy `current.md` ownership only when a repo explicitly chooses
`--layout legacy-ai-plan`.

## Standard Flow

At shift boundary:

```bash
/Users/xin/auto-skills/shared-skills/handover/scripts/offduty --root .
```

Default writes:

- `.agent.local/continuity/checkpoints/<task-id>/<stamp>-<session-id>.json`
- `.agent.local/continuity/sessions/<session-id>.jsonl`
- `.agent.local/continuity/active.json` when this is main/supervisor scope
- `.agent.local/continuity/pickup.md` as a generated fresh-session view

If side session:

- write a checkpoint with `--scope side` when needed
- do not take the `active.json` pointer unless this session owns the mainline
- do not overwrite legacy `.ai/plan/current.md`

## Legacy Current Guard

For repos that explicitly use `.ai/plan/current.md`:

```bash
python3 /Users/xin/auto-skills/shared-skills/handover/scripts/handover_current.py status --root .
python3 /Users/xin/auto-skills/shared-skills/handover/scripts/handover_current.py claim --root . --task-id <id> --owner <agent> --cli <cli> --model <model> --next-action "<next>"
python3 /Users/xin/auto-skills/shared-skills/handover/scripts/handover_current.py audit --root .
```

If audit returns `CONFLICT_OR_INCOMPLETE`, do not write more current state until
the legacy handoff log is checked.
