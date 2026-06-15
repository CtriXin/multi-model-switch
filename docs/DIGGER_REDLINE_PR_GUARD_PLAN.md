# Digger + Redline PR Guard Plan

Status: Draft for committee review
Issue: https://github.com/CtriXin/multi-model-switch/issues/14
Related PR: https://github.com/CtriXin/multi-model-switch/pull/4
Last verified: 2026-06-15

## Problem

MMS needs a repeatable PR validation flow that does not depend on one
maintainer's local machine, local worktrees, or private `/Users/xin/...` paths.
The project already has two sibling tools:

- `digger`: PR/MR reviewer, validation runner, evidence collector, and optional
  PR comment writer.
- `redline-guard`: downstream merge-readiness gate that consumes Digger
  artifacts plus CI/check/local-validation/LLM-audit evidence and returns one
  decision: `mergeable`, `needs-review`, `blocked`, or `unknown`.

PR #4 wires Digger into GitHub Actions. Redline is not yet part of the MMS CI
flow. The desired outcome is a GitHub-hosted guard path that runs on PRs after
code is pushed, produces durable artifacts for committee review, and does not
merge, approve, deploy, force-push, or mutate repository state automatically.

## Desired Collaboration Contract

For MMS changes, the expected flow is:

1. Open an issue first.
2. Record the implementation plan in that issue before coding.
3. Execute the plan in an isolated branch/worktree.
4. Commit only after explicit human approval for that commit.
5. Push the branch.
6. Open a PR.
7. Digger and Redline produce CI evidence.
8. Committee reviews the PR and evidence.
9. Merge only after committee/human approval.

This document describes the CI evidence portion of that workflow.

## Current State

Live status verified on 2026-06-15:

- `CtriXin/digger` exists as a separate private repository.
- `CtriXin/redline-guard` exists as a separate private repository.
- PR #4 is open, targets `main`, and currently has HEAD `1da83c25`.
- PR #4 files are `.github/workflows/digger.yml` and
  `docs/DIGGER_PR_VALIDATION.md`.
- PR #4 installs Digger in GitHub Actions from pinned commit
  `9c22178c961ebe25914b6580b9e7a1000af046f9`, not from a floating branch or a
  local path.
- PR #4 limits the Digger job to same-repository PRs with
  `github.event.pull_request.head.repo.full_name == github.repository`.
- PR #4 grants `contents: read`, `pull-requests: write`, and `issues: write`.
  The issue permission is needed because GitHub PR conversation comments use the
  Issues API path.
- PR #4 uploads `.digger/runs` as artifact `digger`.
- Redline is not installed, executed, or uploaded by the MMS workflow yet.

Earlier committee feedback flagged a mismatch between this plan and PR #4 when
#4 still pointed at `4df1c349`. That mismatch is resolved in live PR #4 by
commit `1da83c25`; keep this section tied to verified PR state when the branch
moves.

## Committee Decisions Adopted

The committee's five open questions are resolved for the first Redline
integration as follows:

| Question | Decision |
|---|---|
| Redline start mode | Advisory-only / soft-fail |
| `unknown` decision | Do not fail CI; escalate to human/committee |
| Redline PR comments | Artifact-only at first; no default PR comment |
| Scope of PR #4 | Keep PR #4 Digger-only; use a follow-up PR for Redline |
| Public package / reusable workflow | Desirable Phase 5+, not a blocker for MMS first integration |

Rationale: Digger should land and stabilize first. Redline is a downstream gate
with a higher false-positive blast radius, so the first integration should
produce evidence without blocking normal PR flow unless the committee later opts
into hard-fail behavior.

## Proposed CI Shape

```text
pull_request
  -> digger job
       - checkout PR
       - install pinned Digger
       - run digger ci github
       - upload .digger/runs as artifact: digger
  -> redline job
       - needs: digger
       - if: always() && same-repository PR
       - checkout PR
       - download artifact: digger
       - locate one Digger run root under .digger/runs/<run-id>
       - install pinned redline-guard
       - run redline-guard audit with --digger-run and --out
       - upload artifact: redline-report
       - write one-line Actions step summary
       - soft-fail/advisory in the first integration
  -> committee review
       - inspect PR diff, Digger report, Redline report, CI checks
       - approve/modify/reject
```

