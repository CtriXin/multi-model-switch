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

- Assume the worktree may contain user changes.
- Never revert or overwrite unrelated changes without explicit user request.
- Make surgical changes: every changed line should trace to the current task.
- Before global config changes, irreversible deletion, force-push, or adding dependencies, explicitly tell the user first.
- If changing project conventions, update this file or the relevant rule file.

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
