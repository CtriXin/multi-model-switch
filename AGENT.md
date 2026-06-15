# Agent Rules

This file is the shared rule source for Codex, Claude, and other coding agents in this repository. Tool-specific entry files should import this file instead of duplicating the same rules.

## Default Language

- Always respond in Simplified Chinese.
- Keep technical terms in English.
- Put the conclusion first.
- Keep user-facing answers short unless detail is required.

## Source Of Truth

- Treat this file as the primary shared rule file.
- Tool-specific files such as `CLAUDE.md` should only contain the loader line and truly tool-specific notes.
- When shared behavior changes, update this file first.

## Commit Identity

For every agent-created commit, follow:

@/Users/xin/.agents/rules/commit-identity.md

Minimum required behavior, even if the imported file is not visible:

- Never change global `git config`.
- Use per-command author and committer identity.
- Email format: `<modelName>@<familyName>.com`, for example `claude-sonnet-4.5@anthropic.com` or `gpt-5@openai.com`.
- Add trailers: `Agent-Model`, `Agent-Family`, `Agent-Session`, `Agent-Run` when available, and `Agent-Step`.
- Prefer `CODEX_THREAD_ID`, then `CLAUDE_SESSION_ID`, then other stable session/run ids for `Agent-Session`.
- Prefer small, verified commits.

Example shape:

```text
fix: tighten web UI focus states

Agent-Model: claude-sonnet-4.5
Agent-Family: anthropic
Agent-Session: <session-id>
Agent-Step: 0.0.1
```

## Worktree Safety

- At the start of each coding/review turn, run `git pull --ff-only` for the current branch before editing, unless local changes make that unsafe; if pull is blocked, stop and report the exact blocker.
- Assume the worktree may contain user changes.
- Never revert or overwrite unrelated changes without explicit user request.
- Make surgical changes: every changed line should trace to the current task.
- Before global config changes, irreversible deletion, force-push, or adding dependencies, explicitly tell the user first.
- If changing project conventions, update this file or the relevant rule file.

## Default Dev Entry

- The repository root should be the clean maintainer entrypoint on `dev`.
- Do not use `.worktrees/dev` as the shared default development entry.
- The repository root is for coordination: pull latest `dev`, inspect status, open issues, and create isolated task worktrees.
- Non-trivial work must start from an issue and use a dedicated branch/worktree such as `.worktrees/issue-14-redline-gate`.
- Agents must not stack substantive changes or leave untracked files in the shared `dev` entry unless the human explicitly asks for direct edits there.
- Docs-only plan/report changes may be committed by default when the human asks to record, submit, or produce the document, but the commit must stage only the target document and no unrelated dirty files.

## Issue / PR / Committee Gate

- MMF/MMS development should track problems through issues, submit changes through PRs, and require committee review before merge.
- Agents must not merge PRs or bypass the committee review gate.
- Agents must not create commits unless the human explicitly approves that specific commit.
- If commit approval is granted, keep the commit scoped, verified, and traceable; do not include unrelated dirty files.
- Because this repo is developed from multiple computers, always check remote freshness before work and avoid assuming the local worktree is current.

## Protected Surfaces

Before changing launcher, routing, bridge, config, account, or TUI selection logic, read:

@docs/AGENT_GUARDRAILS.md

Treat these as protected surfaces:

- `mms_core.py`
- `mms_launchers.py`
- `mms_tui.py`
- `mms_bridge.py`
- `mms_account_state.py`
- `mms_session.py`
- `mms_adapter_registry.py`
- `mms`
- `ccs`

Do not silently change default launch behavior, model/source resolution order, config schema, account isolation semantics, bridge fallback rules, provider priority, or TUI return structure.

## Claude-Sensitive Provider Safety

For Claude-sensitive providers such as `xin`, `fishcrs`, and `trcrs` if restored:

- Do not enable `1M context` by default.
- Do not add extra Anthropic endpoint probes by default.
- Only loosen behavior after real smoke tests prove it works.
- For Claude account binding changes, check proxy logs, `metadata.user_id` type, and Admin UI key visibility.

## Design Work

- For UI/frontend design, use the installed `impeccable` skill when available.
- Respect `PRODUCT.md` and `DESIGN.md` when present.
- Do not introduce generic AI design patterns: gradient text, decorative glassmorphism, nested cards, excessive rounded cards, or repeated icon-card grids.
- For design-system changes, update the relevant design docs together with code.

## Validation

- For bugfixes, reproduce or inspect the failure before repair when practical.
- Let validation scale with risk.
- State what was executed, inspected, or assumed in the closeout.
