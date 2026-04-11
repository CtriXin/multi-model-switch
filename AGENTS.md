# AGENTS.md - multi-model-switch Bootstrap

> This file is the bootstrap entry for local agents.
> Treat it as the startup map, not the full rule source.

This file applies to both `Codex` and `Claude`.

## Startup Order

1. Read the primary rule file in this order:
   - `AGENT.md`
   - `CLAUDE.md`
   - `AGENT_RULES.md`
2. Read `.ai/manifest.json` if present
3. Read `.ai/plan/current.md` if present
4. Read `.ai/workflow.md` if present
5. Read `AI_BOOTSTRAP.md` if present

## Conflict Rules

- Project-specific rules win over shared defaults.
- If multiple rule files exist, prefer `AGENT.md`, then `CLAUDE.md`, then `AGENT_RULES.md`.
- `.ai/plan/current.md` is the current task source of truth when present.

## TODO Management

- On plan phase or new task, list TODOs in **four-quadrant format** (Urgent+Important / Important+Not Urgent / Urgent+Not Important / Neither) in `.ai/plan/TODO.md`.
- Each item: `- [ ] description (source: @agent, created: YYYY-MM-DD)`
- On completion: `- [x] description (source: @agent, created: ..., completed: YYYY-MM-DD)`
- At plan start, archive `[x]` items to `docs/archive/todo-archive-YYYY-MM.md` (append-only, never delete).

## Release Handoff

- After each completed iteration stage, append a record to `./.ai/agent-release-notes.md`.
- Keep that file ignored in `.gitignore`; it is local release-prep context.
- Each record should include:
  - timestamp
  - agent name
  - landed commit/tag/release, if any
  - changed file scope
  - concise landed summary
  - reusable release-note bullets
  - validation run and result
- Before preparing a version bump, tag, or GitHub release, `Codex` should read this file first.

## Versioning And GitHub Release

- For user-facing iterations intended to land publicly, do not stop at `git push`; also prepare a version bump, git tag, and GitHub Release.
- Use monotonic semver-like tags (for example `v1.0.1`, `v1.1.0`, `v2.0.0`); do not reuse or overwrite an existing tag.
- Patch release:
  - bug fix
  - docs/install/release-note only changes tied to a shipped fix
- Minor release:
  - backward-compatible feature or notable UX improvement
- Major release:
  - breaking CLI/config/runtime behavior change
- Before `gh release create`, summarize at least:
  - what changed
  - what was fixed
  - any install/upgrade note users must know
- If a turn includes “commit push gh发布” or equivalent release intent, prefer:
  1. choose next version
  2. commit
  3. push branch
  4. create annotated tag
  5. push tag
  6. create GitHub Release with concise notes
- If the version bump policy is ambiguous, state the proposed next version explicitly before tagging.

## Iteration Commit Gate

- After each completed iteration stage, ask the user whether to create a commit before starting the next substantial change.
- Do not assume "not asking" means "continue uncommitted".
- Do not auto-commit without explicit user confirmation.
- If the user declines, continue only for the current requested scope and keep the final note explicit that the work remains uncommitted.

## Operational Guardrails

- Before changing launcher, routing, bridge, config, account, or TUI selection logic, read `docs/AGENT_GUARDRAILS.md`.
- `Claude` must also read `CLAUDE.md` before making any repo changes; when `CLAUDE.md` and a task conflict, Claude should stop and ask the user to confirm scope.
- Treat `mms_core.py`, `mms_launchers.py`, `mms_tui.py`, `mms_bridge.py`, `mms_account_state.py`, `mms_session.py`, `mms_adapter_registry.py`, `mms`, and `ccs` as protected surfaces.
- Do not silently change default launch behavior, model/source resolution order, config schema, account isolation semantics, or bridge fallback rules without an explicit note in the task and targeted validation.
- If a task would alter a protected surface beyond the user's stated scope, stop and narrow the change or ask for confirmation.
- If the current process is running inside an MMS/Codex session that rewrites `HOME`, do not trust auth failures from global CLIs (`gh`, cloud CLIs, package-publishing CLIs) until you also check the real user home from `REAL_HOME`, `ORIGINAL_HOME`, or `MMS_REAL_HOME` and retry with the global config path.

