---
name: xmem
description: Use when the user asks for xmem, cross-project memory, project truth index, finding prior similar project work, preserving feature invariants, importing Project Wiki / issue-tracking evidence, or compact agent context for existing projects.
---

# xmem

xmem is a lightweight truth index between wiki and DB. Use it to find durable project facts, methods, invariants, and evidence without scanning every repo.

Truth rule: `.xmem/*.yaml`, source Markdown, code, git, runtime APIs, and human confirmations are truth. `~/.xmem/registry.sqlite` is generated index/cache only.

## Short Commands

```bash
xmem help
xmem status
xmem doctor
xmem sync
xmem preflight "query"
xmem preflight --fields domain=example.com task="query"
xmem context "query"
xmem why "query"
xmem open "query"
xmem new
xmem check --sources
xmem fix
xmem suppress --card <id> --for-query "query" --reason irrelevant
xmem gain
xmem gain --summary
xmem gain card <id>
```

## Workflow

1. Run `xmem preflight "<task>"` before development or bugfix edits to surface historical bug-patterns, invariants, and required checks.
2. Run `xmem context "<task>"` before broad repo traversal or project selection.
3. If `source_freshness.status` is not `fresh`, run `xmem sync` before relying on the packet.
4. Trust only cards marked `verified`; treat `inferred`, `partial`, `stale`, `unknown`, and `disputed` as hints.
5. For edits that hit a feature with invariant cards, run `xmem check` before final response.
6. Add or update a small card when durable knowledge is discovered; avoid long wiki prose.
7. Use `xmem gain` when asked what xmem saved.
8. Use `xmem doctor` when maintenance state is unclear; it aggregates registry, source exports, local card portability, backup health, outbox, and current repo registration.

`xmem gain` shows the full event/query/card dashboard by default. Use `xmem gain --summary` only when a short key signal is enough: real confidence result, confirmed-vs-rough token numbers, hit overview, risk signals, top query order, and a few queries needing review. Top queries are sorted by calls desc, then matches desc, then rough tokens desc. In detail view, `Top 查询` is query-text aggregation, `Top Cards` is top-card aggregation, missing old telemetry status/confidence is hydrated from current registry, `Top Card 解释` shows common/recent queries plus source/score/why, and `粗估占比` bars are relative rough-token share inside that section, not progress or confirmed savings. Use `xmem gain card <id>` when one card looks noisy or surprisingly high-frequency. `xmem gain --detail` remains a compatibility alias for the default full dashboard.

Policy rule: when deciding whether a memory is truth, hint, or blocker, use `docs/policies/truth-level.md`, `docs/policies/preflight-severity.md`, and `docs/policies/promotion-policy.md`. In short: Project Wiki pending is hint-only, Issue patterns may be partial until repeated/reviewed, dynamic SCMP facts need live verification, and preflight blockers must stop edits/deploy.

Output rule: use `docs/policies/agent-output-compactness.md` when tool output may be large. Prefer compact summaries and evidence paths; avoid pasting raw SCMP pod JSON, broad issue-tracking grep, safe-access card JSON, Feishu read-back payloads, repeated `_notice` text, or long skill docs into agent context.

Layered symbolic rule: use `docs/policies/layered-symbolic-memory.md` for context/preflight packets. Read compact top sections first, then drill down through `node_id`, `memory_layer`, `evidence_ref`, `source_ref`, and `source_path` only when details matter. Do not create lossy summaries without a source path.

`xmem context` is LLM-first: use `symbolic_memory`, `resolution.status`, `suggested_queries`, `correction_guidance`, `why`, `truth`, `source_ref`, `warnings`, and `next_reads` to decide what to read next. Do not infer a single project when `do_not_assume_single_project` is true. Duplicate cards may be fused; read `supporting_cards` for alternate sources behind the primary card.

If a long query contains a verified compact alias such as `网文二 repo validation_service`, treat the verified identity anchor as the route and use the extra words as requested fields. Do not surface weak same-template relation cards once a verified identity family is locked.

For SCMP/domain/service work, also read `traffic_switch` and `gain_hints` when present. A verified `traffic.switch` card can be used as the starting route for prod/validation service, repo, branch hints, approval group, common verification, and skipped lookup guidance. Domain/service binding and latest deploy state still need live verification; Project Wiki pending candidates remain hint-only.

Traffic switch wording rule: `validation_service` is a candidate traffic target for validating new behavior before cutover, not a generic test environment. Do not infer test-environment semantics only because a service name contains `-test`.

`xmem preflight` is the development-start packet. Use `severity`, `can_proceed`, `blockers`, `required_before_edit`, `required_before_deploy`, `readiness`, `risk_level`, `known_bug_patterns`, `must_keep`, `avoid`, `known_failure_modes`, `required_checks`, and `source_refs` before editing. If `severity` is `block` or `can_proceed` is false, stop edits/deploy until blockers are resolved. If `readiness` is `blocked_source_stale`, sync first; if it is `needs_disambiguation`, resolve the project/entity before changing code.

