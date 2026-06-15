# Digger PR Validation

Digger is an advisory CI gate for MMS pull requests. It builds a baseline-aware
review packet and, when validation fails, posts a PR comment with the result. It
is not a merge bot and must not be treated as committee approval.

## Security Boundary

- The workflow runs on `pull_request`, not `pull_request_target`, so it does not
  execute with the target branch's elevated context while checking out untrusted
  PR code.
- The job is limited to same-repository PRs with
  `github.event.pull_request.head.repo.full_name == github.repository`. Fork PRs
  are intentionally skipped until Digger can run from a public, no-secret install
  path.
- The job requests only the permissions it currently needs:
  - `contents: read` to checkout and inspect the repository.
  - `pull-requests: write` and `issues: write` to post PR feedback. GitHub PR
    conversation comments are issue comments, so `issues: write` is required for
    that path.
- The Digger deploy key is used only during the install step to fetch the private
  `CtriXin/digger` package. It is not exported into the later `Run digger` step.
- `GITHUB_TOKEN` is passed only to `digger ci github` so Digger can discover the
  PR context and post the advisory comment.
- `--dry-run` is required. The workflow must not merge, push, apply patches, or
  mutate repository state beyond posting comments and uploading artifacts.
- `DIGGER_MMS_COMMAND` is optional and secret-backed. When absent, Digger runs in
  non-LLM validation mode. When present, it is treated as trusted maintainer CI
  configuration and must not be sourced from PR content.

## Pinning Policy

- GitHub Actions are pinned to major versions for maintenance compatibility:
  - `actions/checkout@v4`
  - `actions/setup-node@v4`
  - `actions/setup-python@v5`
  - `actions/upload-artifact@v4`
- Runtime versions are explicit:
  - Node `24`
  - Python `3.12`
- The Digger package is pinned to a specific commit in the workflow with
  `DIGGER_REF`. Do not switch this back to a floating branch or tag in CI.
- Python test tools are currently installed by package name (`pytest`, `httpx`,
  `rich`) without version pins because they are runner support dependencies, not
  MMS runtime dependencies. If Digger starts depending on exact behavior from
  those tools, pin them or move them into a checked-in constraints file.
- `ssh-keyscan github.com` is used only to establish GitHub as a known SSH host
  for the private install. If this workflow becomes release-blocking for outside
  contributors, replace it with a maintained pinned host-key setup or a public
  package install path.

## Branch Coverage

- The workflow is intentionally declared without `branches` filters. Any branch
  that contains this workflow can run it for PRs targeting that branch.
- Today this PR targets `main`, so the immediate coverage is `head -> main` PRs
  after the workflow lands on `main`.
- To cover `dev` PRs, the workflow must also exist on `dev` because GitHub uses
  the base branch's workflow definition for `pull_request` runs.
- To cover `release/*` PRs, cherry-pick or merge the workflow into the relevant
  release branch first.
- Fork PRs are out of scope for now and are skipped by the same-repository guard.
- Digger results are advisory. A passing Digger run does not replace committee
  review, human merge approval, or the project-specific release checklist.
