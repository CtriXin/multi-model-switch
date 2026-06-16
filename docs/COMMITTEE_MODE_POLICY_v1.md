# OpenCode Committee Mode Policy v1

Status: draft implementation contract
Issue: https://github.com/CtriXin/multi-model-switch/issues/15
Profile: `committee`

## Purpose

The OpenCode `committee` profile is a lightweight independent evaluation
profile. It should support multiple explicit decision modes without becoming a
state-core workflow engine and without importing `debate` semantics.

`committee` owns independent review, estimation, gate decisions, and synthesis.
`debate` owns blind first pass, crossfire, stance changes, and debate-specific
resolution states. The two profiles may share routing and roster infrastructure,
but their workflow contracts must remain separate.

## Policy Axes

A committee dispatch is described by four independent axes:

1. `decision_mode`: what kind of judgment the committee is making.
2. `artifact_mode`: whether outputs remain in chat or are written to scoped
   artifacts.
3. `permission_profile`: what tools and write surfaces are permitted.
4. `playbook`: which domain checklist guides evidence collection and roster
   selection.

The host must declare all four axes before delegating non-trivial work. If a
user or local project rule supplies a stricter contract, that contract overrides
these defaults.

Committee also follows the OpenCode review mission trace contract in
`docs/OPENCODE_REVIEW_MISSION_TRACE_v1.md`. The host must create or preserve a
visible `MMS-MISSION` block before dispatch, include it in every member brief,
include it in the final synthesis trace/provenance area, and repeat at least
`MMS-MISSION` plus `MMS-TARGET` at the end.

## Decision Modes

### `advisory`

Use for open-ended opinion, sanity checking, option comparison, or exploratory
committee input.

Required member output:

- finding summary
- assumptions
- cited evidence or files inspected
- risks / disagreements
- recommended next action

No formal vote, veto, quorum, or approval language is allowed unless the user
explicitly asks to upgrade the dispatch.

### `gate`

Use for approve/reject/modify decisions, merge-readiness gates, policy gates,
or safety-sensitive go/no-go questions.

Required member output:

- `model`
- `verdict`: `approve`, `reject`, or `modify`
- `veto`: `yes` or `no`
- cited evidence
- reason
- conditions required before approval, if any

The host must not treat majority as truth when deterministic evidence is weak or
contradictory. Vetoes and blockers must be preserved in the final synthesis.

### `estimate`

Use for risk, effort, confidence, cost, complexity, or score estimation.

Required member output:

- estimate value or score
- confidence
- evidence
- uncertainty / spread drivers
- what would change the estimate

The host aggregates estimates by median or distribution summary. Veto is not a
scoring tool.

### `review`

Use for finding-first review: bugs, regressions, missing tests, security gaps,
scope drift, documentation mismatches, or release risks.

Required member output:

- findings ordered by severity
- file/path references when available
- missing validation
- residual risk
- recommended fix or escalation

`review` may recommend a later `gate`, but it does not itself ratify approval.

### `execution_packet`

Use when committee output should become a plan for later implementation.

Required host output:

- objective
- constraints
- files/surfaces likely to change
- ordered tasks
- validation commands
- open questions
- explicit non-goals

This mode prepares work. It must not execute implementation unless the user
separately grants execution authority.

## Playbooks

Playbooks are domain checklists. They are not decision modes. For example, a
Git/CI/security request normally uses `decision_mode = gate` or `review` with
`playbook = git_ci_security`; it is not a hidden `git` decision mode.

### `general`

Use when the request does not fit a narrower domain checklist, or when the host
is still classifying a broad request before delegating. `general` is not a
weaker decision mode; the selected `decision_mode` still controls the required
member output.

Evidence checklist:

- user goal and explicit constraints
- relevant local instructions
- files or artifacts inspected
- assumptions and missing context
- why no narrower playbook was selected

Default decision mode: `advisory` for open-ended input, `review` for
finding-first audits.

### `git_ci_security`

Use for Git diffs, CI workflows, GitHub Actions, credentials, token scopes,
security gates, supply-chain risk, or merge automation.

Evidence checklist:

- `git status` / `git diff` / relevant commit or PR references
- workflow permission blocks and token scopes
- secret exposure and credential handling
- artifact upload/download trust boundaries
- command or checker output when available
- whether final merge/approval remains human-gated

