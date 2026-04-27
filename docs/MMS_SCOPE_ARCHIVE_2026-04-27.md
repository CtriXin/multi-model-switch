# MMS Scope Archive - 2026-04-27

This records a local cleanup pass that made `multi-model-switch` more focused on MMS launcher/session/runtime work.

## Goal

Keep active MMS project scope vertical:

- launcher/session/runtime manager
- model/source selection and route diagnostics
- session isolation and fail-closed behavior
- bridge/runtime compatibility that directly serves the MMS launch path
- install/update reliability and guarded config behavior

Move local/off-scope payloads out of the active tree without deleting them.

## Archives

### Scope Archive

Path:

```text
/Users/xin/auto-skills/CtriXin-repo/multi-model-switch.scope-archive-20260427T035916-0400
```

Contains:

- `README.md` - read order and restore command
- `context.md` - context summary / 前情提要
- `basis.md` - archive decision basis / 归档依据
- `manifest.tsv` - old path, archive path, size, reason, basis, action
- `change-list.md` - human-readable moved-path list
- `restore.sh` - restore script

Main moved categories:

- local planning/handoff scratch files
- local CRS/newapi ops docs and scripts
- marketing/social/demo assets
- TUI demo prototypes
- local issue/audit notes
- generated caches
- secondary untracked package workspace payloads

### Physical Cleanup Quarantine

Path:

```text
/Users/xin/auto-skills/CtriXin-repo/multi-model-switch.cleanup-quarantine-20260427T030228-0400
```

Contains larger ignored/generated payloads moved earlier:

- `node_modules`
- `apps/web-v2`
- Python bytecode caches
- `dist`
- `tmp`
- `.pytest_cache`
- local `.DS_Store` files

## Restore

Restore scope archive payload:

```bash
/Users/xin/auto-skills/CtriXin-repo/multi-model-switch.scope-archive-20260427T035916-0400/restore.sh
```

Restore physical cleanup payload:

```bash
/Users/xin/auto-skills/CtriXin-repo/multi-model-switch.cleanup-quarantine-20260427T030228-0400/restore.sh
```

Both scripts refuse to overwrite existing target paths.

## Preserved In Active Tree

- tracked MMS source, tests, installers, public docs, and config examples
- agent safety files: `AGENTS.md`, `CLAUDE.md`, `AI_BOOTSTRAP.md`
- registered git worktrees: `.worktrees/preset-schema`, `apps/worktree-app-store-launch`
- existing `docs/archive/`
- `.ai/` local handoff/cleanup records

## Validation

- `git status --short --untracked-files=no` was clean after cleanup.
- `bash -n` passed for both restore scripts.
- active tree size was about `67M` after the archive pass.
- no real `~/.config/mms` writes were performed.
- no protected runtime source files were edited by the archive pass.

## Local Evidence

- `.ai/regression-reports/2026-04-27-mms-scope-verticalization.md`
- `.ai/regression-reports/2026-04-27-mms-physical-cleanup.md`
- `.ai/plan/handoff.md`
- `.ai/plan/packet.json`
- `/Users/xin/issue-tracking/issues/multi-model-switch/mms-scope-verticalization-20260427/issue.md`
- `/Users/xin/issue-tracking/issues/multi-model-switch/mms-physical-cleanup-20260427/issue.md`
