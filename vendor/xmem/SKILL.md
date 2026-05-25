---
name: xmem
description: Use when the user asks for xmem, cross-project memory, project truth index, prior similar work, preserving feature invariants, or compact agent context; first verify that an `xmem` CLI or source registry is available.
---

# xmem

xmem is a lightweight local truth index between source files, notes, and a generated DB/cache. It helps agents find durable project facts, invariants, decisions, and prior fixes without scanning every repository every time.

Public MMS rule: this bundled skill is generic. It must not assume any specific company, wiki, ticket system, Feishu/Lark workspace, domain registry, or user-specific folder. Use only sources that exist on the current machine.

## Availability Gate

Before relying on xmem, check availability:

```bash
command -v xmem
xmem status
```

If `xmem` is not installed or `xmem status` says no registry/sources are available:

- do not block the user's task;
- do not invent memory facts;
- continue with normal repo inspection;
- optionally suggest installing/configuring xmem if the user asked for memory features.

MMS session hooks are silent and fail-open for this reason.

## Resume Rule

`xmem resume` is a compact takeover packet for agents. Use it when a fresh session receives an issue slug, domain, service, repo, or task phrase and needs identity, historical pitfalls, current gates, evidence refs, token_savers, and next_action without reading long handoffs first. It is a read model only; live runtime facts and owner-source truth still need verification.

## Truth Rule

Truth lives in user-owned sources, such as:

- `.xmem/*.yaml` cards inside a repo;
- source Markdown and docs;
- code and git history;
- local issue/bug/release notes;
- generated compact exports from tools the user has configured;
- explicit human confirmations.

`~/.xmem/registry.sqlite` is a generated index/cache, not the ultimate source of truth.

## Useful Commands

```bash
xmem help
xmem status
xmem doctor
xmem sync
xmem preflight "query"
xmem resume "query"
xmem resume --fields issue=demo domain=example.com task="query"
xmem context "query"
xmem why "query"
xmem open "query"
xmem new
xmem check --sources
xmem fix
xmem suppress --card <id> --for-query "query" --reason irrelevant
xmem gain
```

## Workflow

1. Run `xmem status` or `xmem doctor` when state is unclear.
2. Run `xmem resume "<issue|domain|service|task>"` when taking over an existing task or fresh session before reading long handoffs.
3. Run `xmem preflight "<task>"` before development or bugfix edits when xmem is available.
4. Run `xmem context "<task>"` before broad repo traversal or project selection.
5. If source freshness is stale, run `xmem sync` before relying on the packet.
6. Treat verified cards as evidence; treat inferred/partial/stale/unknown/disputed cards as hints.
7. For edits that hit a feature with invariant cards, run `xmem check` before final response.
8. If a matched card is true but irrelevant, use `xmem suppress`; if it is wrong, use `xmem fix`.

## Agent Hooks

When available, MMS may run lightweight xmem session hooks:

- `start`: register/sync the current project path;
- `finish`: record a close marker without injecting memory text;
- task-specific events such as `fix`, `release`, or `deploy` if the user has configured them.

Hook rule: hooks may create local pending cards or outbox entries, but must not silently rewrite source docs, promote guessed facts, or block the session when xmem is absent.

## Source Routing

Keep xmem compact:

- store small invariants, decisions, relation cards, and source pointers;
- keep long docs/logs/screenshots in their original source;
- use evidence paths instead of pasting bulky raw output;
- verify dynamic runtime state live before acting on it.

Do not duplicate a full wiki, issue tracker, or code database into xmem. xmem is the routing/index layer, not the owner of every fact.

## New Projects

Use `xmem new` in a new repo when the user wants that repo registered. It may create `.xmem/` cards from git/package/folder evidence and make future `xmem sync` discover the repo.

Read `references/card-schema.md` before creating or revising cards.
