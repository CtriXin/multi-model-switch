# MMS System Reinstall Backup Plan

Last updated: 2026-07-30

## Decision

This machine will be rebuilt. Treat `~/.config/mms/` as retired legacy state and do not back it up. Future runtime use is `~/.config/mms-next/` only.

The new system should start without old sessions, project histories, caches, gateway traces, logs, or historical backups. Preserve only the minimum MMS Next configuration and credentials needed to restore routing.

## Why The Current Roots Are Large

Observed sizes before cleanup planning:

- `~/.config/mms/`: about 6.9 GB; retired and intentionally excluded.
- `~/.config/mms-next/`: about 3.6 GB.

The size is not only session history. The largest MMS Next subtrees were:

- `projects/`: about 2.3 GB of project/session state.
- `backups/`: about 985 MB of historical configuration snapshots.
- `codex-gateway/`: about 229 MB of gateway runtime state.
- `pi-gateway/`: about 20 MB of Pi sessions/exports.
- `registry/`, `cache/`, `logs/`, `lb_debug.log`, and route snapshots: generated diagnostics and refresh state.

These are intentionally disposable for a clean rebuild.

## Preserve From `~/.config/mms-next/`

Create a private backup containing the following files or directories when they exist. They can contain credentials and must not be committed to Git or uploaded to an unencrypted public location.

- `config.toml`
- `credentials.sh`
- `preferences.toml`
- `model-policy.json`
- `provider-profiles.json`
- `webui-secrets.json`
- `accounts/` only when preserving current account/API credential state is desired.
- `generated/` only as a convenience snapshot; regenerate it after restore rather than treating it as canonical.

The current policy intentionally includes these plain-name 1M overrides:

- `models.k3.capabilities.context_window_tokens = 1048576`
- `models.qwen3.8-max-preview.capabilities.context_window_tokens = 1048576`

## Do Not Preserve From `~/.config/mms-next/`

Do not copy these directories/files into the clean restored runtime:

- `projects/`
- `backups/`
- `codex-gateway/`
- `pi-gateway/`
- `opencode-gateway/`
- `mimocode-gateway/`
- `cache/`
- `logs/`
- `events/`
- `imports/`
- `model-routes.snapshots/`
- `model-routes.lineup.snapshots/`
- `lb_debug.log`, `provider_debug.log`, `committee-timing.jsonl`
- transient lock files, status files, `usage.json`, speed statistics, and update checks.

## Repo Recovery

`multi-model-switch` is clean and synchronized with `origin/dev` at the time of this document. The code itself can be restored from Git.

The repo has ignored local artifacts. Preserve only if continuity/evidence is useful:

- `.ai/regression-reports/`, `.ai/plan/`, `.ai/results/`, `.ai/runs/`, `.ai/reviews/`, `.ai/continuity/`
- `.agents/`, `.claude/`, `.mms/rescue/`, `.agent.local/`, `.work/`, `.xmem/`
- ignored human-maintained files: `AGENTS.md`, `AI_BOOTSTRAP.md`, `AI_PROJECT_CONTEXT.md`, `HANDOFF_WEB_APP.md`, `progress.md`, `task_plan.md`, `findings.md`

Do not preserve `.ai/cache/` unless offline reuse is needed; it is mostly re-downloadable package cache.

## Global Shell / CLI State

Preserve these small files if the same direct CLI behavior is wanted after reinstall:

- `~/.zshrc`: contains the direct official `pi` and `claude` proxy/OAuth wrappers.
- `~/.local/bin/mmf`: MMS launcher entrypoint.

Node/FNM directories are optional. Reinstalling Node and global packages is preferred over copying them. Current intended state is Node/FNM 24 with global Pi `0.83.0`; MMS Pi now prefers this global binary and falls back to its managed cache.

## Restore Validation

After restore, a backup agent should:

1. Restore the selected private MMS Next configuration only.
2. Regenerate/check MMS routes and model registry rather than copying old cache/log/session data.
3. Confirm plain `k3` and plain `qwen3.8-max-preview` export a Pi `contextWindow` of `1048576`.
4. Confirm `mmf pi` resolves the active global Pi binary rather than an outdated MMS cache.
5. Run a minimal fresh Pi smoke for K3 and Qwen; do not restore old sessions to validate it.
