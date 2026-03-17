# Web-V2 Release Mainline

## Scope

- `main` is the only source of truth for `apps/web-v2` release.
- Feature worktrees are for short-lived iteration only.
- Web feature sync should not include local iOS signing/private packaging state.

## Packaging Isolation Rules

- Do not commit personal signing values (`DEVELOPMENT_TEAM`, personal `PRODUCT_BUNDLE_IDENTIFIER` overrides).
- Keep local packaging diagnostics out of git (`devicectl` logs, local `xcuserdata`, local `target` caches).
- If iOS signing must differ per machine, use local Xcode config/workspace state, not tracked repo defaults.

## Merge Flow

1. Implement in feature worktree.
2. Sync web changes into `main` (prefer `apps/web-v2` scope).
3. Re-run `npm run type-check` and `npm run build` in `apps/web-v2`.
4. Release from `main` only.
