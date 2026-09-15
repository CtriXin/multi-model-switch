# Third-party code inside `index.ts`

`index.ts` is the esbuild output of `@ctrixin-dev/pi-btw` — a fork of
`@narumitw/pi-btw` (see `NOTICE` for provenance and `LICENSE` for the
MIT terms). Besides the fork itself it inlines these runtime
dependencies, because the vendored file has no node_modules to resolve at:

- `@narumitw/pi-tui-kit` 0.59.0
  license: MIT License
- `grok-mermaid` 0.2.3
  license: Copyright 2023-2026 SpaceXAI

Full license texts are shipped in the source packages; see
`SOURCE.json` for the exact ref and sha256 of what is vendored here.