Candidate Redline command based on the current `redline-guard` CLI:

```bash
# Intentionally omit --comment and --notify in the first integration.
redline-guard audit \
  --provider github \
  --pr "$PR_NUMBER" \
  --repo "$GITHUB_WORKSPACE" \
  --digger-run "$DIGGER_RUN_ROOT" \
  --out .redline-guard/report
```

The CLI already supports `--digger-run` and writes `audit-result.json`,
`audit-result.md`, and `digger-evidence.json` when `--out` is supplied.

## Phase Plan

### Phase 1: Keep PR #4 Digger-only

- Keep Digger as the first PR review/validation job.
- Keep `--dry-run` so Digger cannot write code or mutate repo state.
- Keep `--baseline-aware` so existing baseline failures are separated from new
  failures introduced by the PR.
- Keep `.digger/runs` upload so downstream tools and committee reviewers can
  inspect durable evidence.
- Keep Digger installation pinned to a commit SHA or another immutable release
  coordinate.
- Keep same-repo PR guard until private-tool installation no longer requires
  secrets.
- Keep `issues: write` documented while `--post-comment` is enabled.

### Phase 2: Add Redline in a Follow-up PR

- Add a separate `redline` job that depends on `digger`.
- Use `if: always()` on the Redline job so it can report `unknown` or missing
  Digger evidence even when Digger fails before producing a complete report.
- Keep `actions/upload-artifact` in the Digger job under `if: always()`.
- Download the Digger artifact named `digger` into the checkout.
- Locate the run root under `.digger/runs/<run-id>`; if multiple runs exist,
  choose the newest run by manifest timestamp when available, otherwise fail to
  `unknown` rather than guessing silently.
- Install `redline-guard` from a pinned commit SHA or immutable package digest.
- Run Redline with `--digger-run` and `--out`.
- If Digger produced no run root, Redline should exit `0` and write a
  `decision=unknown` report explaining the missing evidence; tool failure is
  escalated to committee, not used to deadlock development.
- Upload `.redline-guard/report` as artifact `redline-report` with explicit
  retention.
- Write a one-line Actions step summary with the Redline decision and artifact
  name so advisory status is visible without opening the artifact first.
- Do not enable `--comment`, `--notify`, callback actions, automatic merge,
  approval, deployment, force-push, close, or destructive actions in the first
  integration.
- Treat `blocked`, `needs-review`, and `unknown` as advisory outputs at first;
  committee/human review remains the final gate.

### Phase 3: Document Security and Operations

- Document required secrets:
  - Digger install credential, if the repo remains private.
  - Redline install credential, if the repo remains private.
  - Optional MMS bridge command secret for semantic review.
- Document GitHub token scopes and why each permission is needed.
- Document same-repo versus fork PR behavior.
- Document branch coverage: `main`, `dev`, `release/*`, and feature branches.
- Document local fallback commands for maintainers, but make CI independent of
  local paths.
- Document a kill switch such as `REDLINE_GUARD_ENABLED=false` or a workflow
  input/env value that skips Redline without changing code.

### Phase 4: Committee Validation Before Merge

Committee should verify:

- Digger and Redline are installed from pinned coordinates.
- No job depends on `/Users/xin/...` or another maintainer-local path.
- Fork PR behavior is safe and explicit.
- Digger artifacts are available to Redline.
- Redline output is uploaded as a durable artifact.
- Any failing behavior is intentional and documented.
- Neither tool can merge, approve, deploy, force-push, or mutate repo state.
- The PR keeps committee/human approval as the final merge gate.

### Phase 5: Reuse Beyond MMS

After the MMS flow proves stable, consider one of these distribution paths:

- reusable GitHub workflow;
- composite action;
- public npm packages;
- Docker images pinned by digest.

This is the path that can eventually make Digger/Redline available to other
repositories and fork PRs without private deploy keys.


## Out of Scope for the First Redline PR

The first Redline follow-up PR should not attempt to solve every guardrail at
once. These items stay out of scope unless committee explicitly reopens them:

- hard-failing CI on `blocked`, `needs-review`, or `unknown`;
- posting Redline PR comments by default;
- enabling Feishu notifications or callback actions;
- supporting fork PRs that require private install credentials;
- publishing public npm packages, Docker images, or reusable workflows;
- replacing Digger as the primary reviewer job;
- changing branch protection rules automatically;
- implementing automatic merge, approval, close, deploy, or force-push actions.