## Routing Signal Contract

- `priority` is the runtime-level default field on `providers` and `accounts`.
- `family_priority_overrides` is the explicit family-level extension; it overrides runtime `priority` for the matched family only.
- Current global rule: larger effective `priority` means higher precedence.
- TUI channel lists, runtime source lists, and exported route ordering should all follow descending effective `priority`.
- Changing one provider/account `priority` still affects every model on that runtime unless a matching `family_priority_overrides` entry exists.
- `role` still outranks `priority`: `primary > auto > fallback`, then compare `priority` within the same role tier.
- `use_count` is model-level usage metadata aggregated from `usage.json`; it is for display/ranking/export metadata, not the primary runtime routing key.
- Current family ordering rule:
  - preferred family for current CLI first (`claude -> Claude`, `codex -> GPT`)
  - then family total `use_count` descending
  - then family name
- Current model ordering rule inside one family:
  - model `use_count` descending
  - then model name
- `model-routes.json` is a derived export for tools such as Hive. It is refreshed by explicit export, config-affecting mutations, and best-effort async export after usage writes; `force=False` reads also invalidate on newer `usage.json`.
- If a new feature needs ranking, affinity, or pinning semantics, prefer reusing or explicitly extending these fields instead of inventing hidden parallel state.

## Local Slash Triggers

- In this repo, if the user sends `/distill`, `distill`, `蒸馏`, or `checkpoint`, treat it as an explicit request to run the global `distill` skill.
- For `/distill`, `Codex` must resolve `repo` with `git rev-parse --show-toplevel` first and only fall back to current `cwd` when git root is unavailable.
- If `mindkeeper.brain_checkpoint` fails, report the exact absolute `repo` path that was attempted instead of saying only "repo not found".

## Stability Window

- The following chain is now under a stability window and must be treated as a protected integration surface:
  - `MMS -> private(/claude) -> CRS`
  - `MMS -> privateopenai(/openai) -> CRS`
  - `MMS -> xin/newapi(4001) -> CRS`
  - `MMS -> fishcrs(/claude) -> CRS`
- Any person or agent touching any of the following must explicitly confirm whether the change can affect the above chain before proceeding:
  - provider `models_endpoint`
  - `extra_models` / `hidden_models`
  - model probe logic / cache logic
  - `channel_affinity`
  - `Codex` / `Claude` header passthrough
  - CRS-facing `/claude` or `/openai` route assumptions
- Minimum pre-change checklist for that chain:
  - Does this change alter model visibility, aliasing, or fallback behavior?
  - Does this change alter whether `/models` is probed, skipped, or cached?
  - Does this change alter client identity headers or sticky-session key sources?
  - Can this break `private`, `privateopenai`, or `xin/newapi` even if the local unit test still passes?
- Any change on that chain must update:
  - `docs/CLI_PROVIDER_COMPAT_QA.md`
  - `docs/PRIVATE_CRS_SMOKETEST_RUNBOOK.md`
- Any change on that chain must run at least one matching smoke test from:
  - `docs/PRIVATE_CRS_SMOKETEST_RUNBOOK.md`

## Claude Provider Safety Notes

- `xin` / `fishcrs` / `trcrs`（若恢复）属于 Claude 敏感 provider：
  - 默认不要启用 `1M context`
  - 默认不要做额外 `Anthropic endpoint probe`
  - 只有在真实 smoke 证明可用时才允许继续放开
- 对 Claude 账号绑定类改动，至少检查 3 件事：
  - 请求日志里是否出现 `Using proxy for Claude request: <expected_proxy>`
  - `metadata.user_id` 是否仍然是 string，不是 object
  - 新建 API Key 后是否补进前台索引，否则 Admin UI 看不见
- 删除 Claude 账号前，先确认所有专属 key 已重新绑定或不再使用；
  - 尤其不要在 `private/独享` 仍指向该账号时直接删账号