Default decision mode: `gate` for go/no-go, `review` for finding-first audits.

### `pr_review`

Use for pull request review, merge readiness, code review, and regression risk.

Evidence checklist:

- changed files and behavior surface
- tests added or missing
- compatibility and migration impact
- rollback risk
- reviewer disagreement and blockers

Default decision mode: `review`; upgrade to `gate` only when approval is
requested.

### `docs_policy`

Use for governance docs, process docs, user-facing docs, policy updates, and
contract language.

Evidence checklist:

- local instructions and governance files
- terms that create authority or permission changes
- consistency with existing docs
- ambiguity, overclaim, or missing constraints

Default decision mode: `advisory` or `gate`, depending on whether a formal
policy decision is requested.

### `architecture`

Use for design decisions, migrations, major refactors, API boundaries, and
long-term maintainability.

Evidence checklist:

- current architecture references
- alternatives considered
- migration cost and rollback
- operational risk
- maintainability and testing impact

Default decision mode: `advisory` or `estimate`; use `gate` only for explicit
approval decisions.

### `release_gate`

Use for release readiness, version promotion, installer changes, deploy gates,
or compatibility signoff.

Evidence checklist:

- release checklist or runbook
- smoke/regression results
- known blockers
- compatibility and rollback plan
- human approval boundary

Default decision mode: `gate`.

## Host Dispatch Contract

For every non-trivial committee dispatch, the host must state:

```text
committee_policy:
  decision_mode: advisory|gate|estimate|review|execution_packet
  playbook: general|git_ci_security|pr_review|docs_policy|architecture|release_gate
  artifact_mode: chat_only|artifact_advisory|formal_vote_files|decision_file|checker_only
  permission_profile: readonly|artifact_write|checker_run|implementation_ask
  selected_members: [...]
  non_dispatched_members: [...]
  reason: <why this policy fits>
```

The final synthesis must use Simplified Chinese headings and prose by default,
while keeping technical terms such as `committee_policy`, `MMS-MISSION`,
`verdict`, `veto`, and file paths in English. It must not wrap the copy-forward
packet in a fenced code block; render it as normal Markdown so headings, bullets,
and syntax-highlighted paths stay readable while still being copyable.

Use this exact section order:

1. `人需要看的 / Human Notes`: conclusion, advisory/formal boundary, direct
   verification status, material risks or dissent, and the task-local subagent
   scorecard. Include `模型耗时 / Model Timing` with each delegated member's
   return order, elapsed wall time when captured, and speed ratio against the
   fastest captured member. If exact timing is unavailable, still record the
   observed return order and mark elapsed time as `not_captured`.
2. `可直接复制转发 / Copy-forward Packet`: a clean, self-contained block that can
   be copied or forwarded directly. Start this packet with `追踪块 / Trace`
   containing the same current mission block, then include the goal,
   `committee_policy`, assignments, direct verification, member findings or
   ballots, model timing, tally/consensus, disagreements, risks, formal artifact
   status, and provenance. Do not include scorecard, host meta commentary, or
   private host advice in this packet.
3. `Host 建议 / Host Recommendation`: the host's recommended next action, placed
   after the copy-forward packet as the last substantive section.
4. `追踪页脚 / Trace Footer`: repeat at least `MMS-MISSION` plus `MMS-TARGET` as
   the final trace footer. The `追踪块 / Trace` and `追踪页脚 / Trace Footer`
   identify the same current dispatch; they are not previous/next pointers.
   Do not place `追踪块 / Trace` before `人需要看的 / Human Notes`.

Use the actual unchanged mission block for the current target. The format is:

```text
MMS-MISSION: committee-<id>
MMS-TARGET: pr<number>@<commit> | unknown
MMS-MODE: gate
MMS-SOURCE: github-pr
```

If the target is unclear, use `MMS-TARGET: unknown` instead of inventing a PR or
commit.

## Non-Goals

- No debate rounds, crossfire, stance-shift tracking, or debate resolution
  states.
- No hidden `git mode` as a bottom-level decision mode. Git/CI/security is a
  playbook.
- No default formal writes.
- No quorum or ratification reimplementation when a project provides a checker.
- No heavy state-core dependency in v1.