## Security Boundary

The guard workflow should follow these rules:

- Use `pull_request`, not `pull_request_target`, unless a future design proves a
  safe split between trusted workflow code and untrusted PR code.
- Skip fork PRs while private install secrets are required.
- Prefer top-level `permissions: contents: read`, then grant narrower job-level
  write permissions only where needed.
- Keep `contents: read` unless a job has a documented reason for more.
- Grant `pull-requests: write` and `issues: write` only to the Digger job while
  Digger posts PR comments.
- Do not grant Redline PR/comment write permissions in the first integration.
- Prefer artifact upload over comments for early Redline integration.
- Treat `DIGGER_MMS_COMMAND` or equivalent LLM bridge commands as trusted
  maintainer CI configuration, never PR-controlled input.
- Keep any LLM bridge command behind an allowlisted command path, controlled env,
  and no PR-controlled shell interpolation.
- Keep network egress for LLM bridge calls scoped to the configured provider or
  MMS bridge endpoint, not arbitrary PR-controlled destinations.
- Redact secrets, bearer tokens, webhook URLs, and provider keys from Digger,
  Redline, and Actions summary output before upload or comment publication.
- Do not store provider keys, webhooks, or deploy credentials in the repository.

## Supply Chain and Pinning Policy

- GitHub Actions may be pinned to major versions for maintainability, but the
  risk should be recorded.
- Digger and Redline must be pinned to commit SHAs or immutable release
  coordinates.
- Do not install Digger or Redline from floating branches in CI.
- Pin or constrain Python support dependencies (`pytest`, `httpx`, `rich`) if
  they become part of the required gate rather than runner support.
- First integration may document the current `ssh-keyscan github.com` TOFU risk;
  Phase 5 should remove that risk by using public packages, reusable workflows,
  Docker images, or pinned host keys.
- Generate low-cost SHA-256 sidecars for Redline report files in the first
  integration; if artifacts become release-blocking, promote this into a full
  manifest with file paths, sizes, and hashes for Digger and Redline reports.

## Artifact Policy

- Digger artifact name: `digger`.
- Digger run path inside the artifact: `.digger/runs/<run-id>`.
- Redline artifact name: `redline-report`.
- Redline output path: `.redline-guard/report`.
- Redline integrity sidecar path: `.redline-guard/report/*.sha256`.
- Set explicit artifact retention instead of relying on GitHub's default.
  Proposed first value: 30 days for normal PR evidence.
- If the committee wants longer auditability for release branches, raise
  retention for release workflows only.

## Baseline Management

`--baseline-aware` prevents old failures from blocking every new PR, but it also
creates a governance question: when does the baseline itself need cleanup?

Recommended policy:

- New failures introduced by a PR should remain blockers or high-priority review
  evidence.
- Existing baseline failures should be reported but not block unrelated PRs.
- If the same baseline failure appears repeatedly across protected branches,
  open a separate issue to fix or explicitly waive it.
- Baseline waivers should be recorded in repo config, not hidden in workflow
  scripts.

## Branch Coverage

GitHub evaluates `pull_request` workflows from the base branch. Therefore:

- `main` PRs are covered only after the workflow exists on `main`.
- `dev` PRs are covered only after the workflow exists on `dev`.
- `release/*` PRs are covered only after the workflow exists on each relevant
  release branch.
- A workflow in a feature branch does not protect PRs targeting a base branch
  until it is merged into that base branch.

After the workflow is stable, branch protection should require the selected
Digger/Redline checks on protected branches.

## Acceptance Criteria

- There is an issue-backed plan before implementation.
- The workflow does not depend on local maintainer paths.
- PR #4 remains Digger-only and accurately documents its security/pinning/branch
  coverage boundaries.
- A follow-up PR adds Redline as an advisory downstream job.
- Digger runs in GitHub Actions and uploads `.digger/runs` as artifact `digger`.
- Redline runs in GitHub Actions and uploads artifact `redline-report`.
- Digger and Redline installs are pinned.
- Same-repo/fork behavior is explicit.
- Branch coverage expectations are documented.
- Committee can review durable Digger and Redline artifacts before approving a
  merge.
- Final merge remains a committee/human decision.
