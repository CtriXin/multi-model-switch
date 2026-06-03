## Caveman Vendor Snapshot

This directory contains the pinned `caveman` assets that `MMS` uses for session-level integration.

- Upstream project: `https://github.com/JuliusBrussee/caveman`
- Upstream license: `MIT`
- Intended use in `MMS`: bundled session asset for `Claude/Codex`, not standalone global hook installation

Included subset:

- `hooks/` files used by the `Claude` session hook integration
- `.codex/hooks.json` used by the `Codex` session hook integration
- `commands/` and `skills/` used for session overlay
- upstream `LICENSE`
- upstream `README` snapshot in `README.upstream.md`

When updating this snapshot, preserve the upstream license and keep the bundled surface minimal.
