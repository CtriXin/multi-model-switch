# Upstream and distribution policy

`CtriXin/web-access` is a maintained fork of
[`eze-is/web-access`](https://github.com/eze-is/web-access).

- Upstream baseline: `7af34af6a25940d917905f0e5f2a7ef056952971` (`v2.5.3`)
- Distribution version: `2.6.0-ctrixin.1`
- Canonical local checkout: `/Users/xin/auto-skills/CtriXin-repo/web-access`
- Runtime, global Agent skill directories, and MMF session overlays are consumers
  of this checkout; they must not become independent source copies.

The fork preserves the original author and MIT attribution. CtriXin-specific
changes cover MMF host-home browser discovery, fail-closed isolation, targeted
proxy lifecycle, real input operations, and source-bound ad-placement
attestation. Upstream updates should be fetched through the `upstream` remote,
reviewed against these contracts, and merged into this fork explicitly.
