# Vendor snapshot — not a source

This directory is a **tracked cross-machine release snapshot** of the canonical
checkout at `/Users/xin/auto-skills/CtriXin-repo/web-access`
(fork: `CtriXin/web-access`, upstream: `eze-is/web-access`).

- Snapshot of canonical commit: `e2a9e1d` (distribution `2.6.0-ctrixin.1`)
- Synced: 2026-07-29 by Kimi (bounded-review follow-up)
- Rule: never edit files here directly. Change the canonical repo, push, then
  re-sync this snapshot from the canonical tracked file set (`git ls-files`),
  excluding the git-ignored `config.env` (template: `templates/config.env.template`).