For hook-generated or noisy prompts, prefer `xmem preflight --fields domain=... service=... repo=... task=... mode=...`. Structured preflight ignores old raw context when fields are present. If domain/service/repo fields do not resolve to a verified target anchor, treat `readiness: needs_clarification` as a blocker and rebuild the query instead of using returned guardrails.

For SCMP/Feishu/issue/rg/log-heavy work, preflight may activate compact-output guardrails. Prefer compact JSON/TOON summaries, store bulky raw output as evidence files, and check current issue/progress, xmem context, Project Wiki index, and directed repo reads before broad grep.

If a matched card is true but irrelevant for this task, use `xmem suppress --card <id> --for-query <query-or-hash> --reason irrelevant`. This is ranking feedback only; do not use it to correct wrong truth. Use `xmem fix` for wrong aliases/facts.

## Agent hooks

When acting as an agent, use xmem hooks without asking the user to remember commands:

- On session/task start: run the `start` hook to register the project and refresh local cards.
- On session/task end: a silent `finish` hook without text may record a close marker; it must not create memory or inject context.
- When durable knowledge is discovered: run a `note` or `finish` hook with a short LLM-written summary.
- For bugfix/release/deploy work: use `fix`, `release`, or `deploy` events so xmem can queue Project Wiki and issue-tracking follow-up.

Hook rule: xmem may create `.xmem/cards/hook.*.yaml`, append a Project Wiki write request, or create an issue seed. It must not silently rewrite Project Wiki Markdown or promote guessed data to a final issue record.

MMS sessions normally inject this skill and run lightweight xmem session-start/session-end hooks automatically. Do not ask the user to install or remember hook commands inside MMS-launched Codex/Claude/OpenCode/agy sessions.

## Sync

Use `xmem sync` as the default refresh. It rebuilds `~/.xmem/registry.sqlite` from Project Wiki, issue-tracking, built-in cards, `~/.xmem/cards`, and known local folders in `~/.xmem/sources.json`.

These imports are read-only. They create searchable cards and evidence pointers in `~/.xmem/registry.sqlite`. If `xmem status` shows `0 cards`, run `xmem sync`; in isolated agent sessions it should still use the real user's `~/.xmem`, not the session-local HOME.

If present, xmem also consumes compact source exports:

- `project-wiki/data/xmem-export.cards.jsonl`
- `project-wiki/data/agent-inbox.jsonl`
- `issue-tracking/index/xmem-export.cards.jsonl`
- `issue-tracking/index/bug-patterns.jsonl`
- `~/.xmem/outbox/project-wiki/*.json`
- `~/.xmem/outbox/issue-tracking/*.md`

These exports are bridge/index inputs only; Project Wiki and Issue Record remain the source truth.
Project Wiki `agent-inbox.jsonl` rows are pending writebacks only: xmem imports them as `wiki.pending` / `partial` / hint-only cards. They must not override verified Project Wiki truth.
xmem outbox writes are also imported as pending hints only: Project Wiki JSON requests become `wiki.pending`, and Issue Record seeds become `evidence.issue` until the owning source accepts/exports them.

Use `xmem check --sources` when Project Wiki or Issue Record changes its export. Missing optional exports are reported as optional_missing; malformed JSONL rows, duplicate ids, invalid truth status, or invalid confidence are errors.

`xmem sync` rebuilds the generated SQLite registry atomically through a temp file and final swap, so concurrent agents should keep reading the previous complete registry until the new one is ready.

If registered repos already have `.ai/map/map.db` or `.codegraph/codegraph.db`, sync imports only compact `code.index` / `code.hotspot` refs. These refs help route an Agent to likely files/symbols, but generated DBs and source files remain truth; verify in code before editing. `map` is the primary quick code map, while `codegraph` is an optional deep-symbol tool.

## Source Routing

- Project/entity truth goes to Project Wiki: service, repo, domain, branch, deploy target, owner, business name, oral alias.
- Bug truth goes to Issue Record: symptom, root cause, fix pattern, verification, regression guard, evidence paths.
- xmem truth stays compact: cross-project method/invariant/relation cards with source pointers only.
- Code structure truth stays in source files plus generated `.ai/map` / `.codegraph` indexes; xmem stores only routing refs.
- Do not duplicate full Project Wiki or Issue Record truth into xmem; xmem is the control plane and generated index consumer.
- When source exports change, require `xmem check --sources` and `xmem sync`; context should be treated as stale until `source_freshness.status` is `fresh`.
- Promotion rule: candidate -> owner source review -> export -> `xmem sync`; never promote pending rows, single-incident bug patterns, or dynamic runtime state silently.
- Output rule: store raw logs/JSON as evidence paths and feed agents compact summaries first.

## New folders and corrections

Use `xmem new` in a new folder. It creates `.xmem/`, writes an identity card from git/package/folder evidence, and registers the folder so future `xmem sync` can find it from other projects.

Use `xmem fix` when a match is wrong or ambiguous. It asks for the entity/query, wrong alias, optional correct alias, and basis; then writes a correction/dispute card under `~/.xmem/cards/corrections`.

`xmem check` uses local and indexed invariant/rule/guard cards to inspect the current git diff. Treat warnings as blockers until the invariant is preserved or consciously updated.

## Card schema

Read `references/card-schema.md` when creating or revising cards.
