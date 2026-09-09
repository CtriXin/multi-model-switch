# Redline PR Gate

Redline is the downstream advisory gate for MMS pull requests. It consumes the
Digger artifact plus provider PR/check metadata and writes a durable
`redline-report` artifact for committee review.

This integration is intentionally advisory-only. Redline does not approve,
merge, deploy, close, force-push, or mutate repository state. Redline may post
one marker-based PR comment when `--comment` is enabled so reviewers can see the
current decision without opening artifacts.
Committee/human approval remains the final merge gate.

## Workflow Shape

The GitHub Actions flow is:

1. `digger` runs first and uploads `.digger/runs` as artifact `digger`.
   The workflow removes checkout-provided `.digger`, recreates `.digger/runs`
   as a symlink to `$RUNNER_TEMP/digger-runs`, and uploads only that trusted
   runner-temp directory. If a tool replaces the symlink, the workflow discards
   checkout-local runs instead of uploading them.
2. `redline` runs with `needs: digger` and `if: always()` for same-repository PRs.
3. The job removes and recreates a trusted artifact directory, downloads artifact
   `digger` into that directory, locates one Digger run root only from that
   downloaded artifact root, installs pinned `redline-guard`, and runs:

   ```bash
   redline-guard audit \
     --provider github \
     --pr "$PR_NUMBER" \
     --repo "$GITHUB_WORKSPACE" \
     --digger-run "$DIGGER_RUN_ROOT" \
     --out .redline-guard/report \
     --comment
   ```

4. The job uploads `.redline-guard/report` as artifact `redline-report` with
   30-day retention.
5. The job creates or updates one Redline marker comment on the PR when the
   audit tool is installed and a Digger run root exists. Tool/setup fallback
   reports still stay artifact-only.
6. The job writes one Actions step-summary line with the decision and artifact
   name so reviewers can see advisory status without opening the artifact first.

If Digger produces no run root, Redline installation is disabled, or Redline
exits non-zero, the workflow writes an `unknown` fallback report and exits `0`.
That keeps tool/setup failures visible without deadlocking development.

## Secrets And Permissions

Required for private-tool install:

- `DIGGER_DEPLOY_KEY`: read-only deploy key for `CtriXin/digger`.
- `REDLINE_GUARD_DEPLOY_KEY`: read-only deploy key for `CtriXin/redline-guard`.

Optional:

- `DIGGER_MMS_COMMAND`: maintainer-controlled command for Digger semantic review.
- Repository variable `REDLINE_GUARD_ENABLED=false`: advisory kill switch that
  makes Redline write an `unknown` report instead of installing/running.

Permissions:

- Top-level default is `contents: read`.
- Digger receives `pull-requests: write` and `issues: write` only because it
  posts advisory PR comments.
- Redline receives `contents: read`, `pull-requests: read`, and `issues: write`.
  The issue permission is only for one marker-based PR conversation comment.

## Pinning

- Digger is pinned by `DIGGER_REF` in the workflow.
- Redline is pinned by `REDLINE_GUARD_REF` in the workflow.
- GitHub Actions are pinned by major versions for maintainability.
- Node is pinned to `24`; Python is pinned to `3.12` for the Digger job.
- `ssh-keyscan github.com` remains a documented TOFU tradeoff while the tools are
  private. Future public packages, reusable workflows, Docker images, or pinned
  host keys should remove that risk.

## Artifact Contract

Redline writes these files when available:

- `audit-result.json`
- `audit-result.md`
- `comment.md`
- `digger-evidence.json`
- `*.sha256` sidecars for each uploaded report file

The artifact name is `redline-report`. The first retention value is 30 days.
Release workflows may raise retention later if committee wants longer audit
history.

Redline also creates or updates one PR comment with marker
`<!-- redline-guard:audit -->` when `--comment` is enabled. The comment is a
short decision summary; the artifact remains the detailed source of truth.

## Branch And Fork Behavior

The workflow uses `pull_request`, not `pull_request_target`, and is guarded to
same-repository PRs while private install credentials are required. Fork PRs are
skipped until Digger and Redline have a public/no-secret distribution path.

A base branch receives this gate only after the workflow exists on that branch.
To cover `dev`, merge or cherry-pick this workflow into `dev`; to cover
`release/*`, land it on the relevant release branch first.

## Local Fallback

Maintainers can run Redline locally after downloading or generating a Digger run:

```bash
redline-guard audit \
  --provider github \
  --pr <number-or-url> \
  --repo <repo-path> \
  --digger-run <repo-path>/.digger/runs/<run-id> \
  --out <repo-path>/.redline-guard/report \
  --comment
```

Do not pass `--notify` or callback/action flags unless the human explicitly asks
for those notification surfaces.
